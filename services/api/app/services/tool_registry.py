"""
Structured tool registry for native OpenAI function calling.
Replaces regex-based ```invoke block parsing with proper tool_calls.
"""

from __future__ import annotations

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
    """Build OpenAI function calling tool list from built-in tools + registered skills."""
    tools = list(BUILTIN_TOOLS)

    if skills:
        for skill in skills:
            skill_tools = skill.get("tools", [])
            for tool in skill_tools:
                if isinstance(tool, dict) and "name" in tool:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", f"Tool from skill {skill.get('skill_id', 'unknown')}"),
                            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                        },
                    })

    return tools


async def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    db_session: Any = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Execute a tool call and return the result."""
    start = time.time()

    try:
        if tool_name == "check_drug_interaction":
            result = await _execute_drug_interaction(arguments)
        elif tool_name == "query_doctor_schedule":
            result = await _execute_query_schedule(arguments, db_session)
        elif tool_name == "lock_appointment_slot":
            result = await _execute_lock_slot(arguments, db_session, user_id)
        else:
            result = {"error": f"Unknown tool: {tool_name}", "status": "failed"}

        latency_ms = int((time.time() - start) * 1000)
        result["_latency_ms"] = latency_ms
        result["_tool_name"] = tool_name
        return result

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        logger.exception(f"Tool execution failed: {tool_name}")
        return {
            "error": str(e),
            "status": "failed",
            "_latency_ms": latency_ms,
            "_tool_name": tool_name,
        }


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
