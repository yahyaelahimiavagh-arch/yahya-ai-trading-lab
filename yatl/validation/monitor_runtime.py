"""Deterministic mocked runtime for the P10 operational monitoring layer."""

import hashlib
import json
import tempfile
from pathlib import Path

from .cli import snapshot_json
from .monitor import build_dashboard, build_notification
from .paper_runner_runtime import build_mock_forward_runner_fixture


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, snapshot, client = build_mock_forward_runner_fixture(root)
        store.close()

        database = root / "p10-forward.sqlite3"
        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(snapshot_json(snapshot), encoding="utf-8")

        dashboard = root / "index.html"
        btc = root / "btc.json"
        eth = root / "eth.json"

        dashboard_result = build_dashboard(database, snapshot_path, dashboard)
        btc_result = build_notification(
            database,
            snapshot_path,
            "BTCUSDT",
            btc,
        )
        eth_result = build_notification(
            database,
            snapshot_path,
            "ETHUSDT",
            eth,
        )

        dashboard_bytes = dashboard.read_bytes()
        if (
            dashboard_result["code"] != "DASHBOARD_UPDATED"
            or btc_result["code"] != "NOTIFICATION_UPDATED"
            or eth_result["code"] != "NOTIFICATION_UPDATED"
            or not dashboard_bytes.startswith(b"<!doctype html>")
            or b"P11 LOCKED" not in dashboard_bytes
            or b"<script" in dashboard_bytes.lower()
            or b"http://" in dashboard_bytes.lower()
            or b"https://" in dashboard_bytes.lower()
            or btc_result["batch_sha256"] == eth_result["batch_sha256"]
            or dashboard_result["paper_only"] is not True
            or dashboard_result["live_master_lock"] != "OFF"
            or dashboard_result["p11_unlocked"] is not False
        ):
            raise RuntimeError("P10 monitoring runtime failed")

        output = {
            "schema_version": 1,
            "monitor_id": dashboard_result["monitor_id"],
            "summary_code": dashboard_result["summary_code"],
            "dashboard_sha256": _sha256(dashboard),
            "dashboard_bytes": len(dashboard_bytes),
            "btc_batch_sha256": btc_result["batch_sha256"],
            "eth_batch_sha256": eth_result["batch_sha256"],
            "paper_only": True,
            "live_master_lock": "OFF",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "p11_unlocked": False,
            "mocked_market_data": True,
            "real_network_called": False,
            "telegram_transport_called": False,
            "server_time_calls": client.server_time_calls,
            "kline_calls": client.kline_calls,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
