import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import yatl.strategy.contracts as strategy_contracts
import yatl.strategy.features as strategy_features
import yatl.strategy.regime as strategy_regime
import yatl.strategy.registry as strategy_registry
import yatl.strategy.trend as trend

from yatl.backtest import BacktestSpec
from yatl.risk import RiskPolicy
from yatl.validation import ValidationCriterion, ValidationEvidenceState
from yatl.validation.registration import (
    CANDIDATE_SOURCE_BLOBS,
    GATE_REGISTRY_ID,
    P10_001_POLICY_SHA256,
    CandidateFreeze,
    CandidateFreezeState,
    CandidateGateRegistration,
    EconomicEvaluationState,
    EconomicGateRegistry,
    ForwardDataState,
    GateRegistrationState,
    RegistrationError,
    ValidationWindowState,
    candidate_from_record,
    gate_registry_from_record,
    registration_from_record,
)


def _git_blob_sha1(path):
    payload = Path(path).read_bytes()
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed).hexdigest()


class CandidateEconomicGateTests(unittest.TestCase):
    def test_candidate_is_exact_trend_pullback_baseline(self):
        candidate = CandidateFreeze()
        self.assertEqual(candidate.strategy_id, "TREND_PULLBACK")
        self.assertEqual(candidate.strategy_version, "1.0.0")
        self.assertEqual(candidate.configuration_sha256, trend.CONFIGURATION.sha256)
        self.assertEqual(candidate.configuration_sha256,
                         "98301c6ee14e9ee01ffdbb1ca68cdce4c0ea0db6a504fc6e4e280bd9f027e20a")
        self.assertEqual(trend.IDENTITY.strategy_id, candidate.strategy_id)
        self.assertEqual(trend.IDENTITY.version, candidate.strategy_version)

    def test_candidate_source_blobs_match_checkout_exactly(self):
        modules = {
            "yatl/strategy/contracts.py": strategy_contracts,
            "yatl/strategy/features.py": strategy_features,
            "yatl/strategy/regime.py": strategy_regime,
            "yatl/strategy/registry.py": strategy_registry,
            "yatl/strategy/trend.py": trend,
        }
        expected = dict(CANDIDATE_SOURCE_BLOBS)
        self.assertEqual(set(modules), set(expected))
        for path, module in modules.items():
            with self.subTest(path=path):
                self.assertEqual(
                    _git_blob_sha1(module.__file__),
                    expected[path],
                )

    def test_selection_is_sample_feasibility_only_not_historical_return(self):
        candidate = CandidateFreeze()
        self.assertEqual(
            candidate.selection_basis,
            "P3_ACCEPTED_SAMPLE_FEASIBILITY_ONLY",
        )
        self.assertFalse(candidate.selection_uses_historical_return)
        self.assertEqual(candidate.accepted_p3_trend_trades, 31)
        self.assertEqual(candidate.accepted_p3_breakout_trades, 4)
        self.assertEqual(candidate.accepted_p3_evidence, "INSUFFICIENT_EVIDENCE")

    def test_candidate_market_scope_and_costs_match_accepted_defaults(self):
        candidate = CandidateFreeze()
        spec = BacktestSpec(
            "BTCUSDT",
            1_800_000_000_000,
            1_800_003_600_000,
        )
        self.assertEqual(candidate.symbols, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(candidate.primary_interval, "1h")
        self.assertEqual(candidate.context_interval, "15m")
        self.assertEqual(candidate.regime_interval, "4h")
        self.assertEqual(
            candidate.execution_price_policy,
            spec.execution_price_policy,
        )
        self.assertEqual(candidate.initial_equity_quote, spec.initial_cash)
        self.assertEqual(candidate.fee_bps, spec.fee_bps)
        self.assertEqual(candidate.slippage_bps, spec.slippage_bps)

    def test_candidate_risk_snapshot_matches_full_accepted_p4_policy(self):
        candidate = CandidateFreeze()
        risk = RiskPolicy()
        self.assertEqual(candidate.risk_policy_id, risk.policy_id)
        self.assertEqual(candidate.risk_per_trade_fraction,
                         risk.risk_per_trade_fraction)
        self.assertEqual(candidate.max_position_fraction,
                         risk.max_position_fraction)
        self.assertEqual(candidate.max_gross_exposure_fraction,
                         risk.max_gross_exposure_fraction)
        self.assertEqual(candidate.max_session_loss_fraction,
                         risk.max_session_loss_fraction)
        self.assertEqual(candidate.max_risk_drawdown_fraction,
                         risk.max_drawdown_fraction)
        self.assertEqual(candidate.max_consecutive_losses,
                         risk.max_consecutive_losses)
        self.assertEqual(candidate.max_open_positions,
                         risk.max_open_positions)

    def test_candidate_baseline_is_non_ai_paper_only_and_authority_free(self):
        candidate = CandidateFreeze()
        self.assertFalse(candidate.baseline_ai_enabled)
        self.assertTrue(candidate.paper_only)
        self.assertEqual(candidate.live_master_lock, "OFF")
        self.assertTrue(candidate.spot_only)
        self.assertTrue(candidate.long_only)
        self.assertFalse(candidate.trade_permission)
        self.assertFalse(candidate.order_endpoint)
        self.assertFalse(candidate.ai_direct_execution)

    def test_candidate_is_frozen_and_digest_is_deterministic(self):
        first = CandidateFreeze()
        second = CandidateFreeze()
        self.assertEqual(first, second)
        self.assertEqual(first.candidate_sha256, second.candidate_sha256)
        self.assertEqual(len(first.candidate_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            first.strategy_id = "RANGE_BREAKOUT"

    def test_candidate_rejects_any_material_mutation(self):
        cases = (
            {"strategy_id": "RANGE_BREAKOUT"},
            {"strategy_version": "1.0.1"},
            {"configuration_sha256": "0" * 64},
            {"fee_bps": "0"},
            {"slippage_bps": "0"},
            {"risk_per_trade_fraction": "0.02"},
            {"max_risk_drawdown_fraction": "0.20"},
            {"selection_uses_historical_return": True},
            {"baseline_ai_enabled": True},
            {"trade_permission": True},
            {"order_endpoint": True},
            {"ai_direct_execution": True},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(RegistrationError):
                CandidateFreeze(**change)

    def test_gate_registry_covers_exactly_all_p10_001_criteria(self):
        gates = EconomicGateRegistry()
        self.assertEqual(
            gates.criteria,
            (
                ValidationCriterion.NET_PNL_AFTER_COSTS,
                ValidationCriterion.MAX_DRAWDOWN,
                ValidationCriterion.SAMPLE_SIZE,
                ValidationCriterion.CONSISTENCY,
                ValidationCriterion.REGIME_STABILITY,
                ValidationCriterion.FAILURE_RECOVERY,
                ValidationCriterion.RISK_CONTROLS,
            ),
        )
        self.assertEqual(len(set(gates.criteria)), 7)

    def test_economic_profitability_gates_are_pre_registered(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.minimum_net_return_after_costs, "0.02")
        self.assertEqual(gates.minimum_profit_factor_after_costs, "1.10")
        self.assertTrue(gates.fee_and_slippage_must_be_included)

    def test_sample_gate_is_90_days_60_total_and_20_per_symbol(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.minimum_validation_days, 90)
        self.assertEqual(gates.minimum_total_completed_trades, 60)
        self.assertEqual(gates.minimum_completed_trades_per_symbol, 20)

    def test_drawdown_gate_is_stricter_than_p4_maximum(self):
        gates = EconomicGateRegistry()
        risk = RiskPolicy()
        self.assertEqual(gates.maximum_validation_drawdown_fraction, "0.08")
        self.assertLess(
            float(gates.maximum_validation_drawdown_fraction),
            float(risk.max_drawdown_fraction),
        )

    def test_consistency_gate_is_exact(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.segment_count, 3)
        self.assertEqual(gates.minimum_positive_segments, 2)
        self.assertEqual(gates.maximum_segment_loss_fraction, "0.04")
        self.assertTrue(gates.positive_net_pnl_each_symbol_required)

    def test_regime_gate_requires_multiple_observed_conditions_and_trend_only_entry(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.minimum_distinct_regimes_observed, 2)
        self.assertEqual(gates.allowed_entry_regimes, ("TREND_UP",))
        self.assertEqual(gates.maximum_entries_outside_allowed_regimes, 0)

    def test_failure_recovery_gate_is_fail_closed(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.maximum_unresolved_data_quality_failures, 0)
        self.assertEqual(gates.maximum_unresolved_reconciliation_failures, 0)
        self.assertEqual(gates.maximum_safety_breaches, 0)
        self.assertEqual(gates.maximum_entries_while_kill_switch_active, 0)
        self.assertTrue(
            gates.recovery_requires_clear_observation_and_manual_reset
        )

    def test_risk_control_gate_allows_zero_authority_violations(self):
        gates = EconomicGateRegistry()
        self.assertEqual(gates.maximum_risk_policy_violations, 0)
        self.assertEqual(gates.maximum_order_endpoint_events, 0)
        self.assertEqual(gates.maximum_ai_direct_execution_events, 0)

    def test_gate_registry_binds_exact_p10_001_policy_and_candidate(self):
        candidate = CandidateFreeze()
        gates = EconomicGateRegistry()
        self.assertEqual(gates.registry_id, GATE_REGISTRY_ID)
        self.assertEqual(gates.p10_001_policy_sha256, P10_001_POLICY_SHA256)
        self.assertEqual(gates.candidate_sha256, candidate.candidate_sha256)

    def test_gate_registry_cannot_be_loosened_or_moved_after_observation(self):
        cases = (
            {"minimum_validation_days": 30},
            {"minimum_total_completed_trades": 30},
            {"minimum_completed_trades_per_symbol": 5},
            {"minimum_net_return_after_costs": "0"},
            {"minimum_profit_factor_after_costs": "1"},
            {"maximum_validation_drawdown_fraction": "0.10"},
            {"minimum_positive_segments": 1},
            {"maximum_segment_loss_fraction": "0.10"},
            {"positive_net_pnl_each_symbol_required": False},
            {"minimum_distinct_regimes_observed": 1},
            {"maximum_entries_outside_allowed_regimes": 1},
            {"maximum_safety_breaches": 1},
            {"maximum_risk_policy_violations": 1},
            {"thresholds_mutable_after_window_open": True},
            {"future_data_used_for_registration": True},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(RegistrationError):
                EconomicGateRegistry(**change)

    def test_registration_bundle_freezes_candidate_and_gates_but_not_window(self):
        registration = CandidateGateRegistration()
        self.assertEqual(registration.candidate_state, CandidateFreezeState.FROZEN)
        self.assertEqual(registration.gate_state, GateRegistrationState.REGISTERED)
        self.assertEqual(registration.window_state, ValidationWindowState.NOT_OPEN)
        self.assertEqual(registration.forward_data_state,
                         ForwardDataState.NOT_COLLECTED)
        self.assertEqual(
            registration.economic_evaluation_state,
            EconomicEvaluationState.NOT_EVALUATED,
        )
        self.assertEqual(
            registration.strategy_evidence,
            ValidationEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertTrue(registration.p11_locked)
        self.assertFalse(registration.live_candidate)
        self.assertFalse(registration.trade_permission)
        self.assertFalse(registration.order_endpoint)
        self.assertFalse(registration.ai_direct_execution)

    def test_registration_digests_are_deterministic_and_cross_bound(self):
        first = CandidateGateRegistration()
        second = CandidateGateRegistration()
        self.assertEqual(first, second)
        self.assertEqual(first.registration_sha256, second.registration_sha256)
        self.assertEqual(
            first.gates.candidate_sha256,
            first.candidate.candidate_sha256,
        )
        self.assertEqual(
            first.gates.p10_001_policy_sha256,
            first.p10_001_policy_sha256,
        )

    def test_strict_round_trip_rejects_schema_smuggling(self):
        candidate = CandidateFreeze()
        gates = EconomicGateRegistry()
        registration = CandidateGateRegistration()

        self.assertEqual(candidate_from_record(candidate.as_record()), candidate)
        self.assertEqual(gate_registry_from_record(gates.as_record()), gates)
        self.assertEqual(
            registration_from_record(registration.as_record()),
            registration,
        )

        candidate_record = candidate.as_record()
        candidate_record["approved_quantity"] = "1"
        with self.assertRaises(RegistrationError):
            candidate_from_record(candidate_record)

        gate_record = gates.as_record()
        gate_record["future_result"] = "PASS"
        with self.assertRaises(RegistrationError):
            gate_registry_from_record(gate_record)

        registration_record = registration.as_record()
        registration_record["states"]["window_state"] = "OPEN"
        with self.assertRaises(RegistrationError):
            registration_from_record(registration_record)

    def test_no_forward_data_or_economic_result_exists_in_registration(self):
        record = CandidateGateRegistration().as_record()
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn("forward_candles", encoded)
        self.assertNotIn("net_pnl_quote", encoded)
        self.assertNotIn("economic_result", encoded)
        self.assertNotIn("PASS_CANDIDATE", encoded)

    def test_registration_source_has_no_data_execution_network_or_provider_capability(self):
        import inspect
        import yatl.validation.registration as registration

        source = inspect.getsource(registration)
        for forbidden in (
            "from yatl.data",
            "import yatl.data",
            "from yatl.strategy",
            "import yatl.strategy",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.analytics",
            "import yatl.analytics",
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
            "sqlite3",
            "pathlib",
            "open(",
            "time.time",
            "datetime",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
