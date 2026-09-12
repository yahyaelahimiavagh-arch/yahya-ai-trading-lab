import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yatl.__main__ import main
from yatl.strategy import (BREAKOUT_IDENTITY, TREND_PULLBACK_IDENTITY,
                           EvidenceLabel, EvidenceReason, P3AuditError,
                           P3AuditResult, audit_p3)
from yatl.strategy.audit import (EXPECTED_CONFIGURATION_SHA256,
                                 EXPECTED_INDEX_SHA256,
                                 EXPECTED_REPORT_SHA256, _read_evidence)


def evaluation(identity):
    return SimpleNamespace(
        plan=SimpleNamespace(
            identity=identity,
            configuration_sha256=EXPECTED_CONFIGURATION_SHA256[identity]),
        sha256=EXPECTED_REPORT_SHA256[identity],
        label=EvidenceLabel.INSUFFICIENT_EVIDENCE,
        reasons=(EvidenceReason.EVALUATION_WINDOW_TOO_SHORT,
                 EvidenceReason.MINIMUM_TRADES_NOT_MET),
    )


def matrix():
    counts = ((TREND_PULLBACK_IDENTITY, "BTCUSDT", 12),
              (TREND_PULLBACK_IDENTITY, "ETHUSDT", 19),
              (BREAKOUT_IDENTITY, "BTCUSDT", 1),
              (BREAKOUT_IDENTITY, "ETHUSDT", 3))
    return SimpleNamespace(
        runs=tuple(SimpleNamespace(
            identity=identity, symbol=symbol,
            report=SimpleNamespace(trade_count=trades),
        ) for identity, symbol, trades in counts),
        evaluations=(evaluation(TREND_PULLBACK_IDENTITY),
                     evaluation(BREAKOUT_IDENTITY)),
    )


class P3AuditTests(unittest.TestCase):
    def test_evidence_snapshot_rejects_tampering_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = {"one.json": "{}\n", "two.json": "[]\n"}
            for name, content in expected.items():
                (root / name).write_text(content, encoding="utf-8")
            self.assertEqual(_read_evidence(root, expected), expected)
            (root / "one.json").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(P3AuditError):
                _read_evidence(root, expected)
            (root / "one.json").write_text("{}\n", encoding="utf-8")
            (root / "extra.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(P3AuditError):
                _read_evidence(root, expected)

    @patch("yatl.strategy.audit.audit_run_manifest")
    @patch("yatl.strategy.audit._read_evidence")
    @patch("yatl.strategy.audit._expected_files")
    @patch("yatl.strategy.audit.candidate_matrix_sha256",
           return_value=EXPECTED_INDEX_SHA256)
    @patch("yatl.strategy.audit.run_accepted_candidate_matrix")
    @patch("yatl.strategy.audit._audit_source_safety")
    @patch("yatl.strategy.audit.audit_p1_manifest")
    def test_final_audit_recomputes_and_checks_all_files(
            self, p1, safety, run, _digest, expected_files, read, p2_audit):
        run.return_value = matrix()
        names = ["p3-009-index.json"]
        for number in range(4):
            names.extend((
                f"run-{number}-candidate-costed.json",
                f"run-{number}-candidate-zero-cost.json",
                f"run-{number}-baseline-no-trade.json",
                f"run-{number}-baseline-buy-hold.json",
                f"run-{number}-decision-trace.json",
            ))
        evidence = {name: ("index\n" if name == "p3-009-index.json"
                           else "artifact\n") for name in names}
        expected_files.return_value = evidence
        read.return_value = evidence
        p2_audit.side_effect = [SimpleNamespace(symbol=symbol)
                                for _ in range(8)
                                for symbol in ("BTCUSDT", "ETHUSDT")]
        with patch("yatl.strategy.audit.hashlib.sha256") as sha:
            sha.return_value.hexdigest.return_value = EXPECTED_INDEX_SHA256
            result = audit_p3("database", "manifest", "evidence")
        self.assertEqual(
            (result.candidates, result.symbols, result.runs, result.files,
             result.p2_artifacts, result.trades),
            (2, 2, 4, 21, 16, 35))
        p1.assert_called_once_with("manifest")
        safety.assert_called_once_with()
        self.assertEqual(p2_audit.call_count, 16)

    @patch("yatl.strategy.audit.candidate_matrix_sha256",
           return_value="0" * 64)
    def test_changed_accepted_replay_fails_closed(self, _digest):
        from yatl.strategy.audit import _audit_frozen_results
        with self.assertRaises(P3AuditError):
            _audit_frozen_results(matrix())

    @patch("yatl.__main__.audit_p3")
    @patch("sys.argv", ["yatl", "p3-audit"])
    def test_cli_reports_safe_final_audit(self, audit):
        audit.return_value = P3AuditResult(
            2, 2, 4, 21, 16, 35, EXPECTED_INDEX_SHA256)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("P3 final acceptance audit", text)
        self.assertIn("files=21", text)
        self.assertIn("INSUFFICIENT_EVIDENCE", text)
        self.assertIn("LIVE_MASTER_LOCK=OFF", text)
        self.assertIn("No exchange order", text)


if __name__ == "__main__":
    unittest.main()
