import inspect
import json
import sqlite3
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from yatl.analyst import EvidenceLayer
from yatl.analyst.evidence import build_evidence_bundle, build_layer_evidence
from yatl.analyst.grounding import ground_model_response
from yatl.analyst.journal import (
    ANALYST_JOURNAL_SCHEMA_VERSION,
    AnalystJournalError,
    AnalystTraceConflict,
    AnalystTraceJournal,
    AnalystTraceRecord,
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


def accepted_grounding(symbol="BTCUSDT"):
    request = build_model_request(bundle(symbol))
    raw = canonical(
        {
            "schema_version": 1,
            "claims": [
                {
                    "claim_id": "MODEL_FACT_MARKET",
                    "kind": "FACT",
                    "text": "Accepted public market evidence is present.",
                    "evidence_ids": ["E_P1_MARKET"],
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
            ],
        }
    )
    return ground_model_response(validate_model_response(request, raw))


def rejected_grounding(symbol="BTCUSDT"):
    request = build_model_request(bundle(symbol))
    return ground_model_response(
        validate_model_response(request, '{"schema_version":1')
    )


class AnalystJournalTests(unittest.TestCase):
    def test_record_from_grounding_is_deterministic(self):
        first = AnalystTraceRecord.from_grounding(accepted_grounding())
        second = AnalystTraceRecord.from_grounding(accepted_grounding())
        self.assertEqual(first, second)
        self.assertEqual(first.trace_sha256, second.trace_sha256)

    def test_record_is_frozen(self):
        record = AnalystTraceRecord.from_grounding(accepted_grounding())
        with self.assertRaises(FrozenInstanceError):
            record.trace_sha256 = "b" * 64

    def test_rejected_trace_is_fail_closed_and_sanitized(self):
        record = AnalystTraceRecord.from_grounding(rejected_grounding())
        self.assertEqual(record.accepted, 0)
        self.assertEqual(record.disposition, "INSUFFICIENT_DATA")
        self.assertEqual(record.reason, "NO_USABLE_CLAIMS")
        self.assertEqual(record.grounded_claim_ids_json, "[]")
        self.assertNotIn("raw_response", record.trace_json)
        self.assertNotIn("canonical_response_json", record.trace_json)

    def test_invalid_grounding_type_is_rejected(self):
        with self.assertRaises(AnalystJournalError):
            AnalystTraceRecord.from_grounding("not-a-grounding")

    def test_persistent_path_required(self):
        for path in ("", ":memory:", None):
            with self.subTest(path=path):
                with self.assertRaises(AnalystJournalError):
                    AnalystTraceJournal(path)

    def test_record_and_get_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            grounding = accepted_grounding()
            with AnalystTraceJournal(path) as journal:
                record = journal.record(grounding)
                self.assertEqual(journal.count(), 1)
                self.assertEqual(journal.get(record.trace_sha256), record)
                self.assertEqual(
                    journal.get_by_response(record.response_validation_sha256),
                    record,
                )

    def test_duplicate_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            grounding = accepted_grounding()
            with AnalystTraceJournal(path) as journal:
                first = journal.record(grounding)
                second = journal.record(grounding)
                self.assertEqual(first, second)
                self.assertEqual(journal.count(), 1)

    def test_accepted_and_rejected_traces_can_coexist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                accepted = journal.record(accepted_grounding())
                rejected = journal.record(rejected_grounding())
                self.assertNotEqual(
                    accepted.response_validation_sha256,
                    rejected.response_validation_sha256,
                )
                self.assertEqual(journal.count(), 2)

    def test_reopen_preserves_exact_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                journal.record(accepted_grounding())
                journal.record(rejected_grounding())
                first_export = journal.canonical_json()
            with AnalystTraceJournal(path) as reopened:
                self.assertEqual(reopened.schema_version(), ANALYST_JOURNAL_SCHEMA_VERSION)
                self.assertEqual(reopened.count(), 2)
                self.assertEqual(reopened.canonical_json(), first_export)

    def test_canonical_export_is_order_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "a.sqlite3"
            second_path = Path(directory) / "b.sqlite3"
            accepted = accepted_grounding()
            rejected = rejected_grounding()
            with AnalystTraceJournal(first_path) as journal:
                journal.record(accepted)
                journal.record(rejected)
                first_export = journal.canonical_json()
            with AnalystTraceJournal(second_path) as journal:
                journal.record(rejected)
                journal.record(accepted)
                second_export = journal.canonical_json()
            self.assertEqual(first_export, second_export)

    def test_export_retains_no_raw_provider_text_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                journal.record(accepted_grounding())
                journal.record(rejected_grounding())
                exported = journal.canonical_json()
            for forbidden in (
                "raw_response",
                "canonical_response_json",
                '"api_key":',
                '"api_secret":',
                '"credentials":',
                '"endpoint_url":',
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, exported)

    def test_row_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                record = journal.record(accepted_grounding())

            connection = sqlite3.connect(str(path))
            connection.execute(
                "UPDATE analyst_traces SET report_sha256 = ? WHERE trace_sha256 = ?",
                ("b" * 64, record.trace_sha256),
            )
            connection.commit()
            connection.close()

            with AnalystTraceJournal(path) as journal:
                with self.assertRaises(AnalystJournalError):
                    journal.get(record.trace_sha256)

    def test_trace_json_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                record = journal.record(accepted_grounding())

            trace = json.loads(record.trace_json)
            trace["grounding_code"] = "UPSTREAM_REJECTED"
            connection = sqlite3.connect(str(path))
            connection.execute(
                "UPDATE analyst_traces SET trace_json = ? WHERE trace_sha256 = ?",
                (canonical(trace), record.trace_sha256),
            )
            connection.commit()
            connection.close()

            with AnalystTraceJournal(path) as journal:
                with self.assertRaises(AnalystJournalError):
                    journal.get(record.trace_sha256)

    def test_newer_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path):
                pass
            connection = sqlite3.connect(str(path))
            connection.execute(
                "INSERT INTO analyst_schema_migrations(version) VALUES (?)",
                (ANALYST_JOURNAL_SCHEMA_VERSION + 1,),
            )
            connection.commit()
            connection.close()
            with self.assertRaises(AnalystJournalError):
                AnalystTraceJournal(path)

    def test_insert_failure_rolls_back_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            journal = AnalystTraceJournal(path)
            original_insert = journal._insert

            def fail_after_insert(record):
                original_insert(record)
                raise sqlite3.OperationalError("forced failure")

            journal._insert = fail_after_insert
            with self.assertRaises(AnalystJournalError):
                journal.record(accepted_grounding())
            journal._insert = original_insert
            self.assertEqual(journal.count(), 0)
            journal.close()

    def test_conflicting_response_identity_fails_without_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                stored = journal.record(accepted_grounding())
                connection = journal._connection
                connection.execute(
                    "UPDATE analyst_traces SET trace_sha256 = ? "
                    "WHERE response_validation_sha256 = ?",
                    ("c" * 64, stored.response_validation_sha256),
                )
                connection.commit()
                with self.assertRaises(AnalystJournalError):
                    journal.record(accepted_grounding())
                self.assertEqual(journal.count(), 1)

    def test_invalid_lookup_digests_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            with AnalystTraceJournal(path) as journal:
                for value in ("", "abc", "G" * 64, None):
                    with self.subTest(value=value):
                        with self.assertRaises(AnalystJournalError):
                            journal.get(value)
                        with self.assertRaises(AnalystJournalError):
                            journal.get_by_response(value)

    def test_both_supported_symbols_produce_distinct_traces(self):
        btc = AnalystTraceRecord.from_grounding(accepted_grounding("BTCUSDT"))
        eth = AnalystTraceRecord.from_grounding(accepted_grounding("ETHUSDT"))
        self.assertNotEqual(btc.trace_sha256, eth.trace_sha256)
        self.assertNotEqual(btc.bundle_sha256, eth.bundle_sha256)

    def test_source_has_no_provider_network_environment_or_execution_access(self):
        import yatl.analyst.journal as journal_module

        source = inspect.getsource(journal_module)
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
            "requests",
            "httpx",
            "aiohttp",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
