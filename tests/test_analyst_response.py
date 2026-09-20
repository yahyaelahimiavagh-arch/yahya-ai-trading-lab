import inspect
import json
import unittest
from dataclasses import FrozenInstanceError

from yatl.analyst import AnalystDisposition, AnalystReason, EvidenceLayer
from yatl.analyst.evidence import build_evidence_bundle, build_layer_evidence
from yatl.analyst.request import build_model_request
from yatl.analyst.response import (
    MAX_MODEL_RESPONSE_BYTES,
    MODEL_RESPONSE_SCHEMA_VERSION,
    ModelResponseBoundaryError,
    ModelResponseCode,
    validate_model_response,
)


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


def request(symbol="BTCUSDT"):
    return build_model_request(bundle(symbol))


def accepted_payload():
    return {
        "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
        "claims": [
            {
                "claim_id": "MODEL_FACT_MARKET",
                "kind": "FACT",
                "text": "Accepted public market evidence is present.",
                "evidence_ids": ["E_P1_MARKET"],
            },
            {
                "claim_id": "MODEL_UNCERTAINTY_STRATEGY",
                "kind": "UNCERTAINTY",
                "text": "Strategy evidence remains insufficient for a qualified conclusion.",
                "evidence_ids": ["E_P3_STRATEGY"],
            },
        ],
    }


