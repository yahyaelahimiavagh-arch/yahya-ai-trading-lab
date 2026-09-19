"""Offline deterministic runtime gate for the P5 adversarial execution matrix."""

import argparse

from .scenarios import (
    SCENARIOS,
    execution_matrix_sha256,
    run_and_write_adversarial_execution_matrix,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Build deterministic local-only P5 adversarial execution evidence"
    )
    parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    result = run_and_write_adversarial_execution_matrix(args.output)
    print(
        "OK: P5 adversarial execution matrix; "
        f"symbols=2 scenarios={len(SCENARIOS)} runs={len(result.runs)} "
        "replay_equal=true "
        f"index_sha256={execution_matrix_sha256(result)}"
    )
    print(
        "PAPER ONLY | LOCAL_PAPER | LIVE_MASTER_LOCK=OFF | "
        "Engineering fixtures only | No real strategy qualification | "
        "No credentials | No external transport | No exchange order"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
