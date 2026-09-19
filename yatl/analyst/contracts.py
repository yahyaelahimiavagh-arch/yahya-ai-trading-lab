"""Immutable P6 analysis-only contracts with no execution capability."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum


ANALYST_POLICY_ID = "P6_ANALYSIS_ONLY_V1"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EVIDENCE_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
CLAIM_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
MAX_CLAIM_TEXT_CHARS = 500
MAX_EVIDENCE_REFERENCES = 64
MAX_CLAIMS = 64


class AnalystContractError(ValueError):
    """P6 analysis evidence or output violates the analysis-only boundary."""


class EvidenceLayer(str, Enum):
    P1_PUBLIC_MARKET = "P1_PUBLIC_MARKET"
    P3_STRATEGY_EVIDENCE = "P3_STRATEGY_EVIDENCE"
    P4_RISK_STATUS = "P4_RISK_STATUS"
    P5_SAFETY_STATUS = "P5_SAFETY_STATUS"


class StrategyEvidenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    QUALIFIED_FOR_P4_RESEARCH = "QUALIFIED_FOR_P4_RESEARCH"


class ClaimKind(str, Enum):
    FACT = "FACT"
    DERIVED_OBSERVATION = "DERIVED_OBSERVATION"
    UNCERTAINTY = "UNCERTAINTY"
    UNSUPPORTED = "UNSUPPORTED"


class AnalystDisposition(str, Enum):
    NO_TRADE = "NO_TRADE"
    REVIEW = "REVIEW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnalystReason(str, Enum):
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    UNCERTAINTY_PRESENT = "UNCERTAINTY_PRESENT"
    UNSUPPORTED_CLAIMS = "UNSUPPORTED_CLAIMS"
    NO_USABLE_CLAIMS = "NO_USABLE_CLAIMS"


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_text(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_CLAIM_TEXT_CHARS
        and value == value.strip()
        and all(character >= " " and character != "\x7f" for character in value)
    )


@dataclass(frozen=True, slots=True)
class AnalystPolicy:
    """Frozen P6 boundary. The analyst can produce data, never authority."""

    policy_id: str = ANALYST_POLICY_ID
    mode: str = "ANALYSIS_ONLY"
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_leverage: bool = False
    allow_external_transport: bool = False
    allow_credentials: bool = False
    allow_execution_import: bool = False
    allow_trade_permission: bool = False
    allow_order_endpoint: bool = False
    allow_quantity_authority: bool = False
    allow_risk_authorization_mutation: bool = False
    allow_ai_direct_execution: bool = False

    def __post_init__(self):
        fixed = (
            self.policy_id == ANALYST_POLICY_ID
            and self.mode == "ANALYSIS_ONLY"
            and self.paper_only is True
            and self.live_master_lock == "OFF"
            and self.spot_only is True
            and self.allow_short is False
            and self.allow_leverage is False
            and self.allow_external_transport is False
            and self.allow_credentials is False
            and self.allow_execution_import is False
            and self.allow_trade_permission is False
            and self.allow_order_endpoint is False
            and self.allow_quantity_authority is False
            and self.allow_risk_authorization_mutation is False
            and self.allow_ai_direct_execution is False
        )
        if not fixed:
            raise AnalystContractError(
                "Analyst policy differs from the frozen analysis-only policy"
            )

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }

    @property
    def policy_sha256(self):
        return _sha256({"schema_version": 1, "policy": self.as_record()})


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One provenance-bound, point-in-time reference. It contains no payload."""

    evidence_id: str
    layer: EvidenceLayer
    source_sha256: str
    symbol: str
    observed_at_ms: int

    def __post_init__(self):
        if (
            not isinstance(self.evidence_id, str)
            or EVIDENCE_ID_PATTERN.fullmatch(self.evidence_id) is None
            or not isinstance(self.layer, EvidenceLayer)
            or not isinstance(self.source_sha256, str)
            or SHA256_PATTERN.fullmatch(self.source_sha256) is None
            or self.symbol not in SYMBOLS
            or type(self.observed_at_ms) is not int
            or self.observed_at_ms < 0
        ):
            raise AnalystContractError("Evidence reference is invalid")

    def as_record(self):
        return {
            "evidence_id": self.evidence_id,
            "layer": self.layer.value,
            "source_sha256": self.source_sha256,
            "symbol": self.symbol,
            "observed_at_ms": self.observed_at_ms,
        }


