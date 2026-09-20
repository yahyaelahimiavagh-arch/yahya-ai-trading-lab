import contextlib
import hashlib
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.analytics import cli
from yatl.analytics.cli import (
    EXIT_EXISTS,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_QUALITY,
    MAX_CLI_OUTPUT_BYTES,
    AnalyticsCliCode,
    AnalyticsCliError,
    analytics_export,
    analytics_summary,
    analytics_trades,
    analytics_validate,
    load_analytics_spec,
)
from yatl.analytics.timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from yatl.analytics.trade_runtime import _close_fixture


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class AnalyticsCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p5 = self.root / "p5.sqlite3"
        self.p6 = self.root / "p6.sqlite3"
        self.spec = self.root / "analytics.json"
        _create_p5(self.p5)
        _close_fixture(self.p5)
        _create_p6(self.p6)
        self.write_spec()

    def tearDown(self):
        self.temp.cleanup()

    def spec_record(self):
        return {
            "schema_version": 1,
            "snapshot_time_ms": SNAPSHOT,
            "sources": [
                {
                    "source_id": "SOURCE_P5",
                    "source_kind": "P5_EXECUTION_EVIDENCE",
                    "symbol": "BTCUSDT",
                    "observed_at_ms": START + 90,
                    "database_path": str(self.p5),
                    "expected_database_sha256": file_sha(self.p5),
                },
                {
                    "source_id": "SOURCE_P6",
                    "source_kind": "P6_ANALYST_TRACE",
                    "symbol": "BTCUSDT",
                    "observed_at_ms": P6_OBSERVED,
                    "database_path": str(self.p6),
                    "expected_database_sha256": file_sha(self.p6),
                },
            ],
        }

    def write_spec(self, record=None):
        self.spec.write_text(
            canonical(self.spec_record() if record is None else record),
            encoding="utf-8",
        )

    def test_loader_builds_exact_two_source_binding(self):
        snapshot, specs = load_analytics_spec(self.spec)
        self.assertEqual(snapshot, SNAPSHOT)
        self.assertEqual(
            tuple(item.source_id for item in specs),
            ("SOURCE_P5", "SOURCE_P6"),
        )
        self.assertEqual({item.symbol for item in specs}, {"BTCUSDT"})

    def test_validate_summary_and_trade_view_are_deterministic(self):
        validate_first = analytics_validate(self.spec)
        validate_second = analytics_validate(self.spec)
        summary_first = analytics_summary(self.spec)
        summary_second = analytics_summary(self.spec)
        trades_first = analytics_trades(self.spec, 25)
        trades_second = analytics_trades(self.spec, 25)
        self.assertEqual(validate_first, validate_second)
        self.assertEqual(summary_first, summary_second)
        self.assertEqual(trades_first, trades_second)
        self.assertEqual(validate_first["code"], AnalyticsCliCode.VALIDATED.value)
        self.assertEqual(summary_first["completed_trade_count"], 1)
        self.assertEqual(trades_first["returned_trades"], 1)
        self.assertEqual(
            trades_first["trades"][0]["trade_sha256"],
            summary_first["segmentation_sha256"]
            and trades_second["trades"][0]["trade_sha256"],
        )

    def test_quality_failure_has_no_partial_analytics_payload(self):
        with self.p5.open("ab") as stream:
            stream.write(b"changed")
        result = analytics_validate(self.spec)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], AnalyticsCliCode.QUALITY_FAILED.value)
        self.assertIsNone(result["quality"]["accepted_chain"])
        self.assertFalse(result["quality"]["publication_allowed"])
        encoded = canonical(result)
        self.assertNotIn("trade_metrics", encoded)
        self.assertNotIn("database_path", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_export_is_canonical_deterministic_path_free_and_read_only(self):
        first = self.root / "first.json"
        second = self.root / "second.json"
        before = (file_sha(self.p5), file_sha(self.p6))
        result_one = analytics_export(self.spec, first)
        result_two = analytics_export(self.spec, second)
        after = (file_sha(self.p5), file_sha(self.p6))
        self.assertEqual(
            result_one["export_sha256"],
            result_two["export_sha256"],
        )
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(before, after)
        payload = first.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), payload)
        self.assertNotIn("database_path", payload)
        parsed = json.loads(payload)
        material = {
            "schema_version": parsed["schema_version"],
            "quality": parsed["quality"],
            "analytics": parsed["analytics"],
        }
        expected = hashlib.sha256(canonical(material).encode()).hexdigest()
        self.assertEqual(parsed["export_sha256"], expected)

    def test_export_does_not_overwrite_by_default(self):
        target = self.root / "analytics-export.json"
        analytics_export(self.spec, target)
        original = target.read_bytes()
        with self.assertRaises(AnalyticsCliError) as caught:
            analytics_export(self.spec, target)
        self.assertEqual(caught.exception.code, AnalyticsCliCode.OUTPUT_EXISTS)
        self.assertEqual(target.read_bytes(), original)

    def test_explicit_overwrite_is_allowed_and_atomic_result_stays_canonical(self):
        target = self.root / "analytics-export.json"
        target.write_text("old", encoding="utf-8")
        result = analytics_export(self.spec, target, overwrite=True)
        self.assertEqual(result["code"], AnalyticsCliCode.EXPORTED.value)
        self.assertNotEqual(target.read_text(encoding="utf-8"), "old")
        self.assertEqual(json.loads(target.read_text())["export_sha256"], result["export_sha256"])
        leftovers = tuple(self.root.glob(".yatl-p7-export-*.tmp"))
        self.assertEqual(leftovers, ())

    def test_failed_quality_never_creates_export(self):
        target = self.root / "blocked.json"
        with self.p5.open("ab") as stream:
            stream.write(b"changed")
        result = analytics_export(self.spec, target)
        self.assertEqual(result["code"], AnalyticsCliCode.QUALITY_FAILED.value)
        self.assertFalse(target.exists())

    def test_cli_exit_codes_are_stable(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["validate", "--spec", str(self.spec)])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(output.getvalue())["code"], "VALIDATED")

        target = self.root / "export.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli.main(["export", "--spec", str(self.spec), "--output", str(target)]),
                EXIT_OK,
            )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["export", "--spec", str(self.spec), "--output", str(target)])
        self.assertEqual(code, EXIT_EXISTS)
        self.assertEqual(json.loads(output.getvalue())["code"], "OUTPUT_EXISTS")

        with self.p5.open("ab") as stream:
            stream.write(b"changed")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["validate", "--spec", str(self.spec)])
        self.assertEqual(code, EXIT_QUALITY)

    def test_cli_is_noninteractive(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=AssertionError("interactive input")):
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    cli.main(["summary", "--spec", str(self.spec)]),
                    EXIT_OK,
                )

    def test_rejected_argument_and_missing_path_are_never_echoed(self):
        marker = "DO_NOT_ECHO_ANALYTICS_SECRET_ARGUMENT"
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = cli.main(
                ["summary", "--spec", str(self.spec), "--endpoint", marker]
            )
        self.assertEqual(code, EXIT_INVALID)
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(str(self.spec), output.getvalue())

        missing = self.root / "PRIVATE-MISSING-ANALYTICS.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["summary", "--spec", str(missing)])
        self.assertEqual(code, EXIT_INVALID)
        self.assertNotIn(str(missing), output.getvalue())

    def test_secret_like_spec_is_rejected_without_echo(self):
        marker = "SUPER_SECRET_PASSWORD_VALUE"
        record = self.spec_record()
        record["password"] = marker
        self.write_spec(record)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["validate", "--spec", str(self.spec)])
        self.assertEqual(code, EXIT_INVALID)
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(str(self.spec), output.getvalue())

    def test_duplicate_json_keys_and_oversized_spec_are_rejected(self):
        self.spec.write_text(
            '{"schema_version":1,"schema_version":1}',
            encoding="utf-8",
        )
        with self.assertRaises(AnalyticsCliError):
            load_analytics_spec(self.spec)
        self.spec.write_bytes(b"x" * (cli.MAX_SPEC_BYTES + 1))
        with self.assertRaises(AnalyticsCliError):
            load_analytics_spec(self.spec)

    def test_trade_view_limit_is_bounded(self):
        with self.assertRaises(AnalyticsCliError):
            analytics_trades(self.spec, 0)
        with self.assertRaises(AnalyticsCliError):
            analytics_trades(self.spec, cli.MAX_TRADE_VIEW + 1)

    def test_cli_output_is_bounded_and_contains_no_source_path(self):
        for argv in (
            ["validate", "--spec", str(self.spec)],
            ["summary", "--spec", str(self.spec)],
            ["trades", "--spec", str(self.spec), "--limit", "25"],
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(argv), EXIT_OK)
            encoded = output.getvalue()
            self.assertLessEqual(
                len(encoded.encode("utf-8")),
                MAX_CLI_OUTPUT_BYTES + 1,
            )
            self.assertNotIn(str(self.root), encoded)
            self.assertNotIn("database_path", encoded)

    def test_source_has_no_execution_backtest_account_risk_network_or_provider_import(self):
        source = inspect.getsource(cli)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.backtest",
            "import yatl.backtest",
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
            "input(",
            "eval(",
            "exec(",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
