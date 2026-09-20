"""Offline adversarial runtime gate for P6-005 strict response validation."""

import hashlib
import json

from .contracts import AnalystDisposition, EvidenceLayer
from .evidence import build_evidence_bundle, build_layer_evidence
from .request import build_model_request
from .response import (
    MAX_MODEL_RESPONSE_BYTES,
    ModelResponseCode,
    validate_model_response,
)


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


def _accepted_response():
    return _canonical_json(
        {
            "schema_version": 1,
            "claims": [
                {
                    "claim_id": "MODEL_FACT_MARKET",
                    "kind": "FACT",
                    "text": "Accepted public market evidence is present.",
                    "evidence_ids": ["E_P1_MARKET"],
                },
                {
                    "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                    "kind": "UNCERTAINTY",
                    "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                    "evidence_ids": ["E_P3_STRATEGY"],
                },
            ],
        }
    )


def _adversarial_responses():
    return (
        ("malformed", '{"schema_version":1'),
        (
            "unknown_top_field",
            _canonical_json(
                {"schema_version": 1, "claims": [], "extra": "smuggled"}
            ),
        ),
        (
            "action_field",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [],
                    "action": "BUY",
                }
            ),
        ),
        (
            "quantity_field",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [],
                    "quantity": "0.25",
                }
            ),
        ),
        (
            "url_in_text",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_UNCERTAINTY",
                            "kind": "UNCERTAINTY",
                            "text": "Review https://example.invalid before proceeding.",
                            "evidence_ids": ["E_P3_STRATEGY"],
                        }
                    ],
                }
            ),
        ),
        (
            "command_in_text",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_UNCERTAINTY",
                            "kind": "UNCERTAINTY",
                            "text": "Buy 0.25 BTC now.",
                            "evidence_ids": ["E_P3_STRATEGY"],
                        }
                    ],
                }
            ),
        ),
        (
            "credential_in_text",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_UNCERTAINTY",
                            "kind": "UNCERTAINTY",
                            "text": "Use api key: example-secret-value.",
                            "evidence_ids": ["E_P3_STRATEGY"],
                        }
                    ],
                }
            ),
        ),
        (
            "duplicate_key",
            '{"schema_version":1,"schema_version":1,"claims":[]}',
        ),
        (
            "missing_uncertainty",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_FACT_MARKET",
                            "kind": "FACT",
                            "text": "Accepted public market evidence is present.",
                            "evidence_ids": ["E_P1_MARKET"],
                        }
                    ],
                }
            ),
        ),
        (
            "invented_evidence",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_UNCERTAINTY",
                            "kind": "UNCERTAINTY",
                            "text": "Evidence is uncertain.",
                            "evidence_ids": ["E_NOT_ACCEPTED"],
                        }
                    ],
                }
            ),
        ),
        (
            "unsupported_kind",
            _canonical_json(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "MODEL_UNSUPPORTED",
                            "kind": "UNSUPPORTED",
                            "text": "Unsupported content.",
                            "evidence_ids": [],
                        }
                    ],
                }
            ),
        ),
        ("oversized", "x" * (MAX_MODEL_RESPONSE_BYTES + 1)),
    )


def main():
    request = build_model_request(_bundle())
    first = validate_model_response(request, _accepted_response())
    second = validate_model_response(request, _accepted_response())
    if (
        not first.accepted
        or first.code is not ModelResponseCode.ACCEPTED
        or first != second
        or first.validation_sha256 != second.validation_sha256
        or first.report.disposition is not AnalystDisposition.REVIEW
    ):
        raise RuntimeError("P6-005 accepted response validation failed")

    outcomes = []
    for name, raw_response in _adversarial_responses():
        result = validate_model_response(request, raw_response)
        if (
            result.accepted
            or result.report.disposition is not AnalystDisposition.INSUFFICIENT_DATA
            or result.canonical_response_json is not None
        ):
            raise RuntimeError(f"P6-005 adversarial response escaped: {name}")
        outcomes.append(
            {
                "name": name,
                "code": result.code.value,
                "validation_sha256": result.validation_sha256,
            }
        )

    print(
        "OK: P6 strict model-response schema; "
        f"accepted=1 rejected={len(outcomes)} "
        "fallback=INSUFFICIENT_DATA replay_equal=true "
        f"accepted_validation_sha256={first.validation_sha256} "
        f"canonical_response_sha256={first.canonical_response_sha256} "
        f"matrix_sha256={_sha256(outcomes)}"
    )
    print(
        "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
        "Strict schema | Untrusted response data | No retained rejected text | "
        "No credentials | No URL/action authority | No quantity authority | "
        "No provider/network | No executor import | No RiskAuthorization mutation | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
