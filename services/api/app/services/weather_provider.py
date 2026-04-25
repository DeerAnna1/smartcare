"""Weather provider for proactive interventions."""

from __future__ import annotations

import httpx

CITY_COORDS = {
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "guangzhou": (23.1291, 113.2644),
    "shenzhen": (22.5431, 114.0579),
}


async def fetch_weather_alert(weather_api_base: str, city: str) -> dict:
    lat, lon = CITY_COORDS.get(city.lower(), CITY_COORDS["beijing"])
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_min",
        "forecast_days": 2,
        "timezone": "Asia/Shanghai",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(weather_api_base, params=params)
        response.raise_for_status()
        data = response.json()
    mins = data.get("daily", {}).get("temperature_2m_min", [])
    low = mins[1] if len(mins) > 1 else (mins[0] if mins else None)
    cold_wave = isinstance(low, (int, float)) and low <= 8
    return {"city": city, "tomorrow_min_temp": low, "cold_wave": cold_wave}
