import inspect
import json
import unittest
from dataclasses import FrozenInstanceError

from yatl.analyst import (
    AnalystClaim,
    AnalystDisposition,
    AnalystReason,
    ClaimKind,
    EvidenceLayer,
    StrategyEvidenceState,
    build_analyst_report,
)
from yatl.analyst.baseline import (
    BASELINE_ID,
    DeterministicBaselineAnalysis,
    DeterministicBaselineError,
    build_deterministic_baseline,
)
from yatl.analyst.evidence import build_evidence_bundle, build_layer_evidence


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000
P3_INDEX = "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a"
P4_INDEX = "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783"
P4_POLICY = "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7"
P5_INDEX = "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa"
P5_POLICY = "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72"


def bundle(symbol="BTCUSDT"):
    evidence = (
        build_layer_evidence(
            "E_P1_MARKET",
            EvidenceLayer.P1_PUBLIC_MARKET,
            symbol,
            DECISION_TIME - 4_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
                "latest_closed_at_ms": DECISION_TIME - 5_000,
                "manifest_sha256": "a" * 64,
            },
        ),
        build_layer_evidence(
            "E_P3_STRATEGY",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            symbol,
            DECISION_TIME - 3_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "candidate_matrix_sha256": P3_INDEX,
                "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            },
        ),
        build_layer_evidence(
            "E_P4_RISK",
            EvidenceLayer.P4_RISK_STATUS,
            symbol,
            DECISION_TIME - 2_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "audit_sha256": P4_INDEX,
                "policy_sha256": P4_POLICY,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "risk_status": "PASS",
            },
        ),
        build_layer_evidence(
            "E_P5_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            symbol,
            DECISION_TIME - 1_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "ai_direct_execution": False,
                "audit_sha256": P5_INDEX,
                "credentials_present": False,
                "live_master_lock": "OFF",
                "order_endpoints": False,
                "paper_only": True,
                "policy_sha256": P5_POLICY,
                "private_payload_present": False,
                "safety_status": "PASS",
                "trade_permission": False,
            },
        ),
    )
    return build_evidence_bundle(symbol, DECISION_TIME, evidence)


