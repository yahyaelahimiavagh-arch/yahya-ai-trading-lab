"""Deterministic read-only point-in-time evidence bundles for P6 analysis."""

import hashlib
import json
import re
from dataclasses import dataclass

from .contracts import (
    AnalystContractError,
    AnalystInput,
    EvidenceLayer,
    EvidenceReference,
    StrategyEvidenceState,
)


EVIDENCE_BUNDLE_SCHEMA_VERSION = 1
EVIDENCE_MATERIAL_SCHEMA_VERSION = 1
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EVIDENCE_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
MAX_CANONICAL_PAYLOAD_BYTES = 4096
REQUIRED_LAYERS = (
    EvidenceLayer.P1_PUBLIC_MARKET,
    EvidenceLayer.P3_STRATEGY_EVIDENCE,
    EvidenceLayer.P4_RISK_STATUS,
    EvidenceLayer.P5_SAFETY_STATUS,
)


class EvidenceBundleError(AnalystContractError):
    """P6 evidence is incomplete, stale, ambiguous or provenance-invalid."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_text(payload):
    if not isinstance(payload, str):
        raise EvidenceBundleError("Digest payload must be text")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_record(payload):
    return _sha256_text(_canonical_json(payload))


def _sha256(value, field):
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise EvidenceBundleError(f"{field} must be a lowercase SHA-256")
    return value


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceBundleError("Evidence payload contains duplicate JSON keys")
        result[key] = value
    return result


def _decode_canonical_payload(payload):
    if (
        not isinstance(payload, str)
        or not payload
        or len(payload.encode("utf-8")) > MAX_CANONICAL_PAYLOAD_BYTES
    ):
        raise EvidenceBundleError("Evidence payload size is invalid")
    try:
        record = json.loads(payload, object_pairs_hook=_no_duplicate_object)
    except (json.JSONDecodeError, EvidenceBundleError):
        raise EvidenceBundleError("Evidence payload JSON is invalid or ambiguous") from None
    if not isinstance(record, dict) or _canonical_json(record) != payload:
        raise EvidenceBundleError("Evidence payload JSON is noncanonical")
    return record


def _exact_keys(record, expected):
    if set(record) != set(expected):
        raise EvidenceBundleError("Evidence payload fields are not exactly allowed")


def _validate_p1(record):
    _exact_keys(
        record,
        ("accepted", "data_scope", "latest_closed_at_ms", "manifest_sha256"),
    )
    if (
        record["accepted"] is not True
        or record["data_scope"] != "PUBLIC_SPOT_CLOSED_OHLCV"
        or type(record["latest_closed_at_ms"]) is not int
        or record["latest_closed_at_ms"] < 0
    ):
        raise EvidenceBundleError("P1 public-market evidence is not accepted")
    _sha256(record["manifest_sha256"], "manifest_sha256")


def _validate_p3(record):
    _exact_keys(
        record,
        ("accepted", "candidate_matrix_sha256", "strategy_evidence"),
    )
    if (
        record["accepted"] is not True
        or record["strategy_evidence"]
        != StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value
    ):
        raise EvidenceBundleError(
            "P3 strategy evidence must remain INSUFFICIENT_EVIDENCE"
        )
    _sha256(record["candidate_matrix_sha256"], "candidate_matrix_sha256")


def _validate_p4(record):
    _exact_keys(
        record,
        (
            "accepted",
            "audit_sha256",
            "policy_sha256",
            "quantity_authority",
            "risk_authorization_mutation",
            "risk_status",
        ),
    )
    if (
        record["accepted"] is not True
        or record["risk_status"] != "PASS"
        or record["risk_authorization_mutation"] is not False
        or record["quantity_authority"] is not False
    ):
        raise EvidenceBundleError("P4 risk status would grant mutable authority")
    _sha256(record["audit_sha256"], "audit_sha256")
    _sha256(record["policy_sha256"], "policy_sha256")


def _validate_p5(record):
    _exact_keys(
        record,
        (
            "accepted",
            "ai_direct_execution",
            "audit_sha256",
            "credentials_present",
            "live_master_lock",
            "order_endpoints",
            "paper_only",
            "policy_sha256",
            "private_payload_present",
            "safety_status",
            "trade_permission",
        ),
    )
    if (
        record["accepted"] is not True
        or record["safety_status"] != "PASS"
        or record["paper_only"] is not True
        or record["live_master_lock"] != "OFF"
        or record["trade_permission"] is not False
        or record["order_endpoints"] is not False
        or record["ai_direct_execution"] is not False
        or record["credentials_present"] is not False
        or record["private_payload_present"] is not False
    ):
        raise EvidenceBundleError("P5 safety status violates analysis-only boundaries")
    _sha256(record["audit_sha256"], "audit_sha256")
    _sha256(record["policy_sha256"], "policy_sha256")


_LAYER_VALIDATORS = {
    EvidenceLayer.P1_PUBLIC_MARKET: _validate_p1,
    EvidenceLayer.P3_STRATEGY_EVIDENCE: _validate_p3,
    EvidenceLayer.P4_RISK_STATUS: _validate_p4,
    EvidenceLayer.P5_SAFETY_STATUS: _validate_p5,
}


def _provenance_record(
    evidence_id,
    layer,
    symbol,
    observed_at_ms,
    valid_through_ms,
    source_sha256,
):
    return {
        "schema_version": EVIDENCE_MATERIAL_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "layer": layer.value,
        "symbol": symbol,
        "observed_at_ms": observed_at_ms,
        "valid_through_ms": valid_through_ms,
        "source_sha256": source_sha256,
    }


@dataclass(frozen=True, slots=True)
class LayerEvidence:
    """One canonical, bounded and provenance-bound read-only layer artifact."""

    evidence_id: str
    layer: EvidenceLayer
    symbol: str
    observed_at_ms: int
    valid_through_ms: int
    canonical_payload: str
    source_sha256: str
    provenance_sha256: str

    def __post_init__(self):
        if (
            not isinstance(self.evidence_id, str)
            or EVIDENCE_ID_PATTERN.fullmatch(self.evidence_id) is None
            or not isinstance(self.layer, EvidenceLayer)
            or self.symbol not in SYMBOLS
            or type(self.observed_at_ms) is not int
            or type(self.valid_through_ms) is not int
            or self.observed_at_ms < 0
            or self.valid_through_ms < self.observed_at_ms
        ):
            raise EvidenceBundleError("Evidence material identity is invalid")

        record = _decode_canonical_payload(self.canonical_payload)
        validator = _LAYER_VALIDATORS.get(self.layer)
        if validator is None:
            raise EvidenceBundleError("Evidence layer is unsupported")
        validator(record)
        if (
            self.layer is EvidenceLayer.P1_PUBLIC_MARKET
            and record["latest_closed_at_ms"] > self.observed_at_ms
        ):
            raise EvidenceBundleError("P1 latest closed data is newer than provenance")

        expected_source = _sha256_text(self.canonical_payload)
        if _sha256(self.source_sha256, "source_sha256") != expected_source:
            raise EvidenceBundleError("Evidence source digest mismatch")
        expected_provenance = _sha256_record(
            _provenance_record(
                self.evidence_id,
                self.layer,
                self.symbol,
                self.observed_at_ms,
                self.valid_through_ms,
                self.source_sha256,
            )
        )
        if _sha256(self.provenance_sha256, "provenance_sha256") != expected_provenance:
            raise EvidenceBundleError("Evidence provenance digest mismatch")

    @property
    def payload(self):
        return _decode_canonical_payload(self.canonical_payload)

    @property
    def reference(self):
        return EvidenceReference(
            self.evidence_id,
            self.layer,
            self.source_sha256,
            self.symbol,
            self.observed_at_ms,
        )

    def as_record(self):
        return {
            **_provenance_record(
                self.evidence_id,
                self.layer,
                self.symbol,
                self.observed_at_ms,
                self.valid_through_ms,
                self.source_sha256,
            ),
            "provenance_sha256": self.provenance_sha256,
            "payload": self.payload,
        }


def build_layer_evidence(
    evidence_id,
    layer,
    symbol,
    observed_at_ms,
    valid_through_ms,
    payload,
):
    """Create an immutable layer artifact and bind payload + provenance digests."""
    if not isinstance(payload, dict):
        raise EvidenceBundleError("Evidence payload must be an object")
    canonical_payload = _canonical_json(payload)
    source_sha256 = _sha256_text(canonical_payload)
    provenance_sha256 = _sha256_record(
        _provenance_record(
            evidence_id,
            layer,
            symbol,
            observed_at_ms,
            valid_through_ms,
            source_sha256,
        )
    )
    return LayerEvidence(
        evidence_id,
        layer,
        symbol,
        observed_at_ms,
        valid_through_ms,
        canonical_payload,
        source_sha256,
        provenance_sha256,
    )


@dataclass(frozen=True, slots=True)
class PointInTimeEvidenceBundle:
    """Exactly one accepted P1/P3/P4/P5 artifact, frozen at one decision time."""

    symbol: str
    decision_time_ms: int
    evidence: tuple[LayerEvidence, ...]
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or type(self.decision_time_ms) is not int
            or self.decision_time_ms < 0
            or type(self.evidence) is not tuple
            or len(self.evidence) != len(REQUIRED_LAYERS)
            or any(not isinstance(item, LayerEvidence) for item in self.evidence)
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise EvidenceBundleError("Evidence bundle identity or coverage is invalid")

        ids = tuple(item.evidence_id for item in self.evidence)
        layers = tuple(item.layer for item in self.evidence)
        if (
            len(set(ids)) != len(ids)
            or ids != tuple(sorted(ids))
            or len(set(layers)) != len(layers)
            or set(layers) != set(REQUIRED_LAYERS)
        ):
            raise EvidenceBundleError(
                "Evidence bundle is duplicate, ambiguous, unordered or incomplete"
            )

        for item in self.evidence:
            replay = LayerEvidence(
                item.evidence_id,
                item.layer,
                item.symbol,
                item.observed_at_ms,
                item.valid_through_ms,
                item.canonical_payload,
                item.source_sha256,
                item.provenance_sha256,
            )
            if replay != item:
                raise EvidenceBundleError("Evidence reconstruction changed identity")
            if item.symbol != self.symbol:
                raise EvidenceBundleError("Evidence bundle contains cross-symbol material")
            if item.observed_at_ms > self.decision_time_ms:
                raise EvidenceBundleError("Evidence bundle contains future material")
            if item.valid_through_ms < self.decision_time_ms:
                raise EvidenceBundleError("Evidence bundle contains stale material")
            if (
                item.layer is EvidenceLayer.P1_PUBLIC_MARKET
                and item.payload["latest_closed_at_ms"] > self.decision_time_ms
            ):
                raise EvidenceBundleError("P1 bundle contains future market data")

        p3 = next(
            item for item in self.evidence
            if item.layer is EvidenceLayer.P3_STRATEGY_EVIDENCE
        )
        if (
            p3.payload["strategy_evidence"]
            != StrategyEvidenceState.INSUFFICIENT_EVIDENCE.value
        ):
            raise EvidenceBundleError("P3 evidence label was upgraded")

    def as_record(self):
        return {
            "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "strategy_evidence": self.strategy_evidence.value,
            "evidence": [item.as_record() for item in self.evidence],
            "safety": {
                "paper_only": True,
                "live_master_lock": "OFF",
                "trade_permission": False,
                "order_endpoints": False,
                "ai_direct_execution": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
            },
        }

    @property
    def bundle_sha256(self):
        return _sha256_record(self.as_record())

    @property
    def analyst_input(self):
        return AnalystInput(
            self.symbol,
            self.decision_time_ms,
            self.strategy_evidence,
            tuple(item.reference for item in self.evidence),
        )


def build_evidence_bundle(symbol, decision_time_ms, evidence):
    """Validate one canonical read-only evidence bundle without ambient state."""
    if type(evidence) is not tuple:
        raise EvidenceBundleError("Evidence bundle input must be an immutable tuple")
    return PointInTimeEvidenceBundle(symbol, decision_time_ms, evidence)
