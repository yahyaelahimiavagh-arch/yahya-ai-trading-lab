"""Deterministic offline runtime gate for P8-005 performance/segmentation."""

import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import load_p7_export
from .performance_views import project_performance_segmentation


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

        first = project_performance_segmentation(loaded)
        second = project_performance_segmentation(loaded)
        by_id = {item.metric_id: item for item in first.metrics}
        symbol_segment = next(
            item
            for item in record["analytics"]["trade_segments"]
            if item["dimension"] == "SYMBOL"
            and item["value"] == record["analytics"]["symbol"]
        )

        if (
            first != second
            or first.projection_sha256 != second.projection_sha256
            or by_id["METRIC_COMPLETED_TRADES"].value
            != str(symbol_segment["member_count"])
            or by_id["METRIC_REALIZED_PNL"].value
            != symbol_segment["realized_pnl_quote"]
            or by_id["METRIC_TOTAL_COST"].value
            != symbol_segment["total_cost_quote"]
            or by_id["METRIC_WINNING_TRADES"].value
            != str(symbol_segment["winning_trades"])
            or by_id["METRIC_LOSING_TRADES"].value
            != str(symbol_segment["losing_trades"])
            or by_id["METRIC_BREAKEVEN_TRADES"].value
            != str(symbol_segment["breakeven_trades"])
            or first.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or first.cross_dimension_aggregation is not False
            or first.causality_claim is not False
        ):
            raise RuntimeError("P8-005 performance/segmentation runtime gate failed")

        print(
            "OK: P8 performance/segmentation; "
            f"metrics={len(first.metrics)} "
            f"trade_segments={len(first.trade_segments)} "
            f"analyst_segments={len(first.analyst_segments)} "
            "source_values_conserved=true symbol_reconciled=true "
            "cross_dimension_aggregation=false causality_claim=false "
            "replay_equal=true strategy=INSUFFICIENT_EVIDENCE "
            f"export_sha256={loaded.export_sha256} "
            f"metrics_sha256={first.source_metrics_sha256} "
            f"segmentation_sha256={first.source_segmentation_sha256} "
            f"projection_sha256={first.projection_sha256}"
        )
        print(
            "PAPER ONLY | COMPLETED_PAPER_TRADES_ONLY | LIVE_MASTER_LOCK=OFF | "
            "Exact null/unavailable handling | No double counting | "
            "No evidence upgrade | No extrapolation | No causality | "
            "No direct P5/P6 access | No credentials | No network/provider | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
