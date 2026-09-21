"""Mocked P10-008 acceptance for guarded local CLI/export behavior."""

import hashlib
import json
import tempfile
from pathlib import Path

from .cli import (
    ValidationCliCode,
    ValidationCliError,
    _export_from_bundle,
    _pipeline,
    _status_from_bundle,
    _summary_from_bundle,
    snapshot_json,
)
from .paper_runner_runtime import build_mock_forward_runner_fixture


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _family_identity(database):
    values = {"database": _sha(database)}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            values[suffix] = _sha(sidecar)
    return values


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, snapshot, client = build_mock_forward_runner_fixture(root)
        database = root / "p10-forward.sqlite3"
        store.close()

        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(snapshot_json(snapshot), encoding="utf-8")

        upstream_before = _family_identity(database)
        snapshot_before = _sha(snapshot_path)

        bundle = _pipeline(database, snapshot_path)
        first_status = _status_from_bundle(bundle)
        second_status = _status_from_bundle(bundle)
        first_summary = _summary_from_bundle(bundle)
        second_summary = _summary_from_bundle(bundle)

        first_path = root / "p10-audit-one.json"
        second_path = root / "p10-audit-two.json"
        first_export = _export_from_bundle(bundle, first_path)
        second_export = _export_from_bundle(bundle, second_path)

        if first_status != second_status or first_summary != second_summary:
            raise RuntimeError("P10-008 status or summary replay diverged")
        if first_path.read_bytes() != second_path.read_bytes():
            raise RuntimeError("P10-008 canonical export replay diverged")
        if first_export["audit_sha256"] != second_export["audit_sha256"]:
            raise RuntimeError("P10-008 audit digest replay diverged")

        try:
            _export_from_bundle(bundle, first_path)
        except ValidationCliError as exc:
            if exc.code is not ValidationCliCode.OUTPUT_EXISTS:
                raise
        else:
            raise RuntimeError("P10-008 export overwrote an existing artifact")

        if _family_identity(database) != upstream_before:
            raise RuntimeError("P10-008 mutated upstream database evidence")
        if _sha(snapshot_path) != snapshot_before:
            raise RuntimeError("P10-008 mutated upstream snapshot evidence")
        if first_status["disposition"] != "INSUFFICIENT_DATA":
            raise RuntimeError("Mocked P10-008 evidence must remain insufficient")
        if first_status["p11_unlocked"] is not False:
            raise RuntimeError("P10-008 must not unlock P11")

        output = {
            "schema_version": 1,
            "status_code": first_status["code"],
            "summary_code": first_summary["code"],
            "export_code": first_export["code"],
            "audit_sha256": first_export["audit_sha256"],
            "export_bytes": first_export["bytes"],
            "paper_run_sha256": first_status["paper_run_sha256"],
            "economics_sha256": first_status["economics_sha256"],
            "gate_sha256": first_status["gate_sha256"],
            "disposition": first_status["disposition"],
            "sample_status": first_status["sample_status"],
            "upstream_unchanged": True,
            "snapshot_unchanged": True,
            "atomic": first_export["atomic"],
            "overwrite_allowed": first_export["overwrite_allowed"],
            "replay_equal": True,
            "mocked_market_data": True,
            "real_network_called": False,
            "real_forward_data_loaded": False,
            "paper_only": first_status["paper_only"],
            "live_master_lock": first_status["live_master_lock"],
            "strategy_evidence": first_status["strategy_evidence"],
            "p11_unlocked": first_status["p11_unlocked"],
            "server_time_calls": client.server_time_calls,
            "kline_calls": client.kline_calls,
        }
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
