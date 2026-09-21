import inspect
import unittest
from dataclasses import FrozenInstanceError, fields, replace

from yatl.risk import RiskPolicy
from yatl.validation import (
    P4_MAX_CONSECUTIVE_LOSSES,
    P4_MAX_DRAWDOWN_FRACTION,
    P4_MAX_SESSION_LOSS_FRACTION,
    P4_RISK_PER_TRADE_FRACTION,
    VALIDATION_CRITERIA,
    VALIDATION_POLICY_ID,
    CandidateState,
    EconomicEvaluationState,
    ForwardDataState,
    RegistrationState,
    ThresholdState,
    ValidationCharter,
    ValidationContractError,
    ValidationCriterion,
    ValidationEvidenceState,
    ValidationPolicy,
    WindowState,
    validation_charter_from_record,
    validation_policy_from_record,
)


REGISTERED_AT_MS = 1_800_000_000_000


def charter():
    return ValidationCharter(
        "P10-REG-TEST-001",
        REGISTERED_AT_MS,
        ValidationPolicy(),
    )


class ValidationContractTests(unittest.TestCase):
    def test_policy_is_frozen_preregistration_only(self):
        policy = ValidationPolicy()
        self.assertEqual(policy.policy_id, VALIDATION_POLICY_ID)
        self.assertEqual(policy.mode, "PREREGISTRATION_ONLY")
        self.assertTrue(policy.forward_only)
        self.assertTrue(policy.new_data_only)
        self.assertTrue(policy.paper_only)
        self.assertEqual(policy.live_master_lock, "OFF")
        with self.assertRaises(FrozenInstanceError):
            policy.mode = "RUN"

    def test_criteria_are_exact_ordered_and_complete(self):
        self.assertEqual(
            VALIDATION_CRITERIA,
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
        self.assertEqual(len(set(VALIDATION_CRITERIA)), 7)

    def test_net_pnl_is_after_fee_and_slippage(self):
        policy = ValidationPolicy()
        self.assertTrue(policy.net_pnl_after_fee_slippage_required)
        self.assertTrue(policy.risk_adjusted_persistence_required)

    def test_point_in_time_no_lookahead_and_no_post_open_tuning_are_fixed(self):
        policy = ValidationPolicy()
        self.assertTrue(policy.point_in_time_only)
        self.assertTrue(policy.no_lookahead_required)
        self.assertTrue(policy.no_post_open_tuning)

    def test_p10_001_cannot_open_threshold_candidate_window_or_data(self):
        policy = ValidationPolicy()
        self.assertFalse(policy.thresholds_registered)
        self.assertFalse(policy.candidate_frozen)
        self.assertFalse(policy.validation_window_open)
        self.assertFalse(policy.forward_data_collection_allowed)
        self.assertFalse(policy.economic_evaluation_allowed)
        self.assertFalse(policy.strategy_evidence_upgrade_allowed)

    def test_prerequisites_are_required_before_future_window(self):
        policy = ValidationPolicy()
        self.assertTrue(policy.threshold_registration_required_before_window)
        self.assertTrue(policy.candidate_freeze_required_before_window)
        self.assertTrue(policy.window_seal_required_before_data)

    def test_inherited_p4_risk_limits_match_actual_risk_policy(self):
        p4 = RiskPolicy()
        policy = ValidationPolicy()
        self.assertEqual(
            policy.inherited_risk_per_trade_fraction,
            p4.risk_per_trade_fraction,
        )
        self.assertEqual(
            policy.inherited_max_session_loss_fraction,
            p4.max_session_loss_fraction,
        )
        self.assertEqual(
            policy.inherited_max_drawdown_fraction,
            p4.max_drawdown_fraction,
        )
        self.assertEqual(
            policy.inherited_max_consecutive_losses,
            p4.max_consecutive_losses,
        )
        self.assertEqual(P4_RISK_PER_TRADE_FRACTION, "0.01")
        self.assertEqual(P4_MAX_SESSION_LOSS_FRACTION, "0.02")
        self.assertEqual(P4_MAX_DRAWDOWN_FRACTION, "0.10")
        self.assertEqual(P4_MAX_CONSECUTIVE_LOSSES, 3)

    def test_policy_cannot_weaken_risk_limits(self):
        for change in (
            {"inherited_risk_per_trade_fraction": "0.02"},
            {"inherited_max_session_loss_fraction": "0.03"},
            {"inherited_max_drawdown_fraction": "0.20"},
            {"inherited_max_consecutive_losses": 4},
        ):
            with self.subTest(change=change), self.assertRaises(
                ValidationContractError
            ):
                ValidationPolicy(**change)

    def test_policy_cannot_enable_forbidden_authority(self):
        for change in (
            {"allow_short": True},
            {"allow_margin": True},
            {"allow_futures": True},
            {"allow_leverage": True},
            {"allow_withdrawal": True},
            {"allow_credentials": True},
            {"allow_network_transport": True},
            {"allow_upstream_mutation": True},
            {"allow_execution_import": True},
            {"allow_risk_authorization_mutation": True},
            {"allow_quantity_authority": True},
            {"allow_trade_permission": True},
            {"allow_order_endpoint": True},
            {"allow_ai_direct_execution": True},
            {"allow_live_candidate": True},
            {"live_master_lock": "ON"},
            {"paper_only": False},
        ):
            with self.subTest(change=change), self.assertRaises(
                ValidationContractError
            ):
                ValidationPolicy(**change)

    def test_policy_digest_is_deterministic(self):
        first = ValidationPolicy()
        second = ValidationPolicy()
        self.assertEqual(first, second)
        self.assertEqual(first.policy_sha256, second.policy_sha256)
        self.assertEqual(len(first.policy_sha256), 64)

    def test_policy_record_round_trip_is_strict(self):
        policy = ValidationPolicy()
        restored = validation_policy_from_record(policy.as_record())
        self.assertEqual(restored, policy)
        self.assertEqual(restored.policy_sha256, policy.policy_sha256)

    def test_policy_record_rejects_unknown_field_and_tampering(self):
        record = ValidationPolicy().as_record()
        record["authority"] = "TRADE"
        with self.assertRaises(ValidationContractError):
            validation_policy_from_record(record)

        record = ValidationPolicy().as_record()
        record["prerequisites"]["validation_window_open"] = True
        with self.assertRaises(ValidationContractError):
            validation_policy_from_record(record)

    def test_charter_is_explicitly_not_started(self):
        item = charter()
        self.assertEqual(
            item.registration_state,
            RegistrationState.PREREGISTRATION_ONLY,
        )
        self.assertEqual(
            item.candidate_state,
            CandidateState.UNFROZEN_PENDING_P10_002,
        )
        self.assertEqual(
            item.threshold_state,
            ThresholdState.UNREGISTERED_PENDING_P10_002,
        )
        self.assertEqual(item.window_state, WindowState.NOT_OPEN)
        self.assertEqual(item.forward_data_state, ForwardDataState.NOT_COLLECTED)
        self.assertEqual(
            item.economic_evaluation_state,
            EconomicEvaluationState.NOT_EVALUATED,
        )
        self.assertEqual(
            item.strategy_evidence,
            ValidationEvidenceState.INSUFFICIENT_EVIDENCE,
        )

    def test_charter_digest_is_deterministic_and_policy_bound(self):
        first = charter()
        second = charter()
        self.assertEqual(first, second)
        self.assertEqual(first.charter_sha256, second.charter_sha256)
        self.assertEqual(
            first.as_record()["policy_sha256"],
            first.policy.policy_sha256,
        )

    def test_charter_cannot_claim_candidate_threshold_window_data_or_evaluation(self):
        item = charter()
        cases = (
            {"candidate_state": "FROZEN"},
            {"threshold_state": "REGISTERED"},
            {"window_state": "OPEN"},
            {"forward_data_state": "COLLECTED"},
            {"economic_evaluation_state": "PASS"},
            {"strategy_evidence": "QUALIFIED"},
        )
        for change in cases:
            record = item.as_record()
            for key, value in change.items():
                record[key] = value
            with self.subTest(change=change), self.assertRaises(
                ValidationContractError
            ):
                validation_charter_from_record(record)

    def test_charter_record_round_trip_is_strict(self):
        item = charter()
        restored = validation_charter_from_record(item.as_record())
        self.assertEqual(restored, item)
        self.assertEqual(restored.charter_sha256, item.charter_sha256)

    def test_charter_rejects_schema_smuggling(self):
        record = charter().as_record()
        record["approved_quantity"] = "1"
        with self.assertRaises(ValidationContractError):
            validation_charter_from_record(record)

    def test_strategy_evidence_enum_has_no_upgrade_member(self):
        self.assertEqual(
            tuple(item.value for item in ValidationEvidenceState),
            ("INSUFFICIENT_EVIDENCE",),
        )

    def test_no_pass_or_live_ready_disposition_exists_in_p10_001(self):
        import yatl.validation.contracts as contracts

        names = {
            name
            for name, value in vars(contracts).items()
            if isinstance(value, type)
        }
        self.assertNotIn("ValidationResult", names)
        self.assertNotIn("ValidationVerdict", names)
        self.assertNotIn("LiveReadiness", names)

    def test_no_p10_numeric_economic_threshold_is_registered_yet(self):
        names = {item.name for item in fields(ValidationPolicy)}
        forbidden = {
            "minimum_completed_trades",
            "minimum_validation_days",
            "minimum_net_pnl",
            "minimum_profit_factor",
            "minimum_positive_weeks",
            "maximum_validation_drawdown",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    def test_contract_source_has_no_data_execution_account_network_or_provider_capability(self):
        import yatl.validation.contracts as contracts

        source = inspect.getsource(contracts)
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
