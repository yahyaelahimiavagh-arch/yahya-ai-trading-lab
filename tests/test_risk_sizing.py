import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import BacktestSpec, MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    FEE_BPS,
    QUANTITY_STEP,
    SLIPPAGE_BPS,
    PortfolioRiskState,
    PositionSize,
    RiskRequest,
    RiskSizingError,
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
    return (Candle(DATA_SOURCE, "BTCUSDT", interval, opened,
                   opened + duration - 1, "95", "105", "90", "100",
                   "100", "10000", 20, True),)


def request(*, equity="10000", label=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
            kill_switch=False, entry="100", stop="95"):
    snapshot = MarketSnapshot("BTCUSDT", DECISION, _candles("1h"),
                              _candles("15m"), _candles("4h"))
    context = StrategyContext(StrategyIdentity("RISK_FIXTURE", "1.0.0"), snapshot)
    decision = StrategyDecision(
        context, StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
        LongSetup(entry, stop, "115"),
    )
    state = PortfolioRiskState(
        "BTCUSDT", DECISION, equity, equity, "0", entry, equity,
        kill_switch_active=kill_switch,
    )
    return RiskRequest(decision, label, state)


class RiskSizingTests(unittest.TestCase):
    def test_frozen_costs_match_the_accepted_p2_defaults(self):
        spec = BacktestSpec("BTCUSDT", DECISION, DECISION + 3_600_000)
        self.assertEqual(FEE_BPS, spec.fee_bps_decimal)
        self.assertEqual(SLIPPAGE_BPS, spec.slippage_bps_decimal)

    def test_hand_calculated_cost_aware_vector(self):
        result = size_entry(request())
        self.assertEqual(result.risk_budget_quote, "100.00")
        self.assertEqual(result.entry_execution_price, "100.0500")
        self.assertEqual(result.stop_execution_price, "94.9525")
        self.assertEqual(result.loss_per_unit_quote, "5.2925025")
        self.assertEqual(result.quantity, "18.894653")
        self.assertEqual(result.planned_loss_quote, "99.9999982391325")
        self.assertEqual(result.fee_quote, "3.6845045716325")
        self.assertEqual(result.slippage_quote, "1.8422286675")

    def test_quantity_is_maximum_safe_downward_step(self):
        result = size_entry(request())
        budget = Decimal(result.risk_budget_quote)
        loss_per_unit = Decimal(result.loss_per_unit_quote)
        self.assertLessEqual(Decimal(result.planned_loss_quote), budget)
        self.assertGreater((Decimal(result.quantity) + QUANTITY_STEP) * loss_per_unit,
                           budget)
        self.assertEqual(Decimal(result.quantity) % QUANTITY_STEP, 0)

    def test_fee_and_slippage_are_included_in_planned_loss(self):
        result = size_entry(request())
        reference_loss = Decimal("100") - Decimal("95")
        self.assertGreater(Decimal(result.loss_per_unit_quote), reference_loss)
        self.assertGreater(Decimal(result.fee_quote), 0)
        self.assertGreater(Decimal(result.slippage_quote), 0)

    def test_replay_is_independent_of_ambient_decimal_precision(self):
        expected = size_entry(request())
        with localcontext() as context:
            context.prec = 6
            replay = size_entry(request())
        self.assertEqual(expected, replay)

    def test_equity_and_stop_distance_change_quantity_materially(self):
        base = size_entry(request())
        smaller_equity = size_entry(request(equity="5000"))
        wider_stop = size_entry(request(stop="90"))
        self.assertLess(Decimal(smaller_equity.quantity), Decimal(base.quantity))
        self.assertLess(Decimal(wider_stop.quantity), Decimal(base.quantity))

    def test_insufficient_evidence_and_kill_switch_fail_closed(self):
        invalid = (
            request(label=EvidenceLabel.INSUFFICIENT_EVIDENCE),
            request(kill_switch=True),
        )
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(RiskSizingError):
                size_entry(item)

    def test_non_entry_and_invalid_request_fail_closed(self):
        item = request()
        no_trade = StrategyDecision(
            item.strategy_decision.context, StrategyAction.NO_TRADE,
            DecisionReason.SETUP_ABSENT,
        )
        with self.assertRaises(RiskSizingError):
            size_entry(replace(item, strategy_decision=no_trade))
        for invalid in (None, object(), 1):
            with self.subTest(invalid=invalid), self.assertRaises(RiskSizingError):
                size_entry(invalid)

    def test_budget_below_minimum_step_is_rejected(self):
        with self.assertRaises(RiskSizingError):
            size_entry(request(equity="0.000001", entry="100", stop="0.000001"))

    def test_result_tampering_and_noncanonical_values_fail_closed(self):
        result = size_entry(request())
        for change in (
            {"quantity": "18.894652"},
            {"quantity": "18.8946530"},
            {"planned_loss_quote": "0"},
            {"fee_quote": 1.0},
        ):
            with self.subTest(change=change), self.assertRaises(RiskSizingError):
                replace(result, **change)

    def test_result_binds_request_identity(self):
        result = size_entry(request())
        self.assertEqual(result.request_sha256, result.request.request_sha256)
        self.assertIsInstance(result, PositionSize)

    @patch("sys.argv", ["yatl", "risk-sizing-check"])
    def test_cli_reports_deterministic_paper_sizing(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 exact position sizing", text)
        self.assertIn("qualified_fixture_quantity=", text)
        self.assertIn("current_candidates=BLOCKED", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
