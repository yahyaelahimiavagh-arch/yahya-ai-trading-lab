import tempfile
import unittest
import json
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

from yatl.backtest import AcceptedBacktestDataset, BacktestSpec
from yatl.data import Candle, DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from yatl.strategy import (BREAKOUT_IDENTITY, EVALUATION_END_MS,
                           EVALUATION_START_MS, TRAINING_START_MS,
                           TREND_PULLBACK_IDENTITY, CandidateRunError,
                           EvidenceLabel, candidate_matrix_sha256,
                           evaluation_plan, run_accepted_candidate_matrix,
                           write_candidate_matrix)
from yatl.strategy.runs import _exact_difference


def candles(symbol, interval):
    duration = INTERVAL_MILLISECONDS[interval]
    end = EVALUATION_END_MS + duration
    return tuple(Candle(
        DATA_SOURCE, symbol, interval, opened, opened + duration - 1,
        "100", "101", "99", "100", "10", "1000", 10, True,
    ) for opened in range(TRAINING_START_MS, end, duration))


def dataset(spec):
    return AcceptedBacktestDataset(
        spec, 1788971310603,
        candles(spec.symbol, "1h"), candles(spec.symbol, "15m"),
        candles(spec.symbol, "4h"),
    )


def loader(_database, _manifest, spec):
    return dataset(spec)


class AcceptedCandidateRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("yatl.strategy.runs.load_accepted_dataset", side_effect=loader):
            cls.matrix = run_accepted_candidate_matrix(
                "market.sqlite3", "manifest.json")

    def test_windows_and_frozen_candidate_plans_are_pre_registered(self):
        self.assertEqual((EVALUATION_START_MS - TRAINING_START_MS) // 86_400_000, 9)
        self.assertEqual((EVALUATION_END_MS - EVALUATION_START_MS) // 86_400_000, 20)
        trend = evaluation_plan(TREND_PULLBACK_IDENTITY)
        breakout = evaluation_plan(BREAKOUT_IDENTITY)
        self.assertNotEqual(trend.sha256, breakout.sha256)
        self.assertEqual(trend.evaluation_days, 20)

    def test_cost_drag_subtraction_ignores_ambient_decimal_precision(self):
        with localcontext() as context:
            context.prec = 4
            drag = _exact_difference(
                Decimal("19.3700100"), Decimal("0.0000001"))
        self.assertEqual(drag, Decimal("19.3700099"))

    def test_full_candidate_symbol_matrix_is_deterministic_and_insufficient(self):
        first = self.matrix
        decoded = json.loads(first.index_json)
        self.assertEqual(
            json.dumps(decoded, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n",
            first.index_json,
        )
        self.assertEqual(len(candidate_matrix_sha256(first)), 64)
        self.assertTrue(all(item["replay_equal"] for item in decoded["runs"]))
        self.assertEqual(len(first.runs), 4)
        self.assertEqual({(item.identity, item.symbol) for item in first.runs}, {
            (identity, symbol)
            for identity in (TREND_PULLBACK_IDENTITY, BREAKOUT_IDENTITY)
            for symbol in SYMBOLS
        })
        self.assertTrue(all(item.report.trade_count == 0 for item in first.runs))
        self.assertTrue(all(item.cost_drag_quote == 0 for item in first.runs))
        self.assertTrue(all(item.buy_hold_report.total_cost_quote > 0
                            for item in first.runs))
        self.assertTrue(all(item.label is EvidenceLabel.INSUFFICIENT_EVIDENCE
                            for item in first.evaluations))

    def test_artifacts_are_canonical_and_future_material_is_excluded(self):
        result = self.matrix
        for item in result.runs:
            self.assertIn('"artifact_kind":"YATL_SPOT_PAPER_BACKTEST"',
                          item.candidate_artifact)
            self.assertIn('"artifact_kind":"YATL_P3_DECISION_TRACE"',
                          item.trace_json)
            self.assertNotIn(str(EVALUATION_END_MS + 14_400_000 - 1),
                             item.candidate_artifact)
            self.assertNotIn("credential", item.trace_json.lower())

    def test_evidence_directory_is_atomic_and_never_overwritten(self):
        result = self.matrix
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            write_candidate_matrix(result, output)
            files = sorted(item.name for item in output.iterdir())
            self.assertEqual(len(files), 21)
            self.assertIn("p3-009-index.json", files)
            original = (output / "p3-009-index.json").read_bytes()
            with self.assertRaises(CandidateRunError):
                write_candidate_matrix(result, output)
            self.assertEqual((output / "p3-009-index.json").read_bytes(), original)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(CandidateRunError):
            evaluation_plan(object())
        with self.assertRaises(CandidateRunError):
            write_candidate_matrix(object(), "output")


if __name__ == "__main__":
    unittest.main()
