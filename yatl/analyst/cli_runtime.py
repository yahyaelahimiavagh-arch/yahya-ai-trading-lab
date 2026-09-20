"""Deterministic runtime gate for P6-008 guarded analyst CLI."""

import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

from . import cli


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_text(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bundle_record():
    return {
        "schema_version": 1,
        "symbol": "BTCUSDT",
        "decision_time_ms": DECISION_TIME,
        "evidence": [
            {
                "evidence_id": "E_P1_MARKET",
                "layer": "P1_PUBLIC_MARKET",
                "observed_at_ms": DECISION_TIME - 4_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
                    "latest_closed_at_ms": DECISION_TIME - 5_000,
                    "manifest_sha256": "a" * 64,
                },
            },
            {
                "evidence_id": "E_P3_STRATEGY",
                "layer": "P3_STRATEGY_EVIDENCE",
                "observed_at_ms": DECISION_TIME - 3_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "candidate_matrix_sha256":
                        "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a",
                    "strategy_evidence": "INSUFFICIENT_EVIDENCE",
                },
            },
            {
                "evidence_id": "E_P4_RISK",
                "layer": "P4_RISK_STATUS",
                "observed_at_ms": DECISION_TIME - 2_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "audit_sha256":
                        "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783",
                    "policy_sha256":
                        "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7",
                    "quantity_authority": False,
                    "risk_authorization_mutation": False,
                    "risk_status": "PASS",
                },
            },
            {
                "evidence_id": "E_P5_SAFETY",
                "layer": "P5_SAFETY_STATUS",
                "observed_at_ms": DECISION_TIME - 1_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
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
            },
        ],
    }


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


def _run(argv):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(argv)
    raw = output.getvalue()
    if len(raw.encode("utf-8")) > cli.MAX_ANALYST_CLI_OUTPUT_BYTES + 1:
        raise RuntimeError("P6-008 CLI output exceeded bound")
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("P6-008 CLI output is not deterministic JSON") from None
    return code, record, raw


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bundle = root / "bundle.json"
        response = root / "response.json"
        rejected = root / "rejected.json"
        journal = root / "analyst.sqlite3"

        bundle.write_text(_canonical_json(_bundle_record()), encoding="utf-8")
        response.write_text(_accepted_response(), encoding="utf-8")
        rejected.write_text("{", encoding="utf-8")

        evidence_code, evidence_record, evidence_raw = _run(
            ["evidence", "--bundle", str(bundle)]
        )
        validate_code, validate_record, validate_raw = _run(
            [
                "validate",
                "--bundle", str(bundle),
                "--response", str(response),
                "--journal", str(journal),
            ]
        )
        replay_code, replay_record, replay_raw = _run(
            [
                "validate",
                "--bundle", str(bundle),
                "--response", str(response),
                "--journal", str(journal),
            ]
        )
        show_code, show_record, show_raw = _run(
            [
                "show",
                "--journal", str(journal),
                "--trace-sha256", validate_record["trace_sha256"],
            ]
        )
        rejected_code, rejected_record, rejected_raw = _run(
            [
                "validate",
                "--bundle", str(bundle),
                "--response", str(rejected),
            ]
        )

        if (
            evidence_code != cli.EXIT_OK
            or evidence_record["code"] != "EVIDENCE_READY"
            or validate_code != cli.EXIT_OK
            or validate_record["code"] != "GROUNDED"
            or replay_code != cli.EXIT_OK
            or replay_record != validate_record
            or replay_raw != validate_raw
            or show_code != cli.EXIT_OK
            or show_record["code"] != "TRACE_READY"
            or show_record["report"] != validate_record["report"]
            or rejected_code != cli.EXIT_NOT_GROUNDED
            or rejected_record["code"] != "NOT_GROUNDED"
            or rejected_record["report"]["disposition"] != "INSUFFICIENT_DATA"
        ):
            raise RuntimeError("P6-008 guarded CLI contract failed")

        combined = evidence_raw + validate_raw + show_raw + rejected_raw
        for forbidden in (
            "raw_response",
            "canonical_response_json",
            '"api_key":',
            '"api_secret":',
            '"endpoint_url":',
        ):
            if forbidden in combined:
                raise RuntimeError("P6-008 CLI exposed forbidden material")

        print(
            "OK: P6 guarded analyst CLI; "
            "commands=3 stable_exit_codes=true bounded_output=true "
            "noninteractive=true duplicate_replay=true "
            f"trace_sha256={validate_record['trace_sha256']} "
            f"runtime_sha256={_sha256_text(combined)}"
        )
        print(
            "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
            "Local files only | Sanitized report only | No raw provider text | "
            "No credentials | No provider/network | No executor import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
