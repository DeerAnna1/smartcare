import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, Boolean, DateTime, Float,
    ForeignKey, Integer, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ─── User ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    account_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[str] = mapped_column(Text, default="{}")
    preferences: Mapped[str] = mapped_column(Text, default="{}")
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)  # user | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list["ConsultationSession"]] = relationship(back_populates="user")
    events: Mapped[list["HealthEvent"]] = relationship(back_populates="user")
    records: Mapped[list["HealthRecord"]] = relationship(back_populates="user")


# ─── ConsultationSession ─────────────────────────────────────────────────────

class ConsultationSession(Base):
    __tablename__ = "consultation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="INIT")
    triage_level: Mapped[str] = mapped_column(String(32), default="observe")
    raw_messages: Mapped[str] = mapped_column(Text, default="[]")
    extracted_fields: Mapped[str] = mapped_column(Text, default="{}")
    clinical_memory: Mapped[str] = mapped_column(Text, default="{}")
    summary: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)  # 乐观锁版本号
    active_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 当前活跃的 Agent run ID
    active_run_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    events: Mapped[list["HealthEvent"]] = relationship(back_populates="session")
    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="session")


# ─── ConversationMessage ───────────────────────────────────────────────────────

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("consultation_sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)  # 会话内序号
    parent_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system|tool
    content_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON 内容
    status: Mapped[str] = mapped_column(String(16), default="completed")  # pending|streaming|completed|failed|cancelled
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 幂等键
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["ConsultationSession"] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint("session_id", "client_request_id", name="uq_conversation_request"),
        {"sqlite_autoincrement": True},
    )


# ─── HealthEvent ─────────────────────────────────────────────────────────────

class HealthEvent(Base):
    __tablename__ = "health_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_session_id: Mapped[str] = mapped_column(ForeignKey("consultation_sessions.id"))
    status: Mapped[str] = mapped_column(String(32), default="CREATED")

    # Event card fields
    chief_complaint: Mapped[str] = mapped_column(Text, default="")
    symptom_summary: Mapped[str] = mapped_column(Text, default="[]")
    duration: Mapped[str] = mapped_column(String(128), default="")
    severity: Mapped[str] = mapped_column(String(64), default="")
    confirmed_points: Mapped[str] = mapped_column(Text, default="[]")
    uncertain_points: Mapped[str] = mapped_column(Text, default="[]")
    red_flags: Mapped[str] = mapped_column(Text, default="[]")
    candidate_conditions: Mapped[str] = mapped_column(Text, default="[]")
    triage_level: Mapped[str] = mapped_column(String(32), default="observe")
    recommended_department: Mapped[str] = mapped_column(String(128), default="")
    visit_preparation: Mapped[str] = mapped_column(Text, default="[]")
    care_todos: Mapped[str] = mapped_column(Text, default="[]")
    medication_reminder_suggestion: Mapped[str] = mapped_column(Text, default="[]")
    followup_reminder_suggestion: Mapped[str] = mapped_column(Text, default="[]")
    record_update_suggestion: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_material_suggestion: Mapped[str] = mapped_column(Text, default="[]")
    task_completion_status: Mapped[str] = mapped_column(Text, default="{}")  # 存储任务完成状态

    # 挂号驱动字段（问诊结论 → 挂号工作区）
    recommended_hospital: Mapped[str] = mapped_column(String(256), default="")
    urgency_level: Mapped[str] = mapped_column(String(32), default="")   # immediate/soon/routine
    preferred_visit_time: Mapped[str] = mapped_column(String(128), default="")  # "近两天 上午"
    registration_ready: Mapped[bool] = mapped_column(Boolean, default=False)    # 问诊结论已足够挂号

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="events")
    session: Mapped["ConsultationSession"] = relationship(back_populates="events")
    reminders: Mapped[list["ReminderTask"]] = relationship(back_populates="event")
    records: Mapped[list["HealthRecord"]] = relationship(back_populates="event")


# ─── ReminderTask ─────────────────────────────────────────────────────────────

