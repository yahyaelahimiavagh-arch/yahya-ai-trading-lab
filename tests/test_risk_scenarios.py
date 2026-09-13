import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import fields
from decimal import localcontext
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import main
from yatl.backtest import AcceptedBacktestDataset, BacktestSpec
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from yatl.risk import (
    SCENARIOS,
    RiskScenarioError,
    RiskScenarioMatrixResult,
    RiskScenarioResult,
    run_adversarial_scenario_matrix,
    scenario_artifact_json,
    scenario_matrix_sha256,
    write_adversarial_scenario_matrix,
)


START = 1_787_184_000_000
END = START + 24 * INTERVAL_MILLISECONDS["1h"]


def _candles(symbol, interval):
    duration = INTERVAL_MILLISECONDS[interval]
    return tuple(Candle(
        DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
        "100", "101", "99", "100", "100000", "10000000", 100, True,
    ) for opened in range(START - 48 * INTERVAL_MILLISECONDS["1h"],
                          END + duration, duration))


def _dataset(spec):
    return AcceptedBacktestDataset(
        spec, 1_788_971_310_603,
        _candles(spec.symbol, "1h"),
        _candles(spec.symbol, "15m"),
        _candles(spec.symbol, "4h"),
    )


def _latest(_manifest, symbol, *, hours=24):
    return BacktestSpec(symbol, START, START + hours * 3_600_000)


def _load(_database, _manifest, spec):
    return _dataset(spec)


def _run_matrix():
    with (
        patch("yatl.risk.scenarios.latest_spec_from_manifest",
              side_effect=_latest),
        patch("yatl.risk.scenarios.load_accepted_dataset", side_effect=_load),
    ):
        return run_adversarial_scenario_matrix(
            "market.sqlite3", "manifest.json",
        )


class RiskScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = _run_matrix()

    def _records(self):
        return {
            (item.symbol, item.name): json.loads(item.artifact_json)
            for item in self.matrix.runs
        }

    def test_matrix_has_every_scenario_for_both_symbols(self):
        self.assertIsInstance(self.matrix, RiskScenarioMatrixResult)
        self.assertEqual(len(self.matrix.runs), 16)
        self.assertEqual(
            {(item.symbol, item.name) for item in self.matrix.runs},
            {(symbol, name) for symbol in SYMBOLS for name in SCENARIOS},
        )
        self.assertEqual(len(scenario_matrix_sha256(self.matrix)), 64)

    def test_matrix_and_artifacts_are_canonical_and_reproducible(self):
        decoded = json.loads(self.matrix.index_json)
        self.assertEqual(
            json.dumps(decoded, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n",
            self.matrix.index_json,
        )
        for item in self.matrix.runs:
            record = json.loads(item.artifact_json)
            self.assertEqual(scenario_artifact_json(record), item.artifact_json)
            self.assertTrue(record["passed"])
            self.assertEqual(len(record["result_sha256"]), 64)

    def test_exact_boundaries_latch_and_block_entry(self):
        records = self._records()
        expected = {
            "SESSION_LOSS_BOUNDARY": "SESSION_LOSS_LIMIT",
            "LOSS_STREAK_BOUNDARY": "CONSECUTIVE_LOSS_LIMIT",
            "DRAWDOWN_BOUNDARY": "DRAWDOWN_LIMIT",
        }
        for symbol in SYMBOLS:
            for name, breaker in expected.items():
                with self.subTest(symbol=symbol, scenario=name):
                    observed = records[(symbol, name)]["observed"]
                    self.assertEqual(observed["triggered_breakers"], [breaker])
                    self.assertTrue(observed["kill_switch_active"])
                    self.assertEqual(observed["adapter_outcome"], "ENTRY_BLOCKED")
                    self.assertEqual(observed["fills"], [])

    def test_gap_and_stale_state_fail_closed_atomically(self):
        records = self._records()
        for symbol in SYMBOLS:
            gap = records[(symbol, "GAP_FAIL_CLOSED")]["observed"]
            self.assertEqual(
                gap["gap_failure"],
                "P2_REJECTED_MISSING_EXPECTED_FILL_CANDLE",
            )
            self.assertTrue(gap["atomic_state_preserved"])
            self.assertTrue(gap["retry_succeeded"])
            stale = records[(symbol, "STALE_STATE_REJECTION")]["observed"]
            self.assertEqual(stale["stale_failure"],
                             "LATEST_CIRCUIT_NOT_CONSUMED")
            self.assertTrue(stale["atomic_state_preserved"])
            self.assertEqual(stale["fills"], [])

    def test_cost_and_insufficient_evidence_cannot_fill(self):
        records = self._records()
        for symbol in SYMBOLS:
            cost = records[(symbol, "POST_COST_REJECTION")]["observed"]
            self.assertEqual(cost["protective_status"], "REJECT")
            self.assertEqual(cost["adapter_outcome"], "ENTRY_BLOCKED")
            self.assertEqual(cost["fills"], [])
            insufficient = records[(symbol, "INSUFFICIENT_EVIDENCE")]["observed"]
            self.assertEqual(insufficient["risk_reason"],
                             "EVIDENCE_NOT_QUALIFIED")
            self.assertEqual(insufficient["fills"], [])

    def test_kill_switch_keeps_exact_risk_reducing_exit(self):
        records = self._records()
        for symbol in SYMBOLS:
            observed = records[(symbol, "KILL_SWITCH_EXIT")]["observed"]
            self.assertTrue(observed["kill_switch_active"])
            self.assertEqual(observed["adapter_outcome"], "EXIT_APPROVED")
            self.assertTrue(observed["final_position_flat"])
            self.assertEqual(
                observed["fills"][0]["quantity"], observed["approved_quantity"],
            )

    def test_replay_ignores_ambient_decimal_precision(self):
        expected = self.matrix
        with localcontext() as arithmetic:
            arithmetic.prec = 6
            replay = _run_matrix()
        self.assertEqual(expected, replay)

    def test_writer_is_atomic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            write_adversarial_scenario_matrix(self.matrix, output)
            self.assertEqual(len(tuple(output.iterdir())), 17)
            self.assertTrue((output / "p4-009-index.json").is_file())
            original = (output / "p4-009-index.json").read_bytes()
            with self.assertRaises(RiskScenarioError):
                write_adversarial_scenario_matrix(self.matrix, output)
            self.assertEqual(
                (output / "p4-009-index.json").read_bytes(), original,
            )

    def test_artifacts_have_no_credentials_or_execution_capability(self):
        text = self.matrix.index_json + "".join(
            item.artifact_json for item in self.matrix.runs
        )
        for forbidden in (
            "api_key", "api_secret", "password", "credential", "broker",
            "database_path", "manifest_path",
        ):
            self.assertNotIn(forbidden, text.lower())
        decoded = json.loads(self.matrix.index_json)
        self.assertFalse(decoded["trade_permission"])
        self.assertFalse(decoded["exchange_order_submission"])
        names = {item.name for item in fields(RiskScenarioResult)}
        self.assertTrue(names.isdisjoint({"endpoint", "account", "order"}))

    def test_invalid_or_tampered_inputs_fail_closed(self):
        with self.assertRaises(RiskScenarioError):
            run_adversarial_scenario_matrix("db", "manifest", hours=1)
        with self.assertRaises(RiskScenarioError):
            write_adversarial_scenario_matrix(object(), "output")
        record = json.loads(self.matrix.runs[0].artifact_json)
        record["passed"] = False
        with self.assertRaises(RiskScenarioError):
            scenario_artifact_json(record)
        with self.assertRaises(RiskScenarioError):
            RiskScenarioMatrixResult(
                self.matrix.runs,
                self.matrix.index_json.replace(
                    '"trade_permission":false', '"trade_permission":true',
                ),
            )

    @patch("yatl.__main__.run_and_write_adversarial_matrix")
    @patch("sys.argv", ["yatl", "risk-scenario-check"])
    def test_cli_reports_matrix_identity_and_safety(self, run):
        run.return_value = self.matrix
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P4 adversarial matrix", text)
        self.assertIn("scenarios=8 symbols=2 runs=16", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
