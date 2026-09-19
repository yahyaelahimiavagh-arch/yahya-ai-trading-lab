"""Deterministic non-AI reference analyst for P6."""

import hashlib
import json
from dataclasses import dataclass

from .contracts import (
    AnalystClaim,
    AnalystContractError,
    AnalystDisposition,
    AnalystReason,
    AnalystReport,
    ClaimKind,
    EvidenceLayer,
    StrategyEvidenceState,
    build_analyst_report,
)
from .evidence import PointInTimeEvidenceBundle


BASELINE_ID = "P6_DETERMINISTIC_ANALYST_BASELINE_V1"
BASELINE_SCHEMA_VERSION = 1


class DeterministicBaselineError(AnalystContractError):
    """The deterministic analyst baseline could not be reproduced safely."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _evidence_id(bundle, layer):
    matches = tuple(item for item in bundle.evidence if item.layer is layer)
    if len(matches) != 1:
        raise DeterministicBaselineError("Baseline requires exactly one evidence layer")
    return matches[0].evidence_id


def _baseline_claims(bundle):
    if not isinstance(bundle, PointInTimeEvidenceBundle):
        raise DeterministicBaselineError("Validated point-in-time evidence is required")
    if bundle.strategy_evidence is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE:
        raise DeterministicBaselineError(
            "Deterministic baseline cannot upgrade strategy evidence"
        )

    market_id = _evidence_id(bundle, EvidenceLayer.P1_PUBLIC_MARKET)
    strategy_id = _evidence_id(bundle, EvidenceLayer.P3_STRATEGY_EVIDENCE)
    risk_id = _evidence_id(bundle, EvidenceLayer.P4_RISK_STATUS)
    safety_id = _evidence_id(bundle, EvidenceLayer.P5_SAFETY_STATUS)

    return (
        AnalystClaim(
            "BASELINE_FACT_MARKET",
            ClaimKind.FACT,
            "Accepted public market evidence is available at the decision boundary.",
            (market_id,),
        ),
        AnalystClaim(
            "BASELINE_FACT_RISK",
            ClaimKind.FACT,
            "Accepted risk status is available and remains outside analyst authority.",
            (risk_id,),
        ),
        AnalystClaim(
            "BASELINE_FACT_SAFETY",
            ClaimKind.FACT,
            "Accepted safety status preserves the analysis-only boundary.",
            (safety_id,),
        ),
        AnalystClaim(
            "BASELINE_OBSERVATION_STRATEGY",
            ClaimKind.DERIVED_OBSERVATION,
            "Strategy evidence remains INSUFFICIENT_EVIDENCE.",
            (strategy_id,),
        ),
        AnalystClaim(
            "BASELINE_UNCERTAINTY_STRATEGY",
            ClaimKind.UNCERTAINTY,
            "Insufficient strategy evidence prevents a qualified research conclusion.",
            (strategy_id,),
        ),
    )


@dataclass(frozen=True, slots=True)
class DeterministicBaselineAnalysis:
    """Canonical reference result produced only from an accepted evidence bundle."""

    bundle: PointInTimeEvidenceBundle
    report: AnalystReport
    baseline_id: str = BASELINE_ID

    def __post_init__(self):
        if (
            not isinstance(self.bundle, PointInTimeEvidenceBundle)
            or not isinstance(self.report, AnalystReport)
            or self.baseline_id != BASELINE_ID
            or self.bundle.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise DeterministicBaselineError("Baseline analysis identity is invalid")

        expected_input = self.bundle.analyst_input
        expected_claims = _baseline_claims(self.bundle)
        expected_report = build_analyst_report(expected_input, expected_claims)
        if (
            self.report != expected_report
            or self.report.analysis_input != expected_input
            or self.report.disposition is not AnalystDisposition.REVIEW
            or self.report.reason is not AnalystReason.UNCERTAINTY_PRESENT
        ):
            raise DeterministicBaselineError(
                "Baseline analysis differs from the conservative reference result"
            )

    def as_record(self):
        return {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "baseline_id": self.baseline_id,
            "bundle_sha256": self.bundle.bundle_sha256,
            "strategy_evidence": self.bundle.strategy_evidence.value,
            "report": self.report.as_record(),
            "report_sha256": self.report.report_sha256,
        }

    @property
    def baseline_sha256(self):
        return _sha256(self.as_record())


def build_deterministic_baseline(bundle):
    """Build the non-AI safety/reference analysis for one accepted bundle."""
    if not isinstance(bundle, PointInTimeEvidenceBundle):
        raise DeterministicBaselineError("Validated point-in-time evidence is required")
    claims = _baseline_claims(bundle)
    report = build_analyst_report(bundle.analyst_input, claims)
    return DeterministicBaselineAnalysis(bundle, report)
