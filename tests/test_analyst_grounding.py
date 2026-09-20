import inspect
import json
import unittest
from dataclasses import FrozenInstanceError

from yatl.analyst import AnalystDisposition, EvidenceLayer
from yatl.analyst.evidence import build_evidence_bundle, build_layer_evidence
from yatl.analyst.grounding import (
    GroundingBoundaryError,
    GroundingCode,
    GroundingValidation,
    ground_model_response,
)
from yatl.analyst.request import build_model_request
from yatl.analyst.response import validate_model_response


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000
P3_INDEX = "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a"
P4_INDEX = "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783"
P4_POLICY = "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7"
P5_INDEX = "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa"
P5_POLICY = "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72"


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


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


def response_payload(claims):
    return canonical(
        {
            "schema_version": 1,
            "claims": claims,
        }
    )


def grounded_claims():
    return [
        {
            "claim_id": "MODEL_FACT_MARKET",
            "kind": "FACT",
            "text": "Accepted public market evidence is present.",
            "evidence_ids": ["E_P1_MARKET"],
        },
        {
            "claim_id": "MODEL_FACT_RISK",
            "kind": "FACT",
            "text": "Accepted risk status is PASS and grants no mutable or quantity authority.",
            "evidence_ids": ["E_P4_RISK"],
        },
        {
            "claim_id": "MODEL_FACT_SAFETY",
            "kind": "FACT",
            "text": "Accepted safety status preserves PAPER ONLY and no trade or AI execution authority.",
            "evidence_ids": ["E_P5_SAFETY"],
        },
        {
            "claim_id": "MODEL_OBSERVATION_STRATEGY",
            "kind": "DERIVED_OBSERVATION",
            "text": "Strategy evidence remains INSUFFICIENT_EVIDENCE.",
            "evidence_ids": ["E_P3_STRATEGY"],
        },
        {
            "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
            "kind": "UNCERTAINTY",
            "text": "Strategy evidence remains insufficient for a qualified conclusion.",
            "evidence_ids": ["E_P3_STRATEGY"],
        },
    ]


def validated(claims=None, symbol="BTCUSDT"):
    req = build_model_request(bundle(symbol))
    raw = response_payload(grounded_claims() if claims is None else claims)
    return validate_model_response(req, raw)