class ReminderTask(Base):
    __tablename__ = "reminder_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("health_events.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), default="medication")
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    schedule: Mapped[str] = mapped_column(Text, default="{}")
    repeat_rule: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    event: Mapped["HealthEvent | None"] = relationship(back_populates="reminders")


# ─── HealthRecord ─────────────────────────────────────────────────────────────

class HealthRecord(Base):
    __tablename__ = "health_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("health_events.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    structured_data: Mapped[str] = mapped_column(Text, default="{}")
    sync_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="records")
    event: Mapped["HealthEvent | None"] = relationship(back_populates="records")


# ─── SkillPackage ─────────────────────────────────────────────────────────────

class SkillPackage(Base):
    __tablename__ = "skill_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    skill_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="通用")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    trigger_examples: Mapped[str] = mapped_column(Text, default="[]")
    permissions: Mapped[str] = mapped_column(Text, default="[]")
    confirm_required: Mapped[bool] = mapped_column(Boolean, default=False)
    mcp_server: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[str] = mapped_column(Text, default="[]")
    retry_policy: Mapped[str] = mapped_column(Text, default="{}")
    degrade_policy: Mapped[str] = mapped_column(Text, default="{}")
    nested_skill_refs: Mapped[str] = mapped_column(Text, default="[]")
    brand_prompt: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_url: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    instructions: Mapped[str] = mapped_column(Text, default="")
    source_scope: Mapped[str] = mapped_column(String(32), default="custom")  # public|custom
    package_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    logs: Mapped[list["ToolInvocationLog"]] = relationship(back_populates="skill")


class MCPServerConfig(Base):
    """Transport/auth configuration for one independent MCP server."""
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    server_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    transport: Mapped[str] = mapped_column(String(32), default="http")  # http|sse|stdio
    url: Mapped[str] = mapped_column(Text, default="")
    command: Mapped[str] = mapped_column(Text, default="")
    args_json: Mapped[str] = mapped_column(Text, default="[]")
    env_json: Mapped[str] = mapped_column(Text, default="{}")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    oauth_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ToolDefinition(Base):
    """A normalized executable tool, independent from procedural Skills."""
    __tablename__ = "tool_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    tool_key: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    namespace: Mapped[str] = mapped_column(String(128), default="builtin")
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    annotations_json: Mapped[str] = mapped_column(Text, default="{}")
    provider_type: Mapped[str] = mapped_column(String(32), default="builtin")  # builtin|mcp
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("mcp_servers.id"), nullable=True, index=True)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SkillToolBinding(Base):
    __tablename__ = "skill_tool_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill_packages.id"), index=True)
    tool_id: Mapped[str] = mapped_column(ForeignKey("tool_definitions.id"), index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    permission: Mapped[str] = mapped_column(String(32), default="allow")

    __table_args__ = (UniqueConstraint("skill_id", "tool_id", name="uq_skill_tool_binding"),)


class AgentSkillPolicy(Base):
    __tablename__ = "agent_skill_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill_packages.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("agent_name", "skill_id", name="uq_agent_skill_policy"),)


# ─── ToolInvocationLog ────────────────────────────────────────────────────────

class ToolInvocationLog(Base):
    __tablename__ = "tool_invocation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    skill_id: Mapped[str | None] = mapped_column(ForeignKey("skill_packages.id"), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    tool_name: Mapped[str] = mapped_column(String(128), default="")
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    result_status: Mapped[str] = mapped_column(String(32), default="success")
    error_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    skill: Mapped["SkillPackage | None"] = relationship(back_populates="logs")


# ─── AuditLog ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), default="")
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Multimodal / IoT ─────────────────────────────────────────────────────────

class LabReport(Base):
    __tablename__ = "lab_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_items: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VitalStreamEvent(Base):
    __tablename__ = "vital_stream_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(64), default="apple-watch")
    metric: Mapped[str] = mapped_column(String(64), default="heart_rate")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(16), default="bpm")
    measured_at: Mapped[str] = mapped_column(String(64), default="")
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Human Handoff ────────────────────────────────────────────────────────────

