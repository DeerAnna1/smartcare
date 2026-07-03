"""飞书自定义机器人 Webhook 通知服务。"""

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeishuConfig:
    enabled: bool
    webhook_url: str
    webhook_secret: str = ""


def validate_feishu_webhook_url(webhook_url: str) -> bool:
    """只允许飞书/Lark 官方自定义机器人 Webhook，避免服务端请求伪造。"""
    parsed = urlparse(webhook_url.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"open.feishu.cn", "open.larksuite.com"}
        and parsed.path.startswith("/open-apis/bot/v2/hook/")
        and len(parsed.path.removeprefix("/open-apis/bot/v2/hook/")) > 8
    )


def resolve_feishu_config(user) -> FeishuConfig:
    """用户配置优先；未配置用户项时回退环境变量。"""
    try:
        preferences = json.loads(user.preferences or "{}")
        config = preferences.get("feishu_config")
        if isinstance(config, dict):
            return FeishuConfig(
                enabled=bool(config.get("enabled", False)),
                webhook_url=str(config.get("webhook_url", "")).strip(),
                webhook_secret=str(config.get("webhook_secret", "")).strip(),
            )
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    settings = get_settings()
    return FeishuConfig(
        enabled=settings.FEISHU_ALERT_ENABLED,
        webhook_url=settings.FEISHU_WEBHOOK_URL.strip(),
        webhook_secret=settings.FEISHU_WEBHOOK_SECRET.strip(),
    )


def get_patient_display_name(user) -> str:
    try:
        profile = json.loads(user.profile or "{}")
        display_name = str(profile.get("name", "")).strip()
        if display_name:
            return display_name
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return str(getattr(user, "account_id", "未知用户"))


def _generate_signature(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


async def send_feishu_alert(
    webhook_url: str,
    patient_name: str,
    risk_level: str,
    reason: str,
    evidence: list[str],
    session_id: str,
    session_link: str = "",
    webhook_secret: str = "",
) -> dict[str, bool | str]:
    """发送高风险告警卡片，并检查飞书 HTTP 与业务响应。"""
    if not validate_feishu_webhook_url(webhook_url):
        return {"success": False, "error": "Webhook URL 不是有效的飞书自定义机器人地址"}

    color = "red" if risk_level == "high" else "orange"
    evidence_text = "\n".join(f"- {str(item)[:300]}" for item in evidence[:5]) if evidence else "无"
    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "智愈高风险患者警报"},
                "template": color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**患者**：{patient_name}\n"
                            f"**风险级别**：{risk_level}\n"
                            f"**触发原因**：{reason}\n"
                            f"**关联证据**：\n{evidence_text}\n"
                            f"**会话 ID**：{session_id}"
                        ),
                    },
                },
            ],
        },
    }

    if webhook_secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _generate_signature(timestamp, webhook_secret)

    if session_link:
        payload["card"]["elements"].append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看详情"},
                        "url": session_link,
                        "type": "primary",
                    }
                ],
            }
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            result = response.json()
        if result.get("code", 0) != 0:
            raise RuntimeError(f"飞书返回错误 code={result.get('code')}: {result.get('msg', 'unknown error')}")
        logger.info("飞书告警已发送: session=%s, risk=%s", session_id, risk_level)
        return {"success": True, "error": ""}
    except Exception as exc:
        error_message = str(exc)[:500]
        logger.error("飞书告警发送失败: %s", error_message)
        return {"success": False, "error": error_message}
