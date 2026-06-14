"""并发控制：信号量 + 有界线程池。

每 Gunicorn worker 进程初始化一次，控制：
- 请求级并发（asyncio.Semaphore）
- LLM 调用并发（asyncio.Semaphore）
- RAG ChromaDB 线程池（ThreadPoolExecutor）
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_request_semaphore: asyncio.Semaphore | None = None
_llm_semaphore: asyncio.Semaphore | None = None
_rag_executor: ThreadPoolExecutor | None = None


def init_concurrency(
    max_requests: int,
    max_llm_calls: int,
    rag_pool_size: int,
) -> None:
    """Initialize per-process concurrency primitives. Call once during app lifespan."""
    global _request_semaphore, _llm_semaphore, _rag_executor
    _request_semaphore = asyncio.Semaphore(max_requests)
    _llm_semaphore = asyncio.Semaphore(max_llm_calls)
    _rag_executor = ThreadPoolExecutor(max_workers=rag_pool_size, thread_name_prefix="rag")
    logger.info(
        "并发控制初始化: max_requests=%d, max_llm_calls=%d, rag_pool_size=%d",
        max_requests, max_llm_calls, rag_pool_size,
    )


def get_request_semaphore() -> asyncio.Semaphore:
    assert _request_semaphore is not None, "init_concurrency() not called"
    return _request_semaphore


def get_llm_semaphore() -> asyncio.Semaphore:
    assert _llm_semaphore is not None, "init_concurrency() not called"
    return _llm_semaphore


def get_rag_executor() -> ThreadPoolExecutor:
    assert _rag_executor is not None, "init_concurrency() not called"
    return _rag_executor


def shutdown_concurrency() -> None:
    """Clean shutdown of thread pool."""
    if _rag_executor is not None:
        _rag_executor.shutdown(wait=False)
        logger.info("RAG 线程池已关闭")
