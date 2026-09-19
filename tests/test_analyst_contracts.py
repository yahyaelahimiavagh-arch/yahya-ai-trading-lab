import inspect
import unittest
from dataclasses import FrozenInstanceError, replace

from yatl.analyst import (
    ANALYST_POLICY_ID,
    AnalystClaim,
    AnalystContractError,
    AnalystDisposition,
    AnalystInput,
    AnalystPolicy,
    AnalystReason,
    AnalystReport,
    ClaimKind,
    EvidenceLayer,
    EvidenceReference,
    StrategyEvidenceState,
    build_analyst_report,
)


DECISION_TIME = 1_700_000_000_000


def evidence():
    return (
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


def analyst_input():
    return AnalystInput(
        "BTCUSDT",
        DECISION_TIME,
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        evidence(),
    )


class AnalystContractTests(unittest.TestCase):
    def test_frozen_policy_is_analysis_only(self):
        policy = AnalystPolicy()
        self.assertEqual(policy.policy_id, ANALYST_POLICY_ID)
        self.assertEqual(policy.mode, "ANALYSIS_ONLY")
        self.assertTrue(policy.paper_only)
        self.assertEqual(policy.live_master_lock, "OFF")
        for field in (
            "allow_external_transport",
            "allow_credentials",
            "allow_execution_import",
            "allow_trade_permission",
            "allow_order_endpoint",
            "allow_quantity_authority",
            "allow_risk_authorization_mutation",
            "allow_ai_direct_execution",
        ):
            self.assertFalse(getattr(policy, field))

    def test_policy_cannot_be_weakened(self):
        with self.assertRaises(AnalystContractError):
            AnalystPolicy(allow_trade_permission=True)
        with self.assertRaises(AnalystContractError):
            AnalystPolicy(allow_ai_direct_execution=True)
        with self.assertRaises(AnalystContractError):
            AnalystPolicy(allow_execution_import=True)

    def test_policy_is_immutable_and_digest_is_deterministic(self):
        policy = AnalystPolicy()
        replay = AnalystPolicy()
        self.assertEqual(policy.policy_sha256, replay.policy_sha256)
        self.assertEqual(len(policy.policy_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            policy.mode = "EXECUTION"

    def test_evidence_reference_requires_exact_identity(self):
        item = evidence()[0]
        self.assertEqual(item.symbol, "BTCUSDT")
        with self.assertRaises(AnalystContractError):
            replace(item, source_sha256="not-a-digest")
        with self.assertRaises(AnalystContractError):
            replace(item, evidence_id="bad id")
        with self.assertRaises(AnalystContractError):
            replace(item, symbol="SOLUSDT")

    def test_input_rejects_duplicate_unordered_future_and_cross_symbol_evidence(self):
        items = evidence()
        cases = (
            (items[0], items[0]),
            tuple(reversed(items)),
            (
                items[0],
                items[1],
                items[2],
                replace(items[3], observed_at_ms=DECISION_TIME + 1),
            ),
            (
                items[0],
                items[1],
                items[2],
                replace(items[3], symbol="ETHUSDT"),
            ),
        )
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(AnalystContractError):
                AnalystInput(
                    "BTCUSDT",
                    DECISION_TIME,
                    StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
                    bad,
                )

    def test_input_digest_is_canonical_and_reconstructable(self):
        first = analyst_input()
        second = AnalystInput(
            first.symbol,
            first.decision_time_ms,
            first.strategy_evidence,
            first.evidence,
            first.paper_only,
            first.live_master_lock,
            first.spot_only,
            first.allow_short,
            first.allow_leverage,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.input_sha256, second.input_sha256)
        self.assertEqual(len(first.input_sha256), 64)

    def test_fact_and_observation_require_evidence(self):
        for kind in (ClaimKind.FACT, ClaimKind.DERIVED_OBSERVATION):
            with self.subTest(kind=kind), self.assertRaises(AnalystContractError):
                AnalystClaim("CLAIM_ONE", kind, "Bounded statement")

    def test_unsupported_claim_cannot_pretend_to_have_evidence(self):
        with self.assertRaises(AnalystContractError):
            AnalystClaim(
                "CLAIM_BAD",
                ClaimKind.UNSUPPORTED,
                "Unsupported statement",
                ("E_MARKET",),
            )

    def test_claim_text_and_reference_order_are_bounded(self):
        with self.assertRaises(AnalystContractError):
            AnalystClaim(
                "CLAIM_TEXT",
                ClaimKind.FACT,
                " contains padding ",
                ("E_MARKET",),
            )
        with self.assertRaises(AnalystContractError):
            AnalystClaim(
                "CLAIM_TEXT",
                ClaimKind.FACT,
                "Line one\nLine two",
                ("E_MARKET",),
            )
        with self.assertRaises(AnalystContractError):
            AnalystClaim(
                "CLAIM_ORDER",
                ClaimKind.FACT,
                "Ordered evidence required",
                ("E_STRATEGY", "E_MARKET"),
            )

    def test_supported_analysis_can_only_end_in_no_trade(self):
        claims = (
            AnalystClaim(
                "CLAIM_FACT",
                ClaimKind.FACT,
                "Public market evidence is available.",
                ("E_MARKET",),
            ),
            AnalystClaim(
                "CLAIM_OBSERVATION",
                ClaimKind.DERIVED_OBSERVATION,
                "Strategy evidence is not qualified.",
                ("E_STRATEGY",),
            ),
        )
        report = build_analyst_report(analyst_input(), claims)
        self.assertEqual(report.disposition, AnalystDisposition.NO_TRADE)
        self.assertEqual(report.reason, AnalystReason.ANALYSIS_ONLY)

    def test_uncertainty_routes_to_review_without_execution_authority(self):
        claims = (
            AnalystClaim(
                "CLAIM_FACT",
                ClaimKind.FACT,
                "Safety evidence is present.",
                ("E_SAFETY",),
            ),
            AnalystClaim(
                "CLAIM_UNCERTAINTY",
                ClaimKind.UNCERTAINTY,
                "The available evidence does not resolve the research question.",
                ("E_STRATEGY",),
            ),
        )
        report = build_analyst_report(analyst_input(), claims)
        self.assertEqual(report.disposition, AnalystDisposition.REVIEW)
        self.assertEqual(report.reason, AnalystReason.UNCERTAINTY_PRESENT)

    def test_unsupported_claim_routes_to_insufficient_data(self):
        report = build_analyst_report(
            analyst_input(),
            (
                AnalystClaim(
                    "CLAIM_UNSUPPORTED",
                    ClaimKind.UNSUPPORTED,
                    "This statement has no accepted evidence.",
                ),
            ),
        )
        self.assertEqual(report.disposition, AnalystDisposition.INSUFFICIENT_DATA)
        self.assertEqual(report.reason, AnalystReason.UNSUPPORTED_CLAIMS)

    def test_empty_analysis_routes_to_insufficient_data(self):
        report = build_analyst_report(analyst_input())
        self.assertEqual(report.disposition, AnalystDisposition.INSUFFICIENT_DATA)
        self.assertEqual(report.reason, AnalystReason.NO_USABLE_CLAIMS)

    def test_unknown_evidence_reference_fails_closed(self):
        claims = (
            AnalystClaim(
                "CLAIM_UNKNOWN",
                ClaimKind.FACT,
                "Unknown evidence must be rejected.",
                ("E_UNKNOWN",),
            ),
        )
        with self.assertRaises(AnalystContractError):
            build_analyst_report(analyst_input(), claims)

    def test_duplicate_or_unordered_claims_fail_closed(self):
        fact = AnalystClaim(
            "CLAIM_FACT",
            ClaimKind.FACT,
            "Public evidence is available.",
            ("E_MARKET",),
        )
        observation = AnalystClaim(
            "CLAIM_OBSERVATION",
            ClaimKind.DERIVED_OBSERVATION,
            "Evidence remains research-only.",
            ("E_STRATEGY",),
        )
        with self.assertRaises(AnalystContractError):
            build_analyst_report(analyst_input(), (fact, fact))
        with self.assertRaises(AnalystContractError):
            build_analyst_report(analyst_input(), (observation, fact))

    def test_report_cannot_override_deterministic_disposition(self):
        claim = AnalystClaim(
            "CLAIM_FACT",
            ClaimKind.FACT,
            "Public evidence is available.",
            ("E_MARKET",),
        )
        with self.assertRaises(AnalystContractError):
            AnalystReport(
                analyst_input(),
                (claim,),
                AnalystDisposition.REVIEW,
                AnalystReason.UNCERTAINTY_PRESENT,
            )

    def test_report_digest_is_deterministic_and_contains_no_action_or_quantity(self):
        claims = (
            AnalystClaim(
                "CLAIM_FACT",
                ClaimKind.FACT,
                "Public evidence is available.",
                ("E_MARKET",),
            ),
        )
        first = build_analyst_report(analyst_input(), claims)
        second = build_analyst_report(analyst_input(), claims)
        self.assertEqual(first, second)
        self.assertEqual(first.report_sha256, second.report_sha256)
        record = first.as_record()
        self.assertNotIn("action", record)
        self.assertNotIn("quantity", record)
        self.assertNotIn("authorization", record)

    def test_analyst_package_has_no_execution_network_or_secret_import(self):
        import yatl.analyst.contracts as contracts

        source = inspect.getsource(contracts)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "urllib",
            "http.client",
            "requests",
            "websockets",
            "socket",
            "API_KEY",
            "API_SECRET",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
