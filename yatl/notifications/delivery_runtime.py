"""Deterministic mocked runtime gate for P9-004 delivery guard."""

import json

from .contracts import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
)
from .delivery import (
    DeliveryGuardPolicy,
    DeliveryStatus,
    delivery_state_from_record,
    guarded_send,
)
from .formatter import format_notification
from .transport import (
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportError,
    TelegramTransportErrorCode,
    TelegramTransportPolicy,
)


def _credentials():
    token = "".join(("123456789", ":", "A" * 30))
    chat_id = "".join(("-", "100", "1234567890"))
    return TelegramCredentials(token, chat_id)


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
    message = _message()
    formatted = format_notification(message)
    credentials = _credentials()
    calls = []
    sleeps = []

    def sender(item, rendered, target):
        calls.append((item.message_sha256, rendered.formatted_sha256))
        if len(calls) == 1:
            raise TelegramTransportError(
                TelegramTransportErrorCode.NETWORK_ERROR
            )
        if len(calls) == 2:
            raise TelegramTransportError(
                TelegramTransportErrorCode.RATE_LIMITED,
                retry_after_seconds=2,
            )
        return TelegramDeliveryReceipt(
            notification_sha256=item.message_sha256,
            formatted_sha256=rendered.formatted_sha256,
            telegram_message_id=271828,
            policy_sha256=TelegramTransportPolicy().policy_sha256,
        )

    first = guarded_send(
        message,
        formatted,
        credentials,
        sender=sender,
        sleep_fn=sleeps.append,
    )
    calls_after_first = len(calls)

    def forbidden_sender(*args, **kwargs):
        raise RuntimeError("duplicate path attempted transport")

    duplicate = guarded_send(
        message,
        formatted,
        credentials,
        state=first.state,
        sender=forbidden_sender,
        sleep_fn=sleeps.append,
    )
    restored = delivery_state_from_record(first.state.as_record())
    restarted_duplicate = guarded_send(
        message,
        formatted,
        credentials,
        state=restored,
        sender=forbidden_sender,
        sleep_fn=sleeps.append,
    )

    if (
        first.status is not DeliveryStatus.DELIVERED
        or first.attempts != 3
        or first.wait_seconds != (1, 2)
        or calls_after_first != 3
        or duplicate.status is not DeliveryStatus.DUPLICATE_SUPPRESSED
        or duplicate.attempts != 0
        or restarted_duplicate.status
        is not DeliveryStatus.DUPLICATE_SUPPRESSED
        or duplicate.delivery_id != first.delivery_id
        or restarted_duplicate.delivery_id != first.delivery_id
        or duplicate.state.state_sha256 != first.state.state_sha256
        or restored.state_sha256 != first.state.state_sha256
        or len(first.state.records) != 1
        or len(calls) != 3
        or sleeps != [1, 2]
    ):
        raise RuntimeError("P9-004 delivery guard runtime gate failed")

    policy = DeliveryGuardPolicy()
    output = {
        "guard_id": policy.guard_id,
        "policy_sha256": policy.policy_sha256,
        "delivery_id": first.delivery_id,
        "state_sha256": first.state.state_sha256,
        "receipt_sha256": first.receipt_sha256,
        "attempts": first.attempts,
        "wait_seconds": list(first.wait_seconds),
        "network_attempts_mocked": len(calls),
        "duplicate_suppressed": True,
        "restart_snapshot_reconstructed": restored == first.state,
        "restart_duplicate_suppressed": True,
        "max_attempts": policy.max_attempts,
        "max_rate_limit_wait_seconds": policy.max_rate_limit_wait_seconds,
        "max_total_wait_seconds": policy.max_total_wait_seconds,
        "persistent_storage": policy.persistent_storage,
        "caller_managed_snapshot": policy.caller_managed_snapshot,
        "upstream_mutation": policy.upstream_mutation,
        "control_loop": policy.control_loop,
        "trade_permission": policy.trade_permission,
        "order_endpoint": policy.order_endpoint,
        "ai_direct_execution": policy.ai_direct_execution,
        "mocked_transport": True,
        "real_credentials_loaded": False,
        "real_network_called": False,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"))
    if credentials.bot_token in encoded or credentials.chat_id in encoded:
        raise RuntimeError("P9-004 runtime output exposed credential material")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
