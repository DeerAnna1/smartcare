"""Proactive event trigger engine."""

from __future__ import annotations


def build_intervention_message(condition_value: str, weather: dict) -> str:
    city = weather.get("city", "")
    low = weather.get("tomorrow_min_temp")
    if condition_value == "高血压":
        return (
            f"检测到 {city} 明日最低温约 {low}°C，且您有高血压史。"
            "请注意保暖、规律监测血压，如出现不适及时就医。"
        )
    return f"检测到 {city} 天气变化，请根据既往病史注意防护。"
