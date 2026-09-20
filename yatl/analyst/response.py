"""Strict, fail-closed validation for untrusted P6 model responses."""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

from .contracts import (
    MAX_CLAIMS,
    AnalystClaim,
    AnalystContractError,
    AnalystDisposition,
    AnalystReason,
    ClaimKind,
    build_analyst_report,
)
from .request import ModelRequestEnvelope


MODEL_RESPONSE_SCHEMA_VERSION = 1
MAX_MODEL_RESPONSE_BYTES = 16_384
_ALLOWED_CLAIM_KINDS = (
    ClaimKind.FACT,
    ClaimKind.DERIVED_OBSERVATION,
    ClaimKind.UNCERTAINTY,
)
_FORBIDDEN_KEYS = frozenset(
    {
        "action",
        "actions",
        "command",
        "commands",
        "quantity",
        "qty",
        "amount",
        "size",
        "order",
        "order_id",
        "endpoint",
        "endpoint_url",
        "url",
        "uri",
        "credential",
        "credentials",
        "api_key",
        "api_secret",
        "password",
        "private_key",
        "token",
        "account",
        "account_id",
        "risk_authorization",
        "trade_permission",
        "execution",
        "execute",
    }
)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:api[ _-]?key|api[ _-]?secret|password|bearer[ _-]?token|"
    r"private[ _-]?key|account[ _-]?id)\b",
    re.IGNORECASE,
)
_ACTION_PATTERN = re.compile(
    r"(?:\b(?:buy|sell|execute|submit|cancel|withdraw)\s+"
    r"(?:now\b|order\b|position\b|trade\b|\d)"
    r"|\b(?:place|send)\s+(?:an?\s+)?order\b"
    r"|\b(?:quantity|qty|amount|position[ _-]?size|action)\s*[:=])",
    re.IGNORECASE,
)


class ModelResponseCode(str, Enum):
    ACCEPTED = "ACCEPTED"
    RESPONSE_TYPE = "RESPONSE_TYPE"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    MALFORMED_JSON = "MALFORMED_JSON"
    DUPLICATE_JSON_KEY = "DUPLICATE_JSON_KEY"
    SCHEMA_REJECTED = "SCHEMA_REJECTED"
    FORBIDDEN_CONTENT = "FORBIDDEN_CONTENT"
    CONTRACT_REJECTED = "CONTRACT_REJECTED"


class ModelResponseBoundaryError(AnalystContractError):
    """Trusted caller contract for strict model-response validation failed."""


