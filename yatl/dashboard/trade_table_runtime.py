"""Deterministic offline runtime gate for P8-004 completed-trade table."""

import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import load_p7_export
from .trade_table import (
    TradeSortDirection,
    TradeSortKey,
    TradeTableQuery,
    project_completed_trade_table,
)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_root = root / "accepted-source"
        source_root.mkdir()
        _, _, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        record, encoded = _export_payload(gate)

        export_path = root / "accepted-p7-export.json"
        export_path.write_text(encoded, encoding="utf-8")
        loaded = load_p7_export(export_path, record["export_sha256"])

        default_first = project_completed_trade_table(loaded)
        default_second = project_completed_trade_table(loaded)
        descending = project_completed_trade_table(
            loaded,
            TradeTableQuery(
                sort_key=TradeSortKey.NET_PNL,
                direction=TradeSortDirection.DESC,
                page_size=25,
            ),
        )

        source_metrics = record["analytics"]["trade_metrics"]
        if (
            default_first != default_second
            or default_first.table_sha256 != default_second.table_sha256
            or default_first.total_completed != len(source_metrics)
            or default_first.total_filtered != len(source_metrics)
            or default_first.returned_count != len(source_metrics)
            or default_first.noncompleted_policy
            != "SEPARATE_NOT_PROJECTED_FROM_P7_TRADE_METRICS"
            or descending.total_completed != default_first.total_completed
            or any(item.status != "COMPLETED" for item in default_first.rows)
            or any(item.side != "LONG" for item in default_first.rows)
            or any(item.paper is not True for item in default_first.rows)
            or any(item.display_only is not True for item in default_first.rows)
            or any(
                item.source_trade_sha256 != metric["trade_sha256"]
                or item.net_pnl != metric["realized_pnl_quote"]
                or item.entry_gross_quote != metric["entry_gross_quote"]
                or item.exit_gross_quote != metric["exit_gross_quote"]
                or item.entry_cash_out_quote != metric["entry_cash_out_quote"]
                or item.gross_return != metric["gross_return"]
                or item.net_return != metric["net_return"]
                or item.fee_total != metric["total_fee_quote"]
                or item.slippage_total != metric["total_slippage_quote"]
                or item.holding_time_ms != metric["holding_time_ms"]
                for item, metric in zip(default_first.rows, source_metrics)
            )
        ):
            raise RuntimeError("P8-004 completed-trade table runtime gate failed")

        print(
            "OK: P8 completed-trade table; "
            f"completed={default_first.total_completed} "
            "source_values_exact=true replay_equal=true "
            "open_incomplete_isolated=true bounded_page=true "
            f"export_sha256={loaded.export_sha256} "
            f"metrics_sha256={default_first.source_metrics_sha256} "
            f"table_sha256={default_first.table_sha256}"
        )
        print(
            "PAPER ONLY | LONG COMPLETED ROWS ONLY | LOCAL_READ_ONLY_DASHBOARD | "
            "LIVE_MASTER_LOCK=OFF | INSUFFICIENT_EVIDENCE preserved | "
            "No invented entry/exit time, quantity or price | "
            "No direct P5/P6 access | No credentials | No network/provider | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