class ClaimEvidenceGroundingTests(unittest.TestCase):
    def test_exact_grounded_response_passes(self):
        result = ground_model_response(validated())
        self.assertTrue(result.accepted)
        self.assertEqual(result.code, GroundingCode.GROUNDED)
        self.assertEqual(result.report.disposition, AnalystDisposition.REVIEW)
        self.assertEqual(
            result.grounded_claim_ids,
            tuple(claim["claim_id"] for claim in grounded_claims()),
        )

    def test_grounded_replay_is_stable(self):
        first = ground_model_response(validated())
        second = ground_model_response(validated())
        self.assertEqual(first, second)
        self.assertEqual(first.grounding_sha256, second.grounding_sha256)

    def test_result_is_frozen(self):
        result = ground_model_response(validated())
        with self.assertRaises(FrozenInstanceError):
            result.accepted = False

    def test_unknown_claim_fails_closed(self):
        claims = grounded_claims()
        claims.insert(
            4,
            {
                "claim_id": "MODEL_UNKNOWN_FACT",
                "kind": "FACT",
                "text": "A new unsupported fact is asserted.",
                "evidence_ids": ["E_P1_MARKET"],
            },
        )
        result = ground_model_response(validated(claims))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.UNSUPPORTED_CLAIM)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_wrong_exact_text_fails_closed(self):
        claims = grounded_claims()
        claims[0]["text"] = "Public market evidence appears available."
        result = ground_model_response(validated(claims))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.CLAIM_SHAPE_MISMATCH)

    def test_wrong_kind_fails_closed(self):
        claims = grounded_claims()
        claims[0]["kind"] = "DERIVED_OBSERVATION"
        result = ground_model_response(validated(claims))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.CLAIM_SHAPE_MISMATCH)

    def test_multiple_evidence_ids_fail_closed(self):
        claims = grounded_claims()
        claims[0]["evidence_ids"] = ["E_P1_MARKET", "E_P4_RISK"]
        result = ground_model_response(validated(claims))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.CLAIM_SHAPE_MISMATCH)

    def test_wrong_evidence_layer_fails_closed(self):
        claims = grounded_claims()
        claims[0]["evidence_ids"] = ["E_P4_RISK"]
        result = ground_model_response(validated(claims))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.EVIDENCE_REFERENCE_MISMATCH)

    def test_contradiction_matrix_fails_closed(self):
        for text in (
            "Strategy evidence is sufficient for a qualified conclusion.",
            "Strategy evidence is QUALIFIED_FOR_P4_RESEARCH.",
            "Accepted risk status grants quantity authority.",
            "Accepted risk status allows RiskAuthorization mutation.",
            "Accepted safety status permits trade execution.",
            "Accepted safety status permits AI direct execution.",
            "LIVE_MASTER_LOCK is ON.",
        ):
            with self.subTest(text=text):
                claims = grounded_claims()
                claims[3]["text"] = text
                result = ground_model_response(validated(claims))
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, GroundingCode.CONTRADICTION)
                self.assertEqual(
                    result.report.disposition,
                    AnalystDisposition.INSUFFICIENT_DATA,
                )

    def test_invented_evidence_fails_closed_upstream(self):
        claims = grounded_claims()
        claims[-1]["evidence_ids"] = ["E_NOT_ACCEPTED"]
        upstream = validated(claims)
        self.assertFalse(upstream.accepted)
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.UPSTREAM_REJECTED)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_upstream_schema_rejection_stays_fail_closed(self):
        req = build_model_request(bundle())
        upstream = validate_model_response(req, '{"schema_version":1')
        self.assertFalse(upstream.accepted)
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, GroundingCode.UPSTREAM_REJECTED)

    def test_stale_evidence_mutation_is_detected(self):
        upstream = validated()
        target = next(
            item
            for item in upstream.request.bundle.evidence
            if item.evidence_id == "E_P3_STRATEGY"
        )
        object.__setattr__(target, "valid_through_ms", DECISION_TIME - 1)
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertIn(
            result.code,
            (
                GroundingCode.INPUT_BINDING_MISMATCH,
                GroundingCode.EVIDENCE_STATE_INVALID,
            ),
        )

    def test_future_evidence_mutation_is_detected(self):
        upstream = validated()
        target = next(
            item
            for item in upstream.request.bundle.evidence
            if item.evidence_id == "E_P1_MARKET"
        )
        object.__setattr__(target, "observed_at_ms", DECISION_TIME + 1)
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertIn(
            result.code,
            (
                GroundingCode.INPUT_BINDING_MISMATCH,
                GroundingCode.EVIDENCE_STATE_INVALID,
            ),
        )

    def test_symbol_mutation_is_detected(self):
        upstream = validated()
        target = next(
            item
            for item in upstream.request.bundle.evidence
            if item.evidence_id == "E_P1_MARKET"
        )
        object.__setattr__(target, "symbol", "ETHUSDT")
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertIn(
            result.code,
            (
                GroundingCode.INPUT_BINDING_MISMATCH,
                GroundingCode.EVIDENCE_REFERENCE_MISMATCH,
                GroundingCode.EVIDENCE_STATE_INVALID,
            ),
        )

    def test_source_digest_mutation_is_detected(self):
        upstream = validated()
        target = next(
            item
            for item in upstream.request.bundle.evidence
            if item.evidence_id == "E_P1_MARKET"
        )
        object.__setattr__(target, "source_sha256", "b" * 64)
        result = ground_model_response(upstream)
        self.assertFalse(result.accepted)
        self.assertIn(
            result.code,
            (
                GroundingCode.INPUT_BINDING_MISMATCH,
                GroundingCode.EVIDENCE_REFERENCE_MISMATCH,
            ),
        )

    def test_forged_grounding_result_is_rejected(self):
        upstream = validated()
        correct = ground_model_response(upstream)
        with self.assertRaises(GroundingBoundaryError):
            GroundingValidation(
                upstream,
                False,
                GroundingCode.UNSUPPORTED_CLAIM,
                correct.report,
                (),
            )

    def test_invalid_caller_type_raises(self):
        with self.assertRaises(GroundingBoundaryError):
            ground_model_response("not-a-validation")

    def test_grounding_record_retains_no_raw_response_text(self):
        result = ground_model_response(validated())
        encoded = canonical(result.as_record())
        self.assertNotIn("raw_response", encoded)
        self.assertIn("response_validation_sha256", encoded)

    def test_both_supported_symbols_replay(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            with self.subTest(symbol=symbol):
                first = ground_model_response(validated(symbol=symbol))
                second = ground_model_response(validated(symbol=symbol))
                self.assertTrue(first.accepted)
                self.assertEqual(first.grounding_sha256, second.grounding_sha256)

    def test_output_contains_no_executable_authority(self):
        encoded = canonical(ground_model_response(validated()).as_record())
        for forbidden_key in (
            '"approved_quantity":',
            '"execution_action":',
            '"order_request":',
            '"risk_authorization":',
            '"trade_permission":true',
            '"order_endpoints":true',
            '"ai_direct_execution":true',
        ):
            with self.subTest(forbidden_key=forbidden_key):
                self.assertNotIn(forbidden_key, encoded)

    def test_source_has_no_transport_provider_environment_or_execution_access(self):
        import yatl.analyst.grounding as grounding_module

        source = inspect.getsource(grounding_module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "urllib",
            "http.client",
            "websockets",
            "socket",
            "os.getenv",
            "os.environ",
            "subprocess",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
