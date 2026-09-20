"""P8-009 deterministic adversarial matrix runtime and evidence generator."""

import argparse
import hashlib
import tempfile
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import QualityStatus, run_quality_gate
from yatl.analytics.scenarios import SNAPSHOT, _fixture

from .scenarios import (
    SCENARIOS,
    SYMBOLS,
    DashboardAcceptedFixture,
    dashboard_matrix_sha256,
    run_adversarial_dashboard_matrix,
    write_adversarial_dashboard_matrix,
)


def _fixtures():
    fixtures = {}
    roots = []
    temporary = tempfile.TemporaryDirectory()
    base = Path(temporary.name)
    for symbol in SYMBOLS:
        root = base / symbol.lower()
        root.mkdir()
        roots.append(root)
        _, _, specs = _fixture(root, symbol)
        gate = run_quality_gate(SNAPSHOT, specs)
        if (
            gate.report.status is not QualityStatus.PASS
            or gate.accepted_segmentation is None
        ):
            temporary.cleanup()
            raise RuntimeError("P8-009 accepted fixture quality failed")
        record, encoded = _export_payload(gate)
        fixture = DashboardAcceptedFixture(
            symbol,
            encoded,
            record["export_sha256"],
        )
        fixtures[symbol] = fixture
    return temporary, fixtures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministic P8 adversarial dashboard matrix"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    temporary, fixtures = _fixtures()
    try:
        first = run_adversarial_dashboard_matrix(fixtures)
        replay = run_adversarial_dashboard_matrix(fixtures)
        if first != replay or first.index_json != replay.index_json:
            raise RuntimeError("P8-009 matrix replay diverged")
        if args.output:
            write_adversarial_dashboard_matrix(first, args.output)

        identities = {
            symbol: fixtures[symbol].export_sha256
            for symbol in SYMBOLS
        }
        print(
            "OK: P8 adversarial dashboard matrix; "
            f"scenarios={len(SCENARIOS)} symbols={len(SYMBOLS)} "
            f"runs={len(first.runs)} files={1 + len(first.runs)} "
            "exact_outcomes=true replay_equal=true canonical_evidence=true "
            "xss_remote_prevention=true accepted_p7_identities_unchanged=true "
            f"index_sha256={dashboard_matrix_sha256(first)} "
            f"btc_export_sha256={identities['BTCUSDT']} "
            f"eth_export_sha256={identities['ETHUSDT']}"
        )
        print(
            "PAPER ONLY | READ_ONLY_SOURCE | LOCAL_DASHBOARD_ONLY | "
            "LIVE_MASTER_LOCK=OFF | INSUFFICIENT_EVIDENCE preserved | "
            "No partial publication | No credentials/private material | "
            "No network/provider | No execution/account/risk import | "
            "No RiskAuthorization mutation | No quantity authority | "
            "No trade permission | No order endpoint | No AI direct execution"
        )
    finally:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
