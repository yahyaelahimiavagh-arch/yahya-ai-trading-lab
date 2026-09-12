import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import MarketSnapshot
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS
from yatl.risk import (
    EntryLimitAssessment,
    LimitReason,
    LimitStatus,
    PortfolioRiskState,
    RiskLimitError,
    RiskRequest,
    assess_entry_limits,
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


def sized(*, equity="10000", cash="10000", entry="100", stop="95"):
    snapshot = MarketSnapshot("BTCUSDT", DECISION, _candles("1h"),
                              _candles("15m"), _candles("4h"))
    context = StrategyContext(StrategyIdentity("RISK_FIXTURE", "1.0.0"), snapshot)
    decision = StrategyDecision(
        context, StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
        LongSetup(entry, stop, "115"),
    )
    state = PortfolioRiskState(
        "BTCUSDT", DECISION, equity, cash, "0", entry, equity,
    )
    request = RiskRequest(decision, EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH, state)
    return size_entry(request)


class RiskLimitTests(unittest.TestCase):
    def test_normal_sized_entry_passes_both_caps_and_cash(self):
        result = assess_entry_limits(sized())
        self.assertEqual(result.status, LimitStatus.PASS)
        self.assertEqual(result.reason, LimitReason.WITHIN_LIMITS)
        self.assertLessEqual(Decimal(result.entry_notional_quote),
                             Decimal(result.position_limit_quote))
        self.assertLessEqual(Decimal(result.gross_exposure_after_quote),
                             Decimal(result.gross_exposure_limit_quote))
        self.assertLessEqual(Decimal(result.cash_required_quote), Decimal("10000"))

    def test_entry_fee_is_included_in_cash_required(self):
        result = assess_entry_limits(sized())
        self.assertEqual(
            Decimal(result.cash_required_quote),
            Decimal(result.entry_notional_quote) + Decimal(result.entry_fee_quote),
        )
        self.assertGreater(Decimal(result.entry_fee_quote), 0)

    def test_insufficient_cash_rejects_without_leverage(self):
        result = assess_entry_limits(sized(cash="500"))
        self.assertEqual(result.status, LimitStatus.REJECT)
        self.assertEqual(result.reason, LimitReason.CASH_INSUFFICIENT)
        self.assertGreater(Decimal(result.cash_required_quote), Decimal("500"))

    def test_tight_stop_is_rejected_by_notional_and_exposure_cap(self):
        result = assess_entry_limits(sized(stop="99.9"))
        self.assertEqual(result.status, LimitStatus.REJECT)
        self.assertEqual(result.reason, LimitReason.NOTIONAL_OR_EXPOSURE_LIMIT)
        self.assertGreater(Decimal(result.entry_notional_quote),
                           Decimal(result.position_limit_quote))
        self.assertGreater(Decimal(result.gross_exposure_after_quote),
                           Decimal(result.gross_exposure_limit_quote))

    def test_exact_cap_boundary_passes(self):
        position = sized()
        notional = Decimal(position.quantity) * Decimal(position.entry_execution_price)
        equity = notional / Decimal("0.25")
        adjusted = sized(equity=format(equity, "f"))
        result = assess_entry_limits(adjusted)
        self.assertLessEqual(Decimal(result.entry_notional_quote),
                             Decimal(result.position_limit_quote))

    def test_replay_is_independent_of_ambient_precision(self):
        expected = assess_entry_limits(sized())
        with localcontext() as context:
            context.prec = 6
            replay = assess_entry_limits(sized())
        self.assertEqual(expected, replay)

    def test_invalid_input_and_result_tampering_fail_closed(self):
        for invalid in (None, object(), "size"):
            with self.subTest(invalid=invalid), self.assertRaises(RiskLimitError):
                assess_entry_limits(invalid)
        result = assess_entry_limits(sized())
        for change in (
            {"status": LimitStatus.REJECT},
            {"reason": LimitReason.CASH_INSUFFICIENT},
            {"entry_notional_quote": "0"},
            {"entry_fee_quote": 1.0},
        ):
            with self.subTest(change=change), self.assertRaises(RiskLimitError):
                replace(result, **change)

    def test_assessment_binds_the_original_request(self):
        result = assess_entry_limits(sized())
        self.assertIsInstance(result, EntryLimitAssessment)
        self.assertEqual(result.request_sha256,
                         result.position_size.request.request_sha256)

    @patch("sys.argv", ["yatl", "risk-limit-check"])
    def test_cli_reports_pass_and_cash_rejection_without_approval(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 entry limits", text)
        self.assertIn("normal=PASS/WITHIN_LIMITS", text)
        self.assertIn("low_cash=REJECT/CASH_INSUFFICIENT", text)
        self.assertIn("No approval", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
