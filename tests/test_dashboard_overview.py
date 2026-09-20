import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from yatl.analytics.cli import _export_payload
from yatl.analytics.quality import run_quality_gate
from yatl.analytics.quality_runtime import SNAPSHOT, _fixture
from yatl.dashboard.loader import LoadedP7Export, load_p7_export
from yatl.dashboard.overview import (
    EXPECTED_CARD_IDS,
    EXPECTED_FIELD_KEYS,
    UNKNOWN_FIELDS,
    UNKNOWN_VALUE,
    DashboardOverviewProjection,
    OverviewProjectionError,
    project_overview,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    material = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DashboardOverviewProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_root = self.root / "source"
        source_root.mkdir()
        _, _, specs = _fixture(source_root)
        gate = run_quality_gate(SNAPSHOT, specs)
        self.record, encoded = _export_payload(gate)
        self.path = self.root / "accepted.json"
        self.path.write_text(encoded, encoding="utf-8")
        self.loaded = load_p7_export(self.path, self.record["export_sha256"])
        self.projection = project_overview(self.loaded)
        self.by_key = {item.field_key: item for item in self.projection.cards}

    def tearDown(self):
        self.temp.cleanup()

    def test_projection_is_deterministic_and_digest_stable(self):
        replay = project_overview(self.loaded)
        self.assertEqual(self.projection, replay)
        self.assertEqual(
            self.projection.overview_sha256,
            replay.overview_sha256,
        )
        self.assertEqual(len(self.projection.overview_sha256), 64)

    def test_projection_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.projection.schema_version = 99

    def test_card_identity_and_field_order_is_frozen(self):
        self.assertEqual(
            tuple(item.card_id for item in self.projection.cards),
            EXPECTED_CARD_IDS,
        )
        self.assertEqual(
            tuple(item.field_key for item in self.projection.cards),
            EXPECTED_FIELD_KEYS,
        )

    def test_symbol_is_conserved_exactly(self):
        self.assertEqual(
            self.by_key["symbol"].value,
            self.record["analytics"]["symbol"],
        )

    def test_export_identity_is_conserved_exactly(self):
        self.assertEqual(
            self.by_key["export_sha256"].value,
            self.record["export_sha256"],
        )

    def test_snapshot_time_is_conserved_without_clock_conversion(self):
        self.assertEqual(
            self.by_key["snapshot_time_ms"].value,
            str(self.record["quality"]["snapshot_time_ms"]),
        )

    def test_paper_state_is_derived_only_from_accepted_p7_boolean(self):
        self.assertIs(self.record["quality"]["safety"]["paper_only"], True)
        self.assertEqual(self.by_key["paper_state"].value, "PAPER ONLY")

    def test_live_master_lock_is_conserved_exactly(self):
        self.assertEqual(
            self.by_key["live_master_lock"].value,
            self.record["quality"]["safety"]["live_master_lock"],
        )
        self.assertEqual(self.by_key["live_master_lock"].value, "OFF")

    def test_strategy_evidence_is_conserved_and_not_upgraded(self):
        self.assertEqual(
            self.by_key["strategy_evidence"].value,
            self.record["analytics"]["strategy_evidence"],
        )
        self.assertEqual(
            self.by_key["strategy_evidence"].value,
            "INSUFFICIENT_EVIDENCE",
        )

    def test_quality_status_is_conserved_exactly(self):
        self.assertEqual(
            self.by_key["quality_status"].value,
            self.record["quality"]["status"],
        )
        self.assertEqual(self.by_key["quality_status"].value, "PASS")

    def test_completed_trade_count_is_conserved_exactly(self):
        self.assertEqual(
            self.by_key["completed_trade_count"].value,
            str(self.record["quality"]["accepted_chain"]["completed_trade_count"]),
        )

    def test_open_trade_count_is_explicit_unknown_not_inferred(self):
        self.assertEqual(self.by_key["open_trade_count"].value, UNKNOWN_VALUE)
        self.assertIn("open_trade_count", self.projection.unknown_fields)

    def test_snapshot_freshness_is_explicit_unknown_without_clock_or_threshold(self):
        self.assertEqual(self.by_key["snapshot_freshness"].value, UNKNOWN_VALUE)
        self.assertIn("snapshot_freshness", self.projection.unknown_fields)

    def test_unknown_field_set_is_fixed(self):
        self.assertEqual(self.projection.unknown_fields, UNKNOWN_FIELDS)

    def test_accepted_chain_identities_are_conserved_exactly(self):
        chain = self.record["quality"]["accepted_chain"]
        mapping = {
            "ingestion_manifest_sha256": "ingestion_manifest_sha256",
            "timeline_sha256": "timeline_sha256",
            "reconstruction_sha256": "reconstruction_sha256",
            "metrics_sha256": "metrics_sha256",
            "segmentation_sha256": "segmentation_sha256",
        }
        for field_key, source_key in mapping.items():
            with self.subTest(field_key=field_key):
                self.assertEqual(
                    self.by_key[field_key].value,
                    chain[source_key],
                )

    def test_source_field_sha_binds_path_and_raw_value(self):
        card = self.by_key["quality_status"]
        expected = digest({
            "source_path": "quality.status",
            "source_value": self.record["quality"]["status"],
        })
        self.assertEqual(card.source_field_sha256, expected)

    def test_unknown_card_sha_binds_explicit_reason(self):
        card = self.by_key["open_trade_count"]
        expected = digest({
            "field_key": "open_trade_count",
            "state": "UNKNOWN",
            "reason": "NOT_EXPORTED_BY_ACCEPTED_P7_SEGMENTATION",
        })
        self.assertEqual(card.source_field_sha256, expected)

    def test_no_card_grants_trade_live_or_readiness_permission(self):
        forbidden_fields = {
            "trade_permission",
            "live_permission",
            "order_endpoint",
            "approved_quantity",
            "risk_authorization",
            "readiness",
            "live_ready",
            "profitability",
        }
        fields = {item.field_key for item in self.projection.cards}
        self.assertTrue(fields.isdisjoint(forbidden_fields))

    def test_projection_rejects_non_loaded_input(self):
        with self.assertRaises(OverviewProjectionError):
            project_overview(object())

    def test_projection_rejects_forged_loaded_export_payload(self):
        forged_record = self.loaded.record()
        forged_record["quality"]["status"] = "FAIL"
        forged_json = canonical(forged_record) + "\n"
        forged = replace(self.loaded, canonical_json=forged_json)
        with self.assertRaises(OverviewProjectionError):
            project_overview(forged)

    def test_projection_rejects_forged_source_symbol(self):
        forged_source = replace(self.loaded.source, symbol="ETHUSDT")
        forged = replace(self.loaded, source=forged_source)
        with self.assertRaises(OverviewProjectionError):
            project_overview(forged)

    def test_projection_rejects_forged_source_snapshot_time(self):
        forged_source = replace(
            self.loaded.source,
            observed_at_ms=self.loaded.source.observed_at_ms + 1,
        )
        forged = replace(self.loaded, source=forged_source)
        with self.assertRaises(OverviewProjectionError):
            project_overview(forged)

    def test_projection_record_has_no_caller_path_or_unknown_private_material(self):
        encoded = canonical(self.projection.as_record())
        self.assertNotIn(str(self.path), encoded)
        for forbidden in (
            "database_path",
            "api_key",
            "api_secret",
            "account_id",
            "raw_response",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_overview_source_has_no_clock_network_execution_or_analytics_runtime_import(self):
        import yatl.dashboard.overview as overview

        source_text = inspect.getsource(overview)
        for forbidden in (
            "from yatl.analytics",
            "import yatl.analytics",
            "datetime",
            "time.time",
            "time.monotonic",
            "sqlite3",
            "database_path",
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
                self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
