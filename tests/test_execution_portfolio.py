import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check, main
from yatl.backtest import BacktestSpec, DecisionEvent, PortfolioLedger
from yatl.data import Candle, DATA_SOURCE
from yatl.execution import (
    DuplicateLocalPaperFill,
    ExecutionIntentJournal,
    LocalOrderEventType,
    LocalPaperFillCostAdapter,
    LocalPaperOrderStore,
    LocalPaperPortfolioError,
    LocalPaperPortfolioStore,
    build_local_order_event,
)


HOUR = 3_600_000


class LocalPaperPortfolioTests(unittest.TestCase):
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
            "BTCUSDT", self.entry_time, self.exit_time + HOUR,
            initial_cash="10000", fee_bps="10", slippage_bps="5",
        )
        self.intents, self.orders = self._durable_evidence(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def _durable_evidence(self, path):
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
                    intent, 0, decision_time - 2, LocalOrderEventType.CREATE,
                )).current
                active = store.apply(build_local_order_event(
                    intent, 1, decision_time - 1,
                    LocalOrderEventType.ACTIVATE, created,
                )).current
                orders.append(active)
        return intents, tuple(orders)

    def _event(self, decision, sequence):
        strategy = decision.authorization.request.strategy_decision
        return DecisionEvent(
            sequence, strategy.decision_time_ms,
            strategy.decision_time_ms, strategy.context.snapshot,
        )

    def _bar(self, decision, price, low, high):
        opened = decision.authorization.request.strategy_decision.decision_time_ms
        return Candle(
            DATA_SOURCE, "BTCUSDT", "1h", opened, opened + HOUR - 1,
            price, high, low, price, "100", "10000", 20, True,
        )

    def _steps(self, *, same_bar=False, spec=None):
        spec = spec or self.spec
        adapter = LocalPaperFillCostAdapter("BTCUSDT", spec)
        entry = adapter.process(
            self._event(self.entry_decision, 0), self.entry_decision,
            self.intents[0], self.orders[0],
            self._bar(
                self.entry_decision, "100",
                "94" if same_bar else "99",
                "116" if same_bar else "106",
            ),
            spec,
        )
        if same_bar:
            return (entry,)
        exit_step = adapter.process(
            self._event(self.exit_decision, 1), self.exit_decision,
            self.intents[1], self.orders[1],
            self._bar(self.exit_decision, "101", "100", "102"), spec,
        )
        return entry, exit_step

    def test_entry_projection_exactly_matches_accepted_p2_ledger(self):
        entry, _ = self._steps()
        ledger = PortfolioLedger(self.spec)
        ledger.apply_many(entry.fills)
        expected = ledger.snapshot("100")
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            result = store.apply(entry, "100")
            self.assertEqual(result.projection.snapshot, expected)
            self.assertEqual(result.projection.snapshot.asset_quantity,
                             entry.fills[0].asset_delta)
            self.assertEqual(result.projection.fill_count, 1)

    def test_entry_exit_projection_is_flat_with_exact_realized_pnl(self):
        entry, exit_step = self._steps()
        ledger = PortfolioLedger(self.spec)
        ledger.apply_many(entry.fills + exit_step.fills)
        expected = ledger.snapshot("101")
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            store.apply(entry, "100")
            result = store.apply(exit_step, "101")
            self.assertEqual(result.projection.snapshot, expected)
            self.assertEqual(result.projection.snapshot.asset_quantity, 0)
            self.assertEqual(result.projection.snapshot.closed_trades, 1)
            self.assertNotEqual(result.projection.snapshot.realized_pnl_quote, 0)

    def test_same_bar_entry_and_protective_exit_commit_as_one_batch(self):
        (step,) = self._steps(same_bar=True)
        self.assertEqual(len(step.fills), 2)
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            result = store.apply(step, "95")
            self.assertEqual(len(result.events), 2)
            self.assertEqual(result.projection.fill_count, 2)
            self.assertEqual(result.projection.snapshot.asset_quantity, 0)
            self.assertEqual(result.projection.snapshot.closed_trades, 1)

    def test_duplicate_fill_step_is_rejected_without_mutation(self):
        entry, _ = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            first = store.apply(entry, "100")
            with self.assertRaises(DuplicateLocalPaperFill):
                store.apply(entry, "100")
            self.assertEqual(len(store.events()), 1)
            self.assertEqual(store.get_projection(), first.projection)

    def test_exit_without_durable_entry_fails_without_writes(self):
        _, exit_step = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.apply(exit_step, "101")
            self.assertEqual(store.events(), ())
            self.assertIsNone(store.get_projection())

    def test_insufficient_cash_rolls_back_fill_and_projection(self):
        small_spec = BacktestSpec(
            "BTCUSDT", self.entry_time, self.exit_time + HOUR,
            initial_cash="1000", fee_bps="10", slippage_bps="5",
        )
        entry, _ = self._steps(spec=small_spec)
        with LocalPaperPortfolioStore(self.path, small_spec) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.apply(entry, "100")
            self.assertEqual(store.events(), ())
            self.assertIsNone(store.get_projection())

    def test_projection_write_failure_rolls_back_every_fill_event(self):
        (step,) = self._steps(same_bar=True)
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            with patch.object(
                store, "_write_projection",
                side_effect=LocalPaperPortfolioError("injected failure"),
            ):
                with self.assertRaises(LocalPaperPortfolioError):
                    store.apply(step, "95")
            count = store._connection.execute(
                "SELECT COUNT(*) FROM local_paper_fill_events"
            ).fetchone()[0]
            self.assertEqual(count, 0)
            self.assertIsNone(store.get_projection())

    def test_second_fill_write_failure_rolls_back_first_fill(self):
        (step,) = self._steps(same_bar=True)
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            original = store._insert_fill
            calls = 0

            def fail_second(event):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise LocalPaperPortfolioError("injected second-fill failure")
                original(event)

            with patch.object(store, "_insert_fill", side_effect=fail_second):
                with self.assertRaises(LocalPaperPortfolioError):
                    store.apply(step, "95")
            self.assertEqual(store.events(), ())

    def test_mismatched_durable_order_state_fails_closed(self):
        entry, _ = self._steps()
        changed = entry.__class__(
            entry.authorization_sha256, entry.intent_sha256,
            self.orders[1].state_sha256, entry.p2_intent,
            entry.references, entry.fills,
        )
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.apply(changed, "100")
            self.assertEqual(store.events(), ())

    def test_invalid_mark_price_fails_without_mutation(self):
        entry, _ = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            for mark in ("0", "-1", "1e2", None):
                with self.subTest(mark=mark), self.assertRaises(
                    LocalPaperPortfolioError
                ):
                    store.apply(entry, mark)
                self.assertEqual(store.events(), ())

    def test_reopen_and_canonical_export_are_deterministic(self):
        entry, exit_step = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            store.apply(entry, "100")
            final = store.apply(exit_step, "101").projection
            canonical = store.canonical_json()
        with LocalPaperPortfolioStore(self.path, self.spec) as reopened:
            self.assertEqual(reopened.schema_version(), 1)
            self.assertEqual(reopened.get_projection(), final)
            self.assertEqual(reopened.canonical_json(), canonical)
            self.assertEqual(len(reopened.events()), 2)
        payload = json.loads(canonical)
        self.assertEqual(payload["projection"]["position"], "FLAT")
        self.assertNotIn(str(self.path), canonical)

    def test_tampered_fill_fails_accepted_p2_replay(self):
        entry, _ = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            store.apply(entry, "100")
        connection = sqlite3.connect(self.path)
        with connection:
            payload = json.loads(connection.execute(
                "SELECT payload_json FROM local_paper_fill_events"
            ).fetchone()[0])
            payload["cash_delta"] = "0"
            connection.execute(
                "UPDATE local_paper_fill_events SET payload_json = ?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
            )
        connection.close()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.events()

    def test_tampered_projection_fails_replay(self):
        entry, _ = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            store.apply(entry, "100")
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE local_paper_portfolios SET mark_price = '101'"
            )
        connection.close()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.get_projection()

    def test_different_spec_cannot_reopen_existing_projection(self):
        entry, _ = self._steps()
        with LocalPaperPortfolioStore(self.path, self.spec) as store:
            store.apply(entry, "100")
        changed = BacktestSpec(
            "BTCUSDT", self.entry_time, self.exit_time + HOUR,
            initial_cash="10000", fee_bps="11", slippage_bps="5",
        )
        with LocalPaperPortfolioStore(self.path, changed) as store:
            with self.assertRaises(LocalPaperPortfolioError):
                store.get_projection()

    def test_newer_schema_and_missing_order_schema_fail_closed(self):
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "CREATE TABLE portfolio_schema_migrations (version INTEGER PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO portfolio_schema_migrations(version) VALUES (2)"
            )
        connection.close()
        with self.assertRaises(LocalPaperPortfolioError):
            LocalPaperPortfolioStore(self.path, self.spec)
        missing = Path(self.temporary.name) / "missing.sqlite3"
        with ExecutionIntentJournal(missing):
            pass
        with self.assertRaises(LocalPaperPortfolioError):
            LocalPaperPortfolioStore(missing, self.spec)

    @patch("sys.argv", ["yatl", "paper-portfolio-check"])
    def test_cli_reports_atomic_durable_projection(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("atomic fill and portfolio projection", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