class _DuplicateJsonKey(ValueError):
    pass


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_text(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _raw_digest(raw_response):
    if isinstance(raw_response, str):
        return _sha256_text(raw_response)
    marker = f"<NON_STRING:{type(raw_response).__name__}>"
    return _sha256_text(marker)


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _contains_forbidden_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _contains_forbidden_text(value):
    if isinstance(value, str):
        return bool(
            _URL_PATTERN.search(value)
            or _CREDENTIAL_PATTERN.search(value)
            or _ACTION_PATTERN.search(value)
        )
    if isinstance(value, dict):
        return any(_contains_forbidden_text(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_text(item) for item in value)
    return False


def _fallback_report(request):
    return build_analyst_report(request.bundle.analyst_input, ())


@dataclass(frozen=True, slots=True)
class ModelResponseValidation:
    """Canonical validation result; rejected model text is never retained."""

    request: ModelRequestEnvelope
    accepted: bool
    code: ModelResponseCode
    report: object
    raw_response_sha256: str
    canonical_response_json: str | None

    def __post_init__(self):
        if (
            not isinstance(self.request, ModelRequestEnvelope)
            or type(self.accepted) is not bool
            or not isinstance(self.code, ModelResponseCode)
            or not isinstance(self.raw_response_sha256, str)
            or len(self.raw_response_sha256) != 64
            or not isinstance(self.canonical_response_json, (str, type(None)))
        ):
            raise ModelResponseBoundaryError("Model response validation identity is invalid")

        fallback = _fallback_report(self.request)
        if self.accepted:
            if (
                self.code is not ModelResponseCode.ACCEPTED
                or not isinstance(self.canonical_response_json, str)
                or not self.canonical_response_json
                or self.report.disposition is not AnalystDisposition.REVIEW
                or self.report.reason is not AnalystReason.UNCERTAINTY_PRESENT
                or not any(
                    claim.kind is ClaimKind.UNCERTAINTY
                    for claim in self.report.claims
                )
            ):
                raise ModelResponseBoundaryError(
                    "Accepted model response is not the conservative validated form"
                )
            try:
                decoded = json.loads(
                    self.canonical_response_json,
                    object_pairs_hook=_no_duplicate_object,
                )
            except (json.JSONDecodeError, _DuplicateJsonKey):
                raise ModelResponseBoundaryError(
                    "Canonical model response cannot be reconstructed"
                ) from None
            if _canonical_json(decoded) != self.canonical_response_json:
                raise ModelResponseBoundaryError(
                    "Validated model response is not canonical"
                )
        else:
            if (
                self.code is ModelResponseCode.ACCEPTED
                or self.canonical_response_json is not None
                or self.report != fallback
                or self.report.disposition is not AnalystDisposition.INSUFFICIENT_DATA
                or self.report.reason is not AnalystReason.NO_USABLE_CLAIMS
                or self.report.claims
            ):
                raise ModelResponseBoundaryError(
                    "Rejected model response did not fail closed"
                )

    @property
    def canonical_response_sha256(self):
        if self.canonical_response_json is None:
            return None
        return _sha256_text(self.canonical_response_json)

    def as_record(self):
        return {
            "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
            "request_sha256": self.request.request_sha256,
            "accepted": self.accepted,
            "code": self.code.value,
            "raw_response_sha256": self.raw_response_sha256,
            "canonical_response_sha256": self.canonical_response_sha256,
            "report": self.report.as_record(),
            "report_sha256": self.report.report_sha256,
        }

    @property
    def validation_sha256(self):
        return _sha256_text(_canonical_json(self.as_record()))


def _reject(request, raw_response, code):
    return ModelResponseValidation(
        request,
        False,
        code,
        _fallback_report(request),
        _raw_digest(raw_response),
        None,
    )


def _exact_keys(record, expected):
    return isinstance(record, dict) and set(record) == set(expected)


def _parse_claims(decoded):
    if not _exact_keys(decoded, ("schema_version", "claims")):
        raise ModelResponseBoundaryError("Top-level response fields are not exact")
    if decoded["schema_version"] != MODEL_RESPONSE_SCHEMA_VERSION:
        raise ModelResponseBoundaryError("Model response schema version is unsupported")
    raw_claims = decoded["claims"]
    if (
        not isinstance(raw_claims, list)
        or not 1 <= len(raw_claims) <= MAX_CLAIMS
    ):
        raise ModelResponseBoundaryError("Model response claim count is invalid")

    claims = []
    for raw_claim in raw_claims:
        if not _exact_keys(
            raw_claim,
            ("claim_id", "kind", "text", "evidence_ids"),
        ):
            raise ModelResponseBoundaryError("Model claim fields are not exact")
        kind_value = raw_claim["kind"]
        if not isinstance(kind_value, str):
            raise ModelResponseBoundaryError("Model claim kind is invalid")
        try:
            kind = ClaimKind(kind_value)
        except ValueError:
            raise ModelResponseBoundaryError("Model claim kind is unknown") from None
        if kind not in _ALLOWED_CLAIM_KINDS:
            raise ModelResponseBoundaryError("Model claim kind is not permitted")
        evidence_ids = raw_claim["evidence_ids"]
        if not isinstance(evidence_ids, list):
            raise ModelResponseBoundaryError("Model evidence references must be a list")
        claims.append(
            AnalystClaim(
                raw_claim["claim_id"],
                kind,
                raw_claim["text"],
                tuple(evidence_ids),
            )
        )

    claims = tuple(claims)
    claim_ids = tuple(claim.claim_id for claim in claims)
    if (
        len(set(claim_ids)) != len(claim_ids)
        or claim_ids != tuple(sorted(claim_ids))
        or not any(claim.kind is ClaimKind.UNCERTAINTY for claim in claims)
    ):
        raise ModelResponseBoundaryError(
            "Model claims are duplicate, unordered, or omit required uncertainty"
        )
    return claims


def validate_model_response(request, raw_response):
    """Validate untrusted provider text and fail closed without retaining it."""

    if not isinstance(request, ModelRequestEnvelope):
        raise ModelResponseBoundaryError("Validated model request envelope is required")
    if not isinstance(raw_response, str):
        return _reject(request, raw_response, ModelResponseCode.RESPONSE_TYPE)
    if (
        not raw_response
        or len(raw_response.encode("utf-8")) > MAX_MODEL_RESPONSE_BYTES
    ):
        return _reject(
            request,
            raw_response,
            ModelResponseCode.RESPONSE_TOO_LARGE,
        )

    try:
        decoded = json.loads(
            raw_response,
            object_pairs_hook=_no_duplicate_object,
        )
    except _DuplicateJsonKey:
        return _reject(
            request,
            raw_response,
            ModelResponseCode.DUPLICATE_JSON_KEY,
        )
    except json.JSONDecodeError:
        return _reject(request, raw_response, ModelResponseCode.MALFORMED_JSON)

    if not isinstance(decoded, dict):
        return _reject(request, raw_response, ModelResponseCode.SCHEMA_REJECTED)
    if _contains_forbidden_key(decoded) or _contains_forbidden_text(decoded):
        return _reject(request, raw_response, ModelResponseCode.FORBIDDEN_CONTENT)

    try:
        claims = _parse_claims(decoded)
    except (ModelResponseBoundaryError, AnalystContractError, TypeError):
        return _reject(request, raw_response, ModelResponseCode.SCHEMA_REJECTED)

    try:
        report = build_analyst_report(request.bundle.analyst_input, claims)
    except AnalystContractError:
        return _reject(request, raw_response, ModelResponseCode.CONTRACT_REJECTED)

    if (
        report.disposition is not AnalystDisposition.REVIEW
        or report.reason is not AnalystReason.UNCERTAINTY_PRESENT
    ):
        return _reject(request, raw_response, ModelResponseCode.CONTRACT_REJECTED)

    canonical_response = _canonical_json(
        {
            "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
            "claims": [claim.as_record() for claim in claims],
        }
    )
    return ModelResponseValidation(
        request,
        True,
        ModelResponseCode.ACCEPTED,
        report,
        _raw_digest(raw_response),
        canonical_response,
    )