class HandoffTicket(Base):
    __tablename__ = "handoff_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("consultation_sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    risk_level: Mapped[str] = mapped_column(String(32), default="high")
    reason: Mapped[str] = mapped_column(Text, default="")
    brief: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ─── Proactive Intervention ───────────────────────────────────────────────────

class ProactiveRule(Base):
    __tablename__ = "proactive_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    condition_type: Mapped[str] = mapped_column(String(64), default="chronic")
    condition_value: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProactiveInterventionLog(Base):
    __tablename__ = "proactive_intervention_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("proactive_rules.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(64), default="weather")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Plugin / OAuth ───────────────────────────────────────────────────────────

class UserOAuthCredential(Base):
    __tablename__ = "user_oauth_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ─── Registration Module ───────────────────────────────────────────────────────

class Hospital(Base):
    """医院基本信息表（对接真实平台时补充平台凭证字段）"""
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(256), index=True)
    short_name: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    district: Mapped[str] = mapped_column(String(64), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    level: Mapped[str] = mapped_column(String(32), default="三级甲等")
    tags: Mapped[str] = mapped_column(Text, default="[]")          # JSON list: ["综合","儿科"]
    platform_code: Mapped[str] = mapped_column(String(128), default="")  # 对接平台唯一标识
    platform_type: Mapped[str] = mapped_column(String(32), default="seed")  # seed/his/jiangtong/...
    booking_url: Mapped[str] = mapped_column(Text, default="")    # V1 直接跳转 URL
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    departments: Mapped[list["Department"]] = relationship(back_populates="hospital")


class Department(Base):
    """科室表"""
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), default="")      # 平台侧科室编码
    category: Mapped[str] = mapped_column(String(64), default="")  # 内科/外科/...
    description: Mapped[str] = mapped_column(Text, default="")
    floor: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hospital: Mapped["Hospital"] = relationship(back_populates="departments")
    schedules: Mapped[list["DoctorSchedule"]] = relationship(back_populates="department")


class DoctorSchedule(Base):
    """医生排班/号源表（真实平台接入后由同步任务刷新）"""
    __tablename__ = "doctor_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), index=True)
    doctor_name: Mapped[str] = mapped_column(String(64))
    doctor_title: Mapped[str] = mapped_column(String(64), default="")   # 主治/副主任/主任
    doctor_bio: Mapped[str] = mapped_column(Text, default="")
    schedule_date: Mapped[str] = mapped_column(String(16), index=True)  # YYYY-MM-DD
    time_slot: Mapped[str] = mapped_column(String(16))                  # 08:30
    period: Mapped[str] = mapped_column(String(8), default="上午")      # 上午/下午/晚上
    total_quota: Mapped[int] = mapped_column(Integer, default=20)
    remaining_quota: Mapped[int] = mapped_column(Integer, default=20)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    platform_slot_id: Mapped[str] = mapped_column(String(128), default="")  # 平台锁号用
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    department: Mapped["Department"] = relationship(back_populates="schedules")


class RegistrationOrder(Base):
    """挂号订单表（锁号后创建，确认后状态变更）"""
    __tablename__ = "registration_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("doctor_schedules.id"))
    health_event_id: Mapped[str | None] = mapped_column(ForeignKey("health_events.id"), nullable=True)

    # 患者信息（敏感字段加密存储，生产环境需 AES/KMS）
    patient_name: Mapped[str] = mapped_column(String(64), default="")
    patient_id_masked: Mapped[str] = mapped_column(String(32), default="")  # 仅保留后4位

    # 订单状态：LOCKED → CONFIRMED → PAID → CANCELLED → COMPLETED
    status: Mapped[str] = mapped_column(String(32), default="LOCKED", index=True)
    lock_expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platform_order_id: Mapped[str] = mapped_column(String(128), default="")  # 平台订单号
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    cancel_reason: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    schedule: Mapped["DoctorSchedule"] = relationship()


