"""Deterministic offline runtime gate for P7-008 guarded analytics CLI/export."""

import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

from .cli import (
    EXIT_EXISTS,
    EXIT_OK,
    analytics_export,
    analytics_summary,
    analytics_trades,
    analytics_validate,
    main as cli_main,
)
from .timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from .trade_runtime import _close_fixture


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_spec(path, p5, p6):
    record = {
        "schema_version": 1,
        "snapshot_time_ms": SNAPSHOT,
        "sources": [
            {
                "source_id": "SOURCE_P5",
                "source_kind": "P5_EXECUTION_EVIDENCE",
                "symbol": "BTCUSDT",
                "observed_at_ms": START + 90,
                "database_path": str(p5),
                "expected_database_sha256": _file_sha(p5),
            },
            {
                "source_id": "SOURCE_P6",
                "source_kind": "P6_ANALYST_TRACE",
                "symbol": "BTCUSDT",
                "observed_at_ms": P6_OBSERVED,
                "database_path": str(p6),
                "expected_database_sha256": _file_sha(p6),
            },
        ],
    }
    path.write_text(_canonical(record), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        p5 = root / "p5.sqlite3"
        p6 = root / "p6.sqlite3"
        spec = root / "analytics.json"
        first_export = root / "first.json"
        second_export = root / "second.json"
        _create_p5(p5)
        _close_fixture(p5)
        _create_p6(p6)
        _write_spec(spec, p5, p6)

        source_before = (_file_sha(p5), _file_sha(p6))
        validate_first = analytics_validate(spec)
        validate_second = analytics_validate(spec)
        summary_first = analytics_summary(spec)
        summary_second = analytics_summary(spec)
        trades_first = analytics_trades(spec, 25)
        trades_second = analytics_trades(spec, 25)
        export_first = analytics_export(spec, first_export)
        export_second = analytics_export(spec, second_export)
        source_after = (_file_sha(p5), _file_sha(p6))

        if (
            validate_first != validate_second
            or summary_first != summary_second
            or trades_first != trades_second
            or export_first["export_sha256"] != export_second["export_sha256"]
            or first_export.read_bytes() != second_export.read_bytes()
            or source_before != source_after
            or summary_first["completed_trade_count"] != 1
            or trades_first["returned_trades"] != 1
        ):
            raise RuntimeError("P7-008 deterministic CLI/export runtime failed")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            first_code = cli_main(["summary", "--spec", str(spec)])
        if first_code != EXIT_OK or not output.getvalue().strip():
            raise RuntimeError("P7-008 CLI summary exit/output gate failed")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exists_code = cli_main(
                ["export", "--spec", str(spec), "--output", str(first_export)]
            )
        if exists_code != EXIT_EXISTS or str(first_export) in output.getvalue():
            raise RuntimeError("P7-008 no-overwrite/path-redaction gate failed")

        export_payload = first_export.read_text(encoding="utf-8")
        if (
            str(root) in export_payload
            or "database_path" in export_payload
            or "api_key" in export_payload.casefold()
            or "password" in export_payload.casefold()
        ):
            raise RuntimeError("P7-008 canonical export leaked local/private material")

        print(
            "OK: P7 guarded analytics CLI/export; "
            "commands=4 stable_exit_codes=true bounded_json=true "
            "atomic_export=true no_overwrite_default=true "
            "path_redaction=true replay_equal=true no_write=true "
            f"quality_sha256={validate_first['quality_sha256']} "
            f"segmentation_sha256={summary_first['segmentation_sha256']} "
            f"export_sha256={export_first['export_sha256']}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Noninteractive | "
            "No partial export on quality failure | No credentials | "
            "No network/provider | No upstream mutation | No executor import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
