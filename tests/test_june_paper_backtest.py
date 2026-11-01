from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.model_lab import june_paper_backtest as june
from yatl.backtest import BacktestSpec, FillReference, FillReason, IntentAction, apply_costs
from yatl.strategy import StrategyAction, StrategyDecision, DecisionReason, LongSetup


def raw_month():
    rows = []
    for at in range(june.START, june.END, 900000):
        rows.append([at, "100", "100.1", "99.9", "100", "100000", at + 899999,
                     "10000000", 100, "100", "10000", "0"])
    return {symbol: deepcopy(rows) for symbol in june.SYMBOLS}


class JuneBacktestTests(unittest.TestCase):
    def test_public_acquisition_requests_only_june_and_binds_pages(self):
        raw = raw_month()
        calls = []
        class PublicClient:
            def server_time(self):
                return june.END + june.DAY
            def klines(self, symbol, interval, *, limit, start_time, end_time):
                calls.append((symbol, interval, limit, start_time, end_time))
                return [row for row in raw[symbol] if start_time <= row[0] <= end_time][:limit]
        with patch.object(june, "BinancePublicRestClient", return_value=PublicClient()) as factory:
            acquired, manifest = june.acquire()
        self.assertEqual(acquired, raw)
        self.assertEqual(len(calls), 6)
        self.assertEqual(factory.call_args.kwargs["base_url"], "https://data-api.binance.vision")
        self.assertEqual(factory.call_args.kwargs["max_attempts"], 1)
        for symbol, interval, limit, start, end in calls:
            self.assertIn(symbol, june.SYMBOLS)
            self.assertEqual((interval, limit, end), ("15m", 1000, june.END - 1))
            self.assertGreaterEqual(start, june.START)
            self.assertLess(start, june.END)
        for symbol in june.SYMBOLS:
            self.assertEqual(manifest["datasets"][symbol]["raw_sha256"], june.sha(june.canonical(raw[symbol])))
        self.assertEqual([request["rows"] for request in manifest["requests"]], [1000, 1000, 880] * 2)

    def test_data_admission_is_june_only_contiguous_and_lossless(self):
        data = june.admit(raw_month())
        for symbol, series in data.items():
            self.assertEqual([len(series[i]) for i in ("15m", "1h", "4h")], [2880, 720, 180])
            self.assertEqual(series["4h"][0].base_volume, "1600000")
            self.assertEqual(series["4h"][-1].close_time_ms, june.END - 1)
        for mutation in ("early", "late", "gap", "duplicate", "unordered", "bad_price"):
            raw = raw_month()
            if mutation == "early": raw["BTCUSDT"][0][0] -= 900000
            elif mutation == "late": raw["BTCUSDT"][-1][0] = june.END
            elif mutation == "gap": raw["ETHUSDT"].pop()
            elif mutation == "duplicate": raw["BTCUSDT"][1] = raw["BTCUSDT"][0]
            elif mutation == "unordered": raw["ETHUSDT"].reverse()
            else: raw["ETHUSDT"][0][1] = "NaN"
            with self.subTest(mutation=mutation), self.assertRaises(Exception):
                june.admit(raw)

    def test_snapshot_excludes_every_future_bar(self):
        data = june.admit(raw_month())
        at = june.START + 205 * june.HOUR
        before = june.snapshot_at(data, "BTCUSDT", at)
        altered = raw_month()
        for row in altered["BTCUSDT"]:
            if row[0] >= at:
                row[1:5] = ["900", "901", "899", "900"]
        after = june.snapshot_at(june.admit(altered), "BTCUSDT", at)
        self.assertEqual(before, after)
        self.assertTrue(all(c.close_time_ms < at for series in (before.primary, before.context, before.regime) for c in series))
        self.assertEqual(len(before.regime), 51)

    def test_protocol_rejects_safety_range_parameters_or_code_changes(self):
        for field, value in (("start_ms", june.START - 1), ("end_ms", june.END + 1),
                             ("module_sha256", "0" * 64), ("dependency_source_sha256", "0" * 64),
                             ("evidence_classification", "FRESH_OOS"), ("ai_decisions", True)):
            record = june.protocol()
            record[field] = value
            with self.subTest(field=field), self.assertRaises(june.JuneReplayError):
                june.validate_protocol(record)
        for flag in june.SAFETY:
            record = deepcopy(june.protocol())
            record["safety"][flag] = not record["safety"][flag]
            with self.subTest(flag=flag), self.assertRaises(june.JuneReplayError):
                june.validate_protocol(record)

    def test_risk_cap_exposure_cash_and_lagged_volume(self):
        for name, limits in june.PROFILES.items():
            sized, veto = june.entry_size(name, Decimal(10000), Decimal(100), Decimal(96), Decimal(108), Decimal(100000))
            quantity, loss = sized
            self.assertIsNone(veto)
            self.assertLessEqual(loss, Decimal(10000) * Decimal(limits["risk"]))
            self.assertLessEqual(quantity * Decimal(100) * june.BUY, Decimal(10000) * Decimal(limits["exposure"]))
        sized, _ = june.entry_size("aggressive", Decimal(10000), Decimal(100), Decimal(96), Decimal(108), Decimal(1))
        self.assertLessEqual(sized[0], Decimal("0.01"))
        self.assertEqual(june.entry_size("aggressive", Decimal(10000), Decimal(95), Decimal(96), Decimal(108), Decimal(10000))[1], "NEXT_OPEN_OUTSIDE_BRACKET")
        self.assertEqual(june.entry_size("aggressive", Decimal(10000), Decimal(100), Decimal(99.99), Decimal(100.01), Decimal(10000))[1], "NONPOSITIVE_POST_COST_REWARD")

    def test_accounting_matches_accepted_cost_model(self):
        account = june.state()
        at = june.START + 204 * june.HOUR
        for side, action, mark, reason in (("BUY", IntentAction.ENTER_LONG, "100", FillReason.NEXT_PRIMARY_OPEN),
                                         ("SELL", IntentAction.EXIT_LONG, "101", FillReason.SCRIPTED_EXIT)):
            before = account["cash"]
            reference = FillReference(action, "BTCUSDT", at, at, "1", mark, reason)
            expected = apply_costs(reference, BacktestSpec("BTCUSDT", june.START, june.END))
            june.record_fill(account, side=side, symbol="BTCUSDT", quantity=Decimal(1), mark=Decimal(mark),
                             at=at, reason=reason.value, setup=LongSetup("100", "96", "108"), planned_loss=Decimal(5))
            self.assertEqual(account["cash"] - before, expected.cash_delta)
            self.assertEqual(Decimal(account["fills"][-1]["fee_usdt"]), expected.fee_quote)
        self.assertEqual(Decimal(account["trades"][0]["net_pnl_usdt"]), account["cash"] - 10000)

    def test_loss_circuits_latch_without_auto_reset(self):
        for value, streak, reason in (("9799", 0, "DAILY_LOSS"), ("8999", 0, "DAILY_LOSS"),
                                       ("10000", 3, "THREE_CONSECUTIVE_LOSSES")):
            account = june.state()
            account["loss_streak"] = streak
            june.observe(account, Decimal(value), june.START)
            self.assertTrue(account["halted"])
            self.assertEqual(account["halt_reason"], reason)
            june.observe(account, Decimal(20000), june.START + june.HOUR)
            self.assertTrue(account["halted"])
        account = june.state()
        account["peak"] = Decimal(12000)
        account["day_start_equity"] = Decimal(10000)
        june.observe(account, Decimal(10500), june.START)
        self.assertEqual(account["halt_reason"], "DRAWDOWN")

    def test_flat_fixture_runs_no_forced_trades_and_no_promotion(self):
        result = june.replay(raw_month(), june.protocol())
        for account in result["accounts"].values():
            self.assertEqual(account["closed_trades"], 0)
            self.assertEqual(account["final_equity_usdt"], "10000")
            self.assertEqual(account["decision_counts"]["INSUFFICIENT_HISTORY"], 400)
            self.assertEqual(len(account["equity_curve"]), 716)
        self.assertEqual(result["status"], "COMPLETED_SEEN_RESEARCH")
        self.assertFalse(result["safety"]["selection_authorized"])

    def test_priority_next_open_terminal_costs_and_no_overlap(self):
        data = june.admit(raw_month())
        def evaluator(context, *, in_position, active_setup):
            if in_position:
                return StrategyDecision(context, StrategyAction.NO_TRADE, DecisionReason.HOLD_POSITION)
            if context.decision_time_ms == june.START + 204 * june.HOUR:
                return StrategyDecision(context, StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
                                        LongSetup("100", "96", "108"))
            return StrategyDecision(context, StrategyAction.NO_TRADE, DecisionReason.SETUP_ABSENT)
        with patch.object(june, "evaluate_trend_pullback", side_effect=evaluator):
            account = june.run_profile(data, "conservative")
        self.assertEqual(len(account["fills"]), 2)
        self.assertEqual(account["fills"][0]["symbol"], "BTCUSDT")
        self.assertEqual(account["fills"][0]["at_ms"], june.START + 204 * june.HOUR)
        self.assertEqual(account["fills"][-1]["at_ms"], june.END - 1)
        self.assertEqual(account["trades"][-1]["exit_reason"], "TERMINAL_VIRTUAL_LIQUIDATION")
        self.assertLess(Decimal(account["net_pnl_usdt"]), 0)
        self.assertEqual(account["open_positions_at_end"], 0)

    def test_intrabar_stop_does_not_enable_second_asset_same_hour(self):
        raw = raw_month()
        at = june.START + 204 * june.HOUR
        for row in raw["BTCUSDT"]:
            if at <= row[0] < at + june.HOUR:
                row[3] = "95"
        data = june.admit(raw)
        def evaluator(context, **kwargs):
            if context.decision_time_ms == at:
                return StrategyDecision(context, StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
                                        LongSetup("100", "96", "108"))
            return StrategyDecision(context, StrategyAction.NO_TRADE, DecisionReason.SETUP_ABSENT)
        with patch.object(june, "evaluate_trend_pullback", side_effect=evaluator):
            account = june.run_profile(data, "conservative")
        self.assertEqual([fill["symbol"] for fill in account["fills"]], ["BTCUSDT", "BTCUSDT"])
        self.assertEqual(account["closed_trades"], 1)
        self.assertLess(Decimal(account["net_pnl_usdt"]), 0)

    def test_exclusive_run_reservation_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "experiment"
            with patch.object(june, "ROOT", root):
                root.mkdir()
                (root / "results").mkdir()
                june.write_new(root / "protocol.json", june.protocol())
                with self.assertRaises(FileExistsError):
                    june.main(["run"])
            with self.assertRaises(june.JuneReplayError):
                june.safe_root(Path("/var/lib/yatl/p10"))


if __name__ == "__main__":
    unittest.main()
