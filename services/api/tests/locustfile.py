"""Locust 压力测试：模拟 100+ 并发用户问诊流程。

用法:
    locust -f tests/locustfile.py --host http://localhost:8001
    # Web UI: http://localhost:8089

    # 无头模式 (CI/CD):
    locust -f tests/locustfile.py --host http://localhost:8001 \
        --users 100 --spawn-rate 10 --run-time 2m --headless --csv=results
"""

import random
import time

from locust import HttpUser, between, task


SYMPTOMS = [
    "我最近三天头疼，特别是太阳穴两侧，伴有轻微恶心",
    "孩子发烧38.5度，咳嗽有痰，精神不太好",
    "我胃痛了两天，吃完饭后更痛，有点反酸",
    "膝盖上下楼梯疼，持续一周了，没有外伤",
    "最近总失眠，入睡困难，白天没精神",
    "皮肤起了一些红疹，很痒，主要在手臂上",
    "感冒三天了，流鼻涕打喷嚏，嗓子有点疼",
    "腰疼，久坐后加重，弯腰时更明显",
    "胸闷气短，运动后加重，休息后缓解",
    "眼睛干涩，看电脑久了模糊，有异物感",
]

FOLLOW_UP_RESPONSES = [
    "大概两三天了",
    "疼痛程度中等吧，能忍受但影响生活",
    "没有其他特别的症状",
    "之前没有类似的情况",
    "没有过敏史和慢性病",
]


class ConsultationUser(HttpUser):
    """模拟完整问诊流程的用户。"""

    wait_time = between(2, 8)

    def on_start(self):
        """每个虚拟用户启动时：注册 → 获取 token。"""
        self.token = None
        self.session_id = None
        username = f"locust_{random.randint(10000, 99999)}_{int(time.time() * 1000)}"
        password = "test_password_123"

        resp = self.client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": password},
        )
        if resp.status_code == 201:
            self.token = resp.json().get("token")

        if not self.token:
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            if resp.status_code == 200:
                self.token = resp.json().get("token")

    def _headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ── Tasks ────────────────────────────────────────────────────────────

    @task(3)
    def full_consultation(self):
        """完整多轮问诊：创建会话 → 发送 2-4 条消息。"""
        if not self.token:
            return

        resp = self.client.post(
            "/api/v1/consultations",
            json={},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            return
        session_id = resp.json().get("session_id")
        if not session_id:
            return

        # 主诉
        self._send_message(random.choice(SYMPTOMS), session_id)

        # 追问 1-3 轮
        for _ in range(random.randint(1, 3)):
            self._send_message(random.choice(FOLLOW_UP_RESPONSES), session_id)

    @task(1)
    def single_turn(self):
        """单轮快速问诊。"""
        if not self.token:
            return

        resp = self.client.post(
            "/api/v1/consultations",
            json={},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            return
        session_id = resp.json().get("session_id")
        if not session_id:
            return

        self._send_message(random.choice(SYMPTOMS), session_id)

    @task(1)
    def list_sessions(self):
        """查看历史会话列表。"""
        if not self.token:
            return
        self.client.get("/api/v1/consultations", headers=self._headers())

    # ── Helpers ──────────────────────────────────────────────────────────

    def _send_message(self, content: str, session_id: str):
        self.client.post(
            f"/api/v1/consultations/{session_id}/messages",
            json={"content": content},
            headers=self._headers(),
            timeout=60,
        )
