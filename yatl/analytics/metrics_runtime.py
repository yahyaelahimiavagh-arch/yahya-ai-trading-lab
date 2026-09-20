"""Deterministic offline runtime gate for P7-005 performance metrics."""

import hashlib
import tempfile
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec
from .metrics import PerformanceMetricsStatus, calculate_performance_metrics
from .timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from .trade_runtime import _close_fixture
from .trades import reconstruct_paper_trades


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
        reconstruction = reconstruct_paper_trades(SNAPSHOT, specs)
        first = calculate_performance_metrics(reconstruction)
        second = calculate_performance_metrics(reconstruction)
        after = tuple(_file_sha(item.database_path) for item in specs)

        if (
            first != second
            or first.canonical_json != second.canonical_json
            or before != after
            or first.status is not PerformanceMetricsStatus.DESCRIPTIVE
            or first.completed_trade_count != 1
            or first.winning_trades + first.losing_trades + first.breakeven_trades != 1
            or first.win_rate is None
            or first.gross_return is None
            or first.net_return is None
        ):
            raise RuntimeError("P7-005 performance metrics runtime gate failed")

        print(
            "OK: P7 deterministic performance metrics; "
            f"trades={first.completed_trade_count} "
            f"wins={first.winning_trades} losses={first.losing_trades} "
            f"breakeven={first.breakeven_trades} "
            f"gross_return={first.gross_return} net_return={first.net_return} "
            f"max_realized_drawdown_quote={first.maximum_realized_drawdown_quote} "
            "replay_equal=true no_write=true "
            f"metrics_sha256={first.metrics_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Completed trades only | "
            "No annualization | No extrapolation | No forecast | "
            "No credentials | No network/provider | No upstream mutation | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
