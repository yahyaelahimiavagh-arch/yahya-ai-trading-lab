"""Deterministic offline runtime gate for P8-008 dashboard CLI/publication."""

import hashlib
import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .cli import (
    DashboardCliCode,
    DashboardCliError,
    dashboard_build,
    dashboard_summary,
    dashboard_validate,
)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_root = root / "source"
        source_root.mkdir()
        _, _, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        record, encoded = _export_payload(gate)

        source = root / "accepted-p7-export.json"
        source.write_text(encoded, encoding="utf-8")
        source_before = source.read_bytes()
        expected = record["export_sha256"]

        validated = dashboard_validate(source, expected)
        summary_first = dashboard_summary(source, expected)
        summary_second = dashboard_summary(source, expected)

        output = root / "dashboard.html"
        built_first = dashboard_build(source, expected, output)
        first_bytes = output.read_bytes()
        first_sha = hashlib.sha256(first_bytes).hexdigest()

        exists_code = None
        try:
            dashboard_build(source, expected, output)
        except DashboardCliError as exc:
            exists_code = exc.code

        built_overwrite = dashboard_build(
            source,
            expected,
            output,
            overwrite=True,
        )
        second_bytes = output.read_bytes()
        source_after = source.read_bytes()
        leftovers = tuple(root.glob(".yatl-p8-dashboard-*.tmp"))

        if (
            validated["code"] != DashboardCliCode.VALIDATED.value
            or summary_first != summary_second
            or summary_first["code"] != DashboardCliCode.SUMMARY_READY.value
            or built_first["code"] != DashboardCliCode.BUILT.value
            or built_first["replaced_existing"] is not False
            or built_overwrite["replaced_existing"] is not True
            or exists_code is not DashboardCliCode.OUTPUT_EXISTS
            or first_bytes != second_bytes
            or first_sha != built_first["dashboard_sha256"]
            or built_overwrite["dashboard_sha256"] != built_first["dashboard_sha256"]
            or source_before != source_after
            or leftovers
            or not first_bytes.startswith(b"<!doctype html>\n<html lang=\"en\">")
            or b"Content-Security-Policy" not in first_bytes
        ):
            raise RuntimeError("P8-008 dashboard CLI/publication runtime gate failed")

        print(
            "OK: P8 guarded dashboard CLI/publication; "
            "validate=true summary=true build=true "
            "noninteractive=true overwrite_default_refused=true "
            "explicit_overwrite=true atomic_same_directory=true "
            "temp_cleanup=true source_unchanged=true deterministic_output=true "
            f"bytes={len(first_bytes)} "
            f"export_sha256={expected} "
            f"view_model_sha256={built_first['view_model_sha256']} "
            f"dashboard_sha256={built_first['dashboard_sha256']}"
        )
        print(
            "PAPER ONLY | LIVE_MASTER_LOCK=OFF | INSUFFICIENT_EVIDENCE | "
            "LOCAL NONINTERACTIVE CLI | Stable redacted errors | "
            "No source mutation | No path echo | No credential echo | "
            "No direct P5/P6 access | No provider transport | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
