import contextlib
import io
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (AcceptedBacktestDataset, BacktestSpec, ScenarioError,
                           run_real_scenario_matrix, run_scripted_scenario)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


BASE = 1_699_977_600_000
START = BASE + 8 * 3_600_000
END = START + 24 * 3_600_000


def history(interval):
    duration = INTERVAL_MILLISECONDS[interval]
    return tuple(Candle(
        DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
        "100", "110", "90", "105", "100", "10000", 20, True,
    ) for opened in range(BASE, END, duration))


def dataset(**changes):
    values = {
        "spec": BacktestSpec("BTCUSDT", START, END),
        "manifest_generated_at_ms": END + 1,
        "primary": history("1h"),
        "context": history("15m"),
        "regime": history("4h"),
    }
    values.update(changes)
    return AcceptedBacktestDataset(**values)


class RealDataScenarioTests(unittest.TestCase):
    def test_fixed_scenarios_have_expected_trade_counts(self):
        expected = {"NO_TRADE": 0, "SINGLE_ROUND_TRIP": 1,
                    "CONTROLLED_MULTI_TRADE": 3}
        for name, trades in expected.items():
            with self.subTest(name=name):
                result = run_scripted_scenario(dataset(), name)
                self.assertEqual(result.report.trade_count, trades)
                self.assertEqual(result.report.points[0].time_ms, START)
                self.assertEqual(result.report.points[-1].time_ms, END - 3_600_000)

    def test_costs_strictly_reduce_trading_results(self):
        for name in ("SINGLE_ROUND_TRIP", "CONTROLLED_MULTI_TRADE"):
            result = run_scripted_scenario(dataset(), name)
            self.assertGreater(result.report.total_cost_quote, 0)
            self.assertLess(result.report.net_pnl_quote,
                            result.zero_cost_net_pnl_quote)

    def test_replay_is_byte_identical(self):
        first = run_scripted_scenario(dataset(), "CONTROLLED_MULTI_TRADE")
        second = run_scripted_scenario(dataset(), "CONTROLLED_MULTI_TRADE")
        self.assertEqual(first.report, second.report)
        self.assertEqual(first.manifest_json, second.manifest_json)

    def test_current_candle_non_open_fields_do_not_change_results(self):
        original = dataset()
        changed = replace(original, primary=tuple(
            replace(item, high="200", low="50", close="150",
                    base_volume="200", quote_volume="20000", trade_count=40)
            for item in original.primary
        ))
        first = run_scripted_scenario(original, "SINGLE_ROUND_TRIP")
        second = run_scripted_scenario(changed, "SINGLE_ROUND_TRIP")
        self.assertEqual(first.report, second.report)
        self.assertNotEqual(first.manifest_json, second.manifest_json)

    def test_invalid_or_short_scenarios_fail_closed(self):
        with self.assertRaises(ScenarioError):
            run_scripted_scenario(object(), "NO_TRADE")
        with self.assertRaises(ScenarioError):
            run_scripted_scenario(dataset(), "UNKNOWN")
        short_spec = BacktestSpec("BTCUSDT", START, START + 4 * 3_600_000)
        short = replace(dataset(), spec=short_spec)
        with self.assertRaises(ScenarioError):
            run_scripted_scenario(short, "SINGLE_ROUND_TRIP")

    @patch("yatl.backtest.scenarios.load_accepted_dataset")
    @patch("yatl.backtest.scenarios.latest_spec_from_manifest")
    def test_matrix_runs_both_symbols_and_all_scenarios(self, latest, load):
        def for_symbol(_manifest, symbol, hours):
            return replace(dataset().spec, symbol=symbol)

        def load_symbol(_database, _manifest, configuration):
            base = dataset()
            convert = lambda rows: tuple(replace(item, symbol=configuration.symbol)
                                         for item in rows)
            return replace(base, spec=configuration, primary=convert(base.primary),
                           context=convert(base.context), regime=convert(base.regime))

        latest.side_effect = for_symbol
        load.side_effect = load_symbol
        results = run_real_scenario_matrix("market.sqlite3", "manifest.json")
        self.assertEqual(len(results), 6)
        self.assertEqual({item.symbol for item in results}, {"BTCUSDT", "ETHUSDT"})
        self.assertEqual({item.name for item in results},
                         {"NO_TRADE", "SINGLE_ROUND_TRIP", "CONTROLLED_MULTI_TRADE"})

    def test_matrix_input_errors_are_normalized(self):
        with self.assertRaises(ScenarioError):
            run_real_scenario_matrix("db", "manifest", hours=19)
        with patch("yatl.backtest.scenarios.latest_spec_from_manifest",
                   side_effect=ValueError("unsafe detail")):
            with self.assertRaises(ScenarioError):
                run_real_scenario_matrix("db", "manifest")

    @patch("yatl.__main__.run_real_scenario_matrix")
    @patch("sys.argv", ["yatl", "backtest-scenario-check"])
    def test_cli_reports_safe_matrix(self, run):
        result = run_scripted_scenario(dataset(), "SINGLE_ROUND_TRIP")
        run.return_value = (result,)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("accepted real-data scenario matrix", text)
        self.assertIn("BTCUSDT SINGLE_ROUND_TRIP", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
