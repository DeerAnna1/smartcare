"""
Structured tool registry for native OpenAI function calling.
Replaces regex-based ```invoke block parsing with proper tool_calls.
"""

from __future__ import annotations

import json
import time
import logging
from typing import Any

from app.services.drug_interaction import query_drug_interactions
from app.services.registration import RegistrationService

logger = logging.getLogger(__name__)

# ── Built-in tool schemas (OpenAI function calling format) ──────────────

BUILTIN_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_drug_interaction",
            "description": "Check drug-drug interactions for a list of medications. Returns interaction level, description, and recommendation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drugs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of drug names to check interactions for (Chinese or English names)",
                    }
                },
                "required": ["drugs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_doctor_schedule",
            "description": "Query available doctor schedules by department name or hospital. Returns available time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "department_name": {
                        "type": "string",
                        "description": "Department name to search for (e.g. '心内科', '骨科')",
                    },
                    "hospital_name": {
                        "type": "string",
                        "description": "Optional hospital name to filter by",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date to query in YYYY-MM-DD format (defaults to tomorrow)",
                    },
                },
                "required": ["department_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_appointment_slot",
            "description": "Lock an appointment slot for a patient. Returns booking confirmation with lock expiry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "The schedule ID to book",
                    },
                    "patient_name": {
                        "type": "string",
                        "description": "Patient's full name",
                    },
                    "patient_id_last4": {
                        "type": "string",
                        "description": "Last 4 digits of patient ID card",
                    },
                },
                "required": ["schedule_id", "patient_name", "patient_id_last4"],
            },
        },
    },
]

