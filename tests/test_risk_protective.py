import contextlib
import io
import unittest
from dataclasses import fields, replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    PortfolioRiskState,
    ProtectiveAssessment,
    ProtectiveGateError,
    ProtectiveReason,
    ProtectiveStatus,
    RiskRequest,
    assess_entry_limits,
    assess_protective_entry,
    size_entry,
)
from yatl.strategy import (
    DecisionReason,
    EvidenceLabel,
    LongSetup,
    StrategyAction,
    StrategyContext,
    StrategyDecision,
    StrategyIdentity,
)


DECISION = 1_699_999_200_000


def _candles(interval):
    duration = INTERVAL_MILLISECONDS[interval]
    opened = (DECISION // duration) * duration - duration
    return (Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        "95", "105", "90", "100", "100", "10000", 20, True,
    ),)


def assessment(*, equity="10000", cash="10000", entry="100", stop="95",
               target="115"):
    snapshot = MarketSnapshot(
        "BTCUSDT", DECISION, _candles("1h"), _candles("15m"), _candles("4h"),
    )
    context = StrategyContext(StrategyIdentity("RISK_FIXTURE", "1.0.0"), snapshot)
    decision = StrategyDecision(
        context, StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
        LongSetup(entry, stop, target),
    )
    state = PortfolioRiskState(
        "BTCUSDT", DECISION, equity, cash, "0", entry, equity,
    )
    request = RiskRequest(decision, EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH, state)
    return assess_protective_entry(assess_entry_limits(size_entry(request)))


class ProtectiveGateTests(unittest.TestCase):
    def test_valid_bracket_passes_with_positive_post_cost_reward(self):
        result = assessment()
        self.assertIsInstance(result, ProtectiveAssessment)
        self.assertEqual(result.status, ProtectiveStatus.PASS)
        self.assertEqual(result.reason, ProtectiveReason.PROTECTIVE_GATE_PASSED)
        self.assertGreater(Decimal(result.net_reward_quote), 0)
        self.assertLess(Decimal(result.stop_execution_price),
                        Decimal(result.entry_execution_price))

    def test_worst_loss_matches_sizing_and_stays_within_budget(self):
        result = assessment()
        size = result.limit_assessment.position_size
        self.assertEqual(result.worst_loss_quote, size.planned_loss_quote)
        self.assertLessEqual(Decimal(result.worst_loss_quote),
                             Decimal(result.risk_budget_quote))

    def test_tiny_raw_target_is_rejected_after_costs(self):
        result = assessment(target="100.1")
        self.assertEqual(result.status, ProtectiveStatus.REJECT)
        self.assertEqual(
            result.reason, ProtectiveReason.NON_POSITIVE_POST_COST_REWARD,
        )
        self.assertLessEqual(Decimal(result.net_reward_quote), 0)

    def test_prior_cash_or_exposure_rejection_has_deterministic_priority(self):
        low_cash = assessment(cash="500")
        tight_stop = assessment(stop="99.9")
        for result in (low_cash, tight_stop):
            with self.subTest(result=result):
                self.assertEqual(result.status, ProtectiveStatus.REJECT)
                self.assertEqual(result.reason, ProtectiveReason.PRIOR_LIMIT_REJECTED)

    def test_exact_fee_and_execution_arithmetic(self):
        result = assessment()
        quantity = Decimal(result.quantity)
        target_execution = Decimal("115") * Decimal("0.9995")
        target_fee = quantity * target_execution * Decimal("0.001")
        self.assertEqual(Decimal(result.target_execution_price), target_execution)
        self.assertEqual(Decimal(result.target_fee_quote), target_fee)

    def test_replay_and_hash_are_deterministic_and_material(self):
        first = assessment()
        replay = assessment()
        changed = assessment(target="116")
        self.assertEqual(first, replay)
        self.assertEqual(first.gate_sha256, replay.gate_sha256)
        self.assertEqual(len(first.gate_sha256), 64)
        self.assertNotEqual(first.gate_sha256, changed.gate_sha256)

    def test_result_binds_upstream_request_and_limit_evidence(self):
        result = assessment()
        self.assertEqual(result.request_sha256,
                         result.limit_assessment.request_sha256)
        self.assertEqual(result.quantity,
                         result.limit_assessment.position_size.quantity)

    def test_result_tampering_and_noncanonical_values_fail_closed(self):
        result = assessment()
        for change in (
            {"status": ProtectiveStatus.REJECT},
            {"reason": ProtectiveReason.NON_POSITIVE_POST_COST_REWARD},
            {"worst_loss_quote": "0"},
            {"net_reward_quote": "1.0"},
            {"target_fee_quote": 1.0},
        ):
            with self.subTest(change=change), self.assertRaises(ProtectiveGateError):
                replace(result, **change)

    def test_invalid_inputs_fail_closed(self):
        for invalid in (None, object(), "limits", 1):
            with self.subTest(invalid=invalid), self.assertRaises(ProtectiveGateError):
                assess_protective_entry(invalid)

    def test_replay_is_independent_of_ambient_decimal_precision(self):
        expected = assessment()
        with localcontext() as context:
            context.prec = 6
            replay = assessment()
        self.assertEqual(expected, replay)
        self.assertEqual(expected.gate_sha256, replay.gate_sha256)

    def test_contract_has_no_execution_or_credential_fields(self):
        names = {item.name for item in fields(ProtectiveAssessment)}
        forbidden = {
            "order", "broker", "api_key", "api_secret", "endpoint",
            "withdrawal_address", "account_id", "approval",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    @patch("sys.argv", ["yatl", "risk-protective-check"])
    def test_cli_reports_pass_and_post_cost_rejection(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 protective entry gate", text)
        self.assertIn("normal=PASS/PROTECTIVE_GATE_PASSED", text)
        self.assertIn("weak_target=REJECT/NON_POSITIVE_POST_COST_REWARD", text)
        self.assertIn("No approval", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