# ─── ConsentRecord ──────────────────────────────────────────────────────────

class ConsentRecord(Base):
    """用户同意记录：追踪用户对各类数据处理的授权状态。"""
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(64), index=True)
    # upload_doc | long_term_memory | third_party_model | ocr | device_data
    policy_version: Mapped[str] = mapped_column(String(32), default="v1")
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── DataExportJob ──────────────────────────────────────────────────────────

class DataExportJob(Base):
    """用户数据导出任务。"""
    __tablename__ = "data_export_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | processing | completed | failed
    object_key: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─── DeletionJob ────────────────────────────────────────────────────────────

class DeletionJob(Base):
    """用户账户删除任务。"""
    __tablename__ = "deletion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | processing | completed | failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── M4: MemoryFact ────────────────────────────────────────────────────────

class MemoryFact(Base):
    """长期健康记忆事实。"""
    __tablename__ = "memory_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fact_type: Mapped[str] = mapped_column(String(32), index=True)
    # allergy | condition | medication | procedure | preference | family_history | other
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    source_type: Mapped[str] = mapped_column(String(32), default="user_message")
    # user_message | health_record | lab_report | device | clinician
    source_id: Mapped[str] = mapped_column(String(128), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    # proposed | confirmed | rejected | superseded | expired
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_fact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ─── M5: Knowledge Domain ──────────────────────────────────────────────────

class KnowledgeDocument(Base):
    """知识库文档元数据。"""
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(64), default="manual")
    # manual | upload | api | public_corpus
    source_uri: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(64), default="public_medical")
    # public_medical | org_{tenant_id} | user_{user_id}
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    # uploaded | parsing | parsed | chunking | embedding | validating | published | failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class KnowledgeChunk(Base):
    """知识库文档切块。"""
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(256), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")
    embedding_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionJob(Base):
    """知识库摄入任务。"""
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | processing | completed | failed
    current_stage: Mapped[str] = mapped_column(String(32), default="")
    # parsing | chunking | embedding | validating
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─── M6: MediaAsset ────────────────────────────────────────────────────────

class MediaAsset(Base):
    """多媒体资产。"""
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    object_key: Mapped[str] = mapped_column(Text, default="")
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    # uploaded | scanning | clean | infected | processing | ready | failed
    malware_scan_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | clean | infected | error
    derived_assets: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── M7: ToolRun ───────────────────────────────────────────────────────────

class ToolRun(Base):
    """工具执行记录（统一 Tool Gateway 审计）。"""
    __tablename__ = "tool_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    tool_version: Mapped[str] = mapped_column(String(32), default="1.0")
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | confirmed | running | success | failed | cancelled | timeout
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_reason: Mapped[str] = mapped_column(Text, default="")
    external_ref: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─── M8: SafetyRule ────────────────────────────────────────────────────────

class SafetyRule(Base):
    """版本化安全规则集。"""
    __tablename__ = "safety_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    rule_type: Mapped[str] = mapped_column(String(64), index=True)
    # red_flag | output_constraint | iot_threshold | specialty_strategy
    name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    pattern: Mapped[str] = mapped_column(Text, default="")  # JSON pattern or regex
    severity: Mapped[str] = mapped_column(String(32), default="high")
    # critical | high | medium | low
    action: Mapped[str] = mapped_column(String(64), default="flag")
    # flag | block | escalate | handoff
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── M9: EvalRun ───────────────────────────────────────────────────────────

class EvalRun(Base):
    """评测运行记录。"""
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    run_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | running | completed | failed
    model_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    graph_version: Mapped[str] = mapped_column(String(32), default="")
    tool_version: Mapped[str] = mapped_column(String(32), default="")
    knowledge_manifest: Mapped[str] = mapped_column(Text, default="{}")
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    average_score: Mapped[float] = mapped_column(Float, default=0.0)
    dimension_scores: Mapped[str] = mapped_column(Text, default="{}")
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
