"""
回填脚本：将 raw_messages JSON 迁移到 conversation_messages 表。

使用方法：
    cd services/api
    python -m scripts.backfill_messages
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.models import ConsultationSession, ConversationMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill_messages():
    """将 raw_messages 回填到 conversation_messages 表。"""

    async with AsyncSessionLocal() as db:
        # 统计迁移前的消息数
        sessions_result = await db.execute(
            select(func.count()).select_from(ConsultationSession)
        )
        total_sessions = sessions_result.scalar()
        logger.info(f"总会话数: {total_sessions}")

        messages_result = await db.execute(
            select(func.count()).select_from(ConversationMessage)
        )
        existing_messages = messages_result.scalar()
        logger.info(f"已存在的消息数: {existing_messages}")

        # 获取所有会话
        sessions = await db.execute(
            select(ConsultationSession).order_by(ConsultationSession.created_at)
        )
        sessions = sessions.scalars().all()

        inserted_count = 0
        skipped_count = 0

        for session in sessions:
            if not session.raw_messages or session.raw_messages == "[]":
                continue

            try:
                messages = json.loads(session.raw_messages)
            except json.JSONDecodeError:
                logger.warning(f"会话 {session.id} 的 raw_messages JSON 解析失败")
                continue

            for idx, msg in enumerate(messages):
                # 使用 session_id + sequence 做幂等
                existing = await db.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.session_id == session.id,
                        ConversationMessage.sequence == idx,
                    )
                )
                if existing.scalar_one_or_none():
                    skipped_count += 1
                    continue

                role = msg.get("role", "user")
                content = json.dumps(msg, ensure_ascii=False)

                message = ConversationMessage(
                    session_id=session.id,
                    sequence=idx,
                    role=role,
                    content_json=content,
                    status="completed",
                )
                db.add(message)
                inserted_count += 1

            # 每 100 个会话提交一次
            if inserted_count % 100 == 0:
                await db.commit()
                logger.info(f"已插入 {inserted_count} 条消息")

        await db.commit()

        # 统计迁移后的消息数
        messages_result = await db.execute(
            select(func.count()).select_from(ConversationMessage)
        )
        final_messages = messages_result.scalar()

        logger.info(f"回填完成:")
        logger.info(f"  - 新插入: {inserted_count}")
        logger.info(f"  - 跳过（已存在）: {skipped_count}")
        logger.info(f"  - 迁移前消息数: {existing_messages}")
        logger.info(f"  - 迁移后消息数: {final_messages}")


if __name__ == "__main__":
    asyncio.run(backfill_messages())
