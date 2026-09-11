import unittest
import contextlib
import io
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from unittest.mock import patch

from yatl.strategy import (BREAKOUT_CONFIGURATION, BREAKOUT_IDENTITY,
                           MIN_EVALUATION_DAYS, EvaluationError,
                           EvaluationPlan, EvaluationReport, EvidenceLabel,
                           EvidenceReason, SymbolEvidence,
                           TREND_PULLBACK_CONFIGURATION,
                           TREND_PULLBACK_IDENTITY, assess_evidence,
                           evaluation_input_sha256)
from yatl.data import Candle, DATA_SOURCE


DAY = 86_400_000


def plan(*, days=180, identity=TREND_PULLBACK_IDENTITY,
         digest=TREND_PULLBACK_CONFIGURATION.sha256):
    return EvaluationPlan(
        identity, digest,
        1000 * DAY, 1180 * DAY,
        1180 * DAY, (1180 + days) * DAY,
    )


def run(item, symbol, **changes):
    defaults = {
        "symbol": symbol,
        "plan_sha256": item.sha256,
        "configuration_sha256": item.configuration_sha256,
        "evaluation_start_ms": item.evaluation_start_ms,
        "evaluation_end_ms": item.evaluation_end_ms,
        "dataset_sha256": ("a" if symbol == "BTCUSDT" else "b") * 64,
        "trade_count": 30,
        "total_return": "0.12",
        "maximum_drawdown": "0.08",
        "total_cost_quote": "10",
        "buy_hold_return": "0.05",
        "buy_hold_maximum_drawdown": "0.15",
        "segment_returns": ("0.03", "0.04", "0.05"),
        "replay_equal": True,
        "point_in_time_verified": True,
        "future_isolation_verified": True,
    }
    defaults.update(changes)
    return SymbolEvidence(**defaults)


def runs(item, **changes):
    return tuple(run(item, symbol, **changes) for symbol in ("BTCUSDT", "ETHUSDT"))


