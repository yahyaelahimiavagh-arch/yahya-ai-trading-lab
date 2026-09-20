"""Offline deterministic runtime gate for P6-006 claim/evidence grounding."""

import hashlib
import json

from .contracts import AnalystDisposition, EvidenceLayer
from .evidence import build_evidence_bundle, build_layer_evidence
from .grounding import GroundingCode, ground_model_response
from .request import build_model_request
from .response import validate_model_response


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload):
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _bundle():
    evidence = (
        build_layer_evidence(
            "E_P1_MARKET",
            EvidenceLayer.P1_PUBLIC_MARKET,
            "BTCUSDT",
            DECISION_TIME - 4_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
                "latest_closed_at_ms": DECISION_TIME - 5_000,
                "manifest_sha256": "a" * 64,
            },
        ),
        build_layer_evidence(
            "E_P3_STRATEGY",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            "BTCUSDT",
            DECISION_TIME - 3_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "candidate_matrix_sha256":
                    "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a",
                "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            },
        ),
        build_layer_evidence(
            "E_P4_RISK",
            EvidenceLayer.P4_RISK_STATUS,
            "BTCUSDT",
            DECISION_TIME - 2_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "audit_sha256":
                    "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783",
                "policy_sha256":
                    "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7",
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "risk_status": "PASS",
            },
        ),
        build_layer_evidence(
            "E_P5_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            "BTCUSDT",
            DECISION_TIME - 1_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "ai_direct_execution": False,
                "audit_sha256":
                    "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa",
                "credentials_present": False,
                "live_master_lock": "OFF",
                "order_endpoints": False,
                "paper_only": True,
                "policy_sha256":
                    "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72",
                "private_payload_present": False,
                "safety_status": "PASS",
                "trade_permission": False,
            },
        ),
    )
    return build_evidence_bundle("BTCUSDT", DECISION_TIME, evidence)


def _response(claims):
    return _canonical_json(
        {
            "schema_version": 1,
            "claims": claims,
        }
    )


def _grounded_response():
    return _response(
        [
            {
                "claim_id": "MODEL_FACT_MARKET",
                "kind": "FACT",
                "text": "Accepted public market evidence is present.",
                "evidence_ids": ["E_P1_MARKET"],
            },
            {
                "claim_id": "MODEL_OBSERVATION_STRATEGY",
                "kind": "DERIVED_OBSERVATION",
                "text": "Strategy evidence remains INSUFFICIENT_EVIDENCE.",
                "evidence_ids": ["E_P3_STRATEGY"],
            },
            {
                "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                "kind": "UNCERTAINTY",
                "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                "evidence_ids": ["E_P3_STRATEGY"],
            },
        ]
    )


def _semantic_adversarial():
    return (
        (
            "unsupported_claim",
            _response(
                [
                    {
                        "claim_id": "MODEL_FACT_MARKET",
                        "kind": "FACT",
                        "text": "Accepted public market evidence is present.",
                        "evidence_ids": ["E_P1_MARKET"],
                    },
                    {
                        "claim_id": "MODEL_NEW_FACT",
                        "kind": "FACT",
                        "text": "A new unsupported fact is asserted.",
                        "evidence_ids": ["E_P1_MARKET"],
                    },
                    {
                        "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                        "kind": "UNCERTAINTY",
                        "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                        "evidence_ids": ["E_P3_STRATEGY"],
                    },
                ]
            ),
            GroundingCode.UNSUPPORTED_CLAIM,
        ),
        (
            "wrong_layer",
            _response(
                [
                    {
                        "claim_id": "MODEL_FACT_MARKET",
                        "kind": "FACT",
                        "text": "Accepted public market evidence is present.",
                        "evidence_ids": ["E_P4_RISK"],
                    },
                    {
                        "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                        "kind": "UNCERTAINTY",
                        "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                        "evidence_ids": ["E_P3_STRATEGY"],
                    },
                ]
            ),
            GroundingCode.EVIDENCE_REFERENCE_MISMATCH,
        ),
        (
            "contradiction",
            _response(
                [
                    {
                        "claim_id": "MODEL_OBSERVATION_STRATEGY",
                        "kind": "DERIVED_OBSERVATION",
                        "text": "Strategy evidence is sufficient for a qualified conclusion.",
                        "evidence_ids": ["E_P3_STRATEGY"],
                    },
                    {
                        "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                        "kind": "UNCERTAINTY",
                        "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                        "evidence_ids": ["E_P3_STRATEGY"],
                    },
                ]
            ),
            GroundingCode.CONTRADICTION,
        ),
        (
            "shape_mismatch",
            _response(
                [
                    {
                        "claim_id": "MODEL_FACT_MARKET",
                        "kind": "FACT",
                        "text": "Public market evidence appears available.",
                        "evidence_ids": ["E_P1_MARKET"],
                    },
                    {
                        "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                        "kind": "UNCERTAINTY",
                        "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                        "evidence_ids": ["E_P3_STRATEGY"],
                    },
                ]
            ),
            GroundingCode.CLAIM_SHAPE_MISMATCH,
        ),
    )


def main():
    request = build_model_request(_bundle())

    accepted = validate_model_response(request, _grounded_response())
    first = ground_model_response(accepted)
    second = ground_model_response(accepted)
    if (
        not first.accepted
        or first.code is not GroundingCode.GROUNDED
        or first != second
        or first.grounding_sha256 != second.grounding_sha256
        or first.report.disposition is not AnalystDisposition.REVIEW
    ):
        raise RuntimeError("P6-006 grounded response failed deterministic validation")

    outcomes = []
    for name, raw_response, expected_code in _semantic_adversarial():
        response_validation = validate_model_response(request, raw_response)
        if not response_validation.accepted:
            raise RuntimeError(f"P6-006 semantic fixture failed upstream: {name}")
        result = ground_model_response(response_validation)
        if (
            result.accepted
            or result.code is not expected_code
            or result.report.disposition is not AnalystDisposition.INSUFFICIENT_DATA
            or result.grounded_claim_ids
        ):
            raise RuntimeError(f"P6-006 semantic fixture escaped: {name}")
        outcomes.append(
            {
                "name": name,
                "code": result.code.value,
                "grounding_sha256": result.grounding_sha256,
            }
        )

    upstream_rejected = validate_model_response(
        request,
        _response(
            [
                {
                    "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                    "kind": "UNCERTAINTY",
                    "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                    "evidence_ids": ["E_NOT_ACCEPTED"],
                }
            ]
        ),
    )
    upstream_grounding = ground_model_response(upstream_rejected)
    if (
        upstream_grounding.accepted
        or upstream_grounding.code is not GroundingCode.UPSTREAM_REJECTED
        or upstream_grounding.report.disposition
        is not AnalystDisposition.INSUFFICIENT_DATA
    ):
        raise RuntimeError("P6-006 invented evidence did not fail closed")

    outcomes.append(
        {
            "name": "invented_evidence",
            "code": upstream_grounding.code.value,
            "grounding_sha256": upstream_grounding.grounding_sha256,
        }
    )

    print(
        "OK: P6 claim/evidence grounding gate; "
        f"grounded={len(first.grounded_claim_ids)} rejected={len(outcomes)} "
        "fallback=INSUFFICIENT_DATA replay_equal=true "
        f"grounding_sha256={first.grounding_sha256} "
        f"matrix_sha256={_sha256(outcomes)}"
    )
    print(
        "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
        "Exact claim/evidence grounding | Deterministic rejection reasons | "
        "No provider/network | No credentials | No executor import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
