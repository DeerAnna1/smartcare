"""定时科普任务 API"""
import re
from datetime import datetime

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, ForeignKey

from app.api.deps.auth import get_current_user_required
from app.core.database import get_db, Base
from app.models.models import gen_uuid, utcnow, User

# ─── Model ────────────────────────────────────────────────────────────────────

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String(32), default="education")
    topic: Mapped[str] = mapped_column(String(128), default="")
    schedule_cron: Mapped[str] = mapped_column(String(64), default="")
    schedule_natural: Mapped[str] = mapped_column(Text, default="")
    content_template: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScheduledTaskLog(Base):
    __tablename__ = "scheduled_task_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("scheduled_tasks.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    title: str = ""
    description: str = ""
    topic: str = ""
    schedule_cron: str = ""
    schedule_natural: str = ""
    content_template: str = ""
    task_type: str = "education"


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    topic: str | None = None
    schedule_cron: str | None = None
    schedule_natural: str | None = None
    content_template: str | None = None
    task_type: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    task_type: str
    topic: str
    schedule_cron: str
    schedule_natural: str
    content_template: str
    status: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime


class UnreadCountResponse(BaseModel):
    total_unread: int
    task_unreads: dict[str, int]


class ParseScheduleRequest(BaseModel):
    text: str


class ParseScheduleResponse(BaseModel):
    cron: str
    topic: str
    description: str


class TaskLogResponse(BaseModel):
    id: str
    task_id: str
    content: str
    status: str
    error_message: str
    executed_at: datetime


# ─── Natural Language Schedule Parser ─────────────────────────────────────────

# 星期映射
_WEEKDAY_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "日": 0, "天": 0,
}

# 常见健康话题关键词
_TOPIC_KEYWORDS = [
    "高血压", "糖尿病", "冠心病", "心脑血管", "心血管",
    "营养", "饮食", "运动", "减肥", "减重", "肥胖",
    "睡眠", "失眠", "心理", "焦虑", "抑郁",
    "中医", "养生", "保健", "免疫力", "免疫",
    "过敏", "哮喘", "呼吸道", "感冒", "流感",
    "骨质疏松", "关节", "腰椎", "颈椎",
    "眼科", "近视", "口腔", "牙齿",
    "皮肤", "护肤", "防晒",
    "孕期", "育儿", "儿童健康", "老年健康",
    "用药", "药物", "疫苗", "体检",
    "肝脏", "肾脏", "肠胃", "消化",
]


_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19,
            "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "三十": 30, "四十五": 45, "五十": 50}


