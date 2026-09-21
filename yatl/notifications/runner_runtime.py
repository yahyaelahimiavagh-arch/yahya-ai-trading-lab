"""Deterministic mocked runtime gate for the P9-005 notifier runner."""

import contextlib
import io
import json
import tempfile
from pathlib import Path

from .contracts import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    build_notification_batch,
)
from .runner import main
from .transport import (
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportPolicy,
)


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _credentials():
    return TelegramCredentials(
        "".join(("123456789", ":", "A" * 30)),
        "".join(("-", "100", "1234567890")),
    )


def _batch():
    source = NotificationSourceIdentity(
        source_id="P8_STATUS_BTC",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=1_800_000_000_000,
        payload_sha256="8" * 64,
        symbol="BTCUSDT",
    )
    message = NotificationMessage(
        notification_id="NOTICE_P8_STATUS",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title="YATL Paper status",
        body="Accepted P8 Paper status is ready for information-only delivery.",
        source=source,
        event_time_ms=1_799_999_999_000,
        symbol="BTCUSDT",
    )
    return build_notification_batch(message)


def main_runtime():
    batch = _batch()
    calls = []

    def sender(message, formatted, credentials):
        calls.append(message.message_sha256)
        return TelegramDeliveryReceipt(
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            telegram_message_id=161803,
            policy_sha256=TelegramTransportPolicy().policy_sha256,
        )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "notification.json"
        state = root / "delivery-state.json"
        source.write_text(_json(batch.as_record()), encoding="utf-8", newline="")
        source_before = source.read_bytes()

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            first_exit = main(
                [
                    "--input", str(source),
                    "--expected-batch-sha256", batch.batch_sha256,
                    "--state", str(state),
                    "--symbol", "BTCUSDT",
                ],
                credentials=_credentials(),
                sender=sender,
                sleep_fn=lambda seconds: None,
            )
        first = json.loads(stream.getvalue())
        state_after_first = state.read_bytes()

        def forbidden_sender(*args, **kwargs):
            raise RuntimeError("duplicate path reached sender")

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            second_exit = main(
                [
                    "--input", str(source),
                    "--expected-batch-sha256", batch.batch_sha256,
                    "--state", str(state),
                    "--symbol", "BTCUSDT",
                ],
                environ={},
                sender=forbidden_sender,
                sleep_fn=lambda seconds: None,
            )
        second = json.loads(stream.getvalue())

        if (
            first_exit != 0
            or second_exit != 0
            or first["code"] != "DELIVERED"
            or second["code"] != "DUPLICATE_SUPPRESSED"
            or first["delivery_id"] != second["delivery_id"]
            or first["delivery_state_sha256"] != second["delivery_state_sha256"]
            or first["attempts"] != 1
            or second["attempts"] != 0
            or first["duplicate_suppressed"] is not False
            or second["duplicate_suppressed"] is not True
            or len(calls) != 1
            or state.read_bytes() != state_after_first
            or source.read_bytes() != source_before
            or first["trade_permission"] is not False
            or first["order_endpoint"] is not False
            or first["ai_direct_execution"] is not False
        ):
            raise RuntimeError("P9-005 notifier runner runtime gate failed")

        output = {
            "runner_id": first["runner_id"],
            "batch_sha256": batch.batch_sha256,
            "delivery_id": first["delivery_id"],
            "delivery_state_sha256": first["delivery_state_sha256"],
            "receipt_sha256": first["receipt_sha256"],
            "first_code": first["code"],
            "restart_code": second["code"],
            "sender_calls": len(calls),
            "source_unchanged": source.read_bytes() == source_before,
            "state_replay_equal": state.read_bytes() == state_after_first,
            "duplicate_before_credentials": True,
            "mocked_transport": True,
            "real_credentials_loaded": False,
            "real_network_called": False,
            "paper_only": True,
            "live_master_lock": "OFF",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "trade_permission": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
        }
        encoded = json.dumps(output, sort_keys=True, separators=(",", ":"))
        credentials = _credentials()
        if credentials.bot_token in encoded or credentials.chat_id in encoded:
            raise RuntimeError("P9-005 runtime exposed credential material")
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runtime())
