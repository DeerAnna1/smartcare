"""Send a signed IoT webhook request for local testing."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request


def sign(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    base = f"{timestamp}.{nonce}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


def main():
    url = "http://localhost:8001/api/v1/iot/webhook"
    # 替换为你的真实 user_id
    payload = {
        "source": "xiaomi-health",
        "user_id": "replace-with-user-id",
        "metric": "heart_rate",
        "value": 126,
        "unit": "bpm",
        "measured_at": "2026-04-22T11:00:00Z",
        "event_id": f"evt-{int(time.time())}",
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    nonce = f"n{ts}"
    secret = "replace-with-IOT_WEBHOOK_HMAC_SECRET"
    signature = sign(secret, ts, nonce, body)

    req = urllib.request.Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-iot-timestamp": ts,
            "x-iot-nonce": nonce,
            "x-iot-signature": signature,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
