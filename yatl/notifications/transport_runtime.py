"""Deterministic mocked runtime gate for P9-003 Telegram transport."""

import json

from .contracts import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
)
from .formatter import format_notification
from .transport import (
    TELEGRAM_CHAT_ID_ENV,
    TELEGRAM_HOST,
    TELEGRAM_METHOD,
    TELEGRAM_PATH_SUFFIX,
    TELEGRAM_PORT,
    TELEGRAM_TOKEN_ENV,
    TelegramTransportPolicy,
    load_telegram_credentials,
    send_formatted_notification,
)


_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
_CHAT_ID = "-1001234567890"


class _Response:
    status = 200

    def __init__(self):
        self._body = json.dumps(
            {
                "ok": True,
                "result": {
                    "message_id": 314159,
                    "chat": {"id": -1001234567890},
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def getheader(self, name):
        if name == "Content-Length":
            return str(len(self._body))
        return None

    def read(self, limit):
        if limit <= len(self._body):
            raise RuntimeError("P9-003 response bound is too small")
        return self._body


class _Connection:
    def __init__(self, host, port, *, timeout, context):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.request_record = None
        self.closed = False

    def request(self, method, path, *, body, headers):
        self.request_record = (method, path, body, headers)

    def getresponse(self):
        return _Response()

    def close(self):
        self.closed = True


def _message():
    source = NotificationSourceIdentity(
        source_id="P8_OVERVIEW_BTCUSDT",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=1_800_000_000_000,
        payload_sha256="7" * 64,
        symbol="BTCUSDT",
    )
    return NotificationMessage(
        notification_id="NOTICE_STATUS_BTCUSDT_777777777777",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title="YATL Paper status BTCUSDT",
        body=(
            "Symbol BTCUSDT; P7 quality PASS; completed Paper trades 3; "
            "open trade count UNKNOWN; snapshot freshness UNKNOWN."
        ),
        source=source,
        event_time_ms=1_800_000_000_000,
        symbol="BTCUSDT",
    )


def main():
    credentials = load_telegram_credentials(
        {
            TELEGRAM_TOKEN_ENV: _TOKEN,
            TELEGRAM_CHAT_ID_ENV: _CHAT_ID,
        }
    )
    message = _message()
    formatted = format_notification(message)
    captured = {}

    def factory(host, port, *, timeout, context):
        connection = _Connection(
            host,
            port,
            timeout=timeout,
            context=context,
        )
        captured["connection"] = connection
        return connection

    receipt = send_formatted_notification(
        message,
        formatted,
        credentials,
        connection_factory=factory,
    )
    connection = captured["connection"]
    method, path, body, headers = connection.request_record
    body_record = json.loads(body.decode("utf-8"))

    if (
        connection.host != TELEGRAM_HOST
        or connection.port != TELEGRAM_PORT
        or method != TELEGRAM_METHOD
        or path != f"/bot{_TOKEN}{TELEGRAM_PATH_SUFFIX}"
        or body_record != {"chat_id": _CHAT_ID, "text": formatted.text}
        or "parse_mode" in body_record
        or headers.get("Content-Type") != "application/json; charset=utf-8"
        or connection.closed is not True
        or receipt.notification_sha256 != message.message_sha256
        or receipt.formatted_sha256 != formatted.formatted_sha256
        or receipt.telegram_message_id != 314159
    ):
        raise RuntimeError("P9-003 Telegram transport runtime gate failed")

    policy = TelegramTransportPolicy()
    output = {
        "transport_id": policy.transport_id,
        "policy_sha256": policy.policy_sha256,
        "receipt_sha256": receipt.receipt_sha256,
        "notification_sha256": receipt.notification_sha256,
        "formatted_sha256": receipt.formatted_sha256,
        "telegram_message_id": receipt.telegram_message_id,
        "host": policy.host,
        "port": policy.port,
        "method": policy.method,
        "path_suffix": policy.path_suffix,
        "tls_required": policy.tls_required,
        "outbound_only": policy.outbound_only,
        "send_message_only": policy.send_message_only,
        "parse_mode": policy.parse_mode,
        "redirects_allowed": policy.redirects_allowed,
        "proxies_allowed": policy.proxies_allowed,
        "inbound_updates_allowed": policy.inbound_updates_allowed,
        "inbound_commands_allowed": policy.inbound_commands_allowed,
        "webhook_receiver_allowed": policy.webhook_receiver_allowed,
        "polling_receiver_allowed": policy.polling_receiver_allowed,
        "trade_permission": policy.trade_permission,
        "order_endpoint": policy.order_endpoint,
        "ai_direct_execution": policy.ai_direct_execution,
        "mocked_transport": True,
        "real_credentials_loaded": False,
        "real_network_called": False,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"))
    if _TOKEN in encoded or _CHAT_ID in encoded:
        raise RuntimeError("P9-003 runtime output exposed credential material")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
