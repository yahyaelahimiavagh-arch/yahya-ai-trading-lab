"""Deterministic offline runtime gate for P8-003 overview projection."""

import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import load_p7_export
from .overview import UNKNOWN_FIELDS, project_overview


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
        first = project_overview(loaded)
        second = project_overview(loaded)

        by_key = {item.field_key: item for item in first.cards}
        chain = record["quality"]["accepted_chain"]
        if (
            first != second
            or first.overview_sha256 != second.overview_sha256
            or first.unknown_fields != UNKNOWN_FIELDS
            or by_key["symbol"].value != record["analytics"]["symbol"]
            or by_key["snapshot_time_ms"].value
            != str(record["quality"]["snapshot_time_ms"])
            or by_key["paper_state"].value != "PAPER ONLY"
            or by_key["live_master_lock"].value != "OFF"
            or by_key["strategy_evidence"].value != "INSUFFICIENT_EVIDENCE"
            or by_key["quality_status"].value != "PASS"
            or by_key["completed_trade_count"].value
            != str(chain["completed_trade_count"])
            or by_key["open_trade_count"].value != "UNKNOWN"
            or by_key["snapshot_freshness"].value != "UNKNOWN"
            or by_key["segmentation_sha256"].value
            != chain["segmentation_sha256"]
        ):
            raise RuntimeError("P8-003 overview projection runtime gate failed")

        print(
            "OK: P8 system/safety/quality overview; "
            "cards=15 source_fields_conserved=true "
            "open_trade_count=UNKNOWN snapshot_freshness=UNKNOWN "
            "readiness_inference=false replay_equal=true "
            "strategy=INSUFFICIENT_EVIDENCE "
            f"export_sha256={loaded.export_sha256} "
            f"overview_sha256={first.overview_sha256}"
        )
        print(
            "PAPER ONLY | LOCAL_READ_ONLY_DASHBOARD | LIVE_MASTER_LOCK=OFF | "
            "P7 quality=PASS | Explicit unknown handling | "
            "No new health/readiness inference | No trade/live permission | "
            "No direct P5/P6 access | No credentials | No network/provider | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
