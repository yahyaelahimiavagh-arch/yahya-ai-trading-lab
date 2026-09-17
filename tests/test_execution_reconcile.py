import sqlite3
import tempfile
import unittest
from pathlib import Path

from yatl.__main__ import _paper_execution_contract_runtime_check
from yatl.backtest import BacktestSpec, DecisionEvent
from yatl.data import Candle, DATA_SOURCE
from yatl.execution import (
    ExecutionDisposition,
    ExecutionIntentJournal,
    LocalOrderEventType,
    LocalPaperFillCostAdapter,
    LocalPaperOrderStore,
    LocalPaperPortfolioStore,
    RecoveryReadiness,
    RecoveryStatus,
    assess_local_paper_authorization,
    build_local_order_event,
)
from yatl.execution.reconcile import ReconciliationCode, reconcile_startup


HOUR = 3_600_000


class StartupReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.entry_decision, cls.exit_decision = (
            _paper_execution_contract_runtime_check()
        )
        cls.entry_time = (
            cls.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )
        cls.exit_time = (
            cls.exit_decision.authorization.request.strategy_decision.decision_time_ms
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "execution.sqlite3"
        self.spec = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.exit_time + HOUR,
            initial_cash="10000",
            fee_bps="10",
            slippage_bps="5",
        )
        self.intents, self.orders, self.steps = self._build_full_state(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def _event(self, decision, sequence):
        strategy = decision.authorization.request.strategy_decision
        return DecisionEvent(
            sequence,
            strategy.decision_time_ms,
            strategy.decision_time_ms,
            strategy.context.snapshot,
        )

    def _bar(self, decision, price, low, high):
        opened = decision.authorization.request.strategy_decision.decision_time_ms
        return Candle(
            DATA_SOURCE,
            "BTCUSDT",
            "1h",
            opened,
            opened + HOUR - 1,
            price,
            high,
            low,
            price,
            "100",
            "10000",
            20,
            True,
        )

    def _build_full_state(self, path):
        decisions = (self.entry_decision, self.exit_decision)
        with ExecutionIntentJournal(path) as journal:
            intents = tuple(journal.record(decision) for decision in decisions)
        orders = []
        with LocalPaperOrderStore(path) as store:
            for decision, intent in zip(decisions, intents, strict=True):
                decision_time = (
                    decision.authorization.request.strategy_decision.decision_time_ms
                )
                created = store.apply(build_local_order_event(
                    intent,
                    0,
                    decision_time - 2,
                    LocalOrderEventType.CREATE,
                )).current
                orders.append(store.apply(build_local_order_event(
                    intent,
                    1,
                    decision_time - 1,
                    LocalOrderEventType.ACTIVATE,
                    created,
                )).current)
        adapter = LocalPaperFillCostAdapter("BTCUSDT", self.spec)
        steps = (
            adapter.process(
                self._event(self.entry_decision, 0),
                self.entry_decision,
                intents[0],
                orders[0],
                self._bar(self.entry_decision, "100", "99", "106"),
                self.spec,
            ),
            adapter.process(
                self._event(self.exit_decision, 1),
                self.exit_decision,
                intents[1],
                orders[1],
                self._bar(self.exit_decision, "101", "100", "102"),
                self.spec,
            ),
        )
        with LocalPaperPortfolioStore(path, self.spec) as store:
            store.apply(steps[0], "100")
            store.apply(steps[1], "101")
        return intents, tuple(orders), steps

    def test_clean_state_reconciles_ready_and_is_deterministic(self):
        first = reconcile_startup(self.path, self.spec)
        second = reconcile_startup(self.path, self.spec)
        self.assertEqual(first, second)
        self.assertTrue(first.ready)
        self.assertEqual(first.code, ReconciliationCode.MATCH)
        self.assertEqual(first.intent_count, 2)
        self.assertEqual(first.order_count, 2)
        self.assertEqual(first.fill_count, 2)
        self.assertIsNotNone(first.journal_sha256)
        self.assertIsNotNone(first.orders_sha256)
        self.assertIsNotNone(first.portfolio_sha256)
        self.assertEqual(first.readiness.status, RecoveryStatus.READY)
        self.assertEqual(
            first.reconciliation_sha256,
            second.reconciliation_sha256,
        )

    def test_reconciled_readiness_unlocks_only_local_paper_contract(self):
        report = reconcile_startup(self.path, self.spec)
        startup = assess_local_paper_authorization(
            self.entry_decision.authorization,
            RecoveryReadiness(),
        )
        reconciled = assess_local_paper_authorization(
            self.entry_decision.authorization,
            report.readiness,
        )
        self.assertEqual(startup.disposition, ExecutionDisposition.BLOCKED)
        self.assertEqual(
            reconciled.disposition,
            ExecutionDisposition.ACCEPT_LOCAL_PAPER,
        )
        self.assertEqual(reconciled.approved_quantity, self.entry_decision.approved_quantity)

    def test_empty_initialized_store_is_ready(self):
        path = Path(self.temporary.name) / "empty.sqlite3"
        with ExecutionIntentJournal(path):
            pass
        with LocalPaperOrderStore(path):
            pass
        with LocalPaperPortfolioStore(path, self.spec):
            pass
        report = reconcile_startup(path, self.spec)
        self.assertTrue(report.ready)
        self.assertEqual(report.code, ReconciliationCode.MATCH)
        self.assertEqual((report.intent_count, report.order_count, report.fill_count), (0, 0, 0))

    def test_orphan_intent_fails_closed(self):
        path = Path(self.temporary.name) / "orphan.sqlite3"
        with ExecutionIntentJournal(path) as journal:
            journal.record(self.entry_decision)
        with LocalPaperOrderStore(path):
            pass
        with LocalPaperPortfolioStore(path, self.spec):
            pass
        report = reconcile_startup(path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.ORDER_COVERAGE_MISMATCH)
        self.assertEqual(report.readiness.status, RecoveryStatus.RECOVERY_REQUIRED)

    def test_missing_order_event_fails_replay(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "DELETE FROM local_paper_order_events "
                "WHERE authorization_sha256 = ? AND sequence = 1",
                (self.intents[0].authorization_sha256,),
            )
        connection.close()
        report = reconcile_startup(self.path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.ORDER_REPLAY_MISMATCH)

    def test_extra_valid_order_event_fails_replay(self):
        active = self.orders[0]
        extra = build_local_order_event(
            self.intents[0],
            2,
            active.updated_time_ms + 1,
            LocalOrderEventType.CANCEL,
            active,
        )
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "INSERT INTO local_paper_order_events "
                "(authorization_sha256, intent_sha256, sequence, event_time_ms, "
                "event_type, reason, previous_event_sha256, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    extra.authorization_sha256,
                    extra.intent_sha256,
                    extra.sequence,
                    extra.event_time_ms,
                    extra.event_type.value,
                    extra.reason.value,
                    extra.previous_event_sha256,
                    extra.event_sha256,
                ),
            )
        connection.close()
        report = reconcile_startup(self.path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.ORDER_REPLAY_MISMATCH)

    def test_order_event_digest_mismatch_fails_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET event_sha256 = ? "
                "WHERE authorization_sha256 = ? AND sequence = 0",
                ("0" * 64, self.intents[0].authorization_sha256),
            )
        connection.close()
        report = reconcile_startup(self.path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.ORDER_EVENT_INVALID)

    def test_stale_portfolio_materialization_fails_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_portfolios SET mark_price = '102'"
            )
        connection.close()
        report = reconcile_startup(self.path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.PORTFOLIO_INVALID)

    def test_unsupported_schema_version_fails_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "INSERT INTO order_schema_migrations(version) VALUES (2)"
            )
        connection.close()
        report = reconcile_startup(self.path, self.spec)
        self.assertFalse(report.ready)
        self.assertEqual(report.code, ReconciliationCode.UNSUPPORTED_SCHEMA)


if __name__ == "__main__":
    unittest.main()
