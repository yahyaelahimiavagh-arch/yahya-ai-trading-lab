import inspect
import unittest
from dataclasses import FrozenInstanceError, replace

from yatl.notifications import (
    MAX_NOTIFICATIONS,
    NOTIFICATION_POLICY_ID,
    NotificationBatch,
    NotificationCategory,
    NotificationContractError,
    NotificationMessage,
    NotificationPolicy,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    StrategyEvidenceState,
    build_notification_batch,
    notification_batch_from_record,
)


OBSERVED_AT_MS = 1_800_000_000_000


def source(symbol="BTCUSDT"):
    return NotificationSourceIdentity(
        source_id="P8_STATUS_BTC" if symbol == "BTCUSDT" else "P8_STATUS_ETH",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=OBSERVED_AT_MS,
        payload_sha256="8" * 64,
        symbol=symbol,
    )


def message(
    notification_id="NOTICE_ALPHA",
    symbol="BTCUSDT",
    category=NotificationCategory.SYSTEM_STATUS,
):
    return NotificationMessage(
        notification_id=notification_id,
        category=category,
        severity=NotificationSeverity.INFO,
        title="YATL status",
        body="Accepted read-only Paper status is available.",
        source=source(symbol),
        event_time_ms=OBSERVED_AT_MS - 1_000,
        symbol=symbol,
    )


