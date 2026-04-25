"""Lab report parsing and interpretation utilities."""

from __future__ import annotations

import re
from typing import Any


_LINE_PATTERNS = [
    re.compile(
        r"(?P<name>[\u4e00-\u9fa5A-Za-z0-9\-\(\)]+)\s*[:：]?\s*"
        r"(?P<value>-?\d+(?:\.\d+)?)\s*"
        r"(?P<unit>[A-Za-z/%\u00b5\u03bc\u4e00-\u9fa5]*)\s*"
        r"(?P<range>\d+(?:\.\d+)?\s*[-~]\s*\d+(?:\.\d+)?)?"
    ),
]

_KNOWN_METRICS = {
    "白细胞",
    "红细胞",
    "血红蛋白",
    "血小板",
    "中性粒细胞百分比",
    "淋巴细胞百分比",
    "谷丙转氨酶",
    "谷草转氨酶",
    "肌酐",
    "尿素",
    "C反应蛋白",
    "总胆红素",
    "白蛋白",
    "空腹血糖",
    "钾",
    "钠",
    "氯",
    "钙",
    "eGFR",
}


def _parse_range(raw: str) -> tuple[float, float] | None:
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*[-~]\s*(-?\d+(?:\.\d+)?)", raw or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _is_abnormal(value: str, range_text: str) -> bool:
    parsed = _parse_range(range_text)
    if not parsed:
        return False
    low, high = parsed
    try:
        numeric = float(value)
    except ValueError:
        return False
    return numeric < low or numeric > high


def parse_lab_text(raw_text: str) -> list[dict[str, Any]]:
    # 优先按常见化验单表格格式解析
    table_items = _parse_from_table_lines(raw_text)
    if table_items:
        return table_items

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        for pattern in _LINE_PATTERNS:
            m = pattern.search(clean)
            if not m:
                continue
            name = m.group("name")
            key = f"{name}:{m.group('value')}"
            if key in seen:
                continue
            seen.add(key)
            ref = (m.group("range") or "").strip()
            abnormal = _is_abnormal(m.group("value"), ref)
            items.append(
                {
                    "name": name,
                    "value": m.group("value"),
                    "unit": (m.group("unit") or "").strip(),
                    "reference_range": ref,
                    "abnormal": abnormal,
                    "interpretation": "超出参考范围" if abnormal else "在参考范围内",
                }
            )
            break
    return items


def _parse_from_table_lines(raw_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # OCR.space 常见输出：每行一个项目，用 Tab 分隔四列
    for row in raw_text.splitlines():
        row = row.strip()
        if not row or "结果提示" in row or "补充说明" in row:
            continue
        parts = [x.strip() for x in row.split("\t") if x.strip()]
        if len(parts) < 3:
            continue
        name = parts[0]
        if name not in _KNOWN_METRICS:
            continue
        value = parts[1] if len(parts) > 1 else ""
        ref = parts[2] if len(parts) > 2 else ""
        unit = parts[3] if len(parts) > 3 else ""
        abnormal = _is_abnormal(value, ref)
        items.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "reference_range": ref,
                "abnormal": abnormal,
                "interpretation": "超出参考范围" if abnormal else "在参考范围内",
            }
        )

    if items:
        return items

    # 兼容另一类 OCR 输出：按 4 行分组（项目/结果/参考范围/单位）
    lines = [x.strip() for x in raw_text.splitlines() if x.strip()]
    header = ["检验项目", "结果", "参考范围", "单位"]
    try:
        start = lines.index(header[0])
        if lines[start : start + 4] != header:
            return []
    except ValueError:
        return []
    cursor = start + 4
    while cursor + 3 < len(lines):
        name = lines[cursor]
        value = lines[cursor + 1]
        ref = lines[cursor + 2]
        unit = lines[cursor + 3]
        if "结果提示" in name or "补充说明" in name:
            break
        if name in _KNOWN_METRICS:
            abnormal = _is_abnormal(value, ref)
            items.append(
                {
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "reference_range": ref,
                    "abnormal": abnormal,
                    "interpretation": "超出参考范围" if abnormal else "在参考范围内",
                }
            )
        cursor += 4
    return items


def summarize_lab_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "未识别到可结构化的检验指标。"
    abnormal = [x for x in items if x.get("abnormal")]
    if abnormal:
        names = "、".join(x["name"] for x in abnormal[:5])
        return f"共识别 {len(items)} 项指标，其中 {len(abnormal)} 项异常：{names}。"
    return f"共识别 {len(items)} 项指标，均在参考范围内或未提供参考区间。"
