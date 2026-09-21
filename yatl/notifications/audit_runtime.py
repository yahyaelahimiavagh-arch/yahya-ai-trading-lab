"""Deterministic runtime gate for the independent P9-006 final audit."""

import argparse
import tempfile
from pathlib import Path

from .audit import _audit_identity_set, audit_p9
from .scenarios import (
    run_adversarial_notification_matrix,
    write_adversarial_notification_matrix,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent P9 final notification acceptance audit"
    )
    parser.add_argument("--evidence")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixtures, identities, identity_set_sha = _audit_identity_set()

        if args.evidence:
            evidence = Path(args.evidence)
        else:
            evidence = root / "p9-005-evidence"
            matrix = run_adversarial_notification_matrix(fixtures)
            write_adversarial_notification_matrix(matrix, evidence)

        before = {
            path.name: path.read_bytes()
            for path in sorted(evidence.iterdir(), key=lambda item: item.name)
        }
        result = audit_p9(evidence)
        after = {
            path.name: path.read_bytes()
            for path in sorted(evidence.iterdir(), key=lambda item: item.name)
        }
        if before != after:
            raise RuntimeError("P9-006 final audit mutated P9-005 evidence")

        if identity_set_sha != result.identity_set_sha256:
            raise RuntimeError("P9-006 identity set changed during runtime audit")

        print(
            "OK: P9 independent final audit; "
            f"symbols={result.symbols} scenarios={result.scenarios} "
            f"runs={result.runs} files={result.files} "
            f"notification_policy_sha256={result.notification_policy_sha256} "
            f"transport_policy_sha256={result.transport_policy_sha256} "
            f"delivery_policy_sha256={result.delivery_policy_sha256} "
            f"identity_set_sha256={result.identity_set_sha256} "
            f"index_sha256={result.index_sha256} "
            "exact_outcomes=true replay_equal=true identities_recomputed=true "
            "formatter_recomputed=true delivery_recomputed=true "
            "evidence_verified=true no_write=true source_safe=true "
            "real_credentials_loaded=false real_network_called=false"
        )
        print(
            "PAPER ONLY | OUTBOUND ONLY | LIVE_MASTER_LOCK=OFF | "
            "INSUFFICIENT_EVIDENCE preserved | BTCUSDT/ETHUSDT identities frozen | "
            "P9-005 evidence byte-identical | No inbound commands/callbacks/webhooks/polling | "
            "No execution/account/risk import | No RiskAuthorization mutation | "
            "No quantity authority | No trade permission | No order endpoint | "
            "No AI direct execution"
        )
        print(
            "BTCUSDT batch_sha256="
            f"{identities['BTCUSDT']['batch_sha256']} "
            "ETHUSDT batch_sha256="
            f"{identities['ETHUSDT']['batch_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
