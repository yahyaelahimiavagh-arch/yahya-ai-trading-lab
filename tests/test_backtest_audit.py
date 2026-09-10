import contextlib
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import (AcceptedBacktestDataset, BacktestSpec, P2AuditError,
                           artifact_json, audit_p2, audit_run_manifest,
                           run_scripted_scenario)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


BASE = 1_699_977_600_000
START = BASE + 8 * 3_600_000
END = START + 24 * 3_600_000


def history(symbol, interval):
    duration = INTERVAL_MILLISECONDS[interval]
    return tuple(Candle(
        DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
        "100", "110", "90", "105", "100", "10000", 20, True,
    ) for opened in range(BASE, END, duration))


def dataset(symbol="BTCUSDT"):
    return AcceptedBacktestDataset(
        BacktestSpec(symbol, START, END), END + 1,
        history(symbol, "1h"), history(symbol, "15m"), history(symbol, "4h"),
    )


def encoded(name="SINGLE_ROUND_TRIP"):
    return run_scripted_scenario(dataset(), name).manifest_json


class P2AuditTests(unittest.TestCase):
    def test_independent_artifact_audit_accepts_all_scenario_shapes(self):
        expected = {"NO_TRADE": 0, "SINGLE_ROUND_TRIP": 1,
                    "CONTROLLED_MULTI_TRADE": 3}
        for name, trades in expected.items():
            with self.subTest(name=name):
                result = audit_run_manifest(encoded(name))
                self.assertEqual(result.symbol, "BTCUSDT")
                self.assertEqual(result.trades, trades)
                self.assertEqual(len(result.input_sha256), 64)

    def test_noncanonical_and_unsafe_configuration_fail_closed(self):
        raw = encoded()
        with self.assertRaises(P2AuditError):
            audit_run_manifest(json.dumps(json.loads(raw), indent=2))
        manifest = json.loads(raw)
        manifest["configuration"]["allow_leverage"] = True
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))

    def test_digest_and_trade_arithmetic_tampering_fail_closed(self):
        manifest = json.loads(encoded())
        manifest["input_sha256"] = "0" * 64
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))
        manifest = json.loads(encoded())
        manifest["trades"][0]["net_pnl_quote"] = "999"
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))

    def test_metric_and_equity_tampering_fail_closed(self):
        manifest = json.loads(encoded())
        manifest["metrics"]["total_cost_quote"] = "0"
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))
        manifest = json.loads(encoded())
        manifest["metrics"]["mean_period_return"] = "0"
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))
        manifest = json.loads(encoded())
        manifest["equity_curve"]["final_equity_quote"] = "1"
        with self.assertRaises(P2AuditError):
            audit_run_manifest(artifact_json(manifest))

    @patch("yatl.backtest.audit._audit_source_safety")
    @patch("yatl.backtest.audit.audit_p1_manifest")
    @patch("yatl.backtest.audit.run_real_scenario_matrix")
    def test_final_audit_requires_complete_two_symbol_matrix(self, matrix, p1, safety):
        matrix.return_value = tuple(
            run_scripted_scenario(dataset(symbol), name)
            for symbol in ("BTCUSDT", "ETHUSDT")
            for name in ("NO_TRADE", "SINGLE_ROUND_TRIP", "CONTROLLED_MULTI_TRADE")
        )
        result = audit_p2("db", "manifest")
        self.assertEqual((result.symbols, result.scenarios, result.artifacts, result.trades),
                         (2, 6, 6, 8))
        p1.assert_called_once_with("manifest")
        safety.assert_called_once_with()

    @patch("yatl.backtest.audit._audit_source_safety")
    @patch("yatl.backtest.audit.audit_p1_manifest")
    @patch("yatl.backtest.audit.run_real_scenario_matrix")
    def test_incomplete_or_failed_final_audit_is_rejected(self, matrix, _p1, _safety):
        matrix.return_value = (run_scripted_scenario(dataset(), "NO_TRADE"),)
        with self.assertRaises(P2AuditError):
            audit_p2("db", "manifest")
        matrix.side_effect = ValueError("unsafe detail")
        with self.assertRaises(P2AuditError):
            audit_p2("db", "manifest")

    @patch("yatl.__main__.audit_p2")
    @patch("sys.argv", ["yatl", "p2-audit"])
    def test_cli_reports_safe_final_audit(self, audit):
        from yatl.backtest import P2AuditResult
        audit.return_value = P2AuditResult(2, 6, 6, 8)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P2 final acceptance audit", text)
        self.assertIn("scenarios=6", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
