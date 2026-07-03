"""conversation_messages 模型测试。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.models import ConversationMessage, ConsultationSession, User


@pytest.mark.asyncio
async def test_conversation_message_model_exists(test_db: AsyncSession):
    """测试 ConversationMessage 模型可以正常创建。"""
    # 先创建用户和会话
    user = User(account_id="test_user_msg", password_hash="hash")
    test_db.add(user)
    await test_db.flush()

    session = ConsultationSession(user_id=user.id, status="INIT")
    test_db.add(session)
    await test_db.flush()

    message = ConversationMessage(
        session_id=session.id,
        sequence=0,
        role="user",
        content_json='{"content": "test"}',
        status="completed",
    )
    test_db.add(message)
    await test_db.flush()

    assert message.id is not None
    assert message.created_at is not None


@pytest.mark.asyncio
async def test_session_version_field(test_db: AsyncSession):
    """测试 ConsultationSession 的 version 字段。"""
    user = User(account_id="test_user_ver", password_hash="hash")
    test_db.add(user)
    await test_db.flush()

    session = ConsultationSession(
        user_id=user.id,
        status="INIT",
        version=1,
    )
    test_db.add(session)
    await test_db.flush()

    assert session.version == 1
    assert session.active_run_id is None


@pytest.mark.asyncio
async def test_conversation_message_sequence_ordering(test_db: AsyncSession):
    """测试 conversation_messages 的 sequence 序号。"""
    # 先创建用户和会话
    user = User(account_id="test_user_seq", password_hash="hash")
    test_db.add(user)
    await test_db.flush()

    session = ConsultationSession(user_id=user.id, status="INIT")
    test_db.add(session)
    await test_db.flush()

    # 创建多个消息，验证 sequence 序号
    for i in range(3):
        msg = ConversationMessage(
            session_id=session.id,
            sequence=i,
            role="user" if i % 2 == 0 else "assistant",
            content_json=f'{{"content": "message {i}"}}',
        )
        test_db.add(msg)
    await test_db.flush()

    # 查询验证
    result = await test_db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session.id)
        .order_by(ConversationMessage.sequence)
    )
    messages = result.scalars().all()
    assert len(messages) == 3
    assert [m.sequence for m in messages] == [0, 1, 2]