class ModelResponseSchemaTests(unittest.TestCase):
    def test_valid_response_is_accepted_and_canonicalized(self):
        raw = json.dumps(accepted_payload(), indent=2)
        result = validate_model_response(request(), raw)
        self.assertTrue(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.ACCEPTED)
        self.assertEqual(result.report.disposition, AnalystDisposition.REVIEW)
        self.assertEqual(result.report.reason, AnalystReason.UNCERTAINTY_PRESENT)
        self.assertEqual(
            result.canonical_response_json,
            canonical(accepted_payload()),
        )

    def test_accepted_replay_is_stable(self):
        raw = canonical(accepted_payload())
        first = validate_model_response(request(), raw)
        second = validate_model_response(request(), raw)
        self.assertEqual(first, second)
        self.assertEqual(first.validation_sha256, second.validation_sha256)
        self.assertEqual(
            first.canonical_response_sha256,
            second.canonical_response_sha256,
        )

    def test_validation_result_is_frozen(self):
        result = validate_model_response(request(), canonical(accepted_payload()))
        with self.assertRaises(FrozenInstanceError):
            result.accepted = False

    def test_raw_rejected_text_is_not_retained(self):
        secret_marker = "this-content-must-not-be-retained"
        raw = canonical(
            {
                "schema_version": 1,
                "claims": [],
                "credential": secret_marker,
            }
        )
        result = validate_model_response(request(), raw)
        self.assertFalse(result.accepted)
        encoded = canonical(result.as_record())
        self.assertNotIn(secret_marker, encoded)
        self.assertIsNone(result.canonical_response_json)

    def test_non_string_fails_closed(self):
        result = validate_model_response(request(), {"claims": []})
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.RESPONSE_TYPE)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_empty_response_fails_closed(self):
        result = validate_model_response(request(), "")
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.RESPONSE_TOO_LARGE)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_oversized_response_fails_closed(self):
        raw = "x" * (MAX_MODEL_RESPONSE_BYTES + 1)
        result = validate_model_response(request(), raw)
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.RESPONSE_TOO_LARGE)

    def test_malformed_json_fails_closed(self):
        result = validate_model_response(request(), '{"schema_version":1')
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.MALFORMED_JSON)

    def test_duplicate_json_key_fails_closed(self):
        raw = '{"schema_version":1,"schema_version":1,"claims":[]}'
        result = validate_model_response(request(), raw)
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.DUPLICATE_JSON_KEY)

    def test_unknown_top_level_field_is_rejected(self):
        payload = accepted_payload()
        payload["extra"] = "smuggled"
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_unknown_claim_field_is_rejected(self):
        payload = accepted_payload()
        payload["claims"][0]["extra"] = "smuggled"
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_forbidden_structured_fields_matrix(self):
        for field, value in (
            ("action", "BUY"),
            ("command", "submit"),
            ("quantity", "0.25"),
            ("amount", "100"),
            ("endpoint_url", "example.invalid"),
            ("credentials", "redacted"),
            ("api_key", "redacted"),
            ("risk_authorization", "grant"),
            ("trade_permission", True),
        ):
            with self.subTest(field=field):
                payload = accepted_payload()
                payload[field] = value
                result = validate_model_response(request(), canonical(payload))
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, ModelResponseCode.FORBIDDEN_CONTENT)
                self.assertEqual(
                    result.report.disposition,
                    AnalystDisposition.INSUFFICIENT_DATA,
                )

    def test_forbidden_text_matrix(self):
        for text in (
            "Review https://example.invalid for details.",
            "Visit www.example.invalid for details.",
            "Use api key: example-secret.",
            "Use bearer token before analysis.",
            "Buy 0.25 BTC now.",
            "Sell order now.",
            "Place an order now.",
            "Quantity: 0.25",
            "Action: BUY",
        ):
            with self.subTest(text=text):
                payload = accepted_payload()
                payload["claims"][1]["text"] = text
                result = validate_model_response(request(), canonical(payload))
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, ModelResponseCode.FORBIDDEN_CONTENT)

    def test_unsupported_claim_kind_is_rejected(self):
        payload = accepted_payload()
        payload["claims"][1]["kind"] = "UNSUPPORTED"
        payload["claims"][1]["evidence_ids"] = []
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_unknown_claim_kind_is_rejected(self):
        payload = accepted_payload()
        payload["claims"][1]["kind"] = "CERTAIN"
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_missing_uncertainty_fails_closed(self):
        payload = accepted_payload()
        payload["claims"] = payload["claims"][:1]
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_claims_must_be_ordered_and_unique(self):
        payload = accepted_payload()
        payload["claims"] = list(reversed(payload["claims"]))
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

        payload = accepted_payload()
        payload["claims"].append(dict(payload["claims"][0]))
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_evidence_ids_must_be_list(self):
        payload = accepted_payload()
        payload["claims"][0]["evidence_ids"] = "E_P1_MARKET"
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.SCHEMA_REJECTED)

    def test_invented_evidence_reference_fails_closed(self):
        payload = accepted_payload()
        payload["claims"][1]["evidence_ids"] = ["E_NOT_ACCEPTED"]
        result = validate_model_response(request(), canonical(payload))
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, ModelResponseCode.CONTRACT_REJECTED)
        self.assertEqual(result.report.disposition, AnalystDisposition.INSUFFICIENT_DATA)

    def test_validated_output_contains_no_executable_authority(self):
        result = validate_model_response(request(), canonical(accepted_payload()))
        encoded = canonical(result.as_record())
        for forbidden_key in (
            '"action":',
            '"command":',
            '"quantity":',
            '"order":',
            '"endpoint_url":',
            '"credentials":',
            '"risk_authorization":',
            '"trade_permission":true',
        ):
            with self.subTest(forbidden_key=forbidden_key):
                self.assertNotIn(forbidden_key, encoded)

    def test_both_supported_symbols_replay(self):
        raw = canonical(accepted_payload())
        for symbol in ("BTCUSDT", "ETHUSDT"):
            with self.subTest(symbol=symbol):
                first = validate_model_response(request(symbol), raw)
                second = validate_model_response(request(symbol), raw)
                self.assertTrue(first.accepted)
                self.assertEqual(first.validation_sha256, second.validation_sha256)

    def test_invalid_request_is_trusted_caller_error(self):
        with self.assertRaises(ModelResponseBoundaryError):
            validate_model_response("not-a-request", canonical(accepted_payload()))

    def test_source_has_no_transport_provider_environment_or_execution_access(self):
        import yatl.analyst.response as response_module

        source = inspect.getsource(response_module)
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
