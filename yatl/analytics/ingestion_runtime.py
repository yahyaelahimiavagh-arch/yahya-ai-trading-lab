"""Deterministic offline runtime gate for P7-002 read-only ingestion."""

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec, ingest_readonly_sources


SNAPSHOT_TIME = 1_790_000_100_000
OBSERVED_TIME = SNAPSHOT_TIME - 1_000


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_p5(path):
    authorization = "1" * 64
    material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "effect_sha256": authorization,
        "decision_sha256": "2" * 64,
        "readiness_sha256": "3" * 64,
        "action": "ENTER_LONG",
        "approved_quantity": "1",
        "policy_id": "P5_LOCAL_PAPER_V1",
    }
    intent_sha256 = _sha256_text(_json(material))
    connection = sqlite3.connect(str(path))
    with connection:
        connection.execute(
            "CREATE TABLE execution_schema_migrations (version INTEGER PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO execution_schema_migrations(version) VALUES (1)"
        )
        connection.execute(
            """
            CREATE TABLE local_paper_intents (
                authorization_sha256 TEXT PRIMARY KEY,
                effect_sha256 TEXT NOT NULL UNIQUE,
                decision_sha256 TEXT NOT NULL,
                readiness_sha256 TEXT NOT NULL,
                action TEXT NOT NULL,
                approved_quantity TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL UNIQUE
            )
            """
        )
        connection.execute(
            "INSERT INTO local_paper_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                authorization,
                "2" * 64,
                "3" * 64,
                "ENTER_LONG",
                "1",
                "P5_LOCAL_PAPER_V1",
                intent_sha256,
            ),
        )
    connection.close()


def _create_p6(path):
    request = "a" * 64
    response = "b" * 64
    bundle = "c" * 64
    grounding = "d" * 64
    input_sha = "e" * 64
    report_sha = "f" * 64
    claims = ["CLAIM_ONE"]
    grounding_record = {
        "schema_version": 1,
        "request_sha256": request,
        "response_validation_sha256": response,
        "bundle_sha256": bundle,
        "accepted": True,
        "code": "GROUNDED",
        "grounded_claim_ids": claims,
        "report": {
            "input_sha256": input_sha,
            "disposition": "REVIEW",
            "reason": "UNCERTAINTY_PRESENT",
        },
        "report_sha256": report_sha,
    }
    trace = {
        "schema_version": 1,
        "request_sha256": request,
        "response_validation_sha256": response,
        "bundle_sha256": bundle,
        "grounding_sha256": grounding,
        "input_sha256": input_sha,
        "report_sha256": report_sha,
        "accepted": True,
        "grounding_code": "GROUNDED",
        "disposition": "REVIEW",
        "reason": "UNCERTAINTY_PRESENT",
        "grounded_claim_ids": claims,
        "grounding_record": grounding_record,
    }
    trace_json = _json(trace)
    trace_sha = _sha256_text(trace_json)

    connection = sqlite3.connect(str(path))
    with connection:
        connection.execute(
            "CREATE TABLE analyst_schema_migrations (version INTEGER PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO analyst_schema_migrations(version) VALUES (1)"
        )
        connection.execute(
            """
            CREATE TABLE analyst_traces (
                trace_sha256 TEXT PRIMARY KEY,
                request_sha256 TEXT NOT NULL,
                response_validation_sha256 TEXT NOT NULL UNIQUE,
                bundle_sha256 TEXT NOT NULL,
                grounding_sha256 TEXT NOT NULL UNIQUE,
                input_sha256 TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                grounding_code TEXT NOT NULL,
                disposition TEXT NOT NULL,
                reason TEXT NOT NULL,
                grounded_claim_ids_json TEXT NOT NULL,
                trace_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO analyst_traces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace_sha,
                request,
                response,
                bundle,
                grounding,
                input_sha,
                report_sha,
                1,
                "GROUNDED",
                "REVIEW",
                "UNCERTAINTY_PRESENT",
                _json(claims),
                trace_json,
            ),
        )
    connection.close()


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        p5 = root / "p5.sqlite3"
        p6 = root / "p6.sqlite3"
        _create_p5(p5)
        _create_p6(p6)

        specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                OBSERVED_TIME,
                p5,
                _file_sha(p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                OBSERVED_TIME,
                p6,
                _file_sha(p6),
            ),
        )
        before = (_file_sha(p5), _file_sha(p6))
        first = ingest_readonly_sources(SNAPSHOT_TIME, specs)
        second = ingest_readonly_sources(SNAPSHOT_TIME, specs)
        after = (_file_sha(p5), _file_sha(p6))

        if (
            first != second
            or first.manifest_sha256 != second.manifest_sha256
            or before != after
            or tuple(item.record_count for item in first.sources) != (1, 1)
            or any(item.read_only is not True for item in first.sources)
        ):
            raise RuntimeError("P7-002 read-only ingestion replay failed")

        print(
            "OK: P7 read-only upstream ingestion; "
            "sources=2 records=2 reopen_equal=true no_write=true "
            f"p5_canonical_sha256={first.sources[0].canonical_sha256} "
            f"p6_canonical_sha256={first.sources[1].canonical_sha256} "
            f"manifest_sha256={first.manifest_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | SQLite mode=ro/query_only | "
            "Database identity verified | No path export | No credentials | "
            "No network/provider | No upstream mutation | No executor import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
