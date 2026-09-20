import hashlib
import inspect
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yatl.analytics import (
    AnalyticsSourceKind,
    RelationshipKind,
    TimelineEntry,
    TimelineError,
    TimelineKind,
    TimelineRelationship,
    TimelineTimeBasis,
    UnifiedTimeline,
    UpstreamSourceSpec,
    build_unified_timeline,
)
from yatl.analytics.timeline_runtime import (
    P6_OBSERVED,
    SNAPSHOT,
    START,
    _create_p5,
    _create_p6,
    _fixture_specs,
)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UnifiedTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.specs = _fixture_specs(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_replay_is_byte_identical_and_deterministic(self):
        first = build_unified_timeline(SNAPSHOT, self.specs)
        second = build_unified_timeline(SNAPSHOT, self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.timeline_sha256, second.timeline_sha256)
        self.assertEqual(len(first.timeline_sha256), 64)

    def test_exact_entry_order_and_time_basis(self):
        timeline = build_unified_timeline(SNAPSHOT, self.specs)
        self.assertEqual(
            tuple(item.kind for item in timeline.entries),
            (
                TimelineKind.P5_INTENT_BINDING,
                TimelineKind.P5_ORDER_EVENT,
                TimelineKind.P5_ORDER_EVENT,
                TimelineKind.P5_FILL_EVENT,
                TimelineKind.P5_PORTFOLIO_PROJECTION,
                TimelineKind.P6_ANALYST_TRACE,
            ),
        )
        self.assertEqual(
            tuple(item.time_basis for item in timeline.entries),
            (
                TimelineTimeBasis.RELATED_ORDER_TIME,
                TimelineTimeBasis.UPSTREAM_EVENT_TIME,
                TimelineTimeBasis.UPSTREAM_EVENT_TIME,
                TimelineTimeBasis.UPSTREAM_FILL_TIME,
                TimelineTimeBasis.LAST_FILL_TIME,
                TimelineTimeBasis.SOURCE_OBSERVED_AT,
            ),
        )
        self.assertEqual(
            tuple(item.sequence for item in timeline.entries),
            tuple(range(6)),
        )

    def test_intent_binds_risk_and_execution_identities_without_inventing_time(self):
        timeline = build_unified_timeline(SNAPSHOT, self.specs)
        intent = timeline.entries[0]
        kinds = {item.kind for item in intent.relationships}
        self.assertEqual(
            kinds,
            {
                RelationshipKind.AUTHORIZATION,
                RelationshipKind.DECISION,
                RelationshipKind.READINESS,
            },
        )
        self.assertEqual(intent.time_basis, TimelineTimeBasis.RELATED_ORDER_TIME)

    def test_fill_binds_exact_intent_order_state_and_fill_step(self):
        timeline = build_unified_timeline(SNAPSHOT, self.specs)
        fill = next(
            item for item in timeline.entries
            if item.kind is TimelineKind.P5_FILL_EVENT
        )
        self.assertEqual(
            {item.kind for item in fill.relationships},
            {
                RelationshipKind.AUTHORIZATION,
                RelationshipKind.INTENT,
                RelationshipKind.ORDER_STATE,
                RelationshipKind.FILL_STEP,
            },
        )

    def test_analyst_trace_binds_input_report_and_evidence_identities(self):
        timeline = build_unified_timeline(SNAPSHOT, self.specs)
        trace = timeline.entries[-1]
        self.assertEqual(trace.kind, TimelineKind.P6_ANALYST_TRACE)
        self.assertEqual(
            {item.kind for item in trace.relationships},
            {
                RelationshipKind.REQUEST,
                RelationshipKind.RESPONSE_VALIDATION,
                RelationshipKind.BUNDLE,
                RelationshipKind.GROUNDING,
                RelationshipKind.ANALYST_INPUT,
                RelationshipKind.ANALYST_REPORT,
            },
        )

    def test_build_is_read_only(self):
        before = tuple(file_sha(item.database_path) for item in self.specs)
        build_unified_timeline(SNAPSHOT, self.specs)
        after = tuple(file_sha(item.database_path) for item in self.specs)
        self.assertEqual(before, after)

    def test_orphan_intent_fails_closed(self):
        p5 = self.specs[0].database_path
        authorization = "9" * 64
        material = {
            "schema_version": 1,
            "authorization_sha256": authorization,
            "effect_sha256": authorization,
            "decision_sha256": "8" * 64,
            "readiness_sha256": "7" * 64,
            "action": "ENTER_LONG",
            "approved_quantity": "1",
            "policy_id": "P5_LOCAL_PAPER_V1",
        }
        import json
        intent_sha = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "INSERT INTO local_paper_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    authorization,
                    authorization,
                    "8" * 64,
                    "7" * 64,
                    "ENTER_LONG",
                    "1",
                    "P5_LOCAL_PAPER_V1",
                    intent_sha,
                ),
            )
        connection.close()
        specs = (
            replace(self.specs[0], expected_database_sha256=file_sha(p5)),
            self.specs[1],
        )
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, specs)

    def test_cross_symbol_fill_fails_closed(self):
        other = self.root / "p5-eth.sqlite3"
        _create_p5(other, "ETHUSDT")
        specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                START + 45,
                other,
                file_sha(other),
            ),
            self.specs[1],
        )
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, specs)

    def test_future_order_or_fill_fails_closed(self):
        future = self.root / "p5-future.sqlite3"
        _create_p5(future, "BTCUSDT", SNAPSHOT + 1)
        specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                SNAPSHOT,
                future,
                file_sha(future),
            ),
            self.specs[1],
        )
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, specs)

    def test_future_analyst_source_fails_closed(self):
        future_p6 = replace(self.specs[1], observed_at_ms=SNAPSHOT + 1)
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, (self.specs[0], future_p6))

    def test_broken_order_chain_fails_closed(self):
        p5 = self.specs[0].database_path
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_order_events "
                "SET previous_event_sha256 = ? WHERE sequence = 1",
                ("0" * 64,),
            )
        connection.close()
        specs = (
            replace(self.specs[0], expected_database_sha256=file_sha(p5)),
            self.specs[1],
        )
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, specs)

    def test_projection_relation_tamper_fails_closed(self):
        p5 = self.specs[0].database_path
        connection = sqlite3.connect(str(p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_portfolios SET last_fill_event_sha256 = ?",
                ("0" * 64,),
            )
        connection.close()
        specs = (
            replace(self.specs[0], expected_database_sha256=file_sha(p5)),
            self.specs[1],
        )
        with self.assertRaises(TimelineError):
            build_unified_timeline(SNAPSHOT, specs)

    def test_duplicate_timeline_identity_is_rejected(self):
        timeline = build_unified_timeline(SNAPSHOT, self.specs)
        original = timeline.entries[0]
        duplicate = TimelineEntry(
            1,
            original.time_ms,
            original.time_basis,
            original.kind,
            original.symbol,
            original.source_id,
            original.primary_sha256,
            original.relationships,
        )
        with self.assertRaises(TimelineError):
            UnifiedTimeline(
                timeline.snapshot_time_ms,
                timeline.symbol,
                timeline.ingestion_manifest_sha256,
                (original, duplicate),
            )

    def test_noncanonical_relationship_order_is_rejected(self):
        rels = (
            TimelineRelationship(RelationshipKind.READINESS, "3" * 64),
            TimelineRelationship(RelationshipKind.AUTHORIZATION, "1" * 64),
        )
        with self.assertRaises(TimelineError):
            TimelineEntry(
                0,
                START,
                TimelineTimeBasis.RELATED_ORDER_TIME,
                TimelineKind.P5_INTENT_BINDING,
                "BTCUSDT",
                "SOURCE_P5",
                "2" * 64,
                rels,
            )

    def test_source_has_no_execution_account_risk_network_or_provider_import(self):
        import yatl.analytics.timeline as module

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
