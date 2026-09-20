"""Runtime entry point for the P6 independent final acceptance audit."""

import argparse

from .audit import audit_p6


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Independent final audit of accepted P6 analyst evidence"
    )
    parser.add_argument(
        "--evidence",
        default="data/p6/p6-009-evidence",
    )
    args = parser.parse_args(argv)
    result = audit_p6(args.evidence)
    print(
        "OK: P6 independent final audit; "
        f"symbols={result.symbols} scenarios={result.scenarios} "
        f"runs={result.runs} files={result.files} "
        f"index_sha256={result.index_sha256} "
        f"policy_sha256={result.policy_sha256} "
        f"evidence_sha256={result.evidence_sha256} "
        "exact_outcomes=true replay_equal=true source_safe=true"
    )
    print(
        "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | Independent accepted-artifact audit | "
        "No credentials | No provider/network | No executor import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
