"""Independent fail-closed acceptance audit for the complete P3 framework."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from yatl.backtest import P2AuditError, audit_run_manifest
from yatl.data import AuditError, SYMBOLS, audit_p1_manifest

from .breakout import CONFIGURATION as BREAKOUT_CONFIGURATION
from .breakout import IDENTITY as BREAKOUT_IDENTITY
from .evaluate import EvidenceLabel, EvidenceReason
from .runs import (CandidateRunError, candidate_matrix_sha256,
                   run_accepted_candidate_matrix)
from .trend import CONFIGURATION as TREND_CONFIGURATION
from .trend import IDENTITY as TREND_IDENTITY


EXPECTED_INDEX_SHA256 = (
    "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a"
)
EXPECTED_REPORT_SHA256 = {
    TREND_IDENTITY: "d2e4ec2d1c8064bf2c133439293880890a5fcf72a7f23329172d44b5e7f7be82",
    BREAKOUT_IDENTITY: "63be327a16cd922088923f108b964ff7d24d1a9a4cec6149669cb291c8dd99d0",
}
EXPECTED_CONFIGURATION_SHA256 = {
    TREND_IDENTITY: TREND_CONFIGURATION.sha256,
    BREAKOUT_IDENTITY: BREAKOUT_CONFIGURATION.sha256,
}
EXPECTED_TRADES = {
    (TREND_IDENTITY, "BTCUSDT"): 12,
    (TREND_IDENTITY, "ETHUSDT"): 19,
    (BREAKOUT_IDENTITY, "BTCUSDT"): 1,
    (BREAKOUT_IDENTITY, "ETHUSDT"): 3,
}
EXPECTED_REASONS = (
    EvidenceReason.EVALUATION_WINDOW_TOO_SHORT,
    EvidenceReason.MINIMUM_TRADES_NOT_MET,
)
MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 24 * 1024 * 1024


class P3AuditError(Exception):
    """P3 acceptance evidence is incomplete, inconsistent or unsafe."""


@dataclass(frozen=True, slots=True)
class P3AuditResult:
    candidates: int
    symbols: int
    runs: int
    files: int
    p2_artifacts: int
    trades: int
    index_sha256: str

    def __post_init__(self):
        if ((self.candidates, self.symbols, self.runs, self.files,
             self.p2_artifacts, self.trades)
                != (2, 2, 4, 21, 16, 35)
                or self.index_sha256 != EXPECTED_INDEX_SHA256):
            raise P3AuditError("P3 audit result is inconsistent")


def _name(result, suffix):
    strategy = result.identity.strategy_id.lower().replace("_", "-")
    return (f"{strategy}-{result.identity.version}-"
            f"{result.symbol.lower()}-{suffix}.json")


def _expected_files(result):
    files = {"p3-009-index.json": result.index_json}
    for item in result.runs:
        files.update({
            _name(item, "candidate-costed"): item.candidate_artifact,
            _name(item, "candidate-zero-cost"): item.zero_cost_artifact,
            _name(item, "baseline-no-trade"): item.no_trade_artifact,
            _name(item, "baseline-buy-hold"): item.buy_hold_artifact,
            _name(item, "decision-trace"): item.trace_json,
        })
    if len(files) != 21:
        raise P3AuditError("P3 evidence file coverage is incomplete")
    return files


def _read_evidence(directory, expected):
    target = (Path(directory)
              if isinstance(directory, (str, Path)) and str(directory)
              else None)
    if target is None or not target.is_dir() or target.is_symlink():
        raise P3AuditError("P3 evidence directory is invalid")
    try:
        paths = tuple(sorted(target.iterdir(), key=lambda item: item.name))
        if (set(item.name for item in paths) != set(expected)
                or any(item.is_symlink() or not item.is_file() for item in paths)):
            raise P3AuditError("P3 evidence directory contents are invalid")
        before = {}
        total = 0
        for path in paths:
            payload = path.read_bytes()
            total += len(payload)
            if (not payload or len(payload) > MAX_EVIDENCE_FILE_BYTES
                    or total > MAX_EVIDENCE_TOTAL_BYTES):
                raise P3AuditError("P3 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
        if before != after:
            raise P3AuditError("P3 evidence changed during audit")
        decoded = {name: payload.decode("utf-8")
                   for name, payload in before.items()}
    except P3AuditError:
        raise
    except (OSError, UnicodeDecodeError):
        raise P3AuditError("P3 evidence cannot be read safely") from None
    if decoded != expected:
        raise P3AuditError("P3 evidence differs from deterministic replay")
    return decoded


def _audit_source_safety():
    forbidden = (("/api/v3/" + "order"), ("f" + "api"), ("d" + "api"),
                 ("with" + "draw("), ("from yatl." + "account"),
                 ("import yatl." + "account"))
    try:
        for path in Path(__file__).parent.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(value in text for value in forbidden):
                raise P3AuditError("P3 source safety boundary failed")
    except OSError:
        raise P3AuditError("P3 source safety scan failed") from None


def _audit_frozen_results(result):
    if (candidate_matrix_sha256(result) != EXPECTED_INDEX_SHA256
            or {(item.identity, item.symbol): item.report.trade_count
                for item in result.runs} != EXPECTED_TRADES):
        raise P3AuditError("P3 accepted-data replay changed")
    if len(result.evaluations) != 2:
        raise P3AuditError("P3 evaluation coverage is incomplete")
    for evaluation in result.evaluations:
        identity = evaluation.plan.identity
        if (EXPECTED_CONFIGURATION_SHA256.get(identity)
                != evaluation.plan.configuration_sha256
                or EXPECTED_REPORT_SHA256.get(identity) != evaluation.sha256
                or evaluation.label is not EvidenceLabel.INSUFFICIENT_EVIDENCE
                or evaluation.reasons != EXPECTED_REASONS):
            raise P3AuditError("P3 frozen digest or evidence label changed")


def audit_p3(database_path="data/p1/market.sqlite3",
             manifest_path="manifests/p1-market-data.json",
             evidence_dir="data/p3/p3-009-evidence"):
    """Recompute P3 and compare every accepted artifact byte-for-byte."""
    try:
        audit_p1_manifest(manifest_path)
        _audit_source_safety()
        result = run_accepted_candidate_matrix(database_path, manifest_path)
        _audit_frozen_results(result)
        expected = _expected_files(result)
        evidence = _read_evidence(evidence_dir, expected)
        p2_names = tuple(name for name in sorted(evidence)
                         if name.endswith(("candidate-costed.json",
                                           "candidate-zero-cost.json",
                                           "baseline-no-trade.json",
                                           "baseline-buy-hold.json")))
        if len(p2_names) != 16:
            raise P3AuditError("P3 P2-artifact coverage is incomplete")
        audited = tuple(audit_run_manifest(evidence[name]) for name in p2_names)
        if len(audited) != 16 or any(item.symbol not in SYMBOLS for item in audited):
            raise P3AuditError("P3 P2-artifact audit is inconsistent")
        digest = hashlib.sha256(
            evidence["p3-009-index.json"].encode("utf-8")).hexdigest()
        return P3AuditResult(
            candidates=2, symbols=len(SYMBOLS), runs=len(result.runs),
            files=len(evidence), p2_artifacts=len(audited),
            trades=sum(item.report.trade_count for item in result.runs),
            index_sha256=digest,
        )
    except P3AuditError:
        raise
    except (AuditError, CandidateRunError, P2AuditError, TypeError, ValueError):
        raise P3AuditError("P3 final acceptance audit failed safely") from None
