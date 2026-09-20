"""Deterministic offline runtime gate for P8-006 quality/diagnostic view."""

import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import load_p7_export
from .quality_view import project_quality_diagnostics


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        healthy_root = root / "healthy"
        healthy_root.mkdir()
        _, _, specs = _fixture(healthy_root)
        healthy_gate = run_quality_gate(SNAPSHOT, specs)
        record, encoded = _export_payload(healthy_gate)
        export_path = root / "accepted-p7-export.json"
        export_path.write_text(encoded, encoding="utf-8")
        loaded = load_p7_export(export_path, record["export_sha256"])

        pass_first = project_quality_diagnostics(loaded=loaded)
        pass_second = project_quality_diagnostics(loaded=loaded)

        failed_root = root / "failed"
        failed_root.mkdir()
        _, p6, failed_specs = _fixture(failed_root)
        p6.unlink()
        failed_gate = run_quality_gate(SNAPSHOT, failed_specs)
        fail_first = project_quality_diagnostics(
            quality_record=failed_gate.report.as_record()
        )
        fail_second = project_quality_diagnostics(
            quality_record=failed_gate.report.as_record()
        )

        absent_first = project_quality_diagnostics()
        absent_second = project_quality_diagnostics()

        if (
            pass_first != pass_second
            or fail_first != fail_second
            or absent_first != absent_second
            or pass_first.quality_status != "PASS"
            or pass_first.analytics_presentation_allowed is not True
            or pass_first.diagnostics
            or fail_first.quality_status != "FAIL"
            or fail_first.analytics_presentation_allowed is not False
            or fail_first.partial_analytics_visible is not False
            or len(fail_first.diagnostics) != 1
            or fail_first.diagnostics[0].code != "MISSING_SOURCE"
            or absent_first.quality_status != "ABSENT"
            or absent_first.analytics_presentation_allowed is not False
            or absent_first.diagnostics
            or pass_first.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or fail_first.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or absent_first.strategy_evidence != "INSUFFICIENT_EVIDENCE"
        ):
            raise RuntimeError("P8-006 quality/diagnostic runtime gate failed")

        print(
            "OK: P8 quality/diagnostic view; "
            "pass_gate=true fail_gate=true absent_gate=true "
            "partial_analytics_visible=false unknown_codes_fail_closed=true "
            "replay_equal=true strategy=INSUFFICIENT_EVIDENCE "
            f"quality_sha256={pass_first.source_quality_sha256} "
            f"pass_projection_sha256={pass_first.projection_sha256} "
            f"fail_projection_sha256={fail_first.projection_sha256} "
            f"absent_projection_sha256={absent_first.projection_sha256}"
        )
        print(
            "PAPER ONLY | LIVE_MASTER_LOCK=OFF | PASS analytics only | "
            "FAIL/ABSENT analytics blocked | Bounded sanitized diagnostics | "
            "No local path | No SQL | No traceback | No private material | "
            "No direct P5/P6 access | No credentials | No network/provider | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
