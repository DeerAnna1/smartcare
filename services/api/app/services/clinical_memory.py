"""Conservative, source-linked clinical memory for context-window compaction."""
from __future__ import annotations

import re
from typing import Any


_PATTERNS = {
    "allergies": (r"(?:过敏|对.{1,20}过敏|无过敏史)",),
    "medications": (r"(?:正在吃|正在服用|用药|药物)[^\n，。；]{0,80}",),
    "history": (r"(?:既往史|有.{1,30}病史|曾患)[^\n，。；]{0,80}",),
    "pregnancy": (r"(?:怀孕|孕期|备孕|哺乳期|未怀孕)",),
    "symptoms": (r"(?:疼|痛|发烧|头晕|恶心|呼吸困难|胸闷|胸痛)[^\n，。；]{0,80}",),
}


def update_clinical_memory(memory: dict[str, Any] | None, user_text: str, message_id: str | None = None) -> dict:
    result = dict(memory or {})
    for category in _PATTERNS:
        result.setdefault(category, [])
    for category, patterns in _PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, user_text, re.IGNORECASE):
                fact = match.group(0).strip()
                if not fact:
                    continue
                if not any(item.get("text") == fact for item in result[category]):
                    result[category].append({"text": fact[:200], "source_message_id": message_id})
        result[category] = result[category][-20:]
    return result


def merge_summary(memory: dict[str, Any] | None, summary: dict[str, Any] | None) -> dict:
    result = dict(memory or {})
    if summary:
        result["latest_summary"] = summary
    return result
