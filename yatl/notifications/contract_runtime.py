"""Deterministic offline runtime gate for P9-001 notification contracts."""

import json

from . import (
    NotificationCategory,
    NotificationMessage,
    NotificationPolicy,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    build_notification_batch,
    notification_batch_from_record,
)


OBSERVED_AT_MS = 1_800_000_000_000


def _source(source_id, phase, sha256, symbol):
    return NotificationSourceIdentity(
        source_id=source_id,
        source_phase=phase,
        observed_at_ms=OBSERVED_AT_MS,
        payload_sha256=sha256,
        symbol=symbol,
    )


def main():
    policy = NotificationPolicy()
    status = NotificationMessage(
        notification_id="NOTICE_P8_STATUS",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title="YATL Paper status",
        body="P8 accepted status is available for read-only notification.",
        source=_source(
            "P8_STATUS_BTC",
            NotificationSourcePhase.P8_DASHBOARD,
            "8" * 64,
            "BTCUSDT",
        ),
        event_time_ms=OBSERVED_AT_MS - 2_000,
        symbol="BTCUSDT",
    )
    quality = NotificationMessage(
        notification_id="NOTICE_P7_QUALITY",
        category=NotificationCategory.DATA_QUALITY_ALERT,
        severity=NotificationSeverity.WARNING,
        title="Data quality review",
        body="Accepted analytics quality material requires operator review.",
        source=_source(
            "P7_QUALITY_ETH",
            NotificationSourcePhase.P7_ANALYTICS,
            "7" * 64,
            "ETHUSDT",
        ),
        event_time_ms=OBSERVED_AT_MS - 1_000,
        symbol="ETHUSDT",
    )
    batch = build_notification_batch(quality, status)
    replay = notification_batch_from_record(batch.as_record())
    output = {
        "policy_id": policy.policy_id,
        "policy_sha256": policy.policy_sha256,
        "batch_sha256": batch.batch_sha256,
        "notifications": len(batch.notifications),
        "replay_equal": replay == batch,
        "transport_mode": policy.transport_mode,
        "outbound_only": policy.outbound_only,
        "network_transport": policy.allow_network_transport,
        "inbound_commands": policy.allow_inbound_commands,
        "trade_permission": policy.allow_trade_permission,
        "order_endpoint": policy.allow_order_endpoint,
        "ai_direct_execution": policy.allow_ai_command_execution,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
