"""Deterministic offline runtime gate for P7-004 Paper trade reconstruction."""

import hashlib
import json
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec
from .timeline_runtime import (
    P6_OBSERVED,
    SNAPSHOT,
    START,
    _create_p5,
    _create_p6,
)
from .trades import TradeBookStatus, reconstruct_paper_trades


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close_fixture(path):
    connection = sqlite3.connect(str(path))
    entry = connection.execute(
        "SELECT payload_json FROM local_paper_fill_events WHERE sequence = 0"
    ).fetchone()
    if entry is None:
        connection.close()
        raise RuntimeError("P7-004 fixture is missing entry fill")
    entry_payload = json.loads(entry[0])

    authorization = "6" * 64
    decision = "7" * 64
    readiness = "8" * 64
    intent_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "effect_sha256": authorization,
        "decision_sha256": decision,
        "readiness_sha256": readiness,
        "action": "EXIT_LONG",
        "approved_quantity": "1",
        "policy_id": "P5_LOCAL_PAPER_V1",
    }
    intent_sha = _digest(intent_material)

    create_material = {
        "schema_version": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "sequence": 0,
        "event_time_ms": START + 60,
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
        "updated_time_ms": START + 60,
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
        "event_time_ms": START + 70,
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
        "updated_time_ms": START + 70,
        "status": "ACTIVE_LOCAL",
        "reason": "LOCAL_ACTIVATION_CONFIRMED",
        "previous_state_sha256": state0_sha,
        "event_sha256": activate_sha,
    }
    state1_sha = _digest(state1_material)

    exit_payload = {
        "action": "EXIT_LONG",
        "symbol": "BTCUSDT",
        "decision_time_ms": START + 80,
        "fill_time_ms": START + 80,
        "quantity": "1",
        "reference_price": "110",
        "reason": "SCRIPTED_EXIT",
        "fee_bps": "10",
        "slippage_bps": "5",
        "execution_price": "109.945",
        "gross_quote": "109.945",
        "fee_quote": "0.109945",
        "slippage_quote": "0.055",
        "cash_delta": "109.835055",
        "asset_delta": "-1",
    }
    fill_step_sha = "9" * 64
    fill_material = {
        "schema_version": 1,
        "sequence": 1,
        "authorization_sha256": authorization,
        "intent_sha256": intent_sha,
        "order_state_sha256": state1_sha,
        "fill_step_sha256": fill_step_sha,
        "fill_index": 0,
        "fill": exit_payload,
    }
    fill_sha = _digest(fill_material)

    entry_cash = entry_payload["cash_delta"]
    realized = str(
        Decimal(entry_cash)
        + Decimal(exit_payload["cash_delta"])
    )
    total_fee = str(
        Decimal(entry_payload["fee_quote"])
        + Decimal(exit_payload["fee_quote"])
    )
    total_slippage = str(
        Decimal(entry_payload["slippage_quote"])
        + Decimal(exit_payload["slippage_quote"])
    )
    current = connection.execute(
        "SELECT spec_sha256 FROM local_paper_portfolios WHERE symbol = 'BTCUSDT'"
    ).fetchone()
    spec_sha = current[0]
    portfolio = {
        "symbol": "BTCUSDT",
        "cash": "1009.685005",
        "asset_quantity": "0",
        "cost_basis_quote": "0",
        "liquidation_value_quote": "0",
        "realized_pnl_quote": realized,
        "unrealized_pnl_quote": "0",
        "equity_quote": "1009.685005",
        "total_fee_quote": total_fee,
        "total_slippage_quote": total_slippage,
        "closed_trades": 1,
    }
    projection_material = {
        "schema_version": 1,
        "spec_sha256": spec_sha,
        "fill_count": 2,
        "last_fill_event_sha256": fill_sha,
        "mark_price": "110",
        "position": "FLAT",
        "portfolio": portfolio,
    }
    projection_sha = _digest(projection_material)
    projection_payload = {
        **projection_material,
        "projection_sha256": projection_sha,
    }

    with connection:
        connection.execute(
            "INSERT INTO local_paper_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                authorization,
                decision,
                readiness,
                "EXIT_LONG",
                "1",
                "P5_LOCAL_PAPER_V1",
                intent_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                authorization,
                intent_sha,
                0,
                START + 60,
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
                START + 70,
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
                START + 70,
                "ACTIVE_LOCAL",
                "LOCAL_ACTIVATION_CONFIRMED",
                state0_sha,
                activate_sha,
                state1_sha,
            ),
        )
        connection.execute(
            "INSERT INTO local_paper_fill_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill_sha,
                "BTCUSDT",
                1,
                authorization,
                intent_sha,
                state1_sha,
                fill_step_sha,
                0,
                _json(exit_payload),
            ),
        )
        connection.execute(
            """
            UPDATE local_paper_portfolios
            SET fill_count = ?, last_fill_event_sha256 = ?, mark_price = ?,
                payload_json = ?, projection_sha256 = ?
            WHERE symbol = 'BTCUSDT'
            """,
            (
                2,
                fill_sha,
                "110",
                _json(projection_payload),
                projection_sha,
            ),
        )
    connection.close()


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        p5 = root / "p5.sqlite3"
        p6 = root / "p6.sqlite3"
        _create_p5(p5)
        _close_fixture(p5)
        _create_p6(p6)
        specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                START + 90,
                p5,
                _file_sha(p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                P6_OBSERVED,
                p6,
                _file_sha(p6),
            ),
        )
        before = tuple(_file_sha(item.database_path) for item in specs)
        first = reconstruct_paper_trades(SNAPSHOT, specs)
        second = reconstruct_paper_trades(SNAPSHOT, specs)
        after = tuple(_file_sha(item.database_path) for item in specs)

        if (
            first != second
            or first.canonical_json != second.canonical_json
            or before != after
            or first.status is not TradeBookStatus.FLAT
            or len(first.completed) != 1
            or first.open_trade is not None
            or first.final_portfolio is None
            or first.final_portfolio.closed_trades != 1
        ):
            raise RuntimeError("P7-004 trade reconstruction runtime gate failed")

        trade = first.completed[0]
        print(
            "OK: P7 completed Paper trade reconstruction; "
            "completed=1 open=0 status=FLAT replay_equal=true no_write=true "
            f"trade_sha256={trade.trade_sha256} "
            f"timeline_sha256={first.timeline_sha256} "
            f"reconstruction_sha256={first.reconstruction_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | PnL from accepted cash effects | "
            "Portfolio reconciliation exact | Open trades not silently closed | "
            "No credentials | No network/provider | No upstream mutation | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
