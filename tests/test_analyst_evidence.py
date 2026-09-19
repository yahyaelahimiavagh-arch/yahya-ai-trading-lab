import inspect
import unittest
from dataclasses import FrozenInstanceError, replace

from yatl.analyst import EvidenceLayer, StrategyEvidenceState
from yatl.analyst.evidence import (
    EvidenceBundleError,
    LayerEvidence,
    PointInTimeEvidenceBundle,
    build_evidence_bundle,
    build_layer_evidence,
)


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000
P3_INDEX = "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a"
P4_INDEX = "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783"
P4_POLICY = "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7"
P5_INDEX = "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa"
P5_POLICY = "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72"


def p1_payload():
    return {
        "accepted": True,
        "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
        "latest_closed_at_ms": DECISION_TIME - 5_000,
        "manifest_sha256": "a" * 64,
    }


def p3_payload():
    return {
        "accepted": True,
        "candidate_matrix_sha256": P3_INDEX,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }


def p4_payload():
    return {
        "accepted": True,
        "audit_sha256": P4_INDEX,
        "policy_sha256": P4_POLICY,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "risk_status": "PASS",
    }


def p5_payload():
    return {
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
    }


def material(evidence_id, layer, offset, payload, *, symbol="BTCUSDT",
             valid_through=VALID_THROUGH):
    return build_layer_evidence(
        evidence_id,
        layer,
        symbol,
        DECISION_TIME + offset,
        valid_through,
        payload,
    )


def materials():
    return (
        material("E_P1_MARKET", EvidenceLayer.P1_PUBLIC_MARKET, -4_000, p1_payload()),
        material(
            "E_P3_STRATEGY",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            -3_000,
            p3_payload(),
        ),
        material("E_P4_RISK", EvidenceLayer.P4_RISK_STATUS, -2_000, p4_payload()),
        material(
            "E_P5_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            -1_000,
            p5_payload(),
        ),
    )


class PointInTimeEvidenceTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_canonical(self):
        first = build_evidence_bundle("BTCUSDT", DECISION_TIME, materials())
        second = build_evidence_bundle("BTCUSDT", DECISION_TIME, materials())
        self.assertEqual(first, second)
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
        self.assertEqual(len(first.bundle_sha256), 64)
        self.assertEqual(first.as_record(), second.as_record())

    def test_bundle_maps_exactly_to_analysis_input(self):
        bundle = build_evidence_bundle("BTCUSDT", DECISION_TIME, materials())
        analysis_input = bundle.analyst_input
        self.assertEqual(analysis_input.symbol, "BTCUSDT")
        self.assertEqual(analysis_input.decision_time_ms, DECISION_TIME)
        self.assertEqual(
            analysis_input.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            tuple(item.evidence_id for item in analysis_input.evidence),
            ("E_P1_MARKET", "E_P3_STRATEGY", "E_P4_RISK", "E_P5_SAFETY"),
        )

    def test_material_is_frozen_and_digest_bound(self):
        item = materials()[0]
        with self.assertRaises(FrozenInstanceError):
            item.symbol = "ETHUSDT"
        with self.assertRaises(EvidenceBundleError):
            replace(item, source_sha256="0" * 64)
        with self.assertRaises(EvidenceBundleError):
            replace(item, provenance_sha256="0" * 64)

    def test_payload_tamper_fails_digest_check(self):
        item = materials()[0]
        tampered = item.canonical_payload.replace('"accepted":true', '"accepted":false')
        with self.assertRaises(EvidenceBundleError):
            LayerEvidence(
                item.evidence_id,
                item.layer,
                item.symbol,
                item.observed_at_ms,
                item.valid_through_ms,
                tampered,
                item.source_sha256,
                item.provenance_sha256,
            )

    def test_noncanonical_and_duplicate_json_keys_fail_closed(self):
        item = materials()[0]
        noncanonical = item.canonical_payload.replace(",", ", ")
        with self.assertRaises(EvidenceBundleError):
            LayerEvidence(
                item.evidence_id,
                item.layer,
                item.symbol,
                item.observed_at_ms,
                item.valid_through_ms,
                noncanonical,
                item.source_sha256,
                item.provenance_sha256,
            )
        duplicate = '{"accepted":true,"accepted":true}'
        with self.assertRaises(EvidenceBundleError):
            LayerEvidence(
                "E_DUP_JSON",
                EvidenceLayer.P1_PUBLIC_MARKET,
                "BTCUSDT",
                DECISION_TIME - 1,
                VALID_THROUGH,
                duplicate,
                "0" * 64,
                "0" * 64,
            )

    def test_future_evidence_fails_closed(self):
        bad = list(materials())
        bad[0] = material(
            "E_P1_MARKET",
            EvidenceLayer.P1_PUBLIC_MARKET,
            1,
            p1_payload(),
            valid_through=DECISION_TIME + 60_000,
        )
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, tuple(bad))

    def test_stale_evidence_fails_closed(self):
        bad = list(materials())
        bad[3] = material(
            "E_P5_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            -2_000,
            p5_payload(),
            valid_through=DECISION_TIME - 1,
        )
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, tuple(bad))

    def test_cross_symbol_evidence_fails_closed(self):
        bad = list(materials())
        bad[2] = material(
            "E_P4_RISK",
            EvidenceLayer.P4_RISK_STATUS,
            -2_000,
            p4_payload(),
            symbol="ETHUSDT",
        )
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, tuple(bad))

    def test_missing_layer_fails_closed(self):
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, materials()[:-1])

    def test_duplicate_id_fails_closed(self):
        bad = list(materials())
        bad[1] = material(
            "E_P1_MARKET",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            -3_000,
            p3_payload(),
        )
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, tuple(bad))

    def test_duplicate_layer_fails_closed(self):
        bad = list(materials())
        bad[3] = material(
            "E_P5_SAFETY",
            EvidenceLayer.P4_RISK_STATUS,
            -1_000,
            p4_payload(),
        )
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle("BTCUSDT", DECISION_TIME, tuple(bad))

    def test_unordered_material_fails_closed(self):
        with self.assertRaises(EvidenceBundleError):
            build_evidence_bundle(
                "BTCUSDT", DECISION_TIME, tuple(reversed(materials()))
            )

    def test_p3_label_cannot_be_upgraded(self):
        payload = p3_payload()
        payload["strategy_evidence"] = "QUALIFIED_FOR_P4_RESEARCH"
        with self.assertRaises(EvidenceBundleError):
            material(
                "E_P3_STRATEGY",
                EvidenceLayer.P3_STRATEGY_EVIDENCE,
                -3_000,
                payload,
            )

    def test_p4_cannot_grant_authority(self):
        for field in ("risk_authorization_mutation", "quantity_authority"):
            payload = p4_payload()
            payload[field] = True
            with self.subTest(field=field), self.assertRaises(EvidenceBundleError):
                material(
                    "E_P4_RISK",
                    EvidenceLayer.P4_RISK_STATUS,
                    -2_000,
                    payload,
                )

    def test_p5_cannot_open_safety_boundaries(self):
        for field in (
            "trade_permission",
            "order_endpoints",
            "ai_direct_execution",
            "credentials_present",
            "private_payload_present",
        ):
            payload = p5_payload()
            payload[field] = True
            with self.subTest(field=field), self.assertRaises(EvidenceBundleError):
                material(
                    "E_P5_SAFETY",
                    EvidenceLayer.P5_SAFETY_STATUS,
                    -1_000,
                    payload,
                )

    def test_unknown_payload_fields_fail_closed(self):
        payload = p5_payload()
        payload["account_id"] = "private"
        with self.assertRaises(EvidenceBundleError):
            material(
                "E_P5_SAFETY",
                EvidenceLayer.P5_SAFETY_STATUS,
                -1_000,
                payload,
            )

    def test_p1_future_market_close_is_rejected(self):
        payload = p1_payload()
        payload["latest_closed_at_ms"] = DECISION_TIME + 1
        with self.assertRaises(EvidenceBundleError):
            material(
                "E_P1_MARKET",
                EvidenceLayer.P1_PUBLIC_MARKET,
                2,
                payload,
            )

    def test_bundle_contains_no_execution_or_secret_capability(self):
        import yatl.analyst.evidence as evidence_module

        source = inspect.getsource(evidence_module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "RiskAuthorization",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "API_KEY",
            "API_SECRET",
            "os.getenv",
            "os.environ",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
