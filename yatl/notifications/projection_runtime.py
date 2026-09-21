"""Deterministic offline P9-002 upstream projection and formatter gate."""

import json
import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.loader import load_p7_export
from yatl.dashboard.overview import project_overview
from yatl.dashboard.quality_view import project_quality_diagnostics

from .formatter import format_notification
from .projection import project_data_quality_alert, project_system_status


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
        overview = project_overview(loaded)

        status_first = project_system_status(overview)
        status_second = project_system_status(overview)
        status_rendered = format_notification(status_first)

        failed_root = root / "failed"
        failed_root.mkdir()
        _, p6, failed_specs = _fixture(failed_root)
        p6.unlink()
        failed_gate = run_quality_gate(SNAPSHOT, failed_specs)
        failed_quality = project_quality_diagnostics(
            quality_record=failed_gate.report.as_record()
        )
        alert_first = project_data_quality_alert(failed_quality)
        alert_second = project_data_quality_alert(failed_quality)
        alert_rendered = format_notification(alert_first)

        if (
            status_first != status_second
            or alert_first != alert_second
            or status_first.message_sha256 != status_second.message_sha256
            or alert_first.message_sha256 != alert_second.message_sha256
            or status_first.source.payload_sha256 != overview.overview_sha256
            or alert_first.source.payload_sha256 != failed_quality.projection_sha256
            or "open trade count UNKNOWN" not in status_first.body
            or "snapshot freshness UNKNOWN" not in status_first.body
            or alert_first.actionability != "INFORMATION_ONLY"
            or status_rendered.format_mode != "PLAIN_TEXT_NO_PARSE_MODE"
            or alert_rendered.format_mode != "PLAIN_TEXT_NO_PARSE_MODE"
        ):
            raise RuntimeError("P9-002 projection/formatter runtime gate failed")

        output = {
            "status_notification_sha256": status_first.message_sha256,
            "status_formatted_sha256": status_rendered.formatted_sha256,
            "quality_notification_sha256": alert_first.message_sha256,
            "quality_formatted_sha256": alert_rendered.formatted_sha256,
            "overview_sha256": overview.overview_sha256,
            "quality_projection_sha256": failed_quality.projection_sha256,
            "status_replay_equal": status_first == status_second,
            "quality_replay_equal": alert_first == alert_second,
            "open_trade_count": "UNKNOWN",
            "snapshot_freshness": "UNKNOWN",
            "format_mode": "PLAIN_TEXT_NO_PARSE_MODE",
            "network_transport": False,
            "telegram_transport": False,
            "trade_permission": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
