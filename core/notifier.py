"""异常告警通知模块.

支持 webhook、钉钉、飞书及本地系统通知,
带有按 (task_id, alert_type) 的 5 分钟冷却机制.
"""

import os
import time
import asyncio
from typing import Optional, Dict, Tuple

import httpx


class Notifier:
    """通用告警通知器."""

    def __init__(self) -> None:
        self.webhook_url: Optional[str] = os.getenv("NOTIFIER_WEBHOOK_URL")
        self.notifier_type: str = os.getenv("NOTIFIER_TYPE", "webhook").lower()
        self._last_alert: Dict[Tuple[str, str], float] = {}
        self._default_task_id: Optional[str] = None
        self._default_dashboard_url: Optional[str] = None

    def set_task_context(self, task_id: str, dashboard_url: str) -> None:
        """设置当前任务的上下文信息."""
        self._default_task_id = task_id
        self._default_dashboard_url = dashboard_url

    async def send_alert(
        self,
        level: str,
        title: str,
        message: str,
        task_id: Optional[str] = None,
        dashboard_url: Optional[str] = None,
    ) -> bool:
        """发送告警通知.

        如果在 5 分钟内对同一 (task_id, alert_type) 已发送过相同级别通知,
        则跳过本次发送.
        """
        tid = task_id or self._default_task_id or "unknown"
        durl = dashboard_url or self._default_dashboard_url or ""
        alert_type = level.lower()
        key = (tid, alert_type)

        now = time.time()
        last_sent = self._last_alert.get(key, 0)
        if now - last_sent < 300:  # 5 minutes cooldown
            return False

        self._last_alert[key] = now

        payload = {
            "level": level,
            "title": title,
            "message": message,
            "timestamp": now,
            "task_id": tid,
            "dashboard_url": durl,
        }

        if self.notifier_type in ("webhook", "dingtalk", "lark"):
            return await self._send_http(payload)
        elif self.notifier_type == "local":
            return await self._send_local(title, message)
        else:
            # Unknown type fallback to console
            print(f"[NOTIFIER][{level.upper()}] {title}: {message}")
            return True

    async def _send_http(self, payload: Dict) -> bool:
        """通过 HTTP POST 发送 JSON 载荷."""
        url = self.webhook_url
        if not url:
            print("[NOTIFIER] WARNING: NOTIFIER_WEBHOOK_URL not set, skipping HTTP alert.")
            return False

        headers = {"Content-Type": "application/json; charset=utf-8"}

        # DingTalk and Lark may require specific signature/timestamp logic;
        # for now we send the generic payload.  Users with stricter bots can
        # extend this method.
        if self.notifier_type == "dingtalk":
            # DingTalk custom bot expects JSON with `msgtype` etc.
            # We wrap our payload inside a text message for compatibility.
            text = f"[{payload['level'].upper()}] {payload['title']}\n{payload['message']}\nTask: {payload['task_id']}\nDashboard: {payload['dashboard_url']}"
            payload = {
                "msgtype": "text",
                "text": {"content": text},
            }
        elif self.notifier_type == "lark":
            text = f"[{payload['level'].upper()}] {payload['title']}\n{payload['message']}\nTask: {payload['task_id']}\nDashboard: {payload['dashboard_url']}"
            payload = {
                "msg_type": "text",
                "content": {"text": text},
            }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code < 400:
                    return True
                print(f"[NOTIFIER] HTTP alert failed: {response.status_code} {response.text}")
                return False
        except Exception as e:
            print(f"[NOTIFIER] HTTP alert exception: {e}")
            return False

    async def _send_local(self, title: str, message: str) -> bool:
        """发送本地系统通知 (Windows Toast / macOS Notification)."""
        try:
            from plyer import notification

            notification.notify(
                title=title,
                message=message,
                timeout=10,
            )
            return True
        except Exception:
            # plyer not installed or platform unsupported
            print(f"[NOTIFIER][LOCAL] {title}: {message}")
            return True
