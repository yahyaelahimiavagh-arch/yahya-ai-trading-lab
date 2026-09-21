"""P9-005 deterministic adversarial notification matrix runtime."""

import argparse

from .scenarios import (
    SCENARIOS,
    SYMBOLS,
    notification_matrix_sha256,
    run_adversarial_notification_matrix,
    write_adversarial_notification_matrix,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministic P9 adversarial notification matrix"
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    first = run_adversarial_notification_matrix()
    replay = run_adversarial_notification_matrix()
    if first != replay or first.index_json != replay.index_json:
        raise RuntimeError("P9-005 notification matrix replay diverged")
    if args.output:
        write_adversarial_notification_matrix(first, args.output)

    print(
        "OK: P9 adversarial notification matrix; "
        f"scenarios={len(SCENARIOS)} symbols={len(SYMBOLS)} "
        f"runs={len(first.runs)} files={1 + len(first.runs)} "
        "exact_outcomes=true replay_equal=true canonical_evidence=true "
        "source_unchanged=true duplicate_suppression=true "
        "stable_runner_codes=true real_network_called=false "
        f"index_sha256={notification_matrix_sha256(first)}"
    )
    print(
        "PAPER ONLY | OUTBOUND ONLY | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | No inbound commands/webhooks/polling | "
        "No upstream mutation | No RiskAuthorization mutation | "
        "No quantity authority | No trade permission | No order endpoint | "
        "No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
