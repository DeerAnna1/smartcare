from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.v1.scheduled_tasks import parse_natural_schedule
from app.jobs import scheduled_task_runner
from app.services import feishu_notifier


def test_parse_daily_scheduled_education():
    parsed = parse_natural_schedule("每天早上9点推送高血压科普")

    assert parsed["cron"] == "0 9 * * *"
    assert parsed["topic"] == "高血压"
    assert "每天" in parsed["description"]


def test_next_run_uses_business_timezone(monkeypatch):
    monkeypatch.setattr(
        scheduled_task_runner,
        "get_settings",
        lambda: SimpleNamespace(SCHEDULER_TIMEZONE="Asia/Shanghai"),
    )
    base_time = datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc)

    next_run = scheduled_task_runner.calculate_next_run("0 9 * * *", base_time)

    assert next_run == datetime(2026, 6, 29, 1, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://open.feishu.cn/open-apis/bot/v2/hook/abcdefghijk", True),
        ("https://open.larksuite.com/open-apis/bot/v2/hook/abcdefghijk", True),
        ("http://open.feishu.cn/open-apis/bot/v2/hook/abcdefghijk", False),
        ("https://example.com/open-apis/bot/v2/hook/abcdefghijk", False),
        ("https://open.feishu.cn/open-apis/bot/hook/abcdefghijk", False),
    ],
)
def test_validate_feishu_webhook_url(url, expected):
    assert feishu_notifier.validate_feishu_webhook_url(url) is expected


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


class _FakeAsyncClient:
    def __init__(self, response_body, captured, **_kwargs):
        self.response_body = response_body
        self.captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, json):
        self.captured["url"] = url
        self.captured["payload"] = json
        return _FakeResponse(self.response_body)


@pytest.mark.asyncio
async def test_send_feishu_alert_adds_signature(monkeypatch):
    captured = {}
    monkeypatch.setattr(feishu_notifier.time, "time", lambda: 1700000000)
    monkeypatch.setattr(
        feishu_notifier.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient({"code": 0, "msg": "success"}, captured, **kwargs),
    )

    result = await feishu_notifier.send_feishu_alert(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/abcdefghijk",
        webhook_secret="test-secret",
        patient_name="测试用户",
        risk_level="high",
        reason="配置测试",
        evidence=["测试证据"],
        session_id="test-session",
    )

    assert result["success"] is True
    assert captured["payload"]["timestamp"] == "1700000000"
    assert captured["payload"]["sign"] == feishu_notifier._generate_signature("1700000000", "test-secret")
    assert captured["payload"]["msg_type"] == "interactive"


@pytest.mark.asyncio
async def test_send_feishu_alert_detects_business_error(monkeypatch):
    monkeypatch.setattr(
        feishu_notifier.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient({"code": 19021, "msg": "sign match fail"}, {}, **kwargs),
    )

    result = await feishu_notifier.send_feishu_alert(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/abcdefghijk",
        patient_name="测试用户",
        risk_level="high",
        reason="配置测试",
        evidence=[],
        session_id="test-session",
    )

    assert result["success"] is False
    assert "19021" in str(result["error"])