class DeterministicAnalystBaselineTests(unittest.TestCase):
    def test_replay_is_byte_stable(self):
        first = build_deterministic_baseline(bundle())
        second = build_deterministic_baseline(bundle())
        self.assertEqual(first, second)
        self.assertEqual(first.as_record(), second.as_record())
        self.assertEqual(first.baseline_sha256, second.baseline_sha256)

    def test_baseline_is_frozen(self):
        result = build_deterministic_baseline(bundle())
        with self.assertRaises(FrozenInstanceError):
            result.baseline_id = "CHANGED"

    def test_baseline_identity_is_fixed(self):
        result = build_deterministic_baseline(bundle())
        self.assertEqual(result.baseline_id, BASELINE_ID)
        self.assertEqual(len(result.baseline_sha256), 64)

    def test_insufficient_evidence_is_preserved(self):
        result = build_deterministic_baseline(bundle())
        self.assertEqual(
            result.bundle.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            result.report.analysis_input.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            result.as_record()["strategy_evidence"],
            "INSUFFICIENT_EVIDENCE",
        )

    def test_conservative_uncertainty_routes_to_review(self):
        result = build_deterministic_baseline(bundle())
        self.assertEqual(result.report.disposition, AnalystDisposition.REVIEW)
        self.assertEqual(result.report.reason, AnalystReason.UNCERTAINTY_PRESENT)
        uncertainty = tuple(
            claim for claim in result.report.claims
            if claim.kind is ClaimKind.UNCERTAINTY
        )
        self.assertEqual(len(uncertainty), 1)
        self.assertEqual(uncertainty[0].evidence_ids, ("E_P3_STRATEGY",))

    def test_expected_claims_are_exact_and_ordered(self):
        result = build_deterministic_baseline(bundle())
        self.assertEqual(
            tuple(claim.claim_id for claim in result.report.claims),
            (
                "BASELINE_FACT_MARKET",
                "BASELINE_FACT_RISK",
                "BASELINE_FACT_SAFETY",
                "BASELINE_OBSERVATION_STRATEGY",
                "BASELINE_UNCERTAINTY_STRATEGY",
            ),
        )

    def test_all_four_layers_are_grounded(self):
        result = build_deterministic_baseline(bundle())
        referenced = {
            evidence_id
            for claim in result.report.claims
            for evidence_id in claim.evidence_ids
        }
        self.assertEqual(
            referenced,
            {"E_P1_MARKET", "E_P3_STRATEGY", "E_P4_RISK", "E_P5_SAFETY"},
        )

    def test_no_unsupported_claim_is_created(self):
        result = build_deterministic_baseline(bundle())
        self.assertFalse(
            any(claim.kind is ClaimKind.UNSUPPORTED for claim in result.report.claims)
        )

    def test_baseline_has_no_executable_output_fields(self):
        result = build_deterministic_baseline(bundle())
        record = result.as_record()
        encoded = json.dumps(record, sort_keys=True)
        for forbidden_key in (
            '"action":',
            '"approved_quantity":',
            '"order":',
            '"authorization":',
            '"endpoint_url":',
        ):
            with self.subTest(forbidden_key=forbidden_key):
                self.assertNotIn(forbidden_key, encoded)
        policy = record["report"]["policy"]
        self.assertFalse(policy["allow_trade_permission"])
        self.assertFalse(policy["allow_order_endpoint"])
        self.assertFalse(policy["allow_quantity_authority"])
        self.assertFalse(policy["allow_risk_authorization_mutation"])
        self.assertFalse(policy["allow_ai_direct_execution"])

    def test_wrong_input_type_fails_closed(self):
        with self.assertRaises(DeterministicBaselineError):
            build_deterministic_baseline("not-a-bundle")

    def test_forged_supported_report_is_rejected(self):
        accepted = bundle()
        forged = build_analyst_report(
            accepted.analyst_input,
            (
                AnalystClaim(
                    "CLAIM_FORGED",
                    ClaimKind.FACT,
                    "Only a supported fact is present.",
                    ("E_P1_MARKET",),
                ),
            ),
        )
        self.assertEqual(forged.disposition, AnalystDisposition.NO_TRADE)
        with self.assertRaises(DeterministicBaselineError):
            DeterministicBaselineAnalysis(accepted, forged)

    def test_missing_uncertainty_is_rejected_even_if_report_is_valid(self):
        accepted = bundle()
        claims = (
            AnalystClaim(
                "BASELINE_FACT_MARKET",
                ClaimKind.FACT,
                "Accepted public market evidence is available at the decision boundary.",
                ("E_P1_MARKET",),
            ),
        )
        forged = build_analyst_report(accepted.analyst_input, claims)
        with self.assertRaises(DeterministicBaselineError):
            DeterministicBaselineAnalysis(accepted, forged)

    def test_report_digest_is_bound_into_baseline_digest(self):
        result = build_deterministic_baseline(bundle())
        record = result.as_record()
        self.assertEqual(record["report_sha256"], result.report.report_sha256)
        self.assertEqual(record["bundle_sha256"], result.bundle.bundle_sha256)

    def test_both_supported_symbols_replay(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            with self.subTest(symbol=symbol):
                first = build_deterministic_baseline(bundle(symbol))
                second = build_deterministic_baseline(bundle(symbol))
                self.assertEqual(first.baseline_sha256, second.baseline_sha256)
                self.assertEqual(first.report.disposition, AnalystDisposition.REVIEW)

    def test_baseline_source_has_no_execution_network_or_provider_import(self):
        import yatl.analyst.baseline as baseline_module

        source = inspect.getsource(baseline_module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
