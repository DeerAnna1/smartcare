"""定时科普任务执行器。"""

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _scheduler_timezone() -> ZoneInfo:
    timezone_name = get_settings().SCHEDULER_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.error("未知的定时任务时区 %s，已回退到 UTC", timezone_name)
        return ZoneInfo("UTC")


def calculate_next_run(cron_expression: str, base_time: datetime | None = None) -> datetime:
    """按业务时区解释 Cron，并返回 UTC 的下一次执行时间。"""
    business_tz = _scheduler_timezone()
    base = base_time or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    local_base = base.astimezone(business_tz)
    next_local = croniter(cron_expression, local_base).get_next(datetime)
    return next_local.astimezone(timezone.utc)


async def execute_scheduled_task(db, task, now: datetime | None = None) -> dict[str, object]:
    """执行单个任务，写入日志并推进下次执行时间。"""
    from app.api.v1.scheduled_tasks import ScheduledTaskLog
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    executed_at = now or datetime.now(timezone.utc)
    generation_timeout = float(settings.LLM_REQUEST_TIMEOUT)

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            temperature=0.7,
            max_tokens=700,
            timeout=generation_timeout,
            max_retries=1,
        )
        topic = task.topic or task.title or "健康科普"
        template_hint = f"\n内容模板：{task.content_template}" if task.content_template else ""
        prompt = (
            "你是一位专业的健康科普作者。请生成一段科学、易懂、可执行的健康科普内容。\n"
            f"主题：{topic}\n标题：{task.title or topic}{template_hint}\n"
            "要求：200-400 字；包含实用建议；说明仅供健康参考；使用 Markdown；直接输出正文。"
        )
        response = await asyncio.wait_for(
            llm.ainvoke(prompt),
            timeout=generation_timeout + 5,
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        if not content.strip():
            raise ValueError("AI 服务返回空内容")

        db.add(
            ScheduledTaskLog(
                task_id=task.id,
                user_id=task.user_id,
                content=content,
                status="success",
                executed_at=executed_at,
            )
        )
        task.last_run_at = executed_at
        task.next_run_at = calculate_next_run(task.schedule_cron, executed_at) if task.schedule_cron else None
        await db.flush()
        logger.info("[SCHEDULER] 任务 %s 执行成功: %s", task.id, task.title)
        return {"status": "success", "content": content}
    except Exception as exc:
        error_message = str(exc).strip()[:500] or type(exc).__name__
        db.add(
            ScheduledTaskLog(
                task_id=task.id,
                user_id=task.user_id,
                content="",
                status="failed",
                error_message=error_message,
                executed_at=executed_at,
            )
        )
        task.last_run_at = executed_at
        if task.schedule_cron:
            try:
                task.next_run_at = calculate_next_run(task.schedule_cron, executed_at)
            except Exception:
                task.next_run_at = None
        await db.flush()
        logger.error("[SCHEDULER] 任务 %s AI 生成失败: %s", task.id, error_message)
        return {"status": "failed", "error": error_message}


async def run_due_tasks() -> int:
    """扫描并执行所有已到期的 active 任务。"""
    from app.api.v1.scheduled_tasks import ScheduledTask

    now = datetime.now(timezone.utc)
    executed_count = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledTask).where(
                ScheduledTask.status == "active",
                ScheduledTask.schedule_cron.isnot(None),
                ScheduledTask.schedule_cron != "",
            )
        )
        for task in result.scalars().all():
            if task.next_run_at is None:
                try:
                    task.next_run_at = calculate_next_run(task.schedule_cron, now)
                except Exception:
                    logger.exception("[SCHEDULER] 任务 %s 的 Cron 无效", task.id)
            elif task.next_run_at <= now:
                await execute_scheduled_task(db, task, now)
                executed_count += 1
        await db.commit()

    if executed_count:
        logger.info("[SCHEDULER] 本轮执行了 %s 个定时任务", executed_count)
    return executed_count


async def scheduled_task_loop() -> None:
    """持续扫描到期任务。"""
    poll_seconds = max(5, get_settings().SCHEDULED_TASK_POLL_SECONDS)
    while True:
        try:
            await run_due_tasks()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[SCHEDULER] 定时任务循环异常")
        await asyncio.sleep(poll_seconds)
