"""Deterministic runtime gate for the independent P8-010 final audit."""

import argparse
import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import QualityStatus, run_quality_gate
from yatl.analytics.scenarios import SNAPSHOT, _fixture

from .audit import EXPECTED_EXPORTS, audit_p8
from .cli import dashboard_build
from .scenarios import (
    SYMBOLS,
    DashboardAcceptedFixture,
    run_adversarial_dashboard_matrix,
    write_adversarial_dashboard_matrix,
)


def _accepted_exports(root):
    paths = {}
    fixtures = {}
    for symbol in SYMBOLS:
        source_root = root / f"source-{symbol.lower()}"
        source_root.mkdir()
        _, _, specs = _fixture(source_root, symbol)
        gate = run_quality_gate(SNAPSHOT, specs)
        if (
            gate.report.status is not QualityStatus.PASS
            or gate.accepted_segmentation is None
        ):
            raise RuntimeError("P8-010 accepted P7 fixture failed")
        record, encoded = _export_payload(gate)
        if record["export_sha256"] != EXPECTED_EXPORTS[symbol]:
            raise RuntimeError("P8-010 accepted P7 export identity changed")
        path = root / f"{symbol.lower()}-accepted-p7.json"
        path.write_text(encoded, encoding="utf-8")
        paths[symbol] = path
        fixtures[symbol] = DashboardAcceptedFixture(
            symbol,
            encoded,
            record["export_sha256"],
        )
    return paths, fixtures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent P8 final Dashboard acceptance audit"
    )
    parser.add_argument("--evidence")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        exports, fixtures = _accepted_exports(root)

        if args.evidence:
            evidence = Path(args.evidence)
        else:
            evidence = root / "p8-009-evidence"
            matrix = run_adversarial_dashboard_matrix(fixtures)
            write_adversarial_dashboard_matrix(matrix, evidence)

        published = {}
        for symbol in SYMBOLS:
            output = root / f"{symbol.lower()}-dashboard.html"
            dashboard_build(
                exports[symbol],
                EXPECTED_EXPORTS[symbol],
                output,
            )
            published[symbol] = output

        before = {symbol: exports[symbol].read_bytes() for symbol in SYMBOLS}
        result = audit_p8(exports, evidence, published)
        after = {symbol: exports[symbol].read_bytes() for symbol in SYMBOLS}
        if before != after:
            raise RuntimeError("P8-010 final audit mutated accepted source exports")

        print(
            "OK: P8 independent final audit; "
            f"symbols={result.symbols} scenarios={result.scenarios} "
            f"runs={result.runs} files={result.files} "
            f"published_artifacts={result.published_artifacts} "
            f"policy_sha256={result.policy_sha256} "
            f"index_sha256={result.index_sha256} "
            f"export_set_sha256={result.export_set_sha256} "
            f"renderer_set_sha256={result.renderer_set_sha256} "
            "exact_outcomes=true replay_equal=true projections_recomputed=true "
            "renderer_recomputed=true artifacts_verified=true "
            "no_write=true source_safe=true"
        )
        print(
            "PAPER ONLY | LOCAL_READ_ONLY_DASHBOARD | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | Accepted BTCUSDT/ETHUSDT P7 exports "
            "recomputed | P8-009 evidence byte-identical | Published HTML verified | "
            "No credentials | No network/provider | No remote assets/scripts | "
            "No direct P5/P6 access | No execution/account/risk import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
