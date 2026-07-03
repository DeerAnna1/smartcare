import pytest

from app.core.retry import EmptyLLMResponseError, llm_retry


@pytest.mark.asyncio
async def test_empty_llm_response_is_retried(monkeypatch):
    monkeypatch.setattr("app.core.retry.get_settings", lambda: type(
        "Settings", (), {"LLM_MAX_RETRIES": 2}
    )())
    attempts = 0

    async for attempt in llm_retry():
        with attempt:
            attempts += 1
            if attempts < 3:
                raise EmptyLLMResponseError("empty upstream response")

    assert attempts == 3


@pytest.mark.asyncio
async def test_non_retryable_stream_error_fails_once(monkeypatch):
    monkeypatch.setattr("app.core.retry.get_settings", lambda: type(
        "Settings", (), {"LLM_MAX_RETRIES": 2}
    )())
    attempts = 0

    with pytest.raises(RuntimeError, match="stream interrupted"):
        async for attempt in llm_retry():
            with attempt:
                attempts += 1
                raise RuntimeError("stream interrupted")

    assert attempts == 1
