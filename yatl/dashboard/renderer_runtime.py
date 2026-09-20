"""Deterministic offline runtime gate for P8-007 dashboard renderer."""

import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import load_p7_export
from .overview import project_overview
from .performance_views import project_performance_segmentation
from .quality_view import project_quality_diagnostics
from .renderer import render_dashboard
from .trade_table import project_completed_trade_table


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        healthy_root = root / "healthy"
        healthy_root.mkdir()
        _, _, specs = _fixture(healthy_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        record, encoded = _export_payload(gate)
        export_path = root / "accepted-p7-export.json"
        export_path.write_text(encoded, encoding="utf-8")
        loaded = load_p7_export(export_path, record["export_sha256"])

        quality = project_quality_diagnostics(loaded=loaded)
        overview = project_overview(loaded)
        trades = project_completed_trade_table(loaded)
        performance = project_performance_segmentation(loaded)

        full_first = render_dashboard(
            quality,
            overview=overview,
            trades=trades,
            performance=performance,
        )
        full_second = render_dashboard(
            quality,
            overview=overview,
            trades=trades,
            performance=performance,
        )

        failed_root = root / "failed"
        failed_root.mkdir()
        _, p6, failed_specs = _fixture(failed_root)
        p6.unlink()
        failed_gate = run_quality_gate(SNAPSHOT, failed_specs)
        fail_quality = project_quality_diagnostics(
            quality_record=failed_gate.report.as_record()
        )
        fail_first = render_dashboard(fail_quality)
        fail_second = render_dashboard(fail_quality)

        absent_quality = project_quality_diagnostics()
        absent = render_dashboard(absent_quality)

        forbidden = (
            "<script",
            "<img",
            "<iframe",
            "<link",
            " src=",
            " href=",
            "fetch(",
            "localStorage",
            "WebSocket",
        )
        if (
            full_first != full_second
            or full_first.dashboard_sha256 != full_second.dashboard_sha256
            or fail_first != fail_second
            or full_first.artifact_kind != "FULL"
            or full_first.quality_status != "PASS"
            or full_first.source_export_sha256 != loaded.export_sha256
            or fail_first.artifact_kind != "QUALITY_BLOCKED"
            or fail_first.source_export_sha256 is not None
            or absent.artifact_kind != "QUALITY_BLOCKED"
            or any(token in full_first.html for token in forbidden)
            or any(token in fail_first.html for token in forbidden)
            or "Content-Security-Policy" not in full_first.html
            or "PAPER ONLY" not in full_first.html
            or "INSUFFICIENT_EVIDENCE" not in full_first.html
        ):
            raise RuntimeError("P8-007 deterministic renderer runtime gate failed")

        print(
            "OK: P8 deterministic dashboard renderer; "
            f"full_bytes={full_first.byte_length} "
            f"blocked_bytes={fail_first.byte_length} "
            "byte_identical=true self_contained=true browser_static=true "
            "strict_escape=true remote_resources=false "
            "failed_quality_partial_analytics=false "
            f"export_sha256={loaded.export_sha256} "
            f"view_model_sha256={full_first.view_model_sha256} "
            f"dashboard_sha256={full_first.dashboard_sha256} "
            f"blocked_dashboard_sha256={fail_first.dashboard_sha256} "
            f"absent_dashboard_sha256={absent.dashboard_sha256}"
        )
        print(
            "PAPER ONLY | LIVE_MASTER_LOCK=OFF | INSUFFICIENT_EVIDENCE | "
            "STATIC HTML ONLY | CSP BLOCKS NETWORK/SCRIPT | No CDN/fonts/fetch/XHR | "
            "No WebSocket/cookies/localStorage | No file publication in P8-007 | "
            "No direct P5/P6 access | No credentials | No provider transport | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
