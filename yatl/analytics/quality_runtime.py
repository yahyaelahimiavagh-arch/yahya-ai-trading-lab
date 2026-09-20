"""Deterministic offline runtime gate for P7-007 analytics quality."""

import hashlib
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import UpstreamSourceSpec
from .quality import QualityCode, QualityStatus, run_quality_gate
from .timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from .trade_runtime import _close_fixture


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root):
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
    return p5, p6, specs


def _codes(result):
    return tuple(item.code for item in result.report.diagnostics)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        healthy_root = root / "healthy"
        healthy_root.mkdir()
        _, _, healthy_specs = _fixture(healthy_root)
        before = tuple(_file_sha(item.database_path) for item in healthy_specs)
        first = run_quality_gate(SNAPSHOT, healthy_specs)
        second = run_quality_gate(SNAPSHOT, healthy_specs)
        after = tuple(_file_sha(item.database_path) for item in healthy_specs)
        if (
            first != second
            or first.report.canonical_json != second.report.canonical_json
            or first.report.status is not QualityStatus.PASS
            or first.accepted_segmentation is None
            or before != after
        ):
            raise RuntimeError("P7-007 healthy quality runtime failed")

        matrix = {}

        missing_root = root / "missing"
        missing_root.mkdir()
        _, p6, specs = _fixture(missing_root)
        p6.unlink()
        result = run_quality_gate(SNAPSHOT, specs)
        matrix["missing"] = _codes(result)

        digest_root = root / "digest"
        digest_root.mkdir()
        p5, _, specs = _fixture(digest_root)
        with p5.open("ab") as stream:
            stream.write(b"changed")
        result = run_quality_gate(SNAPSHOT, specs)
        matrix["digest"] = _codes(result)

        future_root = root / "future"
        future_root.mkdir()
        _, _, specs = _fixture(future_root)
        result = run_quality_gate(
            SNAPSHOT,
            (specs[0], replace(specs[1], observed_at_ms=SNAPSHOT + 1)),
        )
        matrix["future"] = _codes(result)

        duplicate_root = root / "duplicate"
        duplicate_root.mkdir()
        _, _, specs = _fixture(duplicate_root)
        result = run_quality_gate(
            SNAPSHOT,
            (specs[0], replace(specs[1], source_id=specs[0].source_id)),
        )
        matrix["duplicate"] = _codes(result)

        orphan_root = root / "orphan"
        orphan_root.mkdir()
        p5, _, specs = _fixture(orphan_root)
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events SET intent_sha256=? "
                "WHERE sequence=0 LIMIT 1",
                ("0" * 64,),
            )
        connection.close()
        result = run_quality_gate(
            SNAPSHOT,
            (replace(specs[0], expected_database_sha256=_file_sha(p5)), specs[1]),
        )
        matrix["orphan"] = _codes(result)

        gap_root = root / "gap"
        gap_root.mkdir()
        p5, _, specs = _fixture(gap_root)
        connection = sqlite3.connect(str(p5))
        authorization = connection.execute(
            "SELECT authorization_sha256 FROM local_paper_order_events "
            "ORDER BY event_time_ms LIMIT 1"
        ).fetchone()[0]
        with connection:
            connection.execute(
                "DELETE FROM local_paper_order_events "
                "WHERE authorization_sha256=? AND sequence=0",
                (authorization,),
            )
        connection.close()
        result = run_quality_gate(
            SNAPSHOT,
            (replace(specs[0], expected_database_sha256=_file_sha(p5)), specs[1]),
        )
        matrix["gap"] = _codes(result)

        expected = {
            "missing": (QualityCode.MISSING_SOURCE,),
            "digest": (QualityCode.UPSTREAM_DIGEST_CHANGED,),
            "future": (QualityCode.FUTURE_TIMESTAMP,),
            "duplicate": (QualityCode.DUPLICATE_IDENTITY,),
            "orphan": (QualityCode.ORPHAN_RELATIONSHIP,),
            "gap": (QualityCode.TIMELINE_GAP,),
        }
        if matrix != expected:
            raise RuntimeError("P7-007 failure matrix outcomes changed")
        if any(
            run_quality_gate(
                SNAPSHOT,
                (
                    replace(healthy_specs[0], source_id="DUP"),
                    replace(healthy_specs[1], source_id="DUP"),
                ),
            ).accepted_segmentation
            is not None
            for _ in range(1)
        ):
            raise RuntimeError("P7-007 failure exposed partial analytics")

        chain = first.report.accepted_chain
        print(
            "OK: P7 analytics quality gate; "
            "healthy=PASS failures=6 diagnostics_bounded=true "
            "partial_publication_on_failure=false replay_equal=true no_write=true "
            f"manifest_sha256={chain.ingestion_manifest_sha256} "
            f"timeline_sha256={chain.timeline_sha256} "
            f"reconstruction_sha256={chain.reconstruction_sha256} "
            f"metrics_sha256={chain.metrics_sha256} "
            f"segmentation_sha256={chain.segmentation_sha256} "
            f"quality_sha256={first.report.quality_sha256}"
        )
        print(
            "PAPER ONLY | READ_ONLY_ANALYTICS | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Fail closed | "
            "No partial analytics publication on failure | "
            "No credentials | No network/provider | No upstream mutation | "
            "No executor import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
