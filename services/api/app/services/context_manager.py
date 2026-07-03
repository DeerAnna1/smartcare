"""上下文管理器：token 裁剪 + 滑动窗口摘要 + Redis 热缓存。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Token 估算 ──────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    中文约 1.5 字/token，英文约 4 字符/token。
    用混合公式: len(text) / 2 作为保守估计。
    """
    if not text:
        return 0
    # Conservative mixed-language estimate. Chinese characters commonly occupy
    # one or more tokens; treating each as one prevents systematic undercounts.
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    other = len(text) - chinese
    return max(1, chinese + (other + 3) // 4)


def count_message_tokens(messages: list[BaseMessage]) -> int:
    """估算消息列表的总 token 数。"""
    total = 0
    for m in messages:
        # 每条消息有固定开销 (role, metadata)
        total += 4
        if hasattr(m, "content") and m.content:
            total += estimate_tokens(str(m.content))
    return total


# ─── Token 级裁剪 ────────────────────────────────────────────────────────────

def trim_messages_to_budget(
    messages: list[BaseMessage],
    token_budget: int | None = None,
    recent_turns: int | None = None,
) -> list[BaseMessage]:
    """将消息列表裁剪到 token 预算内。

    策略：
    1. 保留最近 recent_turns 轮对话（user+assistant 为一轮）
    2. 如果超出 token_budget，从最旧的消息开始移除
    3. 保证至少保留最后 1 条用户消息
    """
    if token_budget is None:
        token_budget = settings.MEMORY_TOKEN_BUDGET
    if recent_turns is None:
        recent_turns = settings.MEMORY_RECENT_TURNS

    if not messages:
        return messages

    # 按轮次保留最近的消息
    # 一轮 = 1 user + 1 assistant
    kept: list[BaseMessage] = []
    turn_count = 0
    for msg in reversed(messages):
        kept.insert(0, msg)
        if isinstance(msg, HumanMessage):
            turn_count += 1
            if turn_count >= recent_turns:
                break

    # 确保至少保留最后一条用户消息
    if kept and not any(isinstance(m, HumanMessage) for m in kept):
        # 从原始消息中找回最后一条用户消息
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                kept.insert(0, msg)
                break

    # 如果仍然超出 token budget，从最旧端裁剪
    while count_message_tokens(kept) > token_budget and len(kept) > 1:
        # 不要裁掉最后一条消息
        kept.pop(0)

    # A single user message can itself exceed the model window. Fail closed by
    # clipping text while retaining the most recent part, where the question
    # and corrections are most likely to be located.
    if kept and count_message_tokens(kept) > token_budget:
        latest = kept[-1]
        if isinstance(latest.content, str):
            max_chars = max(200, token_budget * 2)
            latest.content = "[较长输入已按 token 预算截断]\n" + latest.content[-max_chars:]
    return kept


# ─── 滑动窗口摘要 ────────────────────────────────────────────────────────────

def build_conversation_summary(
    messages: list[BaseMessage],
    max_chars: int = 1500,
) -> str:
    """从较早的消息中构建摘要文本。

    用于注入 system prompt，让模型了解之前的对话脉络。
    不截断最近的消息，只摘要历史部分。
    """
    if len(messages) <= 4:
        return ""

    # 摘要较早的消息（跳过最近 4 条）
    early_messages = messages[:-4]
    summary_parts: list[str] = []

    for msg in early_messages:
        if isinstance(msg, HumanMessage):
            content = str(msg.content)[:200]
            summary_parts.append(f"患者: {content}")
        elif isinstance(msg, AIMessage):
            content = str(msg.content)[:200]
            summary_parts.append(f"助手: {content}")

    summary = "\n".join(summary_parts)

    # 截断到 max_chars
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "..."

    return summary


# ─── Redis 热缓存 ────────────────────────────────────────────────────────────

_REDIS_CLIENT = None


async def _get_redis():
    """获取 Redis 客户端（惰性初始化）。"""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        try:
            import redis.asyncio as aioredis
            _REDIS_CLIENT = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        except Exception as e:
            logger.warning(f"Redis 连接失败: {e}")
            return None
    return _REDIS_CLIENT


async def cache_session_state(session_id: str, state: dict, ttl: int = 3600) -> bool:
    """缓存会话状态到 Redis。

    用于跨请求快速恢复 agent 上下文，避免每次从 DB 重建。
    TTL 默认 1 小时。
    """
    redis = await _get_redis()
    if redis is None:
        return False
    try:
        key = f"session:{session_id}:state"
        await redis.setex(key, ttl, json.dumps(state, ensure_ascii=False, default=str))
        return True
    except Exception as e:
        logger.warning(f"Redis 缓存写入失败: {e}")
        return False


async def get_cached_session_state(session_id: str) -> dict | None:
    """从 Redis 获取缓存的会话状态。"""
    redis = await _get_redis()
    if redis is None:
        return None
    try:
        key = f"session:{session_id}:state"
        data = await redis.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.warning(f"Redis 缓存读取失败: {e}")
        return None


async def invalidate_session_cache(session_id: str) -> bool:
    """使会话缓存失效。"""
    redis = await _get_redis()
    if redis is None:
        return False
    try:
        key = f"session:{session_id}:state"
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis 缓存删除失败: {e}")
        return False


async def close_redis():
    """关闭 Redis 连接（用于 shutdown）。"""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        try:
            await _REDIS_CLIENT.aclose()
        except Exception:
            pass
        _REDIS_CLIENT = None
