import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (BacktestSpec, EquityPoint, FillReason, FillReference,
                           IntentAction, MetricsError, PortfolioLedger,
                           calculate_metrics, apply_costs)
from yatl.backtest.costs import DECIMAL_PRECISION


TIME = 1_699_999_200_000


def spec():
    return BacktestSpec("BTCUSDT", TIME, TIME + 4 * 3_600_000,
                        initial_cash="1000")


def costed(configuration, action, at, price="100"):
    reason = (FillReason.NEXT_PRIMARY_OPEN if action is IntentAction.ENTER_LONG
              else FillReason.SCRIPTED_EXIT)
    return apply_costs(FillReference(action, configuration.symbol, at, at,
                                     "2", price, reason), configuration)


def round_trip_points(exit_price="110"):
    configuration = spec()
    ledger = PortfolioLedger(configuration)
    points = [EquityPoint(TIME, ledger.snapshot("100"))]
    ledger.apply(costed(configuration, IntentAction.ENTER_LONG, TIME + 3_600_000))
    points.append(EquityPoint(TIME + 3_600_000, ledger.snapshot("100")))
    ledger.apply(costed(configuration, IntentAction.EXIT_LONG,
                        TIME + 2 * 3_600_000, exit_price))
    points.append(EquityPoint(TIME + 2 * 3_600_000, ledger.snapshot(exit_price)))
    return tuple(points)


class PerformanceMetricsTests(unittest.TestCase):
    def test_hand_computed_profitable_round_trip(self):
        report = calculate_metrics(round_trip_points())
        self.assertEqual(report.initial_equity_quote, Decimal("1000"))
        self.assertEqual(report.final_equity_quote, Decimal("1019.37001"))
        self.assertEqual(report.net_pnl_quote, Decimal("19.37001"))
        self.assertEqual(report.total_fee_quote, Decimal("0.41999"))
        self.assertEqual(report.total_slippage_quote, Decimal("0.210"))
        self.assertEqual(report.total_cost_quote, Decimal("0.629990"))
        self.assertEqual(report.gross_pnl_quote, Decimal("20.000000"))
        self.assertEqual(report.total_return, Decimal("0.01937001"))
        self.assertEqual((report.trade_count, report.winning_trades,
                          report.losing_trades, report.breakeven_trades),
                         (1, 1, 0, 0))
        self.assertEqual(report.win_rate, Decimal(1))
        self.assertEqual(report.maximum_drawdown_quote, Decimal("0.60000"))
        self.assertEqual(report.maximum_drawdown, Decimal("0.00060"))

    def test_no_trade_and_single_point_undefined_samples(self):
        ledger = PortfolioLedger(spec())
        report = calculate_metrics((EquityPoint(TIME, ledger.snapshot("100")),))
        self.assertEqual(report.total_return, 0)
        self.assertEqual(report.trade_count, 0)
        self.assertIsNone(report.win_rate)
        self.assertIsNone(report.mean_period_return)
        self.assertIsNone(report.sample_period_volatility)
        self.assertIsNone(report.downside_deviation)
        self.assertIsNone(report.mean_over_volatility)
        self.assertIsNone(report.mean_over_downside)

    def test_one_period_has_mean_but_sample_volatility_is_undefined(self):
        points = round_trip_points()
        report = calculate_metrics((points[0], points[-1]))
        self.assertEqual(report.mean_period_return, Decimal("0.01937001"))
        self.assertIsNone(report.sample_period_volatility)
        self.assertIsNone(report.downside_deviation)

    def test_risk_adjusted_values_follow_documented_formulas(self):
        report = calculate_metrics(round_trip_points())
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            first_return = Decimal("999.40000") / Decimal("1000") - 1
            second_return = Decimal("1019.37001") / Decimal("999.40000") - 1
            mean = (first_return + second_return) / 2
            sample_volatility = (((first_return - mean) ** 2
                                  + (second_return - mean) ** 2)).sqrt()
            downside = ((first_return ** 2) / 2).sqrt()
            mean_over_volatility = mean / sample_volatility
            mean_over_downside = mean / downside
        self.assertEqual(report.mean_period_return, mean)
        self.assertEqual(report.sample_period_volatility, sample_volatility)
        self.assertEqual(report.downside_deviation, downside)
        self.assertEqual(report.mean_over_volatility, mean_over_volatility)
        self.assertEqual(report.mean_over_downside, mean_over_downside)

    def test_loss_and_drawdown_recovery_are_counted(self):
        report = calculate_metrics(round_trip_points("90"))
        self.assertEqual((report.trade_count, report.winning_trades,
                          report.losing_trades), (1, 0, 1))
        self.assertEqual(report.win_rate, 0)
        self.assertLess(report.net_pnl_quote, 0)
        self.assertGreater(report.maximum_drawdown_quote, 0)
        self.assertGreater(report.maximum_drawdown, 0)

    def test_invalid_curves_fail_closed(self):
        points = round_trip_points()
        with self.assertRaises(MetricsError):
            calculate_metrics([])
        with self.assertRaises(MetricsError):
            calculate_metrics((points[1], points[2]))
        with self.assertRaises(MetricsError):
            calculate_metrics((points[0], EquityPoint(TIME, points[2].portfolio)))

        configuration = spec()
        ledger = PortfolioLedger(configuration)
        ledger.apply(costed(configuration, IntentAction.ENTER_LONG, TIME + 3_600_000))
        with self.assertRaises(MetricsError):
            calculate_metrics((EquityPoint(TIME, PortfolioLedger(configuration).snapshot("100")),
                               EquityPoint(TIME + 3_600_000, ledger.snapshot("100"))))

    def test_report_tampering_and_realized_pnl_without_close_fail_closed(self):
        report = calculate_metrics(round_trip_points())
        with self.assertRaises(MetricsError):
            replace(report, net_pnl_quote=report.net_pnl_quote + 1)

        points = list(round_trip_points())
        bad_snapshot = replace(points[1].portfolio, realized_pnl_quote=Decimal("1"))
        with self.assertRaises(MetricsError):
            calculate_metrics((points[0], EquityPoint(points[1].time_ms, bad_snapshot),
                               points[2]))

    @patch("sys.argv", ["yatl", "backtest-metrics-check"])
    def test_cli_reports_safe_hand_computed_metrics(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("gross_pnl=20.000000", text)
        self.assertIn("net_pnl=19.370010", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
