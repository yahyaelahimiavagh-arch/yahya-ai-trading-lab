"""Deterministic runtime gate for P6-007 analyst journal and trace."""

import json
import sqlite3
import tempfile
from pathlib import Path

from .contracts import EvidenceLayer
from .evidence import build_evidence_bundle, build_layer_evidence
from .grounding import ground_model_response
from .journal import AnalystTraceJournal
from .request import build_model_request
from .response import validate_model_response


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


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


def _accepted_grounding():
    request = build_model_request(_bundle())
    raw = _canonical_json(
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
            ],
        }
    )
    return ground_model_response(validate_model_response(request, raw))


def _rejected_grounding():
    request = build_model_request(_bundle())
    return ground_model_response(
        validate_model_response(request, '{"schema_version":1')
    )


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "analyst-traces.sqlite3"

        accepted = _accepted_grounding()
        rejected = _rejected_grounding()

        with AnalystTraceJournal(path) as journal:
            first = journal.record(accepted)
            replay = journal.record(accepted)
            rejected_record = journal.record(rejected)
            if (
                first != replay
                or journal.count() != 2
                or journal.get(first.trace_sha256) != first
                or journal.get_by_response(first.response_validation_sha256) != first
            ):
                raise RuntimeError("P6-007 journal idempotency failed")
            export_first = journal.canonical_json()

        with AnalystTraceJournal(path) as reopened:
            export_second = reopened.canonical_json()
            if (
                reopened.schema_version() != 1
                or reopened.count() != 2
                or export_first != export_second
                or reopened.get(first.trace_sha256) != first
                or reopened.get(rejected_record.trace_sha256) != rejected_record
            ):
                raise RuntimeError("P6-007 journal reopen/replay failed")

        connection = sqlite3.connect(str(path))
        connection.execute(
            "UPDATE analyst_traces SET report_sha256 = ? WHERE trace_sha256 = ?",
            ("b" * 64, first.trace_sha256),
        )
        connection.commit()
        connection.close()

        try:
            with AnalystTraceJournal(path) as tampered:
                tampered.get(first.trace_sha256)
        except Exception:
            tamper_detected = True
        else:
            tamper_detected = False

        if not tamper_detected:
            raise RuntimeError("P6-007 journal tamper was not detected")

        if (
            "raw_response" in export_first
            or "canonical_response_json" in export_first
            or "api_key" in export_first
            or "api_secret" in export_first
        ):
            raise RuntimeError("P6-007 export retained forbidden provider material")

        print(
            "OK: P6 analyst journal and reproducible trace; "
            "records=2 duplicate_replay=true reopen_equal=true "
            f"accepted_trace_sha256={first.trace_sha256} "
            f"rejected_trace_sha256={rejected_record.trace_sha256} "
            "tamper_detected=true"
        )
        print(
            "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
            "SQLite local trace only | Canonical hash-bound journal | "
            "No raw provider text | No credentials | No provider/network | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
