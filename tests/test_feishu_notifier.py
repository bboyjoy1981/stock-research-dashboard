from datetime import datetime
import json

from src.feishu_notifier import (
    NotifierConfig,
    build_webhook_signature,
    build_market_test_message,
    load_notifier_config,
    send_text_notification,
)


def test_load_notifier_config_prefers_environment_and_reports_safe_status():
    config = load_notifier_config(
        env={
            "FEISHU_WEBHOOK_URL": "https://example.test/hook",
            "FEISHU_WEBHOOK_SECRET": "private-secret",
        },
        secrets={"FEISHU_WEBHOOK_URL": "https://example.test/ignored"},
    )

    assert config.configured is True
    assert config.webhook_url == "https://example.test/hook"
    assert config.safe_status == "已配置"


def test_load_notifier_config_treats_blank_webhook_as_unconfigured():
    config = load_notifier_config(env={"FEISHU_WEBHOOK_URL": "  "}, secrets={})

    assert config.configured is False
    assert config.safe_status == "未配置"


def test_load_notifier_config_tolerates_unavailable_streamlit_secrets():
    class UnavailableSecrets:
        def __bool__(self):
            raise RuntimeError("No secrets found")

    config = load_notifier_config(env={}, secrets=UnavailableSecrets())

    assert config.configured is False
    assert config.safe_status == "未配置"


def test_build_market_test_message_marks_unknown_snapshot_date():
    message = build_market_test_message(None, datetime(2026, 9, 25, 15, 30))

    assert "飞书通知测试" in message
    assert "数据截至：未识别" in message
    assert "2026-09-25 15:30" in message


def test_build_webhook_signature_matches_feishu_hmac_payload():
    signature = build_webhook_signature("test-secret", 1700000000)

    assert signature == "mbm4Y4oluIPQ00qlBIhX8vAZ0EKv3nw0LuTb91jPL84="


def test_send_text_notification_posts_feishu_text_payload_with_short_timeout():
    captured = {}

    def fake_post(url, body, headers, timeout):
        captured.update(url=url, body=body, headers=headers, timeout=timeout)
        return 200, b'{"code": 0}'

    result = send_text_notification(
        NotifierConfig("https://example.test/hook", None), "hello", fake_post
    )

    assert result.ok is True
    assert result.status == "已发送"
    assert json.loads(captured["body"]) == {
        "msg_type": "text",
        "content": {"text": "hello"},
    }
    assert captured["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert captured["timeout"] == 5.0


def test_send_text_notification_skips_http_when_unconfigured():
    result = send_text_notification(
        NotifierConfig(None, None),
        "hello",
        lambda *_: (_ for _ in ()).throw(AssertionError("HTTP must not run")),
    )

    assert result.ok is False
    assert result.status == "未配置"


def test_send_text_notification_redacts_webhook_url_from_transport_failure():
    url = "https://example.test/very-private-hook"

    def failing_post(*_args):
        raise TimeoutError(f"timeout while posting {url}")

    result = send_text_notification(NotifierConfig(url, None), "hello", failing_post)

    assert result.ok is False
    assert result.status == "发送失败"
    assert url not in result.message


def test_send_text_notification_rejects_http_and_protocol_failures():
    config = NotifierConfig("https://example.test/hook", None)

    http_failure = send_text_notification(config, "hello", lambda *_: (500, b"server failed"))
    protocol_failure = send_text_notification(config, "hello", lambda *_: (200, b'{"code": 19001}'))

    assert http_failure.status == "发送失败"
    assert protocol_failure.status == "发送失败"
