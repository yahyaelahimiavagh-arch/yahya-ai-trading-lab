import inspect
import json
import tempfile
import unittest
from pathlib import Path

from research.research_intake import registry as rie


def base_registry():
    return {
        "schema": rie.SCHEMA,
        "schema_version": rie.SCHEMA_VERSION,
        "registry_id": rie.REGISTRY_ID,
        "candidates": [],
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def candidate(candidate_id="RIE-CAND-0001", source_id="RIE-SRC-0001"):
    return {
        "candidate_id": candidate_id,
        "source": {
            "source_id": source_id,
            "tier": "A",
            "type": "PAPER",
            "language": "EN",
            "title": "Example momentum research",
            "uri": "https://example.org/paper",
            "publication_date": "2026-01-01",
            "authors": ["Researcher A"],
            "provenance_notes": ["Performance claims are untrusted."],
        },
        "technique_family": "TIME_SERIES_MOMENTUM",
        "market_universe": ["BTCUSDT", "ETHUSDT"],
        "timeframes": ["1h"],
        "hypothesis": "Positive trailing return predicts positive next-period return.",
        "entry_rules": ["Enter long when trailing 24h return is positive."],
        "exit_rules": ["Exit when trailing 12h return is non-positive."],
        "stop_rules": ["Use a preregistered volatility stop."],
        "sizing_rules": ["Fixed research quantity only."],
        "lookbacks": ["24h entry", "12h exit"],
        "cost_assumptions": ["Fee and adverse slippage must be included."],
        "reported_metrics": [
            {
                "name": "Sharpe",
                "value": "reported by source",
                "period": "source sample",
                "caveat": "Not YATL evidence.",
            }
        ],
        "implementation": {
            "availability": "CODE",
            "uri": "https://example.org/repository",
        },
        "known_limitations": ["External sample may differ from YATL."],
        "leakage_risks": ["Verify point-in-time construction independently."],
        "status": "READY_FOR_TRAIN_SEARCH",
        "duplicate_of": None,
        "strategy_evidence_effect": "NONE",
        "p10_evidence_effect": "NONE",
    }


class RIE001CandidateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "registry.json"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, record):
        self.path.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def test_empty_registry_is_valid_and_isolated(self):
        self.write(base_registry())
        result = rie.validate_registry(self.path)
        self.assertEqual(result["candidate_count"], 0)
        self.assertFalse(result["network_used"])
        self.assertFalse(result["external_performance_trusted"])
        self.assertEqual(result["strategy_evidence_effect"], "NONE")
        self.assertFalse(result["p10_write_allowed"])
        self.assertFalse(result["trade_permission"])
        self.assertTrue(result["p11_locked"])

    def test_candidate_fingerprint_is_deterministic_and_ignores_source_claims(self):
        first = candidate()
        second = candidate()
        second["source"]["title"] = "Different title"
        second["reported_metrics"][0]["value"] = "999"
        self.assertEqual(
            rie.candidate_fingerprint(first),
            rie.candidate_fingerprint(second),
        )

    def test_hidden_duplicate_fails_closed(self):
        record = base_registry()
        first = candidate()
        second = candidate("RIE-CAND-0002", "RIE-SRC-0002")
        record["candidates"] = [first, second]
        self.write(record)
        with self.assertRaises(rie.ResearchIntakeError):
            rie.validate_registry(self.path)

    def test_explicit_duplicate_is_retained_and_linked(self):
        record = base_registry()
        first = candidate()
        second = candidate("RIE-CAND-0002", "RIE-SRC-0002")
        second["status"] = "DUPLICATE"
        second["duplicate_of"] = "RIE-CAND-0001"
        record["candidates"] = [first, second]
        self.write(record)
        result = rie.validate_registry(self.path)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["unique_hypothesis_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)

    def test_search_ready_requires_cost_assumptions(self):
        record = base_registry()
        item = candidate()
        item["cost_assumptions"] = []
        record["candidates"] = [item]
        self.write(record)
        with self.assertRaises(rie.ResearchIntakeError):
            rie.validate_registry(self.path)

    def test_external_research_cannot_create_strategy_or_p10_evidence(self):
        record = base_registry()
        item = candidate()
        item["strategy_evidence_effect"] = "QUALIFIED"
        record["candidates"] = [item]
        self.write(record)
        with self.assertRaises(rie.ResearchIntakeError):
            rie.validate_registry(self.path)

    def test_source_has_no_network_credentials_or_execution_authority(self):
        source = inspect.getsource(rie)
        for forbidden in (
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "urllib.request",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "api_key",
            "api_secret",
            "os.environ",
            "os.getenv",
            "RiskAuthorization",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
