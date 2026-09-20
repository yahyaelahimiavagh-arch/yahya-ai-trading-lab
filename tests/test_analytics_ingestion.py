import hashlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check
from yatl.analyst.journal import AnalystTraceJournal
from yatl.analyst.journal_runtime import _accepted_grounding, _rejected_grounding
from yatl.analytics import AnalyticsSourceKind
from yatl.analytics.ingestion import (
    AnalyticsIngestionError,
    ReadOnlyIngestionManifest,
    UpstreamSourceSpec,
    _connect_readonly,
    ingest_readonly_sources,
    ingest_source,
)
from yatl.execution import ExecutionIntentJournal


SNAPSHOT_TIME = 1_790_000_100_000
OBSERVED_TIME = SNAPSHOT_TIME - 1_000


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReadOnlyIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p5 = self.root / "p5.sqlite3"
        self.p6 = self.root / "p6.sqlite3"

        _, _, entry, exit_decision = _paper_execution_contract_runtime_check()
        with ExecutionIntentJournal(self.p5) as journal:
            journal.record(exit_decision)
            journal.record(entry)
            self.p5_export = journal.canonical_json()

        with AnalystTraceJournal(self.p6) as journal:
            journal.record(_rejected_grounding())
            journal.record(_accepted_grounding())
            self.p6_export = journal.canonical_json()

        self.specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                OBSERVED_TIME,
                self.p5,
                file_sha(self.p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                OBSERVED_TIME,
                self.p6,
                file_sha(self.p6),
            ),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_upstream_exports_match_ingested_canonical_digests(self):
        manifest = ingest_readonly_sources(SNAPSHOT_TIME, self.specs)
        self.assertEqual(tuple(item.record_count for item in manifest.sources), (2, 2))
        expected = {
            "SOURCE_P5": hashlib.sha256(self.p5_export.encode()).hexdigest(),
            "SOURCE_P6": hashlib.sha256(self.p6_export.encode()).hexdigest(),
        }
        for item in manifest.sources:
            self.assertEqual(
                item.canonical_sha256,
                expected[item.identity.source_id],
            )
            self.assertEqual(item.identity.source_sha256, item.canonical_sha256)
            self.assertTrue(item.read_only)

    def test_reopen_replay_is_deterministic_and_path_free(self):
        first = ingest_readonly_sources(SNAPSHOT_TIME, self.specs)
        second = ingest_readonly_sources(SNAPSHOT_TIME, self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.manifest_sha256, second.manifest_sha256)
        encoded = json.dumps(first.as_record(), sort_keys=True, separators=(",", ":"))
        self.assertNotIn(str(self.root), encoded)

    def test_ingestion_does_not_write_upstream_databases(self):
        before = (file_sha(self.p5), file_sha(self.p6))
        ingest_readonly_sources(SNAPSHOT_TIME, self.specs)
        after = (file_sha(self.p5), file_sha(self.p6))
        self.assertEqual(before, after)

        connection = _connect_readonly(self.p5)
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden_write(value INTEGER)")
        connection.close()
        self.assertEqual(before[0], file_sha(self.p5))

    def test_wrong_database_identity_fails_closed(self):
        bad = replace(self.specs[0], expected_database_sha256="0" * 64)
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(bad)

    def test_p5_row_tamper_is_detected_even_with_updated_file_identity(self):
        connection = sqlite3.connect(str(self.p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_intents SET approved_quantity = '999' "
                "WHERE rowid = (SELECT MIN(rowid) FROM local_paper_intents)"
            )
        connection.close()
        bad = replace(
            self.specs[0],
            expected_database_sha256=file_sha(self.p5),
        )
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(bad)

    def test_p6_trace_tamper_is_detected_even_with_updated_file_identity(self):
        connection = sqlite3.connect(str(self.p6))
        row = connection.execute(
            "SELECT trace_sha256, trace_json FROM analyst_traces ORDER BY trace_sha256 LIMIT 1"
        ).fetchone()
        trace = json.loads(row[1])
        trace["grounding_record"]["report"]["reason"] = "ANALYSIS_ONLY"
        connection.execute(
            "UPDATE analyst_traces SET trace_json = ? WHERE trace_sha256 = ?",
            (json.dumps(trace, sort_keys=True, separators=(",", ":")), row[0]),
        )
        connection.commit()
        connection.close()
        bad = replace(
            self.specs[1],
            expected_database_sha256=file_sha(self.p6),
        )
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(bad)

    def test_newer_p5_and_p6_schema_fail_closed(self):
        for path, table, spec in (
            (self.p5, "execution_schema_migrations", self.specs[0]),
            (self.p6, "analyst_schema_migrations", self.specs[1]),
        ):
            connection = sqlite3.connect(str(path))
            with connection:
                connection.execute(f"INSERT INTO {table}(version) VALUES (2)")
            connection.close()
            changed = replace(spec, expected_database_sha256=file_sha(path))
            with self.subTest(path=path.name), self.assertRaises(AnalyticsIngestionError):
                ingest_source(changed)

    def test_missing_empty_symlink_and_duplicate_path_fail_closed(self):
        missing = replace(self.specs[0], database_path=self.root / "missing.sqlite3")
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(missing)

        empty = self.root / "empty.sqlite3"
        empty.touch()
        empty_spec = replace(
            self.specs[0],
            database_path=empty,
            expected_database_sha256=hashlib.sha256(b"").hexdigest(),
        )
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(empty_spec)

        link = self.root / "linked.sqlite3"
        try:
            link.symlink_to(self.p5)
        except (OSError, NotImplementedError):
            pass
        else:
            link_spec = replace(
                self.specs[0],
                database_path=link,
                expected_database_sha256=file_sha(self.p5),
            )
            with self.assertRaises(AnalyticsIngestionError):
                ingest_source(link_spec)

        duplicate = replace(
            self.specs[1],
            database_path=self.p5,
            expected_database_sha256=file_sha(self.p5),
        )
        with self.assertRaises(AnalyticsIngestionError):
            ingest_readonly_sources(SNAPSHOT_TIME, (self.specs[0], duplicate))

    def test_mid_read_mutation_signal_fails_closed(self):
        spec = self.specs[0]
        original = file_sha(self.p5)
        with patch(
            "yatl.analytics.ingestion._sha256_file",
            side_effect=(original, "0" * 64),
        ):
            with self.assertRaises(AnalyticsIngestionError):
                ingest_source(spec)

    def test_manifest_requires_one_p5_one_p6_same_symbol_and_sorted_ids(self):
        good = tuple(ingest_source(item) for item in self.specs)
        manifest = ReadOnlyIngestionManifest(
            SNAPSHOT_TIME,
            tuple(sorted(good, key=lambda item: item.identity.source_id)),
        )
        self.assertEqual(len(manifest.manifest_sha256), 64)

        with self.assertRaises(AnalyticsIngestionError):
            ReadOnlyIngestionManifest(SNAPSHOT_TIME, (good[0], good[0]))

        eth_spec = replace(self.specs[1], symbol="ETHUSDT")
        eth = ingest_source(eth_spec)
        with self.assertRaises(AnalyticsIngestionError):
            ReadOnlyIngestionManifest(
                SNAPSHOT_TIME,
                tuple(sorted((good[0], eth), key=lambda item: item.identity.source_id)),
            )

        with self.assertRaises(AnalyticsIngestionError):
            ReadOnlyIngestionManifest(
                SNAPSHOT_TIME,
                tuple(reversed(tuple(sorted(good, key=lambda item: item.identity.source_id)))),
            )

    def test_future_observation_fails_manifest(self):
        future = replace(self.specs[1], observed_at_ms=SNAPSHOT_TIME + 1)
        with self.assertRaises(AnalyticsIngestionError):
            ingest_readonly_sources(SNAPSHOT_TIME, (self.specs[0], future))

    def test_forbidden_provider_material_is_rejected(self):
        connection = sqlite3.connect(str(self.p6))
        row = connection.execute(
            "SELECT trace_sha256, trace_json FROM analyst_traces ORDER BY trace_sha256 LIMIT 1"
        ).fetchone()
        trace = json.loads(row[1])
        trace["raw_response"] = "private"
        changed = json.dumps(trace, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "UPDATE analyst_traces SET trace_json = ? WHERE trace_sha256 = ?",
            (changed, row[0]),
        )
        connection.commit()
        connection.close()
        spec = replace(self.specs[1], expected_database_sha256=file_sha(self.p6))
        with self.assertRaises(AnalyticsIngestionError):
            ingest_source(spec)

    def test_invalid_spec_and_wrong_collection_shape_fail_closed(self):
        with self.assertRaises(AnalyticsIngestionError):
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                OBSERVED_TIME,
                self.p5,
                "bad",
            )
        for value in (list(self.specs), (self.specs[0],), None):
            with self.subTest(value=type(value)), self.assertRaises(AnalyticsIngestionError):
                ingest_readonly_sources(SNAPSHOT_TIME, value)

    def test_source_has_no_execution_account_risk_network_or_provider_import(self):
        import inspect
        import yatl.analytics.ingestion as module

        source = inspect.getsource(module)
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
            "subprocess",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
