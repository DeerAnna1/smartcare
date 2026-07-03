import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import ConsultationSession, ConversationMessage, User
from app.orchestrators.agents import select_next_agent
from app.orchestrators.consultation import OutputLimitExceeded, run_consultation_turn_stream
from app.services.clinical_memory import update_clinical_memory
from app.services.context_manager import count_message_tokens, estimate_tokens, trim_messages_to_budget


def test_first_completed_turn_count_routes_to_triage():
    assert select_next_agent(0, "INIT", False, {}) == "triage"


def test_chinese_token_estimate_is_conservative():
    assert estimate_tokens("胸痛呼吸困难") >= 6


def test_oversized_latest_message_is_clipped_to_budget():
    messages = [HumanMessage(content="症状" * 5000)]
    trimmed = trim_messages_to_budget(messages, token_budget=300, recent_turns=6)
    assert len(trimmed) == 1
    assert trimmed[0].content.startswith("[较长输入已按 token 预算截断]")
    assert count_message_tokens(trimmed) < 700


def test_clinical_memory_preserves_source_linked_facts():
    memory = update_clinical_memory(
        {}, "我对青霉素过敏，正在服用阿司匹林，今天胸痛", "request-1"
    )
    assert memory["allergies"][0]["source_message_id"] == "request-1"
    assert memory["medications"]
    assert memory["symptoms"]


def test_client_request_id_is_unique_per_session():
    from app.core.database import Base

    engine = create_engine("sqlite:///:memory:")
    db = Session(engine)
    Base.metadata.create_all(engine)
    user = User(account_id="unique_request_user", password_hash="hash")
    db.add(user)
    db.flush()
    session = ConsultationSession(user_id=user.id)
    db.add(session)
    db.flush()
    for index in range(2):
        db.add(ConversationMessage(
            session_id=session.id,
            sequence=index,
            role="assistant",
            client_request_id="same-request",
        ))
        if index == 0:
            db.flush()
    with pytest.raises(IntegrityError):
        db.flush()
    db.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_repeated_output_limit_never_emits_completed_state(monkeypatch):
    """Four length-stopped responses must raise instead of yielding state."""
    from app.core.concurrency import init_concurrency, shutdown_concurrency

    class AlwaysTruncatedLLM:
        async def astream(self, _messages):
            yield AIMessageChunk(
                content="未完成。",
                response_metadata={"finish_reason": "length"},
            )

    async def no_rag(_messages):
        return ""

    monkeypatch.setattr("app.orchestrators.consultation.get_llm", lambda **_: AlwaysTruncatedLLM())
    monkeypatch.setattr("app.orchestrators.consultation._get_rag_context", no_rag)
    init_concurrency(max_requests=2, max_llm_calls=2, rag_pool_size=1)
    events = []
    try:
        with pytest.raises(OutputLimitExceeded):
            async for event in run_consultation_turn_stream(
                session_id="limit-test",
                messages=[{"role": "user", "content": "请总结"}],
                current_status="INIT",
                round_count=0,
            ):
                events.append(event)
    finally:
        shutdown_concurrency()
    assert not any(event_type == "state" for event_type, _ in events)


@pytest.mark.asyncio
async def test_sse_idempotent_request_replays_completed_message_without_model(
    test_client, test_db, test_user
):
    created = await test_client.post("/api/v1/consultations", headers=test_user["headers"], json={})
    session_id = created.json()["session_id"]
    existing = ConversationMessage(
        session_id=session_id,
        sequence=1,
        role="assistant",
        content_json=json.dumps({"content": "已完成的幂等回复"}, ensure_ascii=False),
        status="completed",
        client_request_id="same-client-request",
    )
    test_db.add(existing)
    await test_db.commit()

    response = await test_client.post(
        f"/api/v1/consultations/{session_id}/messages/stream",
        headers=test_user["headers"],
        json={"role": "user", "content": "不应再调用模型", "client_request_id": "same-client-request"},
    )
    assert response.status_code == 200
    assert "已完成的幂等回复" in response.text
    assert "event: done" in response.text


@pytest.mark.asyncio
async def test_sse_rejects_a_second_run_for_the_same_session(
    test_client, test_db, test_user, monkeypatch
):
    created = await test_client.post("/api/v1/consultations", headers=test_user["headers"], json={})
    session_id = created.json()["session_id"]
    session = await test_db.get(ConsultationSession, session_id)
    session.active_run_id = "already-running"
    session.active_run_heartbeat_at = datetime.now(timezone.utc)
    await test_db.commit()

    async def fake_context(**_kwargs):
        return SimpleNamespace(
            user_text="普通咨询",
            user_content="普通咨询",
            active_skills=[],
            latest_report=None,
            latest_vital=None,
        )

    async def normal_risk(*_args, **_kwargs):
        return "normal", [], {}

    monkeypatch.setattr("app.services.context_builder.build_consultation_context", fake_context)
    monkeypatch.setattr("app.api.v1.consultations.evaluate_risk_with_llm", normal_risk)
    response = await test_client.post(
        f"/api/v1/consultations/{session_id}/messages/stream",
        headers=test_user["headers"],
        json={"role": "user", "content": "普通咨询", "client_request_id": "second-run"},
    )
    assert response.status_code == 409
    assert "正在生成" in response.text


@pytest.mark.asyncio
async def test_stale_generation_lease_is_failed_and_released(monkeypatch):
    from app.main import _recover_stale_generation_runs

    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    session = ConsultationSession(
        user_id="user-1",
        active_run_id="dead-worker",
        active_run_heartbeat_at=old,
    )
    message = ConversationMessage(
        session_id="session-1",
        sequence=1,
        role="assistant",
        status="streaming",
        content_json='{"content":"partial"}',
        created_at=old,
    )

    class ScalarResult:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return iter(self.values)

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return ScalarResult([session] if self.calls == 1 else [message])

        async def commit(self):
            return None

    fake_db = FakeDB()

    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr("app.main.AsyncSessionLocal", SessionFactory())

    recovered = await _recover_stale_generation_runs()
    assert recovered >= 2
    assert session.active_run_id is None
    assert session.active_run_heartbeat_at is None
    assert message.status == "failed"
    assert "generation_lease_expired" in message.content_json
