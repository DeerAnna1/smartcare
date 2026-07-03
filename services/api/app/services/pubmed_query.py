"""Build fielded PubMed queries from arbitrary Chinese or English topics."""

from __future__ import annotations

import re

import httpx


PUBMED_FIELD_RE = re.compile(
    r"\[(?:Title|Title/Abstract|MeSH Terms|All Fields|Publication Type)\]",
    re.IGNORECASE,
)


async def _translate_zh_to_en(topic: str) -> str:
    """Translate only the query terms; literature data still comes exclusively from MCP."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
        response = await client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "zh-CN", "tl": "en", "dt": "t", "q": topic},
        )
        response.raise_for_status()
        payload = response.json()
    segments = payload[0] if isinstance(payload, list) and payload else []
    translated = "".join(
        str(segment[0]) for segment in segments
        if isinstance(segment, list) and segment and segment[0]
    ).strip()
    if not translated or re.search(r"[\u3400-\u9fff]", translated):
        raise ValueError("中文医学主题实时翻译失败")
    return translated


async def translate_en_to_zh(text: str) -> str:
    """Translate an abstract-derived explanation without adding medical claims."""
    if not text.strip():
        return ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
        response = await client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:3500]},
        )
        response.raise_for_status()
        payload = response.json()
    segments = payload[0] if isinstance(payload, list) and payload else []
    return "".join(
        str(segment[0]) for segment in segments
        if isinstance(segment, list) and segment and segment[0]
    ).strip()


def extract_abstract_explanation(abstract: str, max_chars: int = 1400) -> str:
    """Select informative abstract sentences; never create facts absent from the abstract."""
    cleaned = re.sub(r"\s+", " ", abstract or "").strip()
    if not cleaned:
        return ""
    sections = re.split(
        r"(?=\b(?:BACKGROUND|OBJECTIVE|AIM|METHODS|RESULTS|CONCLUSIONS?)\s*:\s*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    selected: list[str] = []
    if len(sections) > 1:
        for section in sections:
            section = section.strip()
            if not section:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", section)
            selected.append(" ".join(sentences[:2]))
    else:
        selected = re.split(r"(?<=[.!?])\s+", cleaned)[:5]
    explanation = " ".join(selected).strip()
    return explanation[:max_chars].rstrip()


def _field_english_terms(topic: str) -> str:
    stop_words = {
        "and", "or", "the", "a", "an", "of", "in", "on", "for", "with", "to",
        "related", "medical", "research", "study", "studies", "paper", "papers",
    }
    terms = [
        token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9-]*", topic)
        if token.lower() not in stop_words and len(token) > 1
    ]
    terms = list(dict.fromkeys(terms))[:12]
    if not terms:
        raise ValueError("检索主题中没有有效英文关键词")
    return " AND ".join(f"{term}[Title/Abstract]" for term in terms)


async def build_pubmed_query(topic: str) -> str:
    """Return a strict fielded query; fail instead of passing ambiguous natural language."""
    topic = topic.strip()
    if not topic or "[用户长期记忆]" in topic or "[最近检验摘要]" in topic or "[最近穿戴设备数据]" in topic:
        raise ValueError("检索主题为空或包含非用户查询上下文")
    if PUBMED_FIELD_RE.search(topic):
        return topic
    if re.search(r"[\u3400-\u9fff]", topic):
        topic = await _translate_zh_to_en(topic)
    return _field_english_terms(topic)
