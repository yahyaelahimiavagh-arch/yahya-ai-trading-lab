import hashlib
import inspect
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from yatl.backtest import BacktestClock
from yatl.risk import RiskPolicy
from yatl.strategy import (
    FIXED_RESEARCH_QUANTITY,
    StrategyAction,
    StrategyContext,
    TREND_PULLBACK_IDENTITY,
    evaluate_trend_pullback,
)

from yatl.validation.forward_store import ForwardCandleStore
from yatl.validation.ingestion import collect_forward_snapshot
from yatl.validation.paper_runner import (
    FORWARD_PAPER_RUNNER_ID,
    P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1,
    REGIME_WARMUP_BARS,
    RUNNER_QUANTITY,
    EntryVetoReason,
    ForwardPaperRunnerError,
    ValidationRiskState,
    _dataset_for_symbol,
    assess_fixed_quantity_entry,
    run_forward_paper,
)
from yatl.validation.paper_runner_runtime import (
    MockForwardRunnerClient,
    build_mock_forward_runner_fixture,
)
from yatl.validation.window import ForwardWindowSeal


def _git_blob_sha1(path):
    payload = Path(path).read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()


def _first_entry_decision(store, snapshot):
    dataset, _ = _dataset_for_symbol(store, snapshot, "BTCUSDT")
    for event in BacktestClock(dataset).events():
        decision = evaluate_trend_pullback(
            StrategyContext(TREND_PULLBACK_IDENTITY, event.snapshot),
            in_position=False,
            active_setup=None,
        )
        if decision.action is StrategyAction.ENTER_LONG:
            return event, decision
    raise AssertionError("synthetic fixture did not produce an entry decision")


def _flat_risk_state(event, *, equity="10000", cash="10000",
                     session_pnl="0", losses=0, kill=False):
    return ValidationRiskState(
        symbol="BTCUSDT",
        equity_quote=equity,
        cash_quote=cash,
        position_quantity="0",
        mark_price=event.snapshot.latest_primary.close,
        peak_equity_quote=equity,
        session_start_time_ms=(
            event.decision_time_ms // 86_400_000
        ) * 86_400_000,
        session_start_equity_quote=equity,
        session_realized_pnl_quote=session_pnl,
        consecutive_losses=losses,
        open_positions=0,
        kill_switch_active=kill,
    )