@dataclass(frozen=True, slots=True)
class AnalystInput:
    """Canonical analysis input composed only of evidence identities."""

    symbol: str
    decision_time_ms: int
    strategy_evidence: StrategyEvidenceState
    evidence: tuple[EvidenceReference, ...]
    paper_only: bool = True
    live_master_lock: str = "OFF"
    spot_only: bool = True
    allow_short: bool = False
    allow_leverage: bool = False

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or type(self.decision_time_ms) is not int
            or self.decision_time_ms < 0
            or not isinstance(self.strategy_evidence, StrategyEvidenceState)
            or type(self.evidence) is not tuple
            or not 1 <= len(self.evidence) <= MAX_EVIDENCE_REFERENCES
            or any(not isinstance(item, EvidenceReference) for item in self.evidence)
            or self.paper_only is not True
            or self.live_master_lock != "OFF"
            or self.spot_only is not True
            or self.allow_short is not False
            or self.allow_leverage is not False
        ):
            raise AnalystContractError("Analyst input identity or safety policy is invalid")
        ids = tuple(item.evidence_id for item in self.evidence)
        if (
            len(set(ids)) != len(ids)
            or ids != tuple(sorted(ids))
            or any(item.symbol != self.symbol for item in self.evidence)
            or any(item.observed_at_ms > self.decision_time_ms for item in self.evidence)
        ):
            raise AnalystContractError(
                "Analyst evidence is duplicate, unordered, future-dated or cross-symbol"
            )

    def as_record(self):
        return {
            "schema_version": 1,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "strategy_evidence": self.strategy_evidence.value,
            "evidence": [item.as_record() for item in self.evidence],
            "safety": {
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "spot_only": self.spot_only,
                "allow_short": self.allow_short,
                "allow_leverage": self.allow_leverage,
            },
        }

    @property
    def input_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class AnalystClaim:
    """One explicitly typed statement. Unsupported text can never masquerade as fact."""

    claim_id: str
    kind: ClaimKind
    text: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.claim_id, str)
            or CLAIM_ID_PATTERN.fullmatch(self.claim_id) is None
            or not isinstance(self.kind, ClaimKind)
            or not _valid_text(self.text)
            or type(self.evidence_ids) is not tuple
            or any(
                not isinstance(item, str)
                or EVIDENCE_ID_PATTERN.fullmatch(item) is None
                for item in self.evidence_ids
            )
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
            or self.evidence_ids != tuple(sorted(self.evidence_ids))
        ):
            raise AnalystContractError("Analyst claim is invalid")
        if self.kind in (ClaimKind.FACT, ClaimKind.DERIVED_OBSERVATION):
            if not self.evidence_ids:
                raise AnalystContractError(
                    "Supported fact or observation requires evidence references"
                )
        elif self.kind is ClaimKind.UNSUPPORTED and self.evidence_ids:
            raise AnalystContractError(
                "Unsupported claim cannot carry evidence references"
            )

    def as_record(self):
        return {
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
        }


def _expected_disposition(claims):
    if not claims:
        return (
            AnalystDisposition.INSUFFICIENT_DATA,
            AnalystReason.NO_USABLE_CLAIMS,
        )
    if any(item.kind is ClaimKind.UNSUPPORTED for item in claims):
        return (
            AnalystDisposition.INSUFFICIENT_DATA,
            AnalystReason.UNSUPPORTED_CLAIMS,
        )
    if any(item.kind is ClaimKind.UNCERTAINTY for item in claims):
        return (
            AnalystDisposition.REVIEW,
            AnalystReason.UNCERTAINTY_PRESENT,
        )
    return AnalystDisposition.NO_TRADE, AnalystReason.ANALYSIS_ONLY


@dataclass(frozen=True, slots=True)
class AnalystReport:
    """Validated analyst output. It is data only and has no executable action."""

    analysis_input: AnalystInput
    claims: tuple[AnalystClaim, ...]
    disposition: AnalystDisposition
    reason: AnalystReason
    policy: AnalystPolicy = field(default_factory=AnalystPolicy)

    def __post_init__(self):
        if (
            not isinstance(self.analysis_input, AnalystInput)
            or type(self.claims) is not tuple
            or len(self.claims) > MAX_CLAIMS
            or any(not isinstance(item, AnalystClaim) for item in self.claims)
            or not isinstance(self.disposition, AnalystDisposition)
            or not isinstance(self.reason, AnalystReason)
            or not isinstance(self.policy, AnalystPolicy)
        ):
            raise AnalystContractError("Analyst report identity is invalid")

        try:
            reconstructed_input = AnalystInput(
                self.analysis_input.symbol,
                self.analysis_input.decision_time_ms,
                self.analysis_input.strategy_evidence,
                self.analysis_input.evidence,
                self.analysis_input.paper_only,
                self.analysis_input.live_master_lock,
                self.analysis_input.spot_only,
                self.analysis_input.allow_short,
                self.analysis_input.allow_leverage,
            )
            reconstructed_policy = AnalystPolicy(
                **{
                    name: getattr(self.policy, name)
                    for name in self.policy.__dataclass_fields__
                }
            )
        except (AnalystContractError, TypeError, ValueError):
            raise AnalystContractError(
                "Analyst input or policy failed deterministic reconstruction"
            ) from None
        if reconstructed_input != self.analysis_input or reconstructed_policy != self.policy:
            raise AnalystContractError("Analyst report reconstruction changed identity")

        claim_ids = tuple(item.claim_id for item in self.claims)
        if (
            len(set(claim_ids)) != len(claim_ids)
            or claim_ids != tuple(sorted(claim_ids))
        ):
            raise AnalystContractError("Analyst claims are duplicate or unordered")

        known_evidence = {item.evidence_id for item in self.analysis_input.evidence}
        referenced = {
            evidence_id
            for claim in self.claims
            for evidence_id in claim.evidence_ids
        }
        if not referenced.issubset(known_evidence):
            raise AnalystContractError("Analyst claim references unknown evidence")

        expected = _expected_disposition(self.claims)
        if (self.disposition, self.reason) != expected:
            raise AnalystContractError(
                "Analyst disposition does not match validated claims"
            )

    def as_record(self):
        return {
            "schema_version": 1,
            "input_sha256": self.analysis_input.input_sha256,
            "claims": [item.as_record() for item in self.claims],
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "policy": self.policy.as_record(),
        }

    @property
    def report_sha256(self):
        return _sha256(self.as_record())


def build_analyst_report(analysis_input, claims=(), policy=None):
    """Create a deterministic analysis-only report from validated inert records."""

    if not isinstance(analysis_input, AnalystInput):
        raise AnalystContractError("Validated analyst input is required")
    if type(claims) is not tuple:
        raise AnalystContractError("Analyst claims must be an immutable tuple")
    if policy is None:
        policy = AnalystPolicy()
    if not isinstance(policy, AnalystPolicy):
        raise AnalystContractError("Validated analyst policy is required")
    disposition, reason = _expected_disposition(claims)
    return AnalystReport(
        analysis_input,
        claims,
        disposition,
        reason,
        policy,
    )
