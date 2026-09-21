import copy
import hashlib
import inspect
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
from unittest.mock import patch

from yatl.backtest import BacktestSpec, IntentAction, PortfolioLedger, apply_costs
from yatl.backtest.costs import DECIMAL_PRECISION
from yatl.backtest.fills import FillReason, FillReference
from yatl.validation import economics
from yatl.validation.economics import (
    ForwardEconomicsError, _assemble, _drawdown, _reconcile_symbol,
    _trade_statistics, calculate_forward_economics,
)
from yatl.validation.forward_store import ForwardCandleStore
from yatl.validation.paper_runner import _fill_record, _portfolio_record, run_forward_paper
from yatl.validation.paper_runner_runtime import build_mock_forward_runner_fixture
from yatl.validation.registration import CandidateFreeze, EconomicGateRegistry
from yatl.validation.window import ForwardWindowSeal


class ForwardEconomicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.store, cls.snapshot, _ = build_mock_forward_runner_fixture(cls.directory.name)
        cls.evidence = run_forward_paper(cls.store, cls.snapshot)
        cls.report = calculate_forward_economics(cls.store, cls.snapshot, cls.evidence)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.directory.cleanup()

    def arithmetic_symbol(self, prices=(), final_mark="100", symbol="BTCUSDT"):
        """Isolated arithmetic fixture, not admissible public runner evidence."""
        template = next(item for item in self.evidence.symbols if item.symbol == symbol)
        spec = BacktestSpec(symbol, template.first_decision_time_ms, template.end_time_ms)
        ledger = PortfolioLedger(spec)
        fills = []
        trace = []
        for i, price in enumerate(prices):
            time = spec.start_time_ms + i * 3_600_000
            before = ledger.snapshot(price)
            trace.append({"decision_time_ms": time, "risk_state": {
                "equity_quote": economics._plain(before.equity_quote),
                "position_quantity": economics._plain(before.asset_quantity),
                "mark_price": price,
            }})
            action = IntentAction.ENTER_LONG if i % 2 == 0 else IntentAction.EXIT_LONG
            reason = FillReason.NEXT_PRIMARY_OPEN if i % 2 == 0 else FillReason.SCRIPTED_EXIT
            fill = apply_costs(FillReference(action, symbol, time, time, "0.001", price, reason), spec)
            ledger.apply(fill)
            fills.append(_fill_record(fill))
        return replace(template, fills=tuple(fills), trace=tuple(trace),
                       final_portfolio=_portfolio_record(ledger.snapshot(final_mark)))

    def test_mocked_integration_reconciles_both_symbols(self):
        record = self.report.as_record()
        self.assertEqual(record["pooled"]["completed_trades"], 2)
        self.assertEqual(record["input_run_sha256"], self.evidence.run_sha256)
        for actual, source in zip(record["symbols"], self.evidence.symbols):
            self.assertEqual(actual["realized_net_pnl_quote"], source.final_portfolio["realized_pnl_quote"])
            self.assertEqual(actual["executed_fee_quote"], source.final_portfolio["total_fee_quote"])

    def test_restart_reopens_store_and_produces_identical_report(self):
        reopened = ForwardCandleStore(Path(self.directory.name) / "p10-forward.sqlite3")
        try:
            with localcontext() as ambient:
                ambient.prec = 6
                ambient.rounding = ROUND_DOWN
                repeated = calculate_forward_economics(reopened, self.snapshot, self.evidence)
        finally:
            reopened.close()
        self.assertEqual(repeated.canonical_json, self.report.canonical_json)
        self.assertEqual(repeated.report_sha256, self.report.report_sha256)

    def test_exact_costs_and_no_double_slippage(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(("100", "110")), "100")
        self.assertEqual(report["completed_gross_pnl_quote"], "0.01")
        self.assertEqual(report["completed_fee_quote"], "0.000209995")
        self.assertEqual(report["completed_slippage_quote"], "0.000105")
        self.assertEqual(report["realized_net_pnl_quote"], "0.009685005")
        self.assertEqual(report["winning_trades"], 1)
        self.assertEqual(report["profit_factor_after_costs"], None)
        self.assertEqual(report["profit_factor_status"], "UNDEFINED_NO_LOSSES")

    def test_open_position_not_counted_as_completed(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(("100",), "110"), "110")
        self.assertEqual(report["completed_trades"], 0)
        self.assertEqual(report["open_positions"], 1)
        self.assertEqual(report["realized_net_pnl_quote"], "0")
        self.assertEqual(report["completed_gross_pnl_quote"], "0")
        self.assertEqual(report["executed_total_cost_quote"], "0.00015005")
        self.assertEqual(report["open_entry_fee_quote"], "0.00010005")
        self.assertEqual(report["unrealized_liquidation_net_pnl_quote"], "0.009685005")
        self.assertEqual(report["open_holding_ms"], 8 * 3_600_000)
        self.assertIsNone(report["win_rate"])

    def test_empty_flat_run_is_explicitly_undefined(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(), "100")
        self.assertEqual(report["net_pnl_after_costs_quote"], "0")
        self.assertEqual(report["profit_factor_status"], "UNDEFINED_NO_COMPLETED_TRADES")
        self.assertIsNone(report["mean_completed_holding_ms"])
        self.assertEqual(report["position_time_fraction"], "0")

    def test_costs_can_turn_gross_breakeven_into_loss(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(("100", "100")), "100")
        self.assertEqual(report["completed_gross_pnl_quote"], "0")
        self.assertEqual(report["realized_net_pnl_quote"], "-0.0003")
        self.assertEqual(report["losing_trades"], 1)
        self.assertEqual(report["profit_factor_after_costs"], "0")

    def test_wins_losses_breakeven_and_profit_factor(self):
        stats = _trade_statistics([
            {"net_pnl_quote": value, "holding_ms": 10}
            for value in ("2", "-1", "0", "1")
        ])
        self.assertEqual(stats["profit_factor_after_costs"], "3")
        self.assertEqual(stats["winning_trades"], 2)
        self.assertEqual(stats["losing_trades"], 1)
        self.assertEqual(stats["breakeven_trades"], 1)
        self.assertEqual(stats["win_rate"], "0.5")

    def test_realized_drawdown_remembers_losses_after_recovery(self):
        result = _drawdown([Decimal(v) for v in ("100", "110", "99", "120")])
        self.assertEqual(result["maximum_drawdown_fraction"], "0.1")
        self.assertEqual(result["maximum_drawdown_quote"], "11")

    def test_open_loss_is_visible_in_sampled_not_realized_drawdown(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(("100",), "50"), "50")
        self.assertEqual(report["realized_drawdown"]["maximum_drawdown_quote"], "0")
        self.assertGreater(Decimal(report["sampled_liquidation_drawdown"]["maximum_drawdown_quote"]), 0)

    def test_completed_holding_and_exposure(self):
        report, _, _ = _reconcile_symbol(self.arithmetic_symbol(("100", "110")), "100")
        self.assertEqual(report["mean_completed_holding_ms"], "3600000")
        self.assertEqual(report["position_time_ms"], 3_600_000)
        self.assertEqual(report["maximum_sampled_notional_quote"], "0.11")

    def test_pool_uses_sum_of_actual_independent_capital(self):
        record = self.report.as_record()
        self.assertEqual(record["pooled"]["initial_equity_quote"], "20000")
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            self.assertEqual(Decimal(record["pooled"]["net_return_after_costs"]),
                             Decimal(record["pooled"]["net_pnl_after_costs_quote"]) / 20000)

    def test_simultaneous_closes_are_grouped_before_pooled_drawdown(self):
        symbols = (self.arithmetic_symbol(("100", "110")),
                   self.arithmetic_symbol(("100", "90"), symbol="ETHUSDT"))
        report = _assemble(replace(self.evidence, symbols=symbols),
                           {"BTCUSDT": "100", "ETHUSDT": "100"}).as_record()
        self.assertEqual(report["pooled"]["realized_drawdown"]["maximum_drawdown_quote"], "0.0006")

    def test_duration_comes_from_admitted_cutoff_not_system_clock(self):
        record = self.report.as_record()
        self.assertEqual(record["observation_duration_ms"], 212 * 3_600_000)
        self.assertEqual(record["observation_start_ms"], ForwardWindowSeal().forward_window_start_ms)
        self.assertEqual(record["sample_status"], "INSUFFICIENT_DATA")
        self.assertEqual(len(record["insufficiency_reasons"]), 4)

    def test_report_cannot_upgrade_evidence_or_permissions(self):
        safety = self.report.as_record()["safety"]
        self.assertTrue(safety["paper_only"])
        self.assertEqual(safety["live_master_lock"], "OFF")
        self.assertEqual(safety["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(safety["economic_verdict"], "NOT_EVALUATED")
        for key in ("economic_evaluation_allowed", "p11_unlocked", "trade_permission",
                    "order_endpoint", "ai_direct_execution", "quantity_authority_created",
                    "p4_risk_authorization_created", "p3_qualification_fabricated"):
            self.assertIs(safety[key], False)

    def test_frozen_candidate_and_gates_unchanged(self):
        self.assertEqual(CandidateFreeze().candidate_sha256,
                         "64f2e116616f84e09fbf70a19977395eac99b16fe7e24a283dd53a8b0b84ac86")
        self.assertEqual(EconomicGateRegistry().registry_sha256,
                         "f8d706df050bb095219ae4b76e400eff73e1a7a6755c4a197d489b03117a3e95")

    def test_detached_record_mutation_cannot_change_hash(self):
        before = self.report.report_sha256
        self.report.as_record()["pooled"]["completed_trades"] = 999
        self.assertEqual(self.report.report_sha256, before)
        self.assertEqual(hashlib.sha256(self.report.canonical_json.encode()).hexdigest(), before)

    def test_rejects_mutated_fills_portfolio_trace_or_provenance(self):
        for field in ("fills", "final_portfolio", "trace", "input_snapshot_sha256"):
            run = copy.deepcopy(self.evidence)
            symbol = run.symbols[0]
            if field == "fills":
                symbol.fills[0]["fee_quote"] = "0"
            elif field == "final_portfolio":
                symbol.final_portfolio["equity_quote"] = "99999"
            elif field == "trace":
                symbol.trace[0]["risk_state"]["equity_quote"] = "99999"
            else:
                run = replace(run, symbols=(replace(symbol, input_snapshot_sha256="0" * 64), run.symbols[1]))
            # Exercise comparison against known genuine replay; full replay is
            # independently exercised by integration and reopened-store tests.
            with self.subTest(field=field), patch.object(economics, "run_forward_paper", return_value=self.evidence):
                with self.assertRaises(ForwardEconomicsError):
                    calculate_forward_economics(self.store, self.snapshot, run)

    def test_rejects_non_run_input(self):
        with self.assertRaises(ForwardEconomicsError):
            calculate_forward_economics(self.store, self.snapshot, {})

    def test_closed_store_fails_as_stable_economics_error(self):
        closed = ForwardCandleStore(Path(self.directory.name) / "p10-forward.sqlite3")
        closed.close()
        with self.assertRaises(ForwardEconomicsError):
            calculate_forward_economics(closed, self.snapshot, self.evidence)

    def test_recosting_rejects_cost_tamper_even_without_replay_check(self):
        symbol = self.arithmetic_symbol(("100", "110"))
        symbol.fills[0]["fee_quote"] = "0"
        with self.assertRaises(ForwardEconomicsError):
            _reconcile_symbol(symbol, "100")

    def test_final_portfolio_reconciliation_rejects_tamper(self):
        symbol = self.arithmetic_symbol(("100", "110"))
        symbol.final_portfolio["closed_trades"] = 99
        with self.assertRaises(ForwardEconomicsError):
            _reconcile_symbol(symbol, "100")

    def test_quantity_cannot_be_changed(self):
        symbol = self.arithmetic_symbol(("100", "110"))
        symbol.fills[0]["quantity"] = "1"
        with self.assertRaises(ForwardEconomicsError):
            _reconcile_symbol(symbol, "100")

    def test_pre_window_fill_rejected(self):
        symbol = self.arithmetic_symbol(("100", "110"))
        symbol.fills[0]["decision_time_ms"] = ForwardWindowSeal().forward_window_start_ms - 3_600_000
        symbol.fills[0]["fill_time_ms"] = symbol.fills[0]["decision_time_ms"]
        with self.assertRaises(ForwardEconomicsError):
            _reconcile_symbol(symbol, "100")

    def test_long_decimal_prices_reconcile_without_float_rounding(self):
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            prices = ("100.123456789012345678901234567890123456789", "101.987654321098765432109876543210987654321")
            symbol = self.arithmetic_symbol(prices)
            report, _, _ = _reconcile_symbol(symbol, "100")
            gross = Decimal("0.001") * (Decimal(prices[1]) - Decimal(prices[0]))
            self.assertEqual(Decimal(report["completed_gross_pnl_quote"]), gross)
            self.assertEqual(Decimal(report["realized_net_pnl_quote"]), gross
                             - Decimal(report["completed_fee_quote"])
                             - Decimal(report["completed_slippage_quote"]))

    def test_different_cutoffs_cannot_be_pooled(self):
        run = replace(self.evidence, symbols=(self.evidence.symbols[0], replace(
            self.evidence.symbols[1], end_time_ms=self.evidence.symbols[1].end_time_ms + 3_600_000)))
        with self.assertRaises(ForwardEconomicsError):
            _assemble(run, {"BTCUSDT": "100", "ETHUSDT": "100"})

    def test_production_module_has_no_external_execution_or_clock(self):
        source = inspect.getsource(economics)
        for forbidden in ("import socket", "import requests", "import urllib",
                          "os.environ", "time.time", "datetime.now", "RiskAuthorization",
                          "QUALIFIED_FOR_P4_RESEARCH", "size_entry(", "api/v3/order"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