class ForwardPaperRunnerTests(unittest.TestCase):
    def test_frozen_quantity_matches_accepted_p3_adapter_and_blob(self):
        import yatl.strategy.adapter as adapter

        self.assertEqual(RUNNER_QUANTITY, "0.001")
        self.assertEqual(RUNNER_QUANTITY, FIXED_RESEARCH_QUANTITY)
        self.assertEqual(
            _git_blob_sha1(adapter.__file__),
            P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1,
        )

    def test_mock_forward_prefix_exercises_entry_and_exit_on_both_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                result = run_forward_paper(store, snapshot)
            finally:
                store.close()

        self.assertEqual(result.runner_id, FORWARD_PAPER_RUNNER_ID)
        self.assertEqual(tuple(item.symbol for item in result.symbols),
                         ("BTCUSDT", "ETHUSDT"))
        for item in result.symbols:
            with self.subTest(symbol=item.symbol):
                actions = [fill["action"] for fill in item.fills]
                self.assertIn("ENTER_LONG", actions)
                self.assertIn("EXIT_LONG", actions)
                self.assertGreaterEqual(item.entry_signals, 1)
                self.assertGreaterEqual(item.entries_allowed, 1)
                self.assertGreaterEqual(item.exit_signals, 1)
                self.assertEqual(item.final_portfolio["closed_trades"], 1)
                self.assertEqual(item.final_portfolio["asset_quantity"], "0")
                self.assertTrue(item.point_in_time_verified)
                self.assertTrue(item.replay_from_start)

    def test_runner_replay_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                first = run_forward_paper(store, snapshot)
                second = run_forward_paper(store, snapshot)
            finally:
                store.close()
        self.assertEqual(first.as_record(), second.as_record())
        self.assertEqual(first.run_sha256, second.run_sha256)

    def test_first_decision_waits_for_forward_only_4h_warmup(self):
        window = ForwardWindowSeal()
        expected = (
            window.forward_window_start_ms
            + REGIME_WARMUP_BARS * 14_400_000
        )
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                result = run_forward_paper(store, snapshot)
            finally:
                store.close()
        self.assertEqual(result.symbols[0].first_decision_time_ms, expected)
        self.assertEqual(result.symbols[1].first_decision_time_ms, expected)
        self.assertGreater(expected, window.forward_window_start_ms)

    def test_insufficient_forward_warmup_fails_closed(self):
        window = ForwardWindowSeal()
        server_time = window.forward_window_start_ms + 8 * 3_600_000 + 1_234
        with tempfile.TemporaryDirectory() as directory:
            store = ForwardCandleStore(Path(directory) / "forward.sqlite3")
            client = MockForwardRunnerClient(server_time)
            try:
                snapshot = collect_forward_snapshot(store, client)
                with self.assertRaises(ForwardPaperRunnerError):
                    run_forward_paper(store, snapshot)
            finally:
                store.close()

    def test_store_tamper_breaks_ingestion_binding_before_strategy_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p10-forward.sqlite3"
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            store.close()

            connection = sqlite3.connect(path)
            with connection:
                connection.execute(
                    """
                    UPDATE candles
                    SET close = '999'
                    WHERE symbol = 'BTCUSDT' AND interval = '1h'
                      AND open_time_ms = (
                        SELECT MIN(open_time_ms) FROM candles
                        WHERE symbol = 'BTCUSDT' AND interval = '1h'
                      )
                    """
                )
            connection.close()

            reopened = ForwardCandleStore(path)
            try:
                with self.assertRaises(ForwardPaperRunnerError):
                    run_forward_paper(reopened, snapshot)
            finally:
                reopened.close()

    def test_first_entry_passes_fixed_quantity_p4_numeric_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                event, decision = _first_entry_decision(store, snapshot)
            finally:
                store.close()

        veto = assess_fixed_quantity_entry(
            decision,
            _flat_risk_state(event),
        )
        self.assertTrue(veto.allowed)
        self.assertEqual(veto.reasons, ())
        self.assertLessEqual(
            Decimal(veto.planned_loss_quote),
            Decimal(veto.risk_budget_quote),
        )
        policy = RiskPolicy()
        self.assertEqual(policy.risk_per_trade_fraction, "0.01")
        self.assertEqual(policy.max_position_fraction, "0.25")
        self.assertEqual(policy.max_gross_exposure_fraction, "0.25")
        self.assertEqual(policy.max_session_loss_fraction, "0.02")
        self.assertEqual(policy.max_drawdown_fraction, "0.10")
        self.assertEqual(policy.max_consecutive_losses, 3)

    def test_kill_switch_session_loss_and_loss_streak_veto_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                event, decision = _first_entry_decision(store, snapshot)
            finally:
                store.close()

        cases = (
            (
                _flat_risk_state(event, kill=True),
                EntryVetoReason.KILL_SWITCH_ACTIVE,
            ),
            (
                _flat_risk_state(event, session_pnl="-200"),
                EntryVetoReason.SESSION_LOSS_LIMIT,
            ),
            (
                _flat_risk_state(event, losses=3),
                EntryVetoReason.CONSECUTIVE_LOSS_LIMIT,
            ),
        )
        for state, reason in cases:
            with self.subTest(reason=reason):
                veto = assess_fixed_quantity_entry(decision, state)
                self.assertFalse(veto.allowed)
                self.assertIn(reason, veto.reasons)

    def test_cash_and_position_limits_veto_without_changing_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                event, decision = _first_entry_decision(store, snapshot)
            finally:
                store.close()

        low_cash = _flat_risk_state(event, equity="1", cash="0.0001")
        veto = assess_fixed_quantity_entry(decision, low_cash)
        self.assertFalse(veto.allowed)
        self.assertEqual(veto.quantity, RUNNER_QUANTITY)
        self.assertTrue(
            EntryVetoReason.CASH_INSUFFICIENT in veto.reasons
            or EntryVetoReason.POSITION_LIMIT in veto.reasons
            or EntryVetoReason.PLANNED_LOSS_LIMIT in veto.reasons
        )

    def test_result_explicitly_denies_qualification_authorization_and_live_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            store, snapshot, _ = build_mock_forward_runner_fixture(directory)
            try:
                result = run_forward_paper(store, snapshot)
            finally:
                store.close()

        self.assertFalse(result.p3_qualification_fabricated)
        self.assertFalse(result.p4_risk_authorization_created)
        self.assertFalse(result.quantity_authority_created)
        self.assertFalse(result.external_transport_used)
        self.assertFalse(result.trade_permission)
        self.assertFalse(result.order_endpoint)
        self.assertFalse(result.ai_direct_execution)
        self.assertFalse(result.economic_evaluation_allowed)
        self.assertEqual(result.strategy_evidence, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(result.paper_only)
        self.assertEqual(result.live_master_lock, "OFF")

    def test_runner_source_does_not_fabricate_p3_or_p4_authority(self):
        import yatl.validation.paper_runner as runner

        source = inspect.getsource(runner)
        for forbidden in (
            "QUALIFIED_FOR_P4_RESEARCH",
            "RiskAuthorization",
            "authorize_paper_request",
            "RiskManagedPaperAdapter",
            "size_entry(",
            "assess_entry_limits(",
            "assess_protective_entry(",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
            "openai",
            "anthropic",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_runner_has_no_network_or_system_clock_capability(self):
        import yatl.validation.paper_runner as runner

        source = inspect.getsource(runner)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "time.time",
            "time.monotonic",
            "datetime.now",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
