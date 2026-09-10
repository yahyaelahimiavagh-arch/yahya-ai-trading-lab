import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (BacktestSpec, FillReason, FillReference, IntentAction,
                           PortfolioError, PortfolioLedger, apply_costs)


TIME = 1_699_999_200_000


def spec(symbol="BTCUSDT", cash="1000"):
    return BacktestSpec(symbol, TIME, TIME + 2 * 3_600_000, initial_cash=cash)


def fill(action, *, at=TIME, quantity="2", price="100", configuration=None):
    configuration = configuration or spec()
    reason = (FillReason.NEXT_PRIMARY_OPEN if action is IntentAction.ENTER_LONG
              else FillReason.SCRIPTED_EXIT)
    reference = FillReference(action, configuration.symbol, at, at,
                              quantity, price, reason)
    return apply_costs(reference, configuration)


class PortfolioLedgerTests(unittest.TestCase):
    def test_entry_and_conservative_liquidation_snapshot(self):
        ledger = PortfolioLedger(spec())
        ledger.apply(fill(IntentAction.ENTER_LONG))
        view = ledger.snapshot("100")
        self.assertEqual(view.cash, Decimal("799.69990"))
        self.assertEqual(view.asset_quantity, Decimal("2"))
        self.assertEqual(view.cost_basis_quote, Decimal("200.30010"))
        self.assertEqual(view.liquidation_value_quote, Decimal("199.70010"))
        self.assertEqual(view.unrealized_pnl_quote, Decimal("-0.60000"))
        self.assertEqual(view.equity_quote, Decimal("999.40000"))

    def test_round_trip_balances_and_realized_pnl(self):
        ledger = PortfolioLedger(spec())
        ledger.apply_many((fill(IntentAction.ENTER_LONG),
                           fill(IntentAction.EXIT_LONG, at=TIME + 3_600_000)))
        view = ledger.snapshot("100")
        self.assertEqual(view.cash, Decimal("999.40000"))
        self.assertEqual(view.asset_quantity, Decimal("0"))
        self.assertEqual(view.realized_pnl_quote, Decimal("-0.60000"))
        self.assertEqual(view.equity_quote, view.cash)
        self.assertEqual(view.total_fee_quote, Decimal("0.40000"))
        self.assertEqual(view.total_slippage_quote, Decimal("0.20"))
        self.assertEqual(view.closed_trades, 1)

    def test_insufficient_cash_and_batch_failure_roll_back(self):
        low = spec(cash="200")
        ledger = PortfolioLedger(low)
        with self.assertRaises(PortfolioError):
            ledger.apply(fill(IntentAction.ENTER_LONG, configuration=low))
        self.assertEqual(ledger.snapshot("100").cash, Decimal("200"))

        ledger = PortfolioLedger(spec())
        entry = fill(IntentAction.ENTER_LONG)
        with self.assertRaises(PortfolioError):
            ledger.apply_many((entry, entry))
        view = ledger.snapshot("100")
        self.assertEqual((view.cash, view.asset_quantity), (Decimal("1000"), Decimal(0)))

    def test_duplicate_partial_exit_and_exit_without_position_fail_closed(self):
        ledger = PortfolioLedger(spec())
        exit_fill = fill(IntentAction.EXIT_LONG, at=TIME + 3_600_000)
        with self.assertRaises(PortfolioError):
            ledger.apply(exit_fill)
        entry = fill(IntentAction.ENTER_LONG)
        ledger.apply(entry)
        with self.assertRaises(PortfolioError):
            ledger.apply(entry)
        partial = fill(IntentAction.EXIT_LONG, at=TIME + 3_600_000, quantity="1")
        with self.assertRaises(PortfolioError):
            ledger.apply(partial)
        self.assertEqual(ledger.asset_quantity, Decimal("2"))

    def test_time_order_and_symbol_isolation(self):
        btc = PortfolioLedger(spec("BTCUSDT"))
        late_entry = fill(IntentAction.ENTER_LONG, at=TIME + 3_600_000)
        btc.apply(late_entry)
        with self.assertRaises(PortfolioError):
            btc.apply(fill(IntentAction.EXIT_LONG, at=TIME))

        eth_spec = spec("ETHUSDT")
        eth = PortfolioLedger(eth_spec)
        eth.apply(fill(IntentAction.ENTER_LONG, configuration=eth_spec))
        with self.assertRaises(PortfolioError):
            btc.apply(fill(IntentAction.EXIT_LONG, at=TIME + 3_600_000,
                           configuration=eth_spec))
        self.assertEqual((btc.asset_quantity, eth.asset_quantity),
                         (Decimal("2"), Decimal("2")))
        different_costs = BacktestSpec("BTCUSDT", TIME, TIME + 2 * 3_600_000,
                                       initial_cash="1000", fee_bps="20")
        with self.assertRaises(PortfolioError):
            PortfolioLedger(spec()).apply(
                fill(IntentAction.ENTER_LONG, configuration=different_costs))

    def test_invalid_mark_spec_and_snapshot_tampering_fail_closed(self):
        with self.assertRaises(PortfolioError):
            PortfolioLedger(object())
        ledger = PortfolioLedger(spec())
        for mark in (0.0, "0", "NaN", "1e2"):
            with self.subTest(mark=mark), self.assertRaises(PortfolioError):
                ledger.snapshot(mark)
        view = ledger.snapshot("100")
        with self.assertRaises(PortfolioError):
            replace(view, equity_quote=view.equity_quote + 1)

    @patch("sys.argv", ["yatl", "backtest-portfolio-check"])
    def test_cli_reports_balanced_round_trip(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("balanced portfolio round trip", text)
        self.assertIn("cash=999.40000", text)
        self.assertIn("realized_pnl=-0.60000", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