class NotificationContractTests(unittest.TestCase):
    def test_policy_is_frozen_read_only_and_transportless(self):
        policy = NotificationPolicy()
        self.assertEqual(policy.policy_id, NOTIFICATION_POLICY_ID)
        self.assertEqual(policy.mode, "READ_ONLY_NOTIFICATION_CONTRACTS")
        self.assertEqual(
            policy.source_scope,
            "ACCEPTED_SANITIZED_UPSTREAM_STATUS_ALERTS_ONLY",
        )
        self.assertEqual(policy.transport_mode, "NONE")
        self.assertTrue(policy.outbound_only)
        self.assertTrue(policy.notification_only)
        self.assertTrue(policy.read_only)
        self.assertTrue(policy.paper_only)
        self.assertEqual(policy.live_master_lock, "OFF")

    def test_policy_capability_flags_are_all_false(self):
        policy = NotificationPolicy()
        names = (
            "allow_telegram_transport",
            "allow_network_transport",
            "allow_credentials",
            "allow_bot_token",
            "allow_chat_id",
            "allow_inbound_updates",
            "allow_inbound_commands",
            "allow_callback_actions",
            "allow_webhook_receiver",
            "allow_polling_receiver",
            "allow_execution_control",
            "allow_live_control",
            "allow_strategy_optimizer",
            "allow_risk_authorization_controller",
            "allow_api_key_surface",
            "allow_source_write",
            "allow_short",
            "allow_margin",
            "allow_futures",
            "allow_leverage",
            "allow_withdrawal",
            "allow_trade_permission",
            "allow_order_endpoint",
            "allow_ai_command_execution",
            "allow_strategy_evidence_upgrade",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertFalse(getattr(policy, name))

    def test_policy_cannot_be_weakened(self):
        changes = (
            {"allow_telegram_transport": True},
            {"allow_network_transport": True},
            {"allow_credentials": True},
            {"allow_inbound_commands": True},
            {"allow_execution_control": True},
            {"allow_live_control": True},
            {"allow_strategy_optimizer": True},
            {"allow_risk_authorization_controller": True},
            {"allow_api_key_surface": True},
            {"allow_trade_permission": True},
            {"allow_order_endpoint": True},
            {"allow_ai_command_execution": True},
            {"allow_strategy_evidence_upgrade": True},
            {"transport_mode": "TELEGRAM"},
            {"live_master_lock": "ON"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(NotificationContractError):
                NotificationPolicy(**change)

    def test_policy_digest_is_deterministic_and_instance_is_frozen(self):
        first = NotificationPolicy()
        second = NotificationPolicy()
        self.assertEqual(first.policy_sha256, second.policy_sha256)
        self.assertEqual(len(first.policy_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            first.mode = "WRITE"

    def test_categories_cover_required_read_only_surfaces(self):
        self.assertEqual(
            tuple(item.value for item in NotificationCategory),
            (
                "SYSTEM_STATUS",
                "DATA_QUALITY_ALERT",
                "PAPER_TRADE_LIFECYCLE",
                "PAPER_SIGNAL_CANDIDATE",
                "RISK_DRAWDOWN_ALERT",
                "PERIODIC_SUMMARY",
                "P10_VALIDATION_STATUS",
            ),
        )

    def test_source_identity_is_accepted_sanitized_and_read_only(self):
        item = source()
        self.assertTrue(item.accepted)
        self.assertTrue(item.sanitized)
        self.assertTrue(item.read_only)
        self.assertEqual(
            item.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(len(item.identity_sha256), 64)

    def test_source_identity_rejects_tamper_and_unsupported_symbol(self):
        item = source()
        changes = (
            {"payload_sha256": "bad"},
            {"symbol": "SOLUSDT"},
            {"accepted": False},
            {"sanitized": False},
            {"read_only": False},
            {"source_phase": "P8_DASHBOARD"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(NotificationContractError):
                replace(item, **change)

    def test_strategy_evidence_enum_has_no_upgrade_member(self):
        self.assertEqual(
            tuple(item.value for item in StrategyEvidenceState),
            ("INSUFFICIENT_EVIDENCE",),
        )

    def test_message_is_information_only_and_read_only(self):
        item = message()
        self.assertEqual(item.paper_label, "PAPER ONLY")
        self.assertEqual(item.live_lock_label, "LIVE_MASTER_LOCK=OFF")
        self.assertEqual(item.evidence_label, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(item.actionability, "INFORMATION_ONLY")
        self.assertTrue(item.read_only)

    def test_message_rejects_weakened_labels_or_actionability(self):
        item = message()
        changes = (
            {"paper_label": "LIVE"},
            {"live_lock_label": "LIVE_MASTER_LOCK=ON"},
            {"evidence_label": "PROFITABLE"},
            {"actionability": "EXECUTE"},
            {"read_only": False},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(NotificationContractError):
                replace(item, **change)

    def test_message_rejects_future_event_and_cross_symbol_material(self):
        item = message()
        with self.assertRaises(NotificationContractError):
            replace(item, event_time_ms=OBSERVED_AT_MS + 1)
        with self.assertRaises(NotificationContractError):
            replace(item, symbol="ETHUSDT")

    def test_message_rejects_secret_transport_and_authority_text(self):
        item = message()
        rejected = (
            "api_key=secret",
            "Bot Token secret",
            "Authorization: Bearer token",
            "https://api.telegram.org/example",
            "RiskAuthorization approved",
            "order_endpoint enabled",
            "trade_permission true",
        )
        for body in rejected:
            with self.subTest(body=body), self.assertRaises(NotificationContractError):
                replace(item, body=body)

    def test_message_text_is_bounded(self):
        item = message()
        with self.assertRaises(NotificationContractError):
            replace(item, title="x" * 121)
        with self.assertRaises(NotificationContractError):
            replace(item, body="x" * 1001)

    def test_message_digest_is_deterministic(self):
        first = message()
        second = message()
        self.assertEqual(first.message_sha256, second.message_sha256)
        self.assertEqual(len(first.message_sha256), 64)

    def test_batch_is_deterministic_reconstructable_and_ordered(self):
        alpha = message("NOTICE_ALPHA")
        beta = message(
            "NOTICE_BETA",
            category=NotificationCategory.DATA_QUALITY_ALERT,
        )
        batch = build_notification_batch(alpha, beta)
        replay = notification_batch_from_record(batch.as_record())
        self.assertEqual(batch, replay)
        self.assertEqual(batch.batch_sha256, replay.batch_sha256)
        self.assertEqual(len(batch.batch_sha256), 64)

    def test_batch_rejects_duplicate_or_unordered_identities(self):
        alpha = message("NOTICE_ALPHA")
        beta = message("NOTICE_BETA")
        with self.assertRaises(NotificationContractError):
            NotificationBatch((beta, alpha))
        with self.assertRaises(NotificationContractError):
            NotificationBatch((alpha, alpha))

    def test_batch_is_bounded_and_nonempty(self):
        with self.assertRaises(NotificationContractError):
            NotificationBatch(())
        items = tuple(
            message(f"NOTICE_{index:03d}")
            for index in range(MAX_NOTIFICATIONS + 1)
        )
        with self.assertRaises(NotificationContractError):
            NotificationBatch(items)

    def test_top_level_schema_smuggling_is_rejected(self):
        record = build_notification_batch(message()).as_record()
        record["trade_permission"] = True
        with self.assertRaises(NotificationContractError):
            notification_batch_from_record(record)

    def test_nested_schema_smuggling_is_rejected(self):
        record = build_notification_batch(message()).as_record()
        record["notifications"][0]["execution_command"] = "BUY"
        with self.assertRaises(NotificationContractError):
            notification_batch_from_record(record)

    def test_policy_schema_smuggling_is_rejected(self):
        record = build_notification_batch(message()).as_record()
        record["policy"]["telegram_bot_token"] = "secret"
        with self.assertRaises(NotificationContractError):
            notification_batch_from_record(record)

    def test_contract_source_has_no_transport_execution_account_risk_or_provider_import(self):
        import yatl.notifications.contracts as contracts

        source_text = inspect.getsource(contracts)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "subprocess",
            "api.telegram.org",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
