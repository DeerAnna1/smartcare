"""Risk guardrail and handoff heuristics."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

DOCUMENT_CONTEXT_RE = re.compile(
    r"\n?\[文档上下文(?::[^\]]*)?\][\s\S]*?\[/文档上下文\]",
    re.IGNORECASE,
)
ATTACHMENT_MARKER_RE = re.compile(r"\n?\[已查看附件:\s*[^\]]+\]", re.IGNORECASE)


def strip_document_context(text: str) -> str:
    """Remove uploaded document material from text used by symptom-risk screening.

    The document remains in the model message as medical context, but statements in
    a historical EHR must not be treated as symptoms currently asserted by the user.
    """
    cleaned = DOCUMENT_CONTEXT_RE.sub("", text or "")
    return ATTACHMENT_MARKER_RE.sub("", cleaned).strip()


def _risk_messages(messages: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for message in messages:
        copied = dict(message)
        content = copied.get("content", "")
        if copied.get("role") == "user":
            if isinstance(content, list):
                copied["content"] = [
                    {**part, "text": strip_document_context(part.get("text", ""))}
                    if isinstance(part, dict) and part.get("type") == "text"
                    else part
                    for part in content
                ]
            else:
                copied["content"] = strip_document_context(str(content))
        sanitized.append(copied)
    return sanitized

HIGH_RISK_PATTERNS = [
    r"自杀",
    r"轻生",
    r"不想活",
    r"胸痛",
    r"呼吸困难",
    r"意识不清",
    r"大出血",
]

MEDIUM_RISK_PATTERNS = [
    r"高烧",
    r"剧烈头痛",
    r"心悸",
    r"抑郁",
]


def evaluate_risk(text: str) -> tuple[str, list[str]]:
    lowered = strip_document_context(text)
    evidence: list[str] = []
    for pattern in HIGH_RISK_PATTERNS:
        if re.search(pattern, lowered):
            evidence.append(pattern)
    if evidence:
        return "high", evidence

    for pattern in MEDIUM_RISK_PATTERNS:
        if re.search(pattern, lowered):
            evidence.append(pattern)
    if evidence:
        return "medium", evidence
    return "normal", evidence


async def evaluate_risk_with_llm(
    messages: list[dict],
    user_llm_config: dict | None = None,
) -> tuple[str, list[str], dict]:
    """多因子语义风险评分（正则前置 + 加权评分系统）。

    流程：
    1. 正则命中 high → 直接返回 high（不调用评分器）
    2. 正则未命中 high → 调用多因子评分系统
    3. 评分 score >= 7 → high，4-6 → elevated，否则 normal

    Returns:
        (risk_level, evidence, score_detail)
    """
    messages = _risk_messages(messages)

    # 正则前置检查
    latest_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = " ".join(text_parts)
            latest_user_text = content or ""
            break

    regex_level, regex_evidence = evaluate_risk(latest_user_text)
    if regex_level == "high":
        return "high", regex_evidence, {"score": 10, "level": "high", "reason": "正则命中高危关键词", "evidence": regex_evidence}

    # 多因子语义评分
    from app.services.risk_scorer import score_risk
    score_detail = score_risk(messages)
    llm_score = score_detail.get("score", 0)
    llm_evidence = score_detail.get("evidence", [])

    if llm_score >= 7:
        combined_evidence = list(set(regex_evidence + llm_evidence))
        return "high", combined_evidence, score_detail
    elif llm_score >= 4:
        combined_evidence = list(set(regex_evidence + llm_evidence))
        return "elevated", combined_evidence, score_detail
    else:
        if regex_evidence:
            return "medium", regex_evidence, score_detail
        return "normal", [], score_detail


def emergency_reply() -> str:
    return (
        "检测到高风险健康信号。为了安全起见，我已暂停常规问诊并发起人工接管。"
        "请立即联系急救或尽快前往线下急诊。"
    )
