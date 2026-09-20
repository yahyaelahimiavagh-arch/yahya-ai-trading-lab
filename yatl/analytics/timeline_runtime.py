"""Deterministic offline runtime gate for P7-003 unified point-in-time timeline."""

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec
from .timeline import TimelineKind, build_unified_timeline


START = 1_790_001_000_000
SNAPSHOT = START + 100
P6_OBSERVED = START + 50


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_p5(path, symbol="BTCUSDT", start=START):
    authorization = "1" * 64
    decision = "2" * 64
    readiness = "3" * 64
    intent_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "effect_sha256": authorization,
        "decision_sha256": decision,
        "readiness_sha256": readiness,
        "action": "ENTER_LONG",
        "approved_quantity": "1",
        "policy_id": "P5_LOCAL_PAPER_V1",
    }
    intent_sha = _digest(intent_material)

    create_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 0,
        "event_time_ms": start + 10,
        "event_type": "CREATE",
        "reason": "ACCEPTED_INTENT_RECORDED",
        "previous_event_sha256": None,
    }
    create_sha = _digest(create_material)
    state0_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 0,
        "updated_time_ms": start + 10,
        "status": "PENDING_LOCAL",
        "reason": "ACCEPTED_INTENT_RECORDED",
        "previous_state_sha256": None,
        "event_sha256": create_sha,
    }
    state0_sha = _digest(state0_material)

    activate_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 1,
        "event_time_ms": start + 20,
        "event_type": "ACTIVATE",
        "reason": "LOCAL_ACTIVATION_CONFIRMED",
        "previous_event_sha256": create_sha,
    }
    activate_sha = _digest(activate_material)
    state1_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 1,
        "updated_time_ms": start + 20,
        "status": "ACTIVE_LOCAL",
        "reason": "LOCAL_ACTIVATION_CONFIRMED",
        "previous_state_sha256": state0_sha,
        "event_sha256": activate_sha,
    }
    state1_sha = _digest(state1_material)

    fill_payload = {
        "action": "ENTER_LONG",
        "symbol": symbol,
        "decision_time_ms": start + 30,
        "fill_time_ms": start + 40,
        "quantity": "1",
        "reference_price": "100",
        "reason": "NEXT_PRIMARY_OPEN",
        "fee_bps": "10",
        "slippage_bps": "5",
        "execution_price": "100.05",
        "gross_quote": "100.05",
        "fee_quote": "0.10005",
        "slippage_quote": "0.05",
        "cash_delta": "-100.15005",
        "asset_delta": "1",
    }
    fill_step_sha = "4" * 64
    fill_material = {
        "schema_version": 1,
        "sequence": 0,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "order_state_sha256": state1_sha,
        "fill_step_sha256": fill_step_sha,
        "fill_index": 0,
        "fill": fill_payload,
    }
    fill_sha = _digest(fill_material)

    spec_sha = "5" * 64
    portfolio = {
        "symbol": symbol,
        "cash": "899.84995",
        "asset_quantity": "1",
        "cost_basis_quote": "100.15005",
        "liquidation_value_quote": "100",
        "realized_pnl_quote": "0",
        "unrealized_pnl_quote": "-0.15005",
        "equity_quote": "999.84995",
        "total_fee_quote": "0.10005",
        "total_slippage_quote": "0.05",
        "closed_trades": 0,
    }
    projection_material = {
        "schema_version": 1,
        "spec_sha256": spec_sha,
        "fill_count": 1,
        "last_fill_event_sha256": fill_sha,
        "mark_price": "100",
        "position": "LONG",
        "portfolio": portfolio,
    }
    projection_sha = _digest(projection_material)
    projection_payload = {
        **projection_material,
        "projection_sha256": projection_sha,
    }

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
                decision,
                readiness,
                "ENTER_LONG",
                "1",
                "P5_LOCAL_PAPER_V1",
                intent_sha,
            ),
        )
        connection.execute(
            "CREATE TABLE order_schema_migrations (version INTEGER PRIMARY KEY)"
        )
        connection.execute("INSERT INTO order_schema_migrations(version) VALUES (1)")
        connection.execute(
            """
            CREATE TABLE local_paper_order_events (
                authorization_sha256 TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_time_ms INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL UNIQUE,
                PRIMARY KEY (authorization_sha256, sequence)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE local_paper_order_states (
                authorization_sha256 TEXT PRIMARY KEY,
                intent_sha256 TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                updated_time_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                previous_state_sha256 TEXT,
                event_sha256 TEXT NOT NULL,
                state_sha256 TEXT NOT NULL UNIQUE
            )
            """
        )
        connection.execute(
            "INSERT INTO local_paper_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                0,
                start + 10,
                "CREATE",
                "ACCEPTED_INTENT_RECORDED",
                None,
                create_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                1,
                start + 20,
                "ACTIVATE",
                "LOCAL_ACTIVATION_CONFIRMED",
                create_sha,
                activate_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                1,
                start + 20,
                "ACTIVE_LOCAL",
                "LOCAL_ACTIVATION_CONFIRMED",
                state0_sha,
                activate_sha,
                state1_sha,
            ),
        )
        connection.execute(
            "CREATE TABLE portfolio_schema_migrations (version INTEGER PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO portfolio_schema_migrations(version) VALUES (1)"
        )
        connection.execute(
            """
            CREATE TABLE local_paper_fill_events (
                fill_event_sha256 TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                authorization_sha256 TEXT NOT NULL,
                intent_sha256 TEXT NOT NULL,
                order_state_sha256 TEXT NOT NULL,
                fill_step_sha256 TEXT NOT NULL,
                fill_index INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE local_paper_portfolios (
                symbol TEXT PRIMARY KEY,
                spec_sha256 TEXT NOT NULL,
                fill_count INTEGER NOT NULL,
                last_fill_event_sha256 TEXT NOT NULL,
                mark_price TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_sha256 TEXT NOT NULL UNIQUE
            )
            """
        )
        connection.execute(
            "INSERT INTO local_paper_fill_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill_sha,
                symbol,
                0,
                authorization,
                intent_sha,
                state1_sha,
                fill_step_sha,
                0,
                _json(fill_payload),
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_portfolios VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                symbol,
                spec_sha,
                1,
                fill_sha,
                "100",
                _json(projection_payload),
                projection_sha,
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
    trace_sha = _digest(trace_json)

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


def _fixture_specs(root, symbol="BTCUSDT", start=START, observed=P6_OBSERVED):
    p5 = root / "p5.sqlite3"
    p6 = root / "p6.sqlite3"
    _create_p5(p5, symbol, start)
    _create_p6(p6)
    return (
        UpstreamSourceSpec(
            "SOURCE_P5",
            AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
            symbol,
            start + 45,
            p5,
            _file_sha(p5),
        ),
        UpstreamSourceSpec(
            "SOURCE_P6",
            AnalyticsSourceKind.P6_ANALYST_TRACE,
            symbol,
            observed,
            p6,
            _file_sha(p6),
        ),
    )


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        specs = _fixture_specs(root)
        before = tuple(_file_sha(item.database_path) for item in specs)
        first = build_unified_timeline(SNAPSHOT, specs)
        second = build_unified_timeline(SNAPSHOT, specs)
        after = tuple(_file_sha(item.database_path) for item in specs)

        kinds = tuple(item.kind for item in first.entries)
        if (
            first != second
            or first.canonical_json != second.canonical_json
            or before != after
            or len(first.entries) != 6
            or kinds != (
                TimelineKind.P5_INTENT_BINDING,
                TimelineKind.P5_ORDER_EVENT,
                TimelineKind.P5_ORDER_EVENT,
                TimelineKind.P5_FILL_EVENT,
                TimelineKind.P5_PORTFOLIO_PROJECTION,
                TimelineKind.P6_ANALYST_TRACE,
            )
        ):
            raise RuntimeError("P7-003 unified timeline replay failed")

        print(
            "OK: P7 unified point-in-time timeline; "
            "entries=6 intents=1 orders=2 fills=1 portfolios=1 analyst_traces=1 "
            "replay_equal=true no_write=true "
            f"manifest_sha256={first.ingestion_manifest_sha256} "
            f"timeline_sha256={first.timeline_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Explicit time basis | "
            "Exact identity relationships | Cross-symbol/time isolation | "
            "No credentials | No network/provider | No upstream mutation | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
