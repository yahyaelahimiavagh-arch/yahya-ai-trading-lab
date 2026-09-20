"""Deterministic claim/evidence grounding gate for accepted P6 model responses."""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from .contracts import (
    AnalystContractError,
    AnalystDisposition,
    AnalystReason,
    AnalystReport,
    ClaimKind,
    EvidenceLayer,
    StrategyEvidenceState,
    build_analyst_report,
)
from .evidence import LayerEvidence, PointInTimeEvidenceBundle
from .request import build_model_request
from .response import ModelResponseValidation


GROUNDING_SCHEMA_VERSION = 1


class GroundingCode(str, Enum):
    GROUNDED = "GROUNDED"
    UPSTREAM_REJECTED = "UPSTREAM_REJECTED"
    INPUT_BINDING_MISMATCH = "INPUT_BINDING_MISMATCH"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    CLAIM_SHAPE_MISMATCH = "CLAIM_SHAPE_MISMATCH"
    EVIDENCE_REFERENCE_MISMATCH = "EVIDENCE_REFERENCE_MISMATCH"
    EVIDENCE_STATE_INVALID = "EVIDENCE_STATE_INVALID"
    CONTRADICTION = "CONTRADICTION"


class GroundingBoundaryError(AnalystContractError):
    """Trusted caller or grounding result violates the deterministic boundary."""


@dataclass(frozen=True, slots=True)
class _GroundingRule:
    claim_id: str
    kind: ClaimKind
    text: str
    layer: EvidenceLayer


_RULES = {
    "MODEL_FACT_MARKET": _GroundingRule(
        "MODEL_FACT_MARKET",
        ClaimKind.FACT,
        "Accepted public market evidence is present.",
        EvidenceLayer.P1_PUBLIC_MARKET,
    ),
    "MODEL_FACT_RISK": _GroundingRule(
        "MODEL_FACT_RISK",
        ClaimKind.FACT,
        "Accepted risk status is PASS and grants no mutable or quantity authority.",
        EvidenceLayer.P4_RISK_STATUS,
    ),
    "MODEL_FACT_SAFETY": _GroundingRule(
        "MODEL_FACT_SAFETY",
        ClaimKind.FACT,
        "Accepted safety status preserves PAPER ONLY and no trade or AI execution authority.",
        EvidenceLayer.P5_SAFETY_STATUS,
    ),
    "MODEL_OBSERVATION_STRATEGY": _GroundingRule(
        "MODEL_OBSERVATION_STRATEGY",
        ClaimKind.DERIVED_OBSERVATION,
        "Strategy evidence remains INSUFFICIENT_EVIDENCE.",
        EvidenceLayer.P3_STRATEGY_EVIDENCE,
    ),
    "MODEL_UNCERTAINTY_STRATEGY": _GroundingRule(
        "MODEL_UNCERTAINTY_STRATEGY",
        ClaimKind.UNCERTAINTY,
        "Strategy evidence remains insufficient for a qualified conclusion.",
        EvidenceLayer.P3_STRATEGY_EVIDENCE,
    ),
}

