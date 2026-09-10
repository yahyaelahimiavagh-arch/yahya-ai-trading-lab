import contextlib
import io
import json
import os
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from yatl.__main__ import main
from yatl.backtest import (AcceptedBacktestDataset, ArtifactError, BacktestSpec,
                           EquityPoint, FillReason, FillReference, IntentAction,
                           PortfolioLedger, apply_costs, artifact_json,
                           build_run_manifest, calculate_metrics,
                           write_run_manifest)
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS


TIME = 1_699_999_200_000


def candle(interval, opened, close="100"):
    duration = INTERVAL_MILLISECONDS[interval]
    return Candle(DATA_SOURCE, "BTCUSDT", interval, opened, opened + duration - 1,
                  "100", "120", "80", close, "10", "1000", 10, True)


def scenario(exit_price="110"):
    configuration = BacktestSpec("BTCUSDT", TIME, TIME + 3 * 3_600_000,
                                 initial_cash="1000")
    dataset = AcceptedBacktestDataset(
        configuration, TIME + 10,
        (candle("1h", TIME - 3_600_000), candle("1h", TIME)),
        (candle("15m", TIME - 900_000), candle("15m", TIME)),
        (candle("4h", (TIME // INTERVAL_MILLISECONDS["4h"] - 1)
                * INTERVAL_MILLISECONDS["4h"]),),
    )
    ledger = PortfolioLedger(configuration)
    points = [EquityPoint(TIME, ledger.snapshot("100"))]
    references = (
        FillReference(IntentAction.ENTER_LONG, "BTCUSDT", TIME + 3_600_000,
                      TIME + 3_600_000, "2", "100", FillReason.NEXT_PRIMARY_OPEN),
        FillReference(IntentAction.EXIT_LONG, "BTCUSDT", TIME + 2 * 3_600_000,
                      TIME + 2 * 3_600_000, "2", exit_price, FillReason.SCRIPTED_EXIT),
    )
    fills = tuple(apply_costs(item, configuration) for item in references)
    ledger.apply(fills[0])
    points.append(EquityPoint(TIME + 3_600_000, ledger.snapshot("100")))
    ledger.apply(fills[1])
    points.append(EquityPoint(TIME + 2 * 3_600_000, ledger.snapshot(exit_price)))
    return dataset, fills, calculate_metrics(tuple(points))


class BacktestArtifactTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("YATL_TEST_TEMP_DIR", "."))
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"p2-artifact-{uuid4().hex}.json"

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_manifest_is_byte_stable_and_reconciled(self):
        dataset, fills, report = scenario()
        first = build_run_manifest(dataset, fills, report)
        second = build_run_manifest(dataset, fills, report)
        self.assertEqual(artifact_json(first), artifact_json(second))
        self.assertEqual(first["trades"][0]["gross_pnl_quote"], "20")
        self.assertEqual(first["trades"][0]["net_pnl_quote"], "19.3700100")
        self.assertEqual(first["metrics"]["net_pnl_quote"], "19.3700100")
        self.assertEqual(first["equity_curve"]["points"], 3)

    def test_material_data_and_run_changes_change_input_digest(self):
        dataset, fills, report = scenario()
        baseline = build_run_manifest(dataset, fills, report)["input_sha256"]
        changed_primary = (replace(dataset.primary[0], close="101"), dataset.primary[1])
        changed_dataset = replace(dataset, primary=changed_primary)
        self.assertNotEqual(
            baseline, build_run_manifest(changed_dataset, fills, report)["input_sha256"])
        other_dataset, other_fills, other_report = scenario("111")
        self.assertNotEqual(
            baseline,
            build_run_manifest(other_dataset, other_fills, other_report)["input_sha256"],
        )

    def test_manifest_excludes_paths_secrets_and_wall_clock(self):
        manifest = build_run_manifest(*scenario())
        text = artifact_json(manifest).lower()
        for forbidden in ("api_key", "api_secret", "password", "database_path",
                          "manifest_path", "run_generated_at", "created_at", "\\users\\"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(manifest["configuration"]["live_master_lock"], "OFF")
        self.assertTrue(manifest["configuration"]["paper_only"])
        self.assertFalse(manifest["configuration"]["allow_leverage"])

    def test_no_trade_manifest_has_explicit_undefined_metrics(self):
        dataset, _, _ = scenario()
        ledger = PortfolioLedger(dataset.spec)
        report = calculate_metrics((EquityPoint(TIME, ledger.snapshot("100")),))
        manifest = build_run_manifest(dataset, (), report)
        self.assertEqual(manifest["trades"], [])
        self.assertIsNone(manifest["metrics"]["win_rate"])
        self.assertIsNone(manifest["metrics"]["sample_period_volatility"])

    def test_inconsistent_inputs_fail_closed(self):
        dataset, fills, report = scenario()
        with self.assertRaises(ArtifactError):
            build_run_manifest(object(), fills, report)
        with self.assertRaises(ArtifactError):
            build_run_manifest(dataset, list(fills), report)
        with self.assertRaises(ArtifactError):
            build_run_manifest(dataset, object(), report)
        with self.assertRaises(ArtifactError):
            build_run_manifest(dataset, fills[:1], report)
        with self.assertRaises(ArtifactError):
            build_run_manifest(replace(dataset, primary=()), fills, report)

    def test_atomic_writer_round_trip(self):
        manifest = build_run_manifest(*scenario())
        self.assertEqual(write_run_manifest(manifest, self.path), self.path)
        raw = self.path.read_bytes()
        self.assertEqual(raw, artifact_json(manifest).encode("utf-8"))
        self.assertEqual(json.loads(raw), manifest)
        write_run_manifest(manifest, self.path)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_invalid_manifest_and_write_failure_leave_no_partial_file(self):
        with self.assertRaises(ArtifactError):
            artifact_json({})
        manifest = build_run_manifest(*scenario())
        injected = dict(manifest)
        injected["api_secret"] = "forbidden"
        with self.assertRaises(ArtifactError):
            artifact_json(injected)
        injected = dict(manifest)
        injected["metrics"] = object()
        with self.assertRaises(ArtifactError):
            artifact_json(injected)
        injected = dict(manifest)
        injected["configuration"] = dict(manifest["configuration"])
        injected["configuration"]["database_path"] = r"C:\\Users\\name\\data.db"
        with self.assertRaises(ArtifactError):
            artifact_json(injected)
        with patch("yatl.backtest.artifacts.Path.replace", side_effect=OSError):
            with self.assertRaises(ArtifactError):
                write_run_manifest(manifest, self.path)
        self.assertFalse(self.path.exists())

    @patch("sys.argv", ["yatl", "backtest-artifact-check"])
    def test_cli_reports_safe_atomic_artifact(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("canonical atomic run artifact", text)
        self.assertIn("trades=1", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
