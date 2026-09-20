"""Deterministic offline runtime gate for P7-006 evidence segmentation."""

import hashlib
import tempfile
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec
from .segmentation import (
    SegmentDimension,
    STRATEGY_ATTRIBUTION_STATUS,
    UNATTRIBUTED_STRATEGY_IDENTITY,
    build_segmentation,
)
from .timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from .trade_runtime import _close_fixture


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        first = build_segmentation(SNAPSHOT, specs)
        second = build_segmentation(SNAPSHOT, specs)
        after = tuple(_file_sha(item.database_path) for item in specs)

        strategy = next(
            item for item in first.trade_segments
            if item.dimension is SegmentDimension.STRATEGY_IDENTITY
        )
        disposition = next(
            item for item in first.analyst_segments
            if item.dimension is SegmentDimension.ANALYST_DISPOSITION
        )

        if (
            first != second
            or first.canonical_json != second.canonical_json
            or first.segmentation_sha256 != second.segmentation_sha256
            or before != after
            or first.strategy_attribution_status != STRATEGY_ATTRIBUTION_STATUS
            or strategy.value != UNATTRIBUTED_STRATEGY_IDENTITY
            or strategy.member_count != 1
            or disposition.value != "REVIEW"
            or disposition.member_count != 1
        ):
            raise RuntimeError("P7-006 segmentation runtime gate failed")

        print(
            "OK: P7 strategy/evidence segmentation; "
            "completed_trades=1 analyst_traces=1 "
            "trade_partition_families=3 analyst_partition_families=3 "
            "strategy_identity=UNATTRIBUTED_DURABLE_P5 "
            "evidence=INSUFFICIENT_EVIDENCE analyst_disposition=REVIEW "
            "replay_equal=true no_write=true "
            f"metrics_sha256={first.metrics_sha256} "
            f"analyst_source_sha256={first.analyst_source_sha256} "
            f"segmentation_sha256={first.segmentation_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Exact partitions | "
            "No double counting | No causal attribution | "
            "No trade-to-analyst linkage invented | "
            "No credentials | No network/provider | No upstream mutation | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
