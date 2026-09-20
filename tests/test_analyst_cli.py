import contextlib
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.analyst import cli
from yatl.analyst.cli import (
    EXIT_INVALID,
    EXIT_NOT_FOUND,
    EXIT_NOT_GROUNDED,
    EXIT_OK,
    MAX_ANALYST_CLI_OUTPUT_BYTES,
    AnalystCliCode,
    AnalystCliError,
    analyst_evidence,
    analyst_show,
    analyst_validate,
    load_bundle_spec,
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


def bundle_record(symbol="BTCUSDT"):
    return {
        "schema_version": 1,
        "symbol": symbol,
        "decision_time_ms": DECISION_TIME,
        "evidence": [
            {
                "evidence_id": "E_P1_MARKET",
                "layer": "P1_PUBLIC_MARKET",
                "observed_at_ms": DECISION_TIME - 4_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
                    "latest_closed_at_ms": DECISION_TIME - 5_000,
                    "manifest_sha256": "a" * 64,
                },
            },
            {
                "evidence_id": "E_P3_STRATEGY",
                "layer": "P3_STRATEGY_EVIDENCE",
                "observed_at_ms": DECISION_TIME - 3_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "candidate_matrix_sha256": P3_INDEX,
                    "strategy_evidence": "INSUFFICIENT_EVIDENCE",
                },
            },
            {
                "evidence_id": "E_P4_RISK",
                "layer": "P4_RISK_STATUS",
                "observed_at_ms": DECISION_TIME - 2_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
                    "accepted": True,
                    "audit_sha256": P4_INDEX,
                    "policy_sha256": P4_POLICY,
                    "quantity_authority": False,
                    "risk_authorization_mutation": False,
                    "risk_status": "PASS",
                },
            },
            {
                "evidence_id": "E_P5_SAFETY",
                "layer": "P5_SAFETY_STATUS",
                "observed_at_ms": DECISION_TIME - 1_000,
                "valid_through_ms": VALID_THROUGH,
                "payload": {
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
            },
        ],
    }