_CONTRADICTIONS = frozenset(
    text.casefold()
    for text in (
        "Strategy evidence is sufficient for a qualified conclusion.",
        "Strategy evidence is QUALIFIED_FOR_P4_RESEARCH.",
        "Accepted risk status grants quantity authority.",
        "Accepted risk status allows RiskAuthorization mutation.",
        "Accepted safety status permits trade execution.",
        "Accepted safety status permits AI direct execution.",
        "LIVE_MASTER_LOCK is ON.",
    )
)


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_text(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fallback_report(validation):
    return build_analyst_report(
        validation.request.bundle.analyst_input,
        (),
    )


def _evidence_state_valid(bundle, evidence):
    if not isinstance(bundle, PointInTimeEvidenceBundle):
        return False
    if not isinstance(evidence, LayerEvidence):
        return False
    if (
        evidence.symbol != bundle.symbol
        or evidence.observed_at_ms > bundle.decision_time_ms
        or evidence.valid_through_ms < bundle.decision_time_ms
    ):
        return False

    payload = evidence.payload
    if evidence.layer is EvidenceLayer.P1_PUBLIC_MARKET:
        return (
            payload.get("accepted") is True
            and payload.get("data_scope") == "PUBLIC_SPOT_CLOSED_OHLCV"
            and type(payload.get("latest_closed_at_ms")) is int
            and payload["latest_closed_at_ms"] <= bundle.decision_time_ms
        )
    if evidence.layer is EvidenceLayer.P3_STRATEGY_EVIDENCE:
        return (
            payload.get("accepted") is True
            and payload.get("strategy_evidence")
            == StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value
            and bundle.strategy_evidence
            is StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        )
    if evidence.layer is EvidenceLayer.P4_RISK_STATUS:
        return (
            payload.get("accepted") is True
            and payload.get("risk_status") == "PASS"
            and payload.get("quantity_authority") is False
            and payload.get("risk_authorization_mutation") is False
        )
    if evidence.layer is EvidenceLayer.P5_SAFETY_STATUS:
        return (
            payload.get("accepted") is True
            and payload.get("safety_status") == "PASS"
            and payload.get("paper_only") is True
            and payload.get("live_master_lock") == "OFF"
            and payload.get("trade_permission") is False
            and payload.get("order_endpoints") is False
            and payload.get("ai_direct_execution") is False
            and payload.get("credentials_present") is False
            and payload.get("private_payload_present") is False
        )
    return False


def _request_binding_valid(validation):
    request = validation.request
    bundle = request.bundle
    try:
        replay = build_model_request(bundle)
    except (AnalystContractError, TypeError, ValueError):
        return False
    return (
        replay.material_json == request.material_json
        and replay.material_sha256 == request.material_sha256
        and replay.request_sha256 == request.request_sha256
        and validation.report.analysis_input == bundle.analyst_input
    )


def _evaluate(validation):
    if not isinstance(validation, ModelResponseValidation):
        raise GroundingBoundaryError(
            "Validated model response is required for grounding"
        )

    fallback = _fallback_report(validation)
    if not validation.accepted:
        return False, GroundingCode.UPSTREAM_REJECTED, fallback, ()

    if not _request_binding_valid(validation):
        return False, GroundingCode.INPUT_BINDING_MISMATCH, fallback, ()

    bundle = validation.request.bundle
    evidence_by_id = {item.evidence_id: item for item in bundle.evidence}
    reference_by_id = {
        item.evidence_id: item
        for item in validation.report.analysis_input.evidence
    }

    grounded_claim_ids = []
    for claim in validation.report.claims:
        if claim.text.casefold() in _CONTRADICTIONS:
            return False, GroundingCode.CONTRADICTION, fallback, ()

        rule = _RULES.get(claim.claim_id)
        if rule is None:
            return False, GroundingCode.UNSUPPORTED_CLAIM, fallback, ()
        if (
            claim.kind is not rule.kind
            or claim.text != rule.text
            or len(claim.evidence_ids) != 1
        ):
            return False, GroundingCode.CLAIM_SHAPE_MISMATCH, fallback, ()

        evidence_id = claim.evidence_ids[0]
        evidence = evidence_by_id.get(evidence_id)
        reference = reference_by_id.get(evidence_id)
        if (
            evidence is None
            or reference is None
            or evidence.reference != reference
            or evidence.layer is not rule.layer
        ):
            return False, GroundingCode.EVIDENCE_REFERENCE_MISMATCH, fallback, ()

        if not _evidence_state_valid(bundle, evidence):
            return False, GroundingCode.EVIDENCE_STATE_INVALID, fallback, ()

        grounded_claim_ids.append(claim.claim_id)

    grounded_claim_ids = tuple(grounded_claim_ids)
    if (
        not grounded_claim_ids
        or grounded_claim_ids
        != tuple(sorted(grounded_claim_ids))
        or not any(
            claim.kind is ClaimKind.UNCERTAINTY
            for claim in validation.report.claims
        )
        or validation.report.disposition is not AnalystDisposition.REVIEW
        or validation.report.reason is not AnalystReason.UNCERTAINTY_PRESENT
    ):
        return False, GroundingCode.CLAIM_SHAPE_MISMATCH, fallback, ()

    return True, GroundingCode.GROUNDED, validation.report, grounded_claim_ids


@dataclass(frozen=True, slots=True)
class GroundingValidation:
    """Canonical grounding result. Rejected output is always fail-closed."""

    validation: ModelResponseValidation
    accepted: bool
    code: GroundingCode
    report: AnalystReport
    grounded_claim_ids: tuple[str, ...]

    def __post_init__(self):
        if (
            not isinstance(self.validation, ModelResponseValidation)
            or type(self.accepted) is not bool
            or not isinstance(self.code, GroundingCode)
            or not isinstance(self.report, AnalystReport)
            or type(self.grounded_claim_ids) is not tuple
            or any(not isinstance(item, str) for item in self.grounded_claim_ids)
        ):
            raise GroundingBoundaryError("Grounding result identity is invalid")

        expected = _evaluate(self.validation)
        actual = (
            self.accepted,
            self.code,
            self.report,
            self.grounded_claim_ids,
        )
        if actual != expected:
            raise GroundingBoundaryError(
                "Grounding result differs from deterministic evaluation"
            )

    def as_record(self):
        return {
            "schema_version": GROUNDING_SCHEMA_VERSION,
            "request_sha256": self.validation.request.request_sha256,
            "response_validation_sha256": self.validation.validation_sha256,
            "bundle_sha256": self.validation.request.bundle.bundle_sha256,
            "accepted": self.accepted,
            "code": self.code.value,
            "grounded_claim_ids": list(self.grounded_claim_ids),
            "report": self.report.as_record(),
            "report_sha256": self.report.report_sha256,
        }

    @property
    def grounding_sha256(self):
        return _sha256_text(_canonical_json(self.as_record()))


def ground_model_response(validation):
    """Apply exact deterministic claim/evidence grounding to P6-005 output."""
    accepted, code, report, claim_ids = _evaluate(validation)
    return GroundingValidation(
        validation,
        accepted,
        code,
        report,
        claim_ids,
    )
