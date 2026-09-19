"""Deterministic offline runtime gate for P6-001 analyst contracts."""

from .contracts import (
    AnalystClaim,
    AnalystDisposition,
    AnalystInput,
    AnalystPolicy,
    ClaimKind,
    EvidenceLayer,
    EvidenceReference,
    StrategyEvidenceState,
    build_analyst_report,
)


DECISION_TIME = 1_700_000_000_000


def _input():
    refs = (
        EvidenceReference(
            "E_MARKET",
            EvidenceLayer.P1_PUBLIC_MARKET,
            "1" * 64,
            "BTCUSDT",
            DECISION_TIME - 4000,
        ),
        EvidenceReference(
            "E_RISK",
            EvidenceLayer.P4_RISK_STATUS,
            "3" * 64,
            "BTCUSDT",
            DECISION_TIME - 2000,
        ),
        EvidenceReference(
            "E_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            "4" * 64,
            "BTCUSDT",
            DECISION_TIME - 1000,
        ),
        EvidenceReference(
            "E_STRATEGY",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            "2" * 64,
            "BTCUSDT",
            DECISION_TIME - 3000,
        ),
    )
    return AnalystInput(
        "BTCUSDT",
        DECISION_TIME,
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        refs,
    )


def main():
    analysis_input = _input()
    policy = AnalystPolicy()

    supported = build_analyst_report(
        analysis_input,
        (
            AnalystClaim(
                "CLAIM_FACT",
                ClaimKind.FACT,
                "Public market evidence is available.",
                ("E_MARKET",),
            ),
            AnalystClaim(
                "CLAIM_OBSERVATION",
                ClaimKind.DERIVED_OBSERVATION,
                "Strategy evidence remains insufficient.",
                ("E_STRATEGY",),
            ),
        ),
        policy,
    )
    uncertain = build_analyst_report(
        analysis_input,
        (
            AnalystClaim(
                "CLAIM_UNCERTAINTY",
                ClaimKind.UNCERTAINTY,
                "The accepted evidence does not resolve the research question.",
                ("E_STRATEGY",),
            ),
        ),
        policy,
    )
    unsupported = build_analyst_report(
        analysis_input,
        (
            AnalystClaim(
                "CLAIM_UNSUPPORTED",
                ClaimKind.UNSUPPORTED,
                "This statement has no accepted evidence.",
            ),
        ),
        policy,
    )

    if (
        supported.disposition is not AnalystDisposition.NO_TRADE
        or uncertain.disposition is not AnalystDisposition.REVIEW
        or unsupported.disposition is not AnalystDisposition.INSUFFICIENT_DATA
        or supported != build_analyst_report(
            analysis_input,
            supported.claims,
            policy,
        )
    ):
        raise RuntimeError("P6-001 analyst contract runtime gate failed")

    print(
        "OK: P6 analyst contracts; "
        "supported=NO_TRADE uncertainty=REVIEW unsupported=INSUFFICIENT_DATA "
        "replay_equal=true "
        f"policy_sha256={policy.policy_sha256} "
        f"input_sha256={analysis_input.input_sha256} "
        f"report_sha256={supported.report_sha256}"
    )
    print(
        "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
        "INSUFFICIENT_EVIDENCE preserved | No credentials | No external transport | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No exchange order | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