def _cn_to_int(s: str) -> int | None:
    """将中文数字或阿拉伯数字字符串转为 int。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    return _CN_NUM.get(s)


def _extract_hour(text: str) -> int:
    """从中文时间描述中提取小时数（支持中文和阿拉伯数字）。"""
    # 匹配 "早上8点", "上午10点", "下午3点", "晚上9点", "下午五点" 等
    num_pattern = r"(\d{1,2}|[零一二两三四五六七八九十]+)"

    m = re.search(rf"(?:早上|上午|早|晨){num_pattern}(?:点|时|:)?", text)
    if m:
        v = _cn_to_int(m.group(1))
        if v is not None:
            return v

    m = re.search(rf"(?:下午|午后){num_pattern}(?:点|时|:)?", text)
    if m:
        v = _cn_to_int(m.group(1))
        if v is not None:
            return v + 12 if v < 12 else v

    m = re.search(rf"(?:晚上|晚间|晚|夜里|夜间){num_pattern}(?:点|时|:)?", text)
    if m:
        v = _cn_to_int(m.group(1))
        if v is not None:
            return v + 12 if v < 12 else v

    # 纯数字 "8点" / "五点"
    m = re.search(rf"{num_pattern}(?:点|时)", text)
    if m:
        v = _cn_to_int(m.group(1))
        if v is not None:
            return v

    # 默认早上9点
    return 9


def _extract_minute(text: str) -> int:
    """从中文时间描述中提取分钟数（支持中文和阿拉伯数字）。"""
    # 匹配 "点十五分", "点30分", "点十五", "点半" 等
    m = re.search(r"点(\d{1,2})分?", text)
    if m:
        return int(m.group(1))

    m = re.search(r"点([零一二两三四五六七八九十百]+)分?", text)
    if m:
        v = _cn_to_int(m.group(1))
        if v is not None:
            return v

    # "点半"
    if "点半" in text:
        return 30

    return 0


def _extract_topic(text: str) -> str:
    """从文本中提取健康话题关键词。"""
    for kw in _TOPIC_KEYWORDS:
        if kw in text:
            return kw
    return "健康科普"


def parse_natural_schedule(text: str) -> dict:
    """
    解析中文自然语言时间描述，返回 cron 表达式和提取的话题。

    示例:
        "每天早上8点" -> {"cron": "0 8 * * *", "topic": "健康科普"}
        "每天下午五点十五" -> {"cron": "15 17 * * *", "topic": "健康科普"}
        "每周一下午3点讲高血压" -> {"cron": "0 15 * * 1", "topic": "高血压"}
        "每月15号" -> {"cron": "0 0 15 * *", "topic": "健康科普"}
    """
    hour = _extract_hour(text)
    minute = _extract_minute(text)
    topic = _extract_topic(text)

    # 每天
    if re.search(r"每天|每日|日日", text):
        return {
            "cron": f"{minute} {hour} * * *",
            "topic": topic,
            "description": f"每天 {_format_hour(hour)} 推送「{topic}」相关内容",
        }

    # 每周X
    weekday_match = re.search(r"每周([一二三四五六日天])", text)
    if weekday_match:
        day_char = weekday_match.group(1)
        day_num = _WEEKDAY_MAP.get(day_char, 1)
        return {
            "cron": f"{minute} {hour} * * {day_num}",
            "topic": topic,
            "description": f"每周{_day_name(day_num)} {_format_hour(hour)} 推送「{topic}」相关内容",
        }

    # 每月N号
    month_day_match = re.search(r"每月(\d{1,2})[号日]", text)
    if month_day_match:
        day = int(month_day_match.group(1))
        day = max(1, min(31, day))
        return {
            "cron": f"{minute} {hour} {day} * *",
            "topic": topic,
            "description": f"每月{day}号 {_format_hour(hour)} 推送「{topic}」相关内容",
        }

    # 工作日 / 周一到周五
    if re.search(r"工作日|周一到周五|周一至周五", text):
        return {
            "cron": f"{minute} {hour} * * 1-5",
            "topic": topic,
            "description": f"工作日 {_format_hour(hour)} 推送「{topic}」相关内容",
        }

    # 默认：每天
    return {
        "cron": f"{minute} {hour} * * *",
        "topic": topic,
        "description": f"每天 {_format_hour(hour)} 推送「{topic}」相关内容",
    }


def _format_hour(h: int) -> str:
    """将24小时制转为中文描述。"""
    if h < 6:
        return f"凌晨{h}点"
    elif h < 12:
        return f"上午{h}点"
    elif h == 12:
        return "中午12点"
    elif h < 18:
        return f"下午{h - 12}点"
    else:
        return f"晚上{h - 12}点"


def _day_name(d: int) -> str:
    """星期数字转中文名。"""
    names = {0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
    return names.get(d, str(d))


# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/scheduled-tasks", tags=["定时科普任务"])


def _to_response(task: ScheduledTask, unread_count: int = 0) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        topic=task.topic,
        schedule_cron=task.schedule_cron,
        schedule_natural=task.schedule_natural,
        content_template=task.content_template,
        status=task.status,
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        unread_count=unread_count,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """获取当前用户的定时科普任务列表（按创建时间倒序），包含未读计数。"""
    from sqlalchemy import func

    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user.id)
        .order_by(ScheduledTask.created_at.desc())
    )
    tasks = result.scalars().all()

    responses = []
    for task in tasks:
        # 计算未读日志数：executed_at > last_read_at 的日志
        if task.last_read_at:
            unread_result = await db.execute(
                select(func.count(ScheduledTaskLog.id))
                .where(
                    ScheduledTaskLog.task_id == task.id,
                    ScheduledTaskLog.executed_at > task.last_read_at,
                )
            )
        else:
            # 从未读过，所有日志都是未读
            unread_result = await db.execute(
                select(func.count(ScheduledTaskLog.id))
                .where(ScheduledTaskLog.task_id == task.id)
            )
        unread_count = unread_result.scalar() or 0
        responses.append(_to_response(task, unread_count))

    return responses


@router.get("/unread", response_model=UnreadCountResponse)
async def get_unread_counts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """获取所有任务的未读计数汇总。"""
    from sqlalchemy import func

    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user.id)
    )
    tasks = result.scalars().all()

    task_unreads: dict[str, int] = {}
    total_unread = 0

    for task in tasks:
        if task.last_read_at:
            unread_result = await db.execute(
                select(func.count(ScheduledTaskLog.id))
                .where(
                    ScheduledTaskLog.task_id == task.id,
                    ScheduledTaskLog.executed_at > task.last_read_at,
                )
            )
        else:
            unread_result = await db.execute(
                select(func.count(ScheduledTaskLog.id))
                .where(ScheduledTaskLog.task_id == task.id)
            )
        count = unread_result.scalar() or 0
        task_unreads[task.id] = count
        total_unread += count

    return UnreadCountResponse(total_unread=total_unread, task_unreads=task_unreads)


@router.post("/{task_id}/read")
async def mark_task_read(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """标记任务日志为已读（更新 last_read_at 为当前时间）。"""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task.last_read_at = utcnow()
    await db.flush()
    return {"status": "ok", "task_id": task_id}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """标记所有任务为已读。"""
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user.id)
    )
    tasks = result.scalars().all()

    now = utcnow()
    for task in tasks:
        task.last_read_at = now

    await db.flush()
    return {"status": "ok", "count": len(tasks)}


@router.post("", response_model=TaskResponse)
async def create_task(
    body: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """创建定时科普任务。如果 schedule_cron 为空但 schedule_natural 不为空，自动解析。"""
    cron = body.schedule_cron.strip()
    topic = body.topic.strip()
    if not cron and body.schedule_natural:
        parsed = parse_natural_schedule(body.schedule_natural)
        cron = parsed["cron"]
        if not topic:
            topic = parsed["topic"]

    if not cron or not croniter.is_valid(cron):
        raise HTTPException(status_code=422, detail="无法识别有效的定时规则")

    topic = topic or "健康科普"
    title = body.title.strip() or f"{topic}定时科普"

    task = ScheduledTask(
        user_id=user.id,
        title=title,
        description=body.description,
        task_type=body.task_type,
        topic=topic,
        schedule_cron=cron,
        schedule_natural=body.schedule_natural,
        content_template=body.content_template,
    )

    from app.jobs.scheduled_task_runner import calculate_next_run
    task.next_run_at = calculate_next_run(cron)

    db.add(task)
    await db.flush()
    await db.refresh(task)
    return _to_response(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    body: UpdateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """更新定时科普任务字段。"""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    update_data = body.model_dump(exclude_unset=True)
    if body.schedule_natural is not None and body.schedule_cron is None:
        parsed = parse_natural_schedule(body.schedule_natural)
        update_data["schedule_cron"] = parsed["cron"]
        if not body.topic:
            update_data["topic"] = parsed["topic"]

    for field, value in update_data.items():
        setattr(task, field, value)

    if not task.schedule_cron or not croniter.is_valid(task.schedule_cron):
        raise HTTPException(status_code=422, detail="无法识别有效的定时规则")

    from app.jobs.scheduled_task_runner import calculate_next_run
    task.next_run_at = calculate_next_run(task.schedule_cron)

    await db.flush()
    await db.refresh(task)
    return _to_response(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """删除定时科普任务。"""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 先删除关联日志（避免外键约束报错）
    await db.execute(delete(ScheduledTaskLog).where(ScheduledTaskLog.task_id == task_id))
    await db.delete(task)
    await db.commit()


@router.post("/{task_id}/toggle", response_model=TaskResponse)
async def toggle_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """切换任务状态：active <-> paused。"""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == "active":
        task.status = "paused"
    else:
        task.status = "active"
        from app.jobs.scheduled_task_runner import calculate_next_run
        task.next_run_at = calculate_next_run(task.schedule_cron)

    await db.flush()
    await db.refresh(task)
    return _to_response(task)


@router.post("/parse", response_model=ParseScheduleResponse)
async def parse_schedule(
    body: ParseScheduleRequest,
    user: User = Depends(get_current_user_required),
):
    """
    解析自然语言时间描述，返回 cron 表达式和提取的话题。

    示例输入:
        - "每天早上8点讲高血压知识"
        - "每周一下午3点"
        - "每月15号推送健康养生内容"
        - "工作日晚上9点"
    """
    parsed = parse_natural_schedule(body.text)
    return ParseScheduleResponse(
        cron=parsed["cron"],
        topic=parsed["topic"],
        description=parsed["description"],
    )


@router.get("/{task_id}/logs", response_model=list[TaskLogResponse])
async def get_task_logs(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """获取任务执行日志（按执行时间倒序）。"""
    # Verify task belongs to user
    task_result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await db.execute(
        select(ScheduledTaskLog)
        .where(ScheduledTaskLog.task_id == task_id)
        .order_by(ScheduledTaskLog.executed_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()
    return [
        TaskLogResponse(
            id=log.id,
            task_id=log.task_id,
            content=log.content,
            status=log.status,
            error_message=log.error_message,
            executed_at=log.executed_at,
        )
        for log in logs
    ]


@router.post("/{task_id}/execute")
async def execute_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """快速测试：立即执行一次，并写入与自动调度相同的日志。"""
    task_result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    from app.jobs.scheduled_task_runner import execute_scheduled_task
    return await execute_scheduled_task(db, task)
