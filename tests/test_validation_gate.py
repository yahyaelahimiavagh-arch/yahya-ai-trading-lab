import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import replace

from yatl.validation.economics import ForwardEconomicsReport, calculate_forward_economics
from yatl.validation.gate import (
    CriterionStatus,
    ForwardGateError,
    GateDisposition,
    _criteria,
    _disposition,
    _segment_summary,
    evaluate_forward_gate,
)
from yatl.validation.paper_runner import run_forward_paper
from yatl.validation.paper_runner_runtime import build_mock_forward_runner_fixture
from yatl.validation.registration import EconomicGateRegistry


DAY_MS = 86_400_000


class ForwardGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.store, cls.snapshot, _ = build_mock_forward_runner_fixture(cls.directory.name)
        cls.run = run_forward_paper(cls.store, cls.snapshot)
        cls.economics = calculate_forward_economics(cls.store, cls.snapshot, cls.run)
        cls.report = evaluate_forward_gate(cls.store, cls.snapshot, cls.run, cls.economics)
        cls.gates = EconomicGateRegistry()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.directory.cleanup()

    def regime(self, **changes):
        value = {
            "distinct_non_unknown_regimes": ["RANGE", "TREND_UP"],
            "distinct_non_unknown_regime_count": 2,
            "unknown_observations": 0,
            "entries_outside_allowed_regimes": 0,
            "entries_while_kill_switch_active": 0,
            "risk_policy_violations": 0,
            "symbols": [],
        }
        value.update(changes)
        return value

    def economics_record(self):
        start = 1_000_000_000_000
        end = start + 90 * DAY_MS
        btc_trades = [
            {
                "symbol": "BTCUSDT",
                "entry_time_ms": start + 5 * DAY_MS,
                "exit_time_ms": start + 10 * DAY_MS,
                "holding_ms": 5 * DAY_MS,
                "gross_pnl_quote": "210",
                "fee_quote": "5",
                "slippage_quote": "5",
                "net_pnl_quote": "200",
            },
            {
                "symbol": "BTCUSDT",
                "entry_time_ms": start + 35 * DAY_MS,
                "exit_time_ms": start + 40 * DAY_MS,
                "holding_ms": 5 * DAY_MS,
                "gross_pnl_quote": "210",
                "fee_quote": "5",
                "slippage_quote": "5",
                "net_pnl_quote": "200",
            },
        ]
        eth_trades = [
            {
                "symbol": "ETHUSDT",
                "entry_time_ms": start + 65 * DAY_MS,
                "exit_time_ms": start + 70 * DAY_MS,
                "holding_ms": 5 * DAY_MS,
                "gross_pnl_quote": "210",
                "fee_quote": "5",
                "slippage_quote": "5",
                "net_pnl_quote": "200",
            }
        ]

        def symbol_record(symbol, final_equity, net, trades):
            return {
                "symbol": symbol,
                "initial_equity_quote": "10000",
                "final_equity_quote": final_equity,
                "net_pnl_after_costs_quote": net,
                "net_return_after_costs": str(int(net) / 10000),
                "realized_net_pnl_quote": net,
                "unrealized_liquidation_net_pnl_quote": "0",
                "completed_gross_pnl_quote": str(int(net) + 20),
                "completed_fee_quote": "10",
                "completed_slippage_quote": "10",
                "executed_fee_quote": "10",
                "executed_slippage_quote": "10",
                "executed_total_cost_quote": "20",
                "open_entry_fee_quote": "0",
                "open_entry_slippage_quote": "0",
                "open_positions": 0,
                "open_holding_ms": 0,
                "position_time_ms": 5 * DAY_MS,
                "position_time_fraction": "0.055555555555555556",
                "maximum_sampled_notional_quote": "1000",
                "realized_drawdown": {
                    "maximum_drawdown_quote": "100",
                    "maximum_drawdown_fraction": "0.01",
                },
                "sampled_liquidation_drawdown": {
                    "maximum_drawdown_quote": "200",
                    "maximum_drawdown_fraction": "0.02",
                },
                "kill_switch_latched": False,
                "entries_blocked": 0,
                "trades": trades,
                "completed_trades": 30,
                "winning_trades": 20,
                "losing_trades": 10,
                "breakeven_trades": 0,
                "win_rate": "0.6666666666666667",
                "profit_factor_after_costs": "1.2",
                "profit_factor_status": "DEFINED",
                "mean_completed_holding_ms": str(5 * DAY_MS),
                "maximum_completed_holding_ms": 5 * DAY_MS,
            }

        return {
            "economics_id": "P10_FORWARD_ECONOMICS_V1",
            "input_run_sha256": self.run.run_sha256,
            "ingestion_snapshot_sha256": self.snapshot.snapshot_sha256,
            "window_sha256": self.run.window_sha256,
            "candidate_sha256": self.run.candidate_sha256,
            "gate_registry_sha256": self.run.gate_registry_sha256,
            "observation_start_ms": start,
            "observation_end_ms": end,
            "observation_duration_ms": end - start,
            "observed_days": "90",
            "sample_status": "MINIMUM_SAMPLE_MET_ONLY",
            "insufficiency_reasons": [],
            "symbols": [
                symbol_record("BTCUSDT", "10400", "400", btc_trades),
                symbol_record("ETHUSDT", "10200", "200", eth_trades),
            ],
            "pooled": {
                "capital_basis": "SUM_OF_INDEPENDENT_P10_005_SYMBOL_PORTFOLIOS",
                "initial_equity_quote": "20000",
                "final_equity_quote": "20600",
                "net_pnl_after_costs_quote": "600",
                "net_return_after_costs": "0.03",
                "realized_drawdown": {
                    "maximum_drawdown_quote": "200",
                    "maximum_drawdown_fraction": "0.01",
                },
                "sampled_liquidation_drawdown": {
                    "maximum_drawdown_quote": "400",
                    "maximum_drawdown_fraction": "0.02",
                },
                "completed_trades": 60,
                "winning_trades": 40,
                "losing_trades": 20,
                "breakeven_trades": 0,
                "win_rate": "0.6666666666666667",
                "profit_factor_after_costs": "1.2",
                "profit_factor_status": "DEFINED",
                "mean_completed_holding_ms": str(5 * DAY_MS),
                "maximum_completed_holding_ms": 5 * DAY_MS,
                "realized_net_pnl_quote": "600",
                "unrealized_liquidation_net_pnl_quote": "0",
                "completed_gross_pnl_quote": "630",
                "completed_fee_quote": "15",
                "completed_slippage_quote": "15",
                "executed_fee_quote": "15",
                "executed_slippage_quote": "15",
                "executed_total_cost_quote": "30",
                "open_entry_fee_quote": "0",
                "open_entry_slippage_quote": "0",
                "open_positions": 0,
            },
            "semantics": {},
            "safety": self.economics.as_record()["safety"],
        }

    def statuses(self, economics=None, regime=None, run=None):
        results = _criteria(
            self.snapshot,
            self.run if run is None else run,
            self.economics_record() if economics is None else economics,
            self.regime() if regime is None else regime,
            self.gates,
        )
        return {item["criterion"]: item["status"] for item in results}

    def test_mocked_integration_is_insufficient_not_pass(self):
        record = self.report.as_record()
        self.assertEqual(record["disposition"], "INSUFFICIENT_DATA")
        self.assertEqual(len(record["criteria"]), 7)
        self.assertEqual(
            [item["criterion"] for item in record["criteria"]],
            [item.value for item in self.gates.criteria],
        )

    def test_mocked_report_hash_is_stable(self):
        record = self.report.as_record()
        before = self.report.report_sha256
        record["disposition"] = "PASS_CANDIDATE"
        self.assertEqual(
            hashlib.sha256(self.report.canonical_json.encode()).hexdigest(),
            before,
        )

    def test_gate_reconciles_exact_economics(self):
        repeated = evaluate_forward_gate(self.store, self.snapshot, self.run, self.economics)
        self.assertEqual(repeated.canonical_json, self.report.canonical_json)

    def test_gate_rejects_detached_mutated_economics(self):
        changed = self.economics.as_record()
        changed["pooled"]["net_return_after_costs"] = "9"
        fake = ForwardEconomicsReport(
            json.dumps(changed, sort_keys=True, separators=(",", ":"))
        )
        with self.assertRaises(ForwardGateError):
            evaluate_forward_gate(self.store, self.snapshot, self.run, fake)

    def test_gate_rejects_non_economics_input(self):
        with self.assertRaises(ForwardGateError):
            evaluate_forward_gate(self.store, self.snapshot, self.run, {})

    def test_registered_pass_fixture_passes_all_criteria(self):
        statuses = self.statuses()
        self.assertTrue(all(value == "PASS" for value in statuses.values()))
        criteria = _criteria(
            self.snapshot, self.run, self.economics_record(), self.regime(), self.gates
        )
        self.assertEqual(_disposition(criteria), GateDisposition.PASS_CANDIDATE)

    def test_sample_shortage_waits_instead_of_fabricating_failure(self):
        record = self.economics_record()
        record["sample_status"] = "INSUFFICIENT_DATA"
        record["insufficiency_reasons"] = ["MINIMUM_DURATION_NOT_MET"]
        statuses = self.statuses(record)
        for criterion in (
            "NET_PNL_AFTER_COSTS",
            "MAX_DRAWDOWN",
            "SAMPLE_SIZE",
            "CONSISTENCY",
            "REGIME_STABILITY",
        ):
            self.assertEqual(statuses[criterion], "INSUFFICIENT_DATA")
        self.assertEqual(statuses["FAILURE_RECOVERY"], "PASS")
        self.assertEqual(statuses["RISK_CONTROLS"], "PASS")

    def test_drawdown_breach_fails_even_before_minimum_sample(self):
        record = self.economics_record()
        record["sample_status"] = "INSUFFICIENT_DATA"
        record["insufficiency_reasons"] = ["MINIMUM_DURATION_NOT_MET"]
        record["pooled"]["sampled_liquidation_drawdown"][
            "maximum_drawdown_fraction"
        ] = "0.081"
        self.assertEqual(self.statuses(record)["MAX_DRAWDOWN"], "FAIL")

    def test_profitability_uses_net_return_and_profit_factor(self):
        record = self.economics_record()
        record["pooled"]["net_return_after_costs"] = "0.019"
        self.assertEqual(self.statuses(record)["NET_PNL_AFTER_COSTS"], "FAIL")
        record = self.economics_record()
        record["pooled"]["profit_factor_after_costs"] = "1.09"
        self.assertEqual(self.statuses(record)["NET_PNL_AFTER_COSTS"], "FAIL")

    def test_undefined_profit_factor_fails_closed_after_sample(self):
        record = self.economics_record()
        record["pooled"]["profit_factor_after_costs"] = None
        record["pooled"]["profit_factor_status"] = "UNDEFINED_NO_LOSSES"
        self.assertEqual(self.statuses(record)["NET_PNL_AFTER_COSTS"], "FAIL")

    def test_segments_are_three_equal_time_buckets(self):
        summary = _segment_summary(self.economics_record(), self.gates)
        self.assertEqual(len(summary["segments"]), 3)
        self.assertEqual(summary["positive_segments"], 3)
        self.assertEqual(
            [item["net_pnl_after_costs_quote"] for item in summary["segments"]],
            ["200", "200", "200"],
        )

    def test_open_liquidation_pnl_is_assigned_only_to_last_segment(self):
        record = self.economics_record()
        record["symbols"][1]["unrealized_liquidation_net_pnl_quote"] = "100"
        record["symbols"][1]["net_pnl_after_costs_quote"] = "300"
        record["pooled"]["unrealized_liquidation_net_pnl_quote"] = "100"
        record["pooled"]["net_pnl_after_costs_quote"] = "700"
        record["pooled"]["net_return_after_costs"] = "0.035"
        summary = _segment_summary(record, self.gates)
        self.assertEqual(
            [item["net_pnl_after_costs_quote"] for item in summary["segments"]],
            ["200", "200", "300"],
        )

    def test_segment_reconciliation_fails_closed(self):
        record = self.economics_record()
        record["pooled"]["net_pnl_after_costs_quote"] = "601"
        with self.assertRaises(ForwardGateError):
            _segment_summary(record, self.gates)

    def test_consistency_requires_two_positive_segments(self):
        record = self.economics_record()
        record["symbols"][0]["trades"][0]["net_pnl_quote"] = "-200"
        record["symbols"][0]["net_pnl_after_costs_quote"] = "0"
        record["pooled"]["net_pnl_after_costs_quote"] = "200"
        record["pooled"]["net_return_after_costs"] = "0.01"
        self.assertEqual(self.statuses(record)["CONSISTENCY"], "FAIL")

    def test_consistency_requires_each_symbol_positive(self):
        record = self.economics_record()
        record["symbols"][1]["net_pnl_after_costs_quote"] = "0"
        self.assertEqual(self.statuses(record)["CONSISTENCY"], "FAIL")

    def test_regime_requires_two_non_unknown_conditions_after_sample(self):
        regime = self.regime(
            distinct_non_unknown_regimes=["TREND_UP"],
            distinct_non_unknown_regime_count=1,
        )
        self.assertEqual(self.statuses(regime=regime)["REGIME_STABILITY"], "FAIL")

    def test_out_of_regime_entry_is_immediate_failure(self):
        record = self.economics_record()
        record["sample_status"] = "INSUFFICIENT_DATA"
        record["insufficiency_reasons"] = ["MINIMUM_DURATION_NOT_MET"]
        regime = self.regime(entries_outside_allowed_regimes=1)
        self.assertEqual(self.statuses(record, regime)["REGIME_STABILITY"], "FAIL")

    def test_kill_switch_entry_fails_failure_recovery(self):
        regime = self.regime(entries_while_kill_switch_active=1)
        self.assertEqual(self.statuses(regime=regime)["FAILURE_RECOVERY"], "FAIL")

    def test_latched_kill_switch_without_reset_evidence_fails(self):
        symbol = replace(self.run.symbols[0], kill_switch_latched=True)
        run = replace(self.run, symbols=(symbol, self.run.symbols[1]))
        self.assertEqual(self.statuses(run=run)["FAILURE_RECOVERY"], "FAIL")

    def test_risk_policy_violation_fails_risk_controls(self):
        regime = self.regime(risk_policy_violations=1)
        self.assertEqual(self.statuses(regime=regime)["RISK_CONTROLS"], "FAIL")

    def test_fail_precedes_insufficient(self):
        criteria = [
            {"status": CriterionStatus.INSUFFICIENT_DATA.value},
            {"status": CriterionStatus.FAIL.value},
        ]
        self.assertEqual(_disposition(criteria), GateDisposition.FAIL)

    def test_insufficient_precedes_pass_candidate(self):
        criteria = [
            {"status": CriterionStatus.PASS.value},
            {"status": CriterionStatus.INSUFFICIENT_DATA.value},
        ]
        self.assertEqual(_disposition(criteria), GateDisposition.INSUFFICIENT_DATA)

    def test_pass_candidate_requires_every_criterion_pass(self):
        criteria = [{"status": CriterionStatus.PASS.value} for _ in range(7)]
        self.assertEqual(_disposition(criteria), GateDisposition.PASS_CANDIDATE)

    def test_safety_locks_remain_closed(self):
        safety = self.report.as_record()["safety"]
        self.assertTrue(safety["paper_only"])
        self.assertEqual(safety["live_master_lock"], "OFF")
        self.assertEqual(safety["strategy_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(safety["p11_unlocked"])
        self.assertFalse(safety["pass_candidate_is_live_authorization"])
        self.assertFalse(safety["trade_permission"])
        self.assertFalse(safety["order_endpoint"])
        self.assertFalse(safety["ai_direct_execution"])

    def test_source_has_no_network_clock_secret_or_execution_capability(self):
        source = inspect.getsource(__import__("yatl.validation.gate", fromlist=["*"]))
        forbidden = (
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "os.environ",
            "os.getenv",
            "API_KEY",
            "API_SECRET",
            "openai",
            "anthropic",
            "datetime.now",
            "time.time",
            "subprocess",
            "sqlite3",
            "api/v3/order",
            "/fapi",
            "/dapi",
        )
        for item in forbidden:
            self.assertNotIn(item, source)


if __name__ == "__main__":
    unittest.main()
