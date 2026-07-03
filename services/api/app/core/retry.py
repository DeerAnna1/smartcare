"""LLM / 外部 HTTP 调用的 tenacity 重试装饰器。

设计原则：
  1. 只重试可能由瞬时故障引起的异常（网络/5xx/超时/RateLimit），不重试客户端错误（4xx）
  2. 指数回退 + 抖动，避免雪崩
  3. 总耗时通过外层 asyncio.wait_for 兜底，而不是把 stop_after_attempt 设到天花板
"""
from __future__ import annotations

import logging
from typing import Callable

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmptyLLMResponseError(RuntimeError):
    """The upstream request succeeded but produced neither text nor tool calls."""


_RETRYABLE_HTTPX = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


def _should_retry_exception(exc: BaseException) -> bool:
    if isinstance(exc, EmptyLLMResponseError):
        return True
    if isinstance(exc, _RETRYABLE_HTTPX):
        return True
    # httpx 5xx -> 重试；4xx 不重试
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    # OpenAI / LangChain 包装的异常类名匹配
    name = exc.__class__.__name__
    # 4xx 客户端错误不重试（AuthenticationError, BadRequestError 等）
    if name in {"AuthenticationError", "BadRequestError", "PermissionDeniedError", "NotFoundError"}:
        return False
    if name in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "APIStatusError",
        "APIError",
    }:
        return True
    return False


def llm_retry(max_attempts: int | None = None) -> AsyncRetrying:
    """LLM 调用专用：默认重试 LLM_MAX_RETRIES+1 次（首次 + 重试次数）。"""
    settings = get_settings()
    attempts = (max_attempts or settings.LLM_MAX_RETRIES) + 1
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=0.5, max=8, jitter=1.0),
        retry=retry_if_exception(_should_retry_exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def http_retry(max_attempts: int = 3) -> AsyncRetrying:
    """通用外部 HTTP 调用重试。"""
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=0.3, max=4, jitter=0.5),
        retry=retry_if_exception(_should_retry_exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


async def with_llm_retry(coro_factory: Callable, *args, **kwargs):
    """包装 LLM 协程：每次重试都重新创建协程对象。"""
    async for attempt in llm_retry():
        with attempt:
            return await coro_factory(*args, **kwargs)
