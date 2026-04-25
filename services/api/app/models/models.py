import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, Boolean, DateTime, Float,
    ForeignKey, Integer
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
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    events: Mapped[list["HealthEvent"]] = relationship(back_populates="session")


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
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    logs: Mapped[list["ToolInvocationLog"]] = relationship(back_populates="skill")


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

