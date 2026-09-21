"""Deterministic mocked runtime for the P10-005 forward Paper runner."""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from yatl.data import BinancePublicRestClient, INTERVAL_MILLISECONDS

from .forward_store import ForwardCandleStore
from .ingestion import collect_forward_snapshot
from .paper_runner import run_forward_paper
from .window import ForwardWindowSeal


class MockForwardRunnerClient(BinancePublicRestClient):
    """Synthetic forward-only public feed with one deterministic trade lifecycle."""

    def __init__(self, server_time_ms):
        super().__init__()
        self._server_time_ms = server_time_ms
        self.server_time_calls = 0
        self.kline_calls = 0

    def server_time(self):
        self.server_time_calls += 1
        return self._server_time_ms

    @staticmethod
    def _plain(value):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _ohlc(self, interval, opened):
        window = ForwardWindowSeal()
        duration = INTERVAL_MILLISECONDS[interval]
        index = (opened - window.forward_window_start_ms) // duration

        if interval == "4h":
            close = Decimal("100") + Decimal(index) * Decimal("0.5")
            opened_price = close - Decimal("0.1")
            high = close + Decimal("0.2")
            low = close - Decimal("0.2")
        elif interval == "1h":
            close = Decimal("100") + Decimal(index) * Decimal("0.125")
            if index == 205:
                close -= Decimal("5")
            opened_price = close - Decimal("0.05")
            high = close + Decimal("0.2")
            low = close - Decimal("0.2")
            if index == 203:
                low = close - Decimal("10")
        else:
            close = Decimal("100") + Decimal(index) * Decimal("0.03125")
            opened_price = close - Decimal("0.02")
            high = close + Decimal("0.05")
            low = opened_price - Decimal("0.03")

        return tuple(self._plain(value) for value in (
            opened_price, high, low, close
        ))

    def klines(self, symbol, interval, *, limit=1000,
               start_time=None, end_time=None):
        self.kline_calls += 1
        duration = INTERVAL_MILLISECONDS[interval]
        rows = []
        cursor = start_time
        while cursor is not None and end_time is not None and cursor <= end_time:
            open_price, high, low, close = self._ohlc(interval, cursor)
            rows.append([
                cursor,
                open_price,
                high,
                low,
                close,
                "1000",
                cursor + duration - 1,
                "100000",
                100,
                "500",
                "50000",
                "0",
            ])
            cursor += duration
            if len(rows) >= limit:
                break
        return rows


def build_mock_forward_runner_fixture(directory):
    window = ForwardWindowSeal()
    server_time = (
        window.forward_window_start_ms
        + 212 * INTERVAL_MILLISECONDS["1h"]
        + 1_234
    )
    store_path = Path(directory) / "p10-forward.sqlite3"
    client = MockForwardRunnerClient(server_time)
    store = ForwardCandleStore(store_path)
    snapshot = collect_forward_snapshot(store, client)
    return store, snapshot, client


def main():
    with tempfile.TemporaryDirectory() as directory:
        store, snapshot, client = build_mock_forward_runner_fixture(directory)
        try:
            first = run_forward_paper(store, snapshot)
            second = run_forward_paper(store, snapshot)
        finally:
            store.close()

    if first.as_record() != second.as_record() or first.run_sha256 != second.run_sha256:
        raise RuntimeError("P10-005 forward Paper replay diverged")

    actions = [
        fill["action"]
        for symbol in first.symbols
        for fill in symbol.fills
    ]
    if "ENTER_LONG" not in actions or "EXIT_LONG" not in actions:
        raise RuntimeError("P10-005 runtime did not exercise entry and exit fills")

    output = {
        "runner_id": first.runner_id,
        "run_sha256": first.run_sha256,
        "ingestion_snapshot_sha256": first.ingestion_snapshot_sha256,
        "window_sha256": first.window_sha256,
        "candidate_sha256": first.candidate_sha256,
        "gate_registry_sha256": first.gate_registry_sha256,
        "execution_policy_id": first.execution_policy_id,
        "fixed_research_quantity": first.fixed_research_quantity,
        "symbols": {
            item.symbol: {
                "result_sha256": item.result_sha256,
                "event_count": item.event_count,
                "entry_signals": item.entry_signals,
                "entries_allowed": item.entries_allowed,
                "entries_blocked": item.entries_blocked,
                "exit_signals": item.exit_signals,
                "fill_count": len(item.fills),
                "closed_trades": item.final_portfolio["closed_trades"],
                "final_equity_quote": item.final_portfolio["equity_quote"],
                "total_fee_quote": item.final_portfolio["total_fee_quote"],
                "total_slippage_quote":
                    item.final_portfolio["total_slippage_quote"],
                "kill_switch_latched": item.kill_switch_latched,
                "point_in_time_verified": item.point_in_time_verified,
                "replay_from_start": item.replay_from_start,
            }
            for item in first.symbols
        },
        "entry_fill_present": "ENTER_LONG" in actions,
        "exit_fill_present": "EXIT_LONG" in actions,
        "paper_only": first.paper_only,
        "live_master_lock": first.live_master_lock,
        "p3_qualification_fabricated": first.p3_qualification_fabricated,
        "p4_risk_authorization_created": first.p4_risk_authorization_created,
        "quantity_authority_created": first.quantity_authority_created,
        "external_transport_used": first.external_transport_used,
        "trade_permission": first.trade_permission,
        "order_endpoint": first.order_endpoint,
        "ai_direct_execution": first.ai_direct_execution,
        "economic_evaluation_allowed": first.economic_evaluation_allowed,
        "strategy_evidence": first.strategy_evidence,
        "mocked_market_data": True,
        "real_network_called": False,
        "real_forward_data_loaded": False,
        "server_time_calls": client.server_time_calls,
        "kline_calls": client.kline_calls,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
