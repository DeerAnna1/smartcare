"""LLM 输出 Pydantic 校验 schema。

用于校验 LLM 生成的结构化 JSON（阶段性结论、事件卡片等）。
"""
from __future__ import annotations

import json
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class CandidateCondition(BaseModel):
    """候选诊断方向。"""
    name: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_points: list[str] = Field(default_factory=list)
    against_points: list[str] = Field(default_factory=list)


class SummaryOutput(BaseModel):
    """阶段性结论 JSON 校验 schema。"""
    status: Literal["SUMMARY_READY"] = "SUMMARY_READY"
    chief_complaint: str = Field(default="", max_length=500)
    symptom_summary: list[str] = Field(default_factory=list)
    duration: str = Field(default="", max_length=200)
    severity: Literal["轻度", "中度", "重度", "mild", "moderate", "severe"] = "中度"
    confirmed_points: list[str] = Field(default_factory=list)
    uncertain_points: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    candidate_conditions: list[CandidateCondition] = Field(default_factory=list)
    triage_level: Literal["observe", "outpatient", "urgent_visit", "emergency"] = "observe"
    recommended_department: str = Field(default="", max_length=100)
    visit_preparation: list[str] = Field(default_factory=list)
    care_todos: list[str] = Field(default_factory=list)
    medication_reminder_suggestion: list[str] = Field(default_factory=list)
    followup_reminder_suggestion: list[str] = Field(default_factory=list)
    record_update_suggestion: bool = True
    insurance_material_suggestion: list[str] = Field(default_factory=list)
    summary_text: str = Field(default="", max_length=2000)

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, v: str) -> str:
        """统一中英文严重程度。"""
        mapping = {"mild": "轻度", "moderate": "中度", "severe": "重度"}
        return mapping.get(v, v)

    @field_validator("triage_level")
    @classmethod
    def validate_triage_level(cls, v: str) -> str:
        """校验分诊级别。"""
        valid = {"observe", "outpatient", "urgent_visit", "emergency"}
        if v not in valid:
            return "observe"
        return v


class EventCardOutput(BaseModel):
    """事件卡片输出校验 schema。"""
    chief_complaint: str = Field(..., min_length=1, max_length=500)
    symptom_summary: list[str] = Field(default_factory=list)
    duration: str = Field(default="", max_length=200)
    severity: Literal["轻度", "中度", "重度"] = "中度"
    confirmed_points: list[str] = Field(default_factory=list)
    uncertain_points: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    candidate_conditions: list[CandidateCondition] = Field(default_factory=list)
    triage_level: Literal["observe", "outpatient", "urgent_visit", "emergency"] = "observe"
    recommended_department: str = Field(default="", max_length=100)


def _sanitize_candidate_conditions(val: list | dict | str) -> list[dict]:
    """尽力将 LLM 输出的候选诊断转为 CandidateCondition 兼容格式。"""
    items: list = []
    if isinstance(val, list):
        items = val
    elif isinstance(val, dict):
        # LLM 可能返回 {"0": {...}, "1": {...}} 或单个对象
        items = list(val.values()) if all(k.isdigit() for k in val) else [val]
    elif isinstance(val, str):
        # 可能是 JSON 字符串
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                items = [parsed]
        except Exception:
            return [{"name": val, "confidence": 0.0}]

    result = []
    for item in items:
        if isinstance(item, str):
            result.append({"name": item, "confidence": 0.0})
        elif isinstance(item, dict):
            result.append({
                "name": str(item.get("name", item.get("condition", item.get("诊断", "")))),
                "confidence": float(item.get("confidence", item.get("probability", 0.0)) or 0.0),
                "supporting_points": item.get("supporting_points", item.get("支持点", [])) if isinstance(item.get("supporting_points", item.get("支持点", [])), list) else [],
                "against_points": item.get("against_points", item.get("反对点", [])) if isinstance(item.get("against_points", item.get("反对点", [])), list) else [],
            })
    return result


def validate_summary_json(raw: dict) -> tuple[SummaryOutput | None, list[str]]:
    """校验 LLM 输出的 summary JSON。

    Returns:
        (validated_model, errors): 如果校验通过返回 (model, [])，否则返回 (None, error_list)
    """
    errors: list[str] = []
    try:
        model = SummaryOutput(**raw)
        return model, []
    except Exception as e:
        errors.append(f"Summary 校验失败: {str(e)[:300]}")

        # 宽松校验：逐字段尝试，跳过校验失败的字段而非放弃全部
        fallback: dict = {
            "status": "SUMMARY_READY",
            "chief_complaint": str(raw.get("chief_complaint", "")),
            "summary_text": str(raw.get("summary_text", "")),
            "triage_level": raw.get("triage_level", "observe"),
            "severity": raw.get("severity", "中度"),
        }
        for key in SummaryOutput.model_fields:
            if key in raw and key not in fallback:
                try:
                    # 用 Pydantic 单字段校验
                    SummaryOutput.model_validate({**fallback, key: raw[key]})
                    fallback[key] = raw[key]
                except Exception:
                    # 该字段校验失败，尝试类型强制转换
                    field_info = SummaryOutput.model_fields[key]
                    expected = field_info.annotation
                    val = raw[key]
                    try:
                        if expected == str:
                            fallback[key] = str(val)
                        elif expected == bool:
                            fallback[key] = bool(val)
                        elif expected == list[str]:
                            fallback[key] = val if isinstance(val, list) else [str(val)]
                        elif expected == list[CandidateCondition]:
                            # 尽力解析候选诊断列表
                            cleaned = _sanitize_candidate_conditions(val)
                            fallback[key] = cleaned
                        else:
                            fallback[key] = val
                    except Exception:
                        pass  # 放弃该字段

        try:
            model = SummaryOutput(**fallback)
            errors.append("使用宽松校验恢复成功")
            return model, errors
        except Exception as e2:
            errors.append(f"宽松校验也失败: {str(e2)[:200]}")
            return None, errors


def validate_and_clean_summary(raw: dict) -> dict | None:
    """校验并清理 LLM 输出的 summary JSON，返回清理后的 dict。

    如果校验失败但能恢复，返回恢复后的 dict。
    如果完全无法恢复，返回 None。
    """
    model, errors = validate_summary_json(raw)
    if model:
        return model.model_dump()
    return None
