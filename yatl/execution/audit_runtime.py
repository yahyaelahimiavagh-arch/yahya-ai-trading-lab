"""Offline runtime gate for the independent final P5 acceptance audit."""

import argparse

from .audit import audit_p5


def _parser():
    parser = argparse.ArgumentParser(
        description="Independently audit deterministic local-only P5 evidence"
    )
    parser.add_argument("--evidence", required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    result = audit_p5(args.evidence)
    print(
        "OK: P5 independent final audit; "
        f"symbols={result.symbols} scenarios={result.scenarios} "
        f"runs={result.runs} files={result.files} "
        f"index_sha256={result.index_sha256} "
        f"policy_sha256={result.policy_sha256} "
        "exact_outcomes=true replay_equal=true source_safe=true"
    )
    print(
        "PAPER ONLY | LOCAL_PAPER | LIVE_MASTER_LOCK=OFF | "
        "P6 unopened | No real strategy qualification | No credentials | "
        "No external transport | No trade permission | No exchange order"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