def build_openai_tools(skills: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Expose only tools bound to the progressively selected Skills."""
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill in skills or []:
        for tool in skill.get("tools", []):
            if not isinstance(tool, dict) or not tool.get("name") or tool["name"] in seen:
                continue
            seen.add(tool["name"])
            tools.append({"type": "function", "function": {
                "name": tool["name"],
                "description": tool.get("description", f"Tool for {skill.get('name', 'Skill')}"),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            }})
    return tools


async def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    db_session: Any = None,
    user_id: str | None = None,
    active_skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a tool call and return the result."""
    start = time.time()

    try:
        tool_meta = next((tool for skill in active_skills or [] for tool in skill.get("tools", [])
                          if isinstance(tool, dict) and tool.get("name") == tool_name), None)
        if tool_meta and tool_meta.get("requires_confirmation") and not tool_meta.get("user_confirmed"):
            result = {
                "status": "confirmation_required",
                "error": f"该操作会修改外部状态。如需继续，请回复：确认执行 {tool_name}",
            }
        elif tool_meta and tool_meta.get("provider"):
            # MCP tool has a configured provider — always prefer MCP over built-in
            result = await _execute_mcp_skill(tool_name, arguments, db_session, active_skills)
        elif tool_name == "check_drug_interaction":
            result = await _execute_drug_interaction(arguments)
        elif tool_name == "query_doctor_schedule":
            result = await _execute_query_schedule(arguments, db_session)
        elif tool_name == "lock_appointment_slot":
            result = await _execute_lock_slot(arguments, db_session, user_id)
        else:
            # Try to find and execute as MCP skill
            result = await _execute_mcp_skill(tool_name, arguments, db_session, active_skills)

        latency_ms = int((time.time() - start) * 1000)
        result["_latency_ms"] = latency_ms
        result["_tool_name"] = tool_name
        await _record_chat_invocation(tool_name, arguments, result, db_session, active_skills, latency_ms)
        return result

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        logger.exception(f"Tool execution failed: {tool_name}")
        failed_result = {
            "error": str(e),
            "status": "failed",
            "_latency_ms": latency_ms,
            "_tool_name": tool_name,
        }
        await _record_chat_invocation(tool_name, arguments, failed_result, db_session, active_skills, latency_ms)
        return failed_result


async def _record_chat_invocation(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    db_session: Any,
    active_skills: list[dict[str, Any]] | None,
    latency_ms: int,
) -> None:
    """Persist tool calls made by chat; direct Skill API calls log themselves."""
    if not db_session or active_skills is None:
        return
    try:
        from sqlalchemy import select
        from app.models.models import SkillPackage, ToolInvocationLog

        skill_id = None
        for skill in active_skills:
            if any(t.get("name") == tool_name for t in skill.get("tools", []) if isinstance(t, dict)):
                skill_id = skill.get("skill_id")
                break
        if not skill_id:
            reverse_builtin = {
                "check_drug_interaction": "drug-safety",
                "query_doctor_schedule": "appointment-booking",
                "lock_appointment_slot": "appointment-booking",
            }
            skill_id = reverse_builtin.get(tool_name)
        if not skill_id:
            return
        row = await db_session.execute(select(SkillPackage).where(SkillPackage.skill_id == skill_id))
        skill = row.scalar_one_or_none()
        if not skill:
            return
        failed = result.get("status") == "failed" or bool(result.get("error"))
        db_session.add(ToolInvocationLog(
            skill_id=skill.id,
            trace_id=str(__import__("uuid").uuid4()),
            tool_name=tool_name,
            request_json=json.dumps(arguments, ensure_ascii=False),
            response_json=json.dumps(result, ensure_ascii=False),
            latency_ms=latency_ms,
            result_status="failed" if failed else "success",
            error_reason=str(result.get("error", "")) or None,
        ))
        await db_session.flush()
    except Exception:
        logger.exception("Failed to persist chat tool invocation: %s", tool_name)


async def _execute_drug_interaction(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute drug interaction check."""
    drugs = arguments.get("drugs", [])
    if not drugs:
        return {"error": "No drugs provided", "status": "failed"}

    return await query_drug_interactions(drugs)


async def _execute_query_schedule(
    arguments: dict[str, Any],
    db_session: Any = None,
) -> dict[str, Any]:
    """Query doctor schedules."""
    department_name = arguments.get("department_name", "")
    hospital_name = arguments.get("hospital_name", "")
    date = arguments.get("date", "")

    if not db_session:
        return {"error": "Database session not available", "status": "failed"}

    try:
        from datetime import date as _date, timedelta
        if not date:
            date = (_date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        service = RegistrationService(db_session)
        results = await service.search_by_department_name(
            hospital_name=hospital_name,
            department_name=department_name,
            date=date,
        )
        return {
            "status": "success",
            "result": results,
        }
    except Exception as e:
        return {"error": f"Schedule query failed: {e}", "status": "failed"}


async def _execute_lock_slot(
    arguments: dict[str, Any],
    db_session: Any = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Lock an appointment slot."""
    schedule_id = arguments.get("schedule_id", "")
    patient_name = arguments.get("patient_name", "")
    patient_id_last4 = arguments.get("patient_id_last4", "")

    if not all([schedule_id, patient_name, patient_id_last4]):
        return {"error": "Missing required fields", "status": "failed"}

    if not db_session or not user_id:
        return {"error": "Database session or user not available", "status": "failed"}

    try:
        service = RegistrationService(db_session)
        result = await service.lock_slot(
            schedule_id=schedule_id,
            patient_name=patient_name,
            patient_id_last4=patient_id_last4,
            user_id=user_id,
        )
        return {
            "status": "success",
            "result": result,
        }
    except Exception as e:
        return {"error": f"Slot lock failed: {e}", "status": "failed"}


async def _execute_mcp_skill(
    tool_name: str,
    arguments: dict[str, Any],
    db_session: Any = None,
    active_skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a namespaced Tool through its configured MCP server."""

    try:
        target_tool = None
        for skill in active_skills or []:
            for t in skill.get("tools", []):
                if isinstance(t, dict) and t.get("name") == tool_name:
                    target_tool = t
                    break
            if target_tool:
                break
        if not target_tool:
            return {"error": f"Unknown active MCP tool: {tool_name}", "status": "failed"}
        provider = target_tool.get("provider")
        if not provider:
            return {"error": "该工具没有可执行的 MCP 服务", "status": "failed"}
        from app.mcp.manager import mcp_manager
        return await mcp_manager.invoke(provider, tool_name, arguments)

    except Exception as e:
        return {"error": f"Skill execution failed: {e}", "status": "failed"}
