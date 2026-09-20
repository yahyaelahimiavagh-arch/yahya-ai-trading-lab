"""Deterministic offline runtime gate for P8-002 accepted P7 export loading."""

import hashlib
import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture

from .loader import P7ExportLoadCode, P7ExportLoadError, load_p7_export


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_root = root / "accepted-source"
        source_root.mkdir()
        p5, p6, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        record, encoded = _export_payload(gate)

        export_path = root / "accepted-p7-export.json"
        export_path.write_text(encoded, encoding="utf-8")
        before_export = _file_sha(export_path)
        before_upstream = (_file_sha(p5), _file_sha(p6))

        first = load_p7_export(export_path, record["export_sha256"])
        second = load_p7_export(export_path, record["export_sha256"])

        after_export = _file_sha(export_path)
        after_upstream = (_file_sha(p5), _file_sha(p6))

        tampered_path = root / "tampered.json"
        tampered = encoded.replace('"status":"PASS"', '"status":"FAIL"', 1)
        tampered_path.write_text(tampered, encoding="utf-8")
        try:
            load_p7_export(tampered_path, record["export_sha256"])
        except P7ExportLoadError as exc:
            tampered_code = exc.code
        else:
            raise RuntimeError("P8-002 tampered export was accepted")

        if (
            first != second
            or before_export != after_export
            or before_upstream != after_upstream
            or first.export_sha256 != record["export_sha256"]
            or first.segmentation_sha256
            != record["quality"]["accepted_chain"]["segmentation_sha256"]
            or first.source.strategy_evidence.value != "INSUFFICIENT_EVIDENCE"
            or tampered_code is not P7ExportLoadCode.DIGEST_MISMATCH
        ):
            raise RuntimeError("P8-002 accepted P7 export loader runtime gate failed")

        print(
            "OK: P8 accepted P7 export loader; "
            "quality=PASS accepted=true sanitized=true canonical=true "
            "replay_equal=true no_write=true tamper_rejected=true "
            "strategy=INSUFFICIENT_EVIDENCE "
            f"export_sha256={first.export_sha256} "
            f"quality_sha256={first.quality_sha256} "
            f"segmentation_sha256={first.segmentation_sha256} "
            f"raw_file_sha256={first.raw_file_sha256} "
            f"bytes={first.byte_length}"
        )
        print(
            "PAPER ONLY | LOCAL_READ_ONLY_DASHBOARD | LIVE_MASTER_LOCK=OFF | "
            "Accepted/sanitized P7 export only | Exact expected digest binding | "
            "No source write | No direct P5/P6 access by loader | "
            "No credentials | No network/provider | No execution/account/risk import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
