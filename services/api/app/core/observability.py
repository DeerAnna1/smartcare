"""
Langfuse observability integration (v4 SDK).

Uses langfuse.observe decorator for automatic tracing of LLM calls,
tool executions, and agent transitions via OpenTelemetry.
"""

from __future__ import annotations

import os
import logging
from typing import Callable

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_langfuse_enabled: bool = False


def init_langfuse() -> None:
    """Initialize Langfuse by setting env vars for the observe decorator."""
    global _langfuse_enabled

    settings = get_settings()
    if not settings.LANGFUSE_ENABLED or not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.info("Langfuse disabled (missing configuration)")
        _langfuse_enabled = False
        return

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
    os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
    os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

    _langfuse_enabled = True
    logger.info(f"Langfuse initialized (host={settings.LANGFUSE_HOST})")


def flush_langfuse() -> None:
    """Flush pending Langfuse events."""
    if not _langfuse_enabled:
        return
    try:
        from langfuse import Langfuse
        client = Langfuse()
        client.flush()
    except Exception as e:
        logger.warning(f"Langfuse flush failed: {e}")


def observe_agent(agent_name: str) -> Callable:
    """Decorator to observe agent node executions with Langfuse.

    Always applies langfuse.observe — it reads env vars at call time,
    so it works even if init_langfuse() hasn't run yet at decoration time.
    """
    try:
        from langfuse import observe
        return observe(name=agent_name, as_type="agent", capture_input=False, capture_output=True)
    except Exception as e:
        logger.warning(f"Failed to create observe decorator: {e}")
        def _noop(func: Callable) -> Callable:
            return func
        return _noop


def observe_llm(func: Callable) -> Callable:
    """Decorator to observe LLM calls with Langfuse."""
    try:
        from langfuse import observe
        return observe(name=func.__name__, as_type="generation", capture_input=False, capture_output=False)
    except Exception:
        return func


def observe_tool(func: Callable) -> Callable:
    """Decorator to observe tool executions with Langfuse."""
    try:
        from langfuse import observe
        return observe(name=func.__name__, as_type="tool", capture_input=False, capture_output=True)
    except Exception:
        return func
