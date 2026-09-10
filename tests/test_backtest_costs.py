import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (BacktestSpec, CostModelError, FillReason,
                           FillReference, IntentAction, apply_costs)


TIME = 1_699_999_200_000


def spec(**changes):
    values = {"symbol": "BTCUSDT", "start_time_ms": TIME,
              "end_time_ms": TIME + 3_600_000}
    values.update(changes)
    return BacktestSpec(**values)


def reference(action, *, quantity="2", price="100", symbol="BTCUSDT"):
    reason = (FillReason.NEXT_PRIMARY_OPEN if action is IntentAction.ENTER_LONG
              else FillReason.SCRIPTED_EXIT)
    return FillReference(action, symbol, TIME, TIME, quantity, price, reason)


class BacktestCostTests(unittest.TestCase):
    def test_hand_calculated_entry_vector(self):
        fill = apply_costs(reference(IntentAction.ENTER_LONG), spec())
        self.assertEqual(fill.execution_price, Decimal("100.05"))
        self.assertEqual(fill.gross_quote, Decimal("200.10"))
        self.assertEqual(fill.fee_quote, Decimal("0.20010"))
        self.assertEqual(fill.slippage_quote, Decimal("0.10"))
        self.assertEqual(fill.cash_delta, Decimal("-200.30010"))
        self.assertEqual(fill.asset_delta, Decimal("2"))
        self.assertEqual(fill.total_cost_quote, Decimal("0.30010"))

    def test_hand_calculated_exit_and_round_trip_vector(self):
        entry = apply_costs(reference(IntentAction.ENTER_LONG), spec())
        exit_fill = apply_costs(reference(IntentAction.EXIT_LONG), spec())
        self.assertEqual(exit_fill.execution_price, Decimal("99.95"))
        self.assertEqual(exit_fill.gross_quote, Decimal("199.90"))
        self.assertEqual(exit_fill.fee_quote, Decimal("0.19990"))
        self.assertEqual(exit_fill.slippage_quote, Decimal("0.10"))
        self.assertEqual(exit_fill.cash_delta, Decimal("199.70010"))
        self.assertEqual(exit_fill.asset_delta, Decimal("-2"))
        self.assertEqual(entry.cash_delta + exit_fill.cash_delta, Decimal("-0.60000"))

    def test_zero_and_maximum_cost_bounds(self):
        zero = spec(fee_bps="0", slippage_bps="0")
        self.assertEqual(apply_costs(reference(IntentAction.ENTER_LONG), zero).cash_delta,
                         Decimal("-200"))
        maximum = spec(fee_bps="1000", slippage_bps="1000")
        entry = apply_costs(reference(IntentAction.ENTER_LONG), maximum)
        exit_fill = apply_costs(reference(IntentAction.EXIT_LONG), maximum)
        self.assertEqual((entry.execution_price, entry.fee_quote, entry.cash_delta),
                         (Decimal("110.0"), Decimal("22.00"), Decimal("-242.00")))
        self.assertEqual((exit_fill.execution_price, exit_fill.fee_quote,
                          exit_fill.cash_delta),
                         (Decimal("90.0"), Decimal("18.00"), Decimal("162.00")))

    def test_increasing_costs_never_improves_cash_effect(self):
        low = spec(fee_bps="1", slippage_bps="1")
        high = spec(fee_bps="100", slippage_bps="100")
        for action in (IntentAction.ENTER_LONG, IntentAction.EXIT_LONG):
            with self.subTest(action=action):
                low_fill = apply_costs(reference(action), low)
                high_fill = apply_costs(reference(action), high)
                self.assertLess(high_fill.cash_delta, low_fill.cash_delta)
                self.assertGreater(high_fill.total_cost_quote, low_fill.total_cost_quote)

    def test_large_decimal_product_preserves_exact_internal_precision(self):
        quantity = "9999999999999999999999999999999999999999"
        price = "9999999999999999999999999999999999999999"
        fill = apply_costs(reference(IntentAction.ENTER_LONG,
                                     quantity=quantity, price=price),
                           spec(fee_bps="0", slippage_bps="0"))
        with localcontext() as context:
            context.prec = 256
            expected = Decimal(quantity) * Decimal(price)
        self.assertEqual(fill.gross_quote, expected)
        self.assertEqual(fill.cash_delta, expected.copy_negate())

    def test_invalid_inputs_symbol_and_tampering_fail_closed(self):
        with self.assertRaises(CostModelError):
            apply_costs(object(), spec())
        with self.assertRaises(CostModelError):
            apply_costs(reference(IntentAction.ENTER_LONG), object())
        with self.assertRaises(CostModelError):
            apply_costs(reference(IntentAction.ENTER_LONG),
                        spec(symbol="ETHUSDT"))
        fill = apply_costs(reference(IntentAction.ENTER_LONG), spec())
        for changes in ({"fee_quote": fill.fee_quote + 1},
                        {"fee_bps": Decimal("-1")},
                        {"execution_price": float(fill.execution_price)}):
            with self.subTest(changes=changes), self.assertRaises(CostModelError):
                replace(fill, **changes)

    @patch("sys.argv", ["yatl", "backtest-cost-check"])
    def test_cli_reports_exact_aggregate_costs(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("exact Decimal costs", text)
        self.assertIn("fee_quote=0.1950025", text)
        self.assertIn("slippage_quote=0.0975", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
