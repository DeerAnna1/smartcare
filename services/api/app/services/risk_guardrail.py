"""Risk guardrail and handoff heuristics."""

from __future__ import annotations

import re


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
    lowered = text or ""
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


def emergency_reply() -> str:
    return (
        "检测到高风险健康信号。为了安全起见，我已暂停常规问诊并发起人工接管。"
        "请立即联系急救或尽快前往线下急诊。"
    )
