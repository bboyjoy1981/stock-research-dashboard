"""Safe outbound notifications for a Feishu group custom bot."""

from dataclasses import dataclass
from datetime import datetime
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class NotifierConfig:
    webhook_url: str | None
    secret: str | None

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    @property
    def safe_status(self) -> str:
        return "已配置" if self.configured else "未配置"


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    status: str
    message: str


def _clean_value(values: Mapping[str, str] | None, key: str) -> str | None:
    if values is None:
        return None
    try:
        value = values.get(key)
    except Exception:
        return None
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def load_notifier_config(
    env: Mapping[str, str] | None = None,
    secrets: Mapping[str, str] | None = None,
) -> NotifierConfig:
    environment = os.environ if env is None else env
    return NotifierConfig(
        webhook_url=_clean_value(environment, "FEISHU_WEBHOOK_URL") or _clean_value(secrets, "FEISHU_WEBHOOK_URL"),
        secret=_clean_value(environment, "FEISHU_WEBHOOK_SECRET") or _clean_value(secrets, "FEISHU_WEBHOOK_SECRET"),
    )


def build_market_test_message(import_date: str | None, now: datetime) -> str:
    return "\n".join(
        [
            "飞书通知测试",
            f"生成时间：{now:%Y-%m-%d %H:%M}",
            f"数据截至：{import_date or '未识别'}",
            "这是研究看板的手动测试消息，不构成投资建议。",
        ]
    )


def build_webhook_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _default_http_post(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> tuple[int, bytes]:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    with urlopen(request, timeout=timeout) as response:
        return int(response.status), response.read()


def send_text_notification(
    config: NotifierConfig,
    text: str,
    http_post: Callable[[str, bytes, Mapping[str, str], float], tuple[int, bytes]] = _default_http_post,
    timeout_seconds: float = 5.0,
) -> NotificationResult:
    if not config.configured:
        return NotificationResult(
            ok=False,
            status="未配置",
            message="请先在运行环境配置 FEISHU_WEBHOOK_URL。",
        )

    payload = {
        "msg_type": "text",
        "content": {"text": str(text)},
    }
    if config.secret:
        timestamp = int(time.time())
        payload["timestamp"] = str(timestamp)
        payload["sign"] = build_webhook_signature(config.secret, timestamp)
    try:
        status_code, response_body = http_post(
            config.webhook_url or "",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
            timeout_seconds,
        )
        response_data = json.loads(response_body.decode("utf-8"))
    except (OSError, TimeoutError, ValueError, UnicodeDecodeError, HTTPError, URLError):
        return NotificationResult(
            ok=False,
            status="发送失败",
            message="飞书请求未完成，请检查机器人配置或网络。",
        )

    if not 200 <= int(status_code) < 300 or response_data.get("code") != 0:
        return NotificationResult(
            ok=False,
            status="发送失败",
            message="飞书未确认消息，请检查机器人配置或网络。",
        )
    return NotificationResult(ok=True, status="已发送", message="飞书已确认测试消息。")