class EvaluationProtocolTests(unittest.TestCase):
    @patch("sys.argv", ["yatl", "strategy-evaluation-check"])
    def test_runtime_cli_exercises_all_labels(self):
        from yatl.__main__ import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("INSUFFICIENT_EVIDENCE/REJECTED/QUALIFIED_FOR_P4_RESEARCH", text)
        self.assertIn("minimum_days=180", text)
        self.assertIn("replay_equal=true", text)
        self.assertIn("not trading approval", text)

    def test_qualified_requires_all_symbol_and_pooled_gates(self):
        item = plan()
        report = assess_evidence(item, runs(item))
        self.assertEqual(report.label, EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH)
        self.assertEqual(report.reasons, (EvidenceReason.ALL_GATES_PASSED,))
        self.assertEqual(report.total_trades, 60)
        self.assertEqual(report.mean_total_return, Decimal("0.12"))
        self.assertEqual(report.mean_buy_hold_return, Decimal("0.05"))
        self.assertEqual(report.total_cost_quote, Decimal("20"))
        self.assertTrue(report.to_record()["qualification_is_not_trading_approval"])

    def test_short_window_and_small_sample_remain_insufficient(self):
        item = plan(days=30)
        evidence = runs(item, trade_count=2, total_return="-0.50")
        report = assess_evidence(item, evidence)
        self.assertEqual(report.label, EvidenceLabel.INSUFFICIENT_EVIDENCE)
        self.assertEqual(report.reasons, (
            EvidenceReason.EVALUATION_WINDOW_TOO_SHORT,
            EvidenceReason.MINIMUM_TRADES_NOT_MET,
        ))
        self.assertNotIn(EvidenceReason.NO_TRADE_BASELINE_NOT_BEATEN,
                         report.reasons)
        self.assertEqual(MIN_EVALUATION_DAYS, 180)

    def test_each_failure_gate_rejects_sufficient_evidence(self):
        cases = (
            ({"replay_equal": False}, EvidenceReason.SOFTWARE_EVIDENCE_FAILED),
            ({"total_return": "0"}, EvidenceReason.NO_TRADE_BASELINE_NOT_BEATEN),
            ({"total_return": "0.04"}, EvidenceReason.BUY_HOLD_NOT_BEATEN),
            ({"maximum_drawdown": "0.16"}, EvidenceReason.DRAWDOWN_GATE_FAILED),
            ({"segment_returns": ("0.01", "-0.11", "0.02")},
             EvidenceReason.SEGMENT_STABILITY_FAILED),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                item = plan()
                report = assess_evidence(item, runs(item, **changes))
                self.assertEqual(report.label, EvidenceLabel.REJECTED)
                self.assertIn(reason, report.reasons)

    def test_one_weak_symbol_blocks_pooled_qualification(self):
        item = plan()
        evidence = (
            run(item, "BTCUSDT"),
            run(item, "ETHUSDT", trade_count=29),
        )
        report = assess_evidence(item, evidence)
        self.assertEqual(report.label, EvidenceLabel.INSUFFICIENT_EVIDENCE)
        self.assertIn(EvidenceReason.MINIMUM_TRADES_NOT_MET, report.reasons)

    def test_training_and_evaluation_must_be_separate_and_day_aligned(self):
        item = plan()
        for changes in (
                {"training_end_ms": item.evaluation_start_ms + DAY},
                {"training_start_ms": item.training_end_ms},
                {"evaluation_end_ms": item.evaluation_start_ms},
                {"evaluation_start_ms": item.evaluation_start_ms + 1},
                {"symbols": ("BTCUSDT",)},
                {"segment_count": 4},
                {"protocol_version": "changed"}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                replace(item, **changes)

    def test_candidate_version_and_parameter_digest_are_locked(self):
        trend = plan()
        breakout = plan(identity=BREAKOUT_IDENTITY,
                        digest=BREAKOUT_CONFIGURATION.sha256)
        self.assertNotEqual(trend.sha256, breakout.sha256)
        for identity, digest in (
                (TREND_PULLBACK_IDENTITY, "0" * 64),
                (BREAKOUT_IDENTITY, TREND_PULLBACK_CONFIGURATION.sha256)):
            with self.assertRaises(EvaluationError):
                plan(identity=identity, digest=digest)

    def test_evidence_must_match_plan_and_cover_each_symbol_once(self):
        item = plan()
        valid = runs(item)
        mutations = (
            (replace(valid[0], plan_sha256="c" * 64), valid[1]),
            (replace(valid[0], configuration_sha256="c" * 64), valid[1]),
            (replace(valid[0], evaluation_end_ms=item.evaluation_end_ms + DAY),
             valid[1]),
            (valid[0], replace(valid[1], symbol="BTCUSDT")),
        )
        for evidence in mutations:
            with self.assertRaises(EvaluationError):
                assess_evidence(item, evidence)
        with self.assertRaises(EvaluationError):
            assess_evidence(item, list(valid))

    def test_future_isolation_gate_and_material_digest(self):
        item = plan()
        failed = list(runs(item))
        failed[0] = replace(failed[0], future_isolation_verified=False)
        report = assess_evidence(item, tuple(failed))
        self.assertEqual(report.label, EvidenceLabel.REJECTED)
        self.assertIn(EvidenceReason.SOFTWARE_EVIDENCE_FAILED, report.reasons)

        first = assess_evidence(item, runs(item))
        changed = list(runs(item))
        changed[0] = replace(changed[0], dataset_sha256="c" * 64)
        second = assess_evidence(item, tuple(changed))
        self.assertNotEqual(first.sha256, second.sha256)

    def test_future_candle_mutation_cannot_change_sealed_input(self):
        item = plan()
        duration = 3_600_000

        def candle(opened, close):
            return Candle(
                DATA_SOURCE, "BTCUSDT", "1h", opened,
                opened + duration - 1, close, close, close, close,
                "1", "100", 1, True)

        visible = candle(item.evaluation_end_ms - duration, "100")
        future = candle(item.evaluation_end_ms, "200")
        baseline = evaluation_input_sha256(
            (visible,), "BTCUSDT", item.evaluation_end_ms)
        self.assertEqual(
            baseline,
            evaluation_input_sha256(
                (visible, future), "BTCUSDT", item.evaluation_end_ms))
        changed_future = replace(future, open="999", high="999",
                                 low="999", close="999")
        self.assertEqual(
            baseline,
            evaluation_input_sha256(
                (visible, changed_future), "BTCUSDT", item.evaluation_end_ms))
        changed_visible = replace(visible, open="101", high="101",
                                  low="101", close="101")
        self.assertNotEqual(
            baseline,
            evaluation_input_sha256(
                (changed_visible, future), "BTCUSDT",
                item.evaluation_end_ms))

    def test_decimal_inputs_are_exact_canonical_and_fail_closed(self):
        item = plan()
        canonical = run(
            item, "BTCUSDT", total_return="0.1200",
            maximum_drawdown="0.0800", total_cost_quote="10.00",
            segment_returns=("0.030", "0.040", "0.050"))
        self.assertEqual(canonical.total_return, "0.12")
        self.assertEqual(canonical.total_cost_quote, "10")
        self.assertEqual(canonical.segment_returns, ("0.03", "0.04", "0.05"))
        for changes in (
                {"total_return": 0.1},
                {"total_return": "1e-2"},
                {"maximum_drawdown": "-0.1"},
                {"maximum_drawdown": "1.1"},
                {"total_cost_quote": "-1"},
                {"segment_returns": ("0.1", "NaN", "0.1")},
                {"trade_count": True},
                {"dataset_sha256": "ABC"}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                run(item, "BTCUSDT", **changes)

    def test_report_is_sorted_stable_immutable_and_tamper_checked(self):
        item = plan()
        evidence = runs(item)
        first = assess_evidence(item, tuple(reversed(evidence)))
        second = assess_evidence(item, evidence)
        self.assertEqual(first.to_record(), second.to_record())
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(tuple(run.symbol for run in first.runs),
                         ("BTCUSDT", "ETHUSDT"))
        with self.assertRaises(FrozenInstanceError):
            first.label = EvidenceLabel.REJECTED
        with self.assertRaises(EvaluationError):
            replace(first, total_trades=61)
        self.assertIsInstance(first, EvaluationReport)


if __name__ == "__main__":
    unittest.main()