def accepted_response():
    return canonical(
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


class AnalystCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.bundle = root / "bundle.json"
        self.response = root / "response.json"
        self.journal = root / "analyst.sqlite3"
        self.bundle.write_text(canonical(bundle_record()), encoding="utf-8")
        self.response.write_text(accepted_response(), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_bundle_loader_builds_exact_point_in_time_evidence(self):
        bundle = load_bundle_spec(self.bundle)
        self.assertEqual(bundle.symbol, "BTCUSDT")
        self.assertEqual(bundle.strategy_evidence.value, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(
            tuple(item.evidence_id for item in bundle.evidence),
            ("E_P1_MARKET", "E_P3_STRATEGY", "E_P4_RISK", "E_P5_SAFETY"),
        )

    def test_evidence_command_is_sanitized_and_deterministic(self):
        first = analyst_evidence(self.bundle)
        second = analyst_evidence(self.bundle)
        self.assertEqual(first, second)
        encoded = canonical(first)
        self.assertNotIn('"payload":', encoded)
        self.assertEqual(first["code"], AnalystCliCode.EVIDENCE_READY.value)

    def test_validate_grounded_response(self):
        result = analyst_validate(self.bundle, self.response)
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], AnalystCliCode.GROUNDED.value)
        self.assertEqual(result["report"]["disposition"], "REVIEW")
        self.assertEqual(result["report"]["reason"], "UNCERTAINTY_PRESENT")
        self.assertFalse(result["journaled"])

    def test_validate_and_journal_then_show(self):
        validated = analyst_validate(self.bundle, self.response, self.journal)
        self.assertTrue(validated["journaled"])
        shown = analyst_show(self.journal, validated["trace_sha256"])
        self.assertTrue(shown["ok"])
        self.assertEqual(shown["code"], AnalystCliCode.TRACE_READY.value)
        self.assertEqual(shown["report"], validated["report"])
        self.assertEqual(shown["trace_sha256"], validated["trace_sha256"])

    def test_validate_duplicate_replay_is_idempotent(self):
        first = analyst_validate(self.bundle, self.response, self.journal)
        second = analyst_validate(self.bundle, self.response, self.journal)
        self.assertEqual(first, second)

    def test_malformed_response_is_fail_closed_not_cli_invalid(self):
        self.response.write_text('{"schema_version":1', encoding="utf-8")
        result = analyst_validate(self.bundle, self.response)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], AnalystCliCode.NOT_GROUNDED.value)
        self.assertEqual(result["report"]["disposition"], "INSUFFICIENT_DATA")
        self.assertEqual(result["report"]["claims"], [])

    def test_oversized_response_is_fail_closed_by_response_boundary(self):
        self.response.write_bytes(b"x" * (cli.MAX_MODEL_RESPONSE_BYTES + 1))
        result = analyst_validate(self.bundle, self.response)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], AnalystCliCode.NOT_GROUNDED.value)
        self.assertEqual(result["response_code"], "RESPONSE_TOO_LARGE")

    def test_semantic_rejection_is_fail_closed(self):
        raw = json.loads(accepted_response())
        raw["claims"][0]["text"] = "Public market evidence appears available."
        self.response.write_text(canonical(raw), encoding="utf-8")
        result = analyst_validate(self.bundle, self.response)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], AnalystCliCode.NOT_GROUNDED.value)
        self.assertEqual(result["grounding_code"], "CLAIM_SHAPE_MISMATCH")

    def test_unknown_bundle_fields_are_rejected(self):
        record = bundle_record()
        record["unexpected"] = True
        self.bundle.write_text(canonical(record), encoding="utf-8")
        with self.assertRaises(AnalystCliError):
            load_bundle_spec(self.bundle)

    def test_duplicate_json_keys_are_rejected(self):
        self.bundle.write_text(
            '{"schema_version":1,"schema_version":1}',
            encoding="utf-8",
        )
        with self.assertRaises(AnalystCliError):
            load_bundle_spec(self.bundle)

    def test_oversized_bundle_is_rejected(self):
        self.bundle.write_bytes(b"x" * (cli.MAX_BUNDLE_SPEC_BYTES + 1))
        with self.assertRaises(AnalystCliError):
            load_bundle_spec(self.bundle)

    def test_stale_or_future_bundle_is_rejected(self):
        for key, value in (
            ("valid_through_ms", DECISION_TIME - 1),
            ("observed_at_ms", DECISION_TIME + 1),
        ):
            with self.subTest(key=key):
                record = bundle_record()
                record["evidence"][1][key] = value
                self.bundle.write_text(canonical(record), encoding="utf-8")
                with self.assertRaises(AnalystCliError):
                    load_bundle_spec(self.bundle)
                self.bundle.write_text(canonical(bundle_record()), encoding="utf-8")

    def test_p3_upgrade_is_rejected(self):
        record = bundle_record()
        record["evidence"][1]["payload"]["strategy_evidence"] = (
            "QUALIFIED_FOR_P4_RESEARCH"
        )
        self.bundle.write_text(canonical(record), encoding="utf-8")
        with self.assertRaises(AnalystCliError):
            load_bundle_spec(self.bundle)

    def test_show_missing_trace_is_stable(self):
        analyst_validate(self.bundle, self.response, self.journal)
        missing = analyst_show(self.journal, "f" * 64)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["code"], AnalystCliCode.TRACE_NOT_FOUND.value)

    def test_show_invalid_digest_is_invalid_input(self):
        with self.assertRaises(AnalystCliError) as caught:
            analyst_show(self.journal, "bad")
        self.assertEqual(caught.exception.code, AnalystCliCode.INVALID_INPUT)

    def test_cli_exit_codes_and_output_are_stable(self):
        argv = ["evidence", "--bundle", str(self.bundle)]
        first = io.StringIO()
        second = io.StringIO()
        with contextlib.redirect_stdout(first):
            first_code = cli.main(argv)
        with contextlib.redirect_stdout(second):
            second_code = cli.main(argv)
        self.assertEqual((first_code, second_code), (EXIT_OK, EXIT_OK))
        self.assertEqual(first.getvalue(), second.getvalue())

        self.response.write_text("{", encoding="utf-8")
        failed = io.StringIO()
        with contextlib.redirect_stdout(failed):
            code = cli.main(
                [
                    "validate",
                    "--bundle", str(self.bundle),
                    "--response", str(self.response),
                ]
            )
        self.assertEqual(code, EXIT_NOT_GROUNDED)

        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(
                ["show", "--journal", str(self.journal), "--trace-sha256", "f" * 64]
            )
        self.assertEqual(code, EXIT_NOT_FOUND)

    def test_cli_is_noninteractive(self):
        argv = [
            "validate",
            "--bundle", str(self.bundle),
            "--response", str(self.response),
        ]
        output = io.StringIO()
        with patch("builtins.input", side_effect=AssertionError("interactive input")):
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(argv), EXIT_OK)

    def test_rejected_argument_value_is_never_echoed(self):
        marker = "DO_NOT_ECHO_REJECTED_ANALYST_ARGUMENT"
        output = io.StringIO()
        errors = io.StringIO()
        argv = ["evidence", "--bundle", str(self.bundle), "--endpoint", marker]
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = cli.main(argv)
        self.assertEqual(code, EXIT_INVALID)
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(str(self.bundle), output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "INVALID_REQUEST")

    def test_missing_input_path_is_never_echoed(self):
        marker = Path(self.temporary.name) / "PRIVATE-MISSING-NAME.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["evidence", "--bundle", str(marker)])
        self.assertEqual(code, EXIT_INVALID)
        self.assertNotIn(str(marker), output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "INVALID_INPUT")

    def test_output_is_bounded_and_excludes_raw_response(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(
                [
                    "validate",
                    "--bundle", str(self.bundle),
                    "--response", str(self.response),
                ]
            )
        self.assertEqual(code, EXIT_OK)
        encoded = output.getvalue()
        self.assertLessEqual(
            len(encoded.encode("utf-8")),
            MAX_ANALYST_CLI_OUTPUT_BYTES + 1,
        )
        self.assertNotIn("raw_response", encoded)
        self.assertNotIn("canonical_response_json", encoded)

    def test_both_symbols_are_supported(self):
        btc = load_bundle_spec(self.bundle)
        self.bundle.write_text(canonical(bundle_record("ETHUSDT")), encoding="utf-8")
        eth = load_bundle_spec(self.bundle)
        self.assertNotEqual(btc.bundle_sha256, eth.bundle_sha256)

    def test_source_has_no_provider_network_environment_or_execution_access(self):
        source = inspect.getsource(cli)
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
            "input(",
            "eval(",
            "exec(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
