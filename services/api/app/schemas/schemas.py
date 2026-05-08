"""Pydantic v2 Schemas — 健康事件卡、请求/响应体"""
from __future__ import annotations
from datetime import datetime
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator


# ─── 健康事件卡核心 Schema (PRD §8.2) ─────────────────────────────────────────

class CandidateCondition(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_points: list[str] = []
    against_points: list[str] = []


TriageLevel = Literal["observe", "outpatient", "urgent_visit", "emergency"]


class HealthEventCardSchema(BaseModel):
    """跨工作区唯一合法迁移载体"""
    chief_complaint: str
    symptom_summary: list[str] = []
    duration: str = ""
    severity: str = ""
    confirmed_points: list[str] = []
    uncertain_points: list[str] = []
    red_flags: list[str] = []
    candidate_conditions: list[CandidateCondition] = []
    triage_level: TriageLevel = "observe"
    recommended_department: str = ""
    visit_preparation: list[str] = []
    care_todos: list[str] = []
    medication_reminder_suggestion: list[str] = []
    followup_reminder_suggestion: list[str] = []
    record_update_suggestion: bool = False
    insurance_material_suggestion: list[str] = []
    source_session_id: str  # required per PRD §8.3

    @model_validator(mode="before")
    @classmethod
    def coerce_none_to_defaults(cls, data: dict) -> dict:
        """LLM may output null for string/array fields; coerce to schema defaults."""
        if not isinstance(data, dict):
            return data
        field_info = cls.model_fields
        for key, value in list(data.items()):
            if value is None and key in field_info:
                field = field_info[key]
                # Use field default if available, else type-appropriate empty value
                if field.default is not None and field.default is not ...:
                    data[key] = field.default
                elif isinstance(field.annotation, type):
                    if issubclass(field.annotation, str):
                        data[key] = ""
                    elif issubclass(field.annotation, list):
                        data[key] = []
                    elif issubclass(field.annotation, bool):
                        data[key] = False
                else:
                    data[key] = ""
        return data


# ─── 会话 ─────────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str | None = None  # 单用户模式下可省略


class SessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: datetime
    chief_complaint: str = ""
    triage_level: str = ""
    skill_tags: list[str] = []

    model_config = {"from_attributes": True}


class MessageItem(BaseModel):
    role: str
    content: str


class SessionDetailResponse(BaseModel):
    session_id: str
    status: str
    messages: list[MessageItem]
    red_flag_detected: bool = False


class SendMessageRequest(BaseModel):
    role: Literal["user"] = "user"
    content: str
    lang: str | None = None


class SessionMessageResponse(BaseModel):
    status: str
    assistant_message: str
    structured_state: dict
    red_flag_detected: bool = False


class SessionSummaryResponse(BaseModel):
    session_id: str
    status: str
    summary: str
    triage_level: str
    extracted_fields: dict
    ready_for_event_card: bool


# ─── 健康事件卡 API ────────────────────────────────────────────────────────────

class CreateEventCardRequest(BaseModel):
    event_card: HealthEventCardSchema


class EventCardResponse(BaseModel):
    event_id: str
    status: str
    chief_complaint: str
    triage_level: str
    recommended_department: str
    created_at: datetime
    archived: bool = False

    model_config = {"from_attributes": True}


class ConfirmEventCardRequest(BaseModel):
    notes: str = ""


# ─── 执行工作区 ───────────────────────────────────────────────────────────────

class TaskRecommendation(BaseModel):
    id: str
    type: str
    title: str
    description: str
    priority: Literal["high", "medium", "low"] = "medium"
    actionable: bool = True
    status: Literal["pending", "completed"] = "pending"


class RecommendationsResponse(BaseModel):
    event_id: str
    tasks: list[TaskRecommendation]


# ─── 提醒 ─────────────────────────────────────────────────────────────────────

class CreateReminderRequest(BaseModel):
    task_type: str = "medication"
    title: str
    description: str = ""
    schedule: dict = {}
    repeat_rule: str = ""
    event_id: str | None = None


class ReminderResponse(BaseModel):
    id: str
    task_type: str
    title: str
    description: str
    schedule: dict
    repeat_rule: str
    status: str
    event_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── 健康档案 ─────────────────────────────────────────────────────────────────

class CreateRecordRequest(BaseModel):
    title: str
    department: str = ""
    event_id: str | None = None
    tags: list[str] = []
    structured_data: dict = {}


class RecordResponse(BaseModel):
    id: str
    title: str
    department: str
    sync_status: str
    tags: list[str]
    event_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateEhrSummaryRequest(BaseModel):
    manual_history: str = ""


class GenerateEhrSummaryResponse(BaseModel):
    summary: str
    archived_record_count: int


class ExportEhrPdfRequest(BaseModel):
    content: str
    filename: str = "complete-ehr.pdf"


class HealthArchiveProfileRequest(BaseModel):
    name: str = ""
    gender: str = ""
    age: str = ""
    contact: str = ""
    manual_history: str = ""


class HealthArchiveProfileResponse(BaseModel):
    name: str = ""
    gender: str = ""
    age: str = ""
    contact: str = ""
    manual_history: str = ""
    updated_at: datetime


# ─── 鉴权 ─────────────────────────────────────────────────────────────────────

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{6,}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str

    @model_validator(mode="after")
    def validate_password(self) -> "RegisterRequest":
        if not PASSWORD_PATTERN.fullmatch(self.password):
            raise ValueError("密码必须至少 6 位，且仅包含字母和数字，并同时包含字母和数字")
        return self


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    avatar_url: str = ""
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserProfileResponse


# ─── Skill ────────────────────────────────────────────────────────────────────

class CreateSkillRequest(BaseModel):
    skill_id: str
    name: str
    description: str = ""
    category: str = "通用"
    confirm_required: bool = False
    source_url: str = ""
    keywords: list[str] = []
    trigger_examples: list[str] = []
    version: str = "1.0.0"
    mcp_server: str = ""
    tools: list[dict] = []
    degrade_policy: dict = {}


class SkillResponse(BaseModel):
    id: str
    skill_id: str
    name: str
    description: str
    category: str
    status: str
    confirm_required: bool
    version: str
    keywords: list[str]
    trigger_examples: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class InvokeSkillRequest(BaseModel):
    input: dict = {}
    trace_id: str = ""


class InvokeSkillResponse(BaseModel):
    skill_id: str
    status: Literal["success", "degraded", "failed"]
    result: dict | None = None
    error: str | None = None
    trace_id: str = ""


# ─── Multimodal / IoT ─────────────────────────────────────────────────────────

class LabItem(BaseModel):
    name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    abnormal: bool = False
    interpretation: str = ""


class LabReportParseResponse(BaseModel):
    report_id: str
    filename: str
    summary: str
    items: list[LabItem]


class IoTWebhookRequest(BaseModel):
    source: str = "apple-watch"
    user_id: str | None = None
    metric: str = "heart_rate"
    value: float
    unit: str = "bpm"
    measured_at: str
    event_id: str = ""


# ─── Human Handoff ────────────────────────────────────────────────────────────

class HandoffTicketResponse(BaseModel):
    id: str
    session_id: str
    status: str
    risk_level: str
    reason: str
    brief: str
    evidence: list[str] = []
    created_at: datetime


class UpdateHandoffStatusRequest(BaseModel):
    status: Literal["pending", "processing", "resolved"]


# ─── Proactive Intervention ───────────────────────────────────────────────────

class CreateProactiveRuleRequest(BaseModel):
    condition_type: str = "chronic"
    condition_value: str
    city: str
    enabled: bool = True


class ProactiveRuleResponse(BaseModel):
    id: str
    condition_type: str
    condition_value: str
    city: str
    enabled: bool
    created_at: datetime


# ─── Plugin/OAuth ─────────────────────────────────────────────────────────────

class PluginManifestRequest(BaseModel):
    provider: str
    auth_type: Literal["none", "oauth2"] = "none"
    manifest: dict = {}


class OAuthConnectRequest(BaseModel):
    provider: str
    access_token: str
    refresh_token: str = ""
    expires_at: str = ""
    metadata: dict = {}
