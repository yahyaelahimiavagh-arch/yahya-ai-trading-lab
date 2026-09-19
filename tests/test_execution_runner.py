import contextlib
import inspect
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yatl.__main__ import _paper_execution_contract_runtime_check
from yatl.backtest import BacktestSpec
from yatl.execution import (
    ExecutionIntentJournal,
    LocalOrderEventType,
    LocalPaperOrderStore,
    LocalPaperPortfolioStore,
    build_local_order_event,
    create_recovery_snapshot,
)
from yatl.execution import runner
from yatl.execution.runner import (
    EXIT_INVALID,
    EXIT_NOT_READY,
    EXIT_READY,
    MAX_OUTPUT_BYTES,
    OperatorCode,
    OperatorError,
    load_operator_spec,
    operator_reconcile,
    operator_recover,
    operator_status,
)


HOUR = 3_600_000


def spec_record(spec):
    return {
        "symbol": spec.symbol,
        "start_time_ms": spec.start_time_ms,
        "end_time_ms": spec.end_time_ms,
        "initial_cash": spec.initial_cash,
        "fee_bps": spec.fee_bps,
        "slippage_bps": spec.slippage_bps,
        "seed": spec.seed,
        "paper_only": spec.paper_only,
        "live_master_lock": spec.live_master_lock,
        "spot_only": spec.spot_only,
        "allow_short": spec.allow_short,
        "allow_leverage": spec.allow_leverage,
        "execution_price_policy": spec.execution_price_policy,
    }


class OperatorRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.entry_decision, _ = _paper_execution_contract_runtime_check()
        cls.entry_time = (
            cls.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.database = root / "execution.sqlite3"
        self.snapshot = root / "execution.snapshot.json"
        self.spec_path = root / "spec.json"
        self.spec = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.entry_time + 2 * HOUR,
            initial_cash="10000",
            fee_bps="10",
            slippage_bps="5",
        )
        self.spec_path.write_text(
            json.dumps(spec_record(self.spec), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with ExecutionIntentJournal(self.database):
            pass
        with LocalPaperOrderStore(self.database):
            pass
        with LocalPaperPortfolioStore(self.database, self.spec):
            pass

    def tearDown(self):
        self.temporary.cleanup()

    def _active_order(self):
        with ExecutionIntentJournal(self.database) as journal:
            intent = journal.record(self.entry_decision)
        decision_time = (
            self.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )
        with LocalPaperOrderStore(self.database) as store:
            created = store.apply(build_local_order_event(
                intent,
                0,
                decision_time - 2,
                LocalOrderEventType.CREATE,
            )).current
            active = store.apply(build_local_order_event(
                intent,
                1,
                decision_time - 1,
                LocalOrderEventType.ACTIVATE,
                created,
            )).current
        return intent, active

    def test_spec_loader_is_exact_bounded_and_safe(self):
        self.assertEqual(load_operator_spec(self.spec_path), self.spec)
        raw = spec_record(self.spec)
        raw["endpoint"] = "https://example.invalid"
        self.spec_path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(OperatorError) as caught:
            load_operator_spec(self.spec_path)
        self.assertEqual(caught.exception.code, OperatorCode.INVALID_SPEC)
        self.spec_path.write_bytes(b"x" * (runner.MAX_SPEC_BYTES + 1))
        with self.assertRaises(OperatorError):
            load_operator_spec(self.spec_path)

    def test_missing_snapshot_status_is_ready_from_authoritative_journal(self):
        report = operator_status(self.database, self.snapshot, self.spec)
        self.assertTrue(report.ok)
        self.assertTrue(report.ready)
        self.assertEqual(report.code, OperatorCode.READY)
        self.assertEqual(report.source_code, "JOURNAL_REBUILD_READY")
        self.assertIsNone(report.snapshot_sha256)

    def test_reconcile_is_read_only_ready_and_deterministic(self):
        first = operator_reconcile(self.database, self.spec)
        second = operator_reconcile(self.database, self.spec)
        self.assertEqual(first, second)
        self.assertTrue(first.ready)
        self.assertEqual(first.source_code, "MATCH")
        self.assertEqual((first.intents, first.orders, first.fills), (0, 0, 0))

    def test_explicit_snapshot_creation_is_idempotent(self):
        first = operator_recover(
            self.database, self.snapshot, self.spec, create_snapshot=True
        )
        self.assertEqual(first.code, OperatorCode.SNAPSHOT_CREATED)
        self.assertTrue(first.ready)
        self.assertTrue(self.snapshot.is_file())
        second = operator_recover(
            self.database, self.snapshot, self.spec, create_snapshot=True
        )
        self.assertEqual(second.code, OperatorCode.SNAPSHOT_PRESENT)
        self.assertTrue(second.ready)
        self.assertEqual(second.snapshot_sha256, first.snapshot_sha256)

    def test_corrupt_snapshot_fails_closed_and_is_not_auto_repaired(self):
        self.snapshot.write_text("{", encoding="utf-8")
        status = operator_status(self.database, self.snapshot, self.spec)
        self.assertFalse(status.ready)
        self.assertEqual(status.source_code, "SNAPSHOT_CORRUPT")
        action = operator_recover(
            self.database, self.snapshot, self.spec, create_snapshot=True
        )
        self.assertFalse(action.ok)
        self.assertEqual(action.code, OperatorCode.ACTION_REFUSED)
        self.assertEqual(self.snapshot.read_text(encoding="utf-8"), "{")

    def test_exact_pending_confirmation_is_required(self):
        create_recovery_snapshot(self.database, self.snapshot, self.spec)
        pending = Path(f"{self.snapshot}.pending")
        shutil.copyfile(self.snapshot, pending)
        status = operator_status(self.database, self.snapshot, self.spec)
        self.assertFalse(status.ready)
        self.assertEqual(status.source_code, "AMBIGUOUS_COMMIT")
        self.assertIsNotNone(status.confirmation_sha256)
        wrong = operator_recover(
            self.database,
            self.snapshot,
            self.spec,
            confirmation="0" * 64,
        )
        self.assertFalse(wrong.ok)
        self.assertEqual(wrong.code, OperatorCode.ACTION_REFUSED)
        self.assertTrue(pending.exists())
        confirmed = operator_recover(
            self.database,
            self.snapshot,
            self.spec,
            confirmation=status.confirmation_sha256,
        )
        self.assertTrue(confirmed.ok)
        self.assertTrue(confirmed.ready)
        self.assertEqual(confirmed.code, OperatorCode.PENDING_CONFIRMED)
        self.assertEqual(confirmed.source_code, "MATCH")
        self.assertFalse(pending.exists())

    def test_zero_byte_pending_confirmation_remains_explicit(self):
        pending = Path(f"{self.snapshot}.pending")
        pending.touch()
        status = operator_status(self.database, self.snapshot, self.spec)
        self.assertEqual(status.source_code, "AMBIGUOUS_COMMIT")
        confirmed = operator_recover(
            self.database,
            self.snapshot,
            self.spec,
            confirmation=status.confirmation_sha256,
        )
        self.assertTrue(confirmed.ready)
        self.assertEqual(confirmed.source_code, "JOURNAL_REBUILD_READY")
        self.assertFalse(pending.exists())

    def test_stale_snapshot_tail_is_reported_but_not_rewritten(self):
        intent, active = self._active_order()
        create_recovery_snapshot(self.database, self.snapshot, self.spec)
        before = self.snapshot.read_bytes()
        with LocalPaperOrderStore(self.database) as store:
            store.apply(build_local_order_event(
                intent,
                2,
                active.updated_time_ms + 1,
                LocalOrderEventType.CANCEL,
                active,
            ))
        status = operator_status(self.database, self.snapshot, self.spec)
        self.assertTrue(status.ready)
        self.assertEqual(status.source_code, "TAIL_REPLAYED")
        self.assertEqual(status.tail_order_events, 1)
        attempted = operator_recover(
            self.database, self.snapshot, self.spec, create_snapshot=True
        )
        self.assertFalse(attempted.ok)
        self.assertTrue(attempted.ready)
        self.assertEqual(attempted.code, OperatorCode.ACTION_REFUSED)
        self.assertEqual(self.snapshot.read_bytes(), before)

    def test_json_and_text_outputs_are_deterministic_bounded_and_path_free(self):
        report = operator_status(self.database, self.snapshot, self.spec)
        self.assertEqual(report.to_json(), report.to_json())
        self.assertEqual(report.to_text(), report.to_text())
        for output in (report.to_json(), report.to_text()):
            self.assertLessEqual(len(output.encode("utf-8")), MAX_OUTPUT_BYTES)
            self.assertNotIn(str(self.database), output)
            self.assertNotIn(str(self.snapshot), output)
            self.assertNotIn(str(self.spec_path), output)

    def test_cli_is_noninteractive_with_stable_exit_codes(self):
        argv = [
            "status",
            "--database", str(self.database),
            "--snapshot", str(self.snapshot),
            "--spec", str(self.spec_path),
            "--format", "json",
        ]
        output = io.StringIO()
        with patch("builtins.input", side_effect=AssertionError("interactive input")):
            with contextlib.redirect_stdout(output):
                first = runner.main(argv)
            replay = io.StringIO()
            with contextlib.redirect_stdout(replay):
                second = runner.main(argv)
        self.assertEqual((first, second), (EXIT_READY, EXIT_READY))
        self.assertEqual(output.getvalue(), replay.getvalue())
        record = json.loads(output.getvalue())
        self.assertTrue(record["ready"])

        self.snapshot.write_text("{", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(argv), EXIT_NOT_READY)

    def test_rejected_cli_arguments_never_echo_values(self):
        marker = "DO_NOT_ECHO_REJECTED_ARGUMENT"
        output = io.StringIO()
        errors = io.StringIO()
        argv = [
            "status",
            "--database", str(self.database),
            "--snapshot", str(self.snapshot),
            "--spec", str(self.spec_path),
            "--endpoint", marker,
        ]
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            exit_code = runner.main(argv)
        self.assertEqual(exit_code, EXIT_INVALID)
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(str(self.database), output.getvalue())
        record = json.loads(output.getvalue())
        self.assertEqual(record["command"], "invalid")
        self.assertEqual(record["code"], "INVALID_REQUEST")

    def test_invalid_spec_cli_never_echoes_payload_or_path(self):
        marker = "DO_NOT_ECHO_THIS_SECRET_LIKE_VALUE"
        self.spec_path.write_text(marker, encoding="utf-8")
        argv = [
            "reconcile",
            "--database", str(self.database),
            "--spec", str(self.spec_path),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = runner.main(argv)
        self.assertEqual(exit_code, EXIT_INVALID)
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(str(self.spec_path), output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["code"], "INVALID_SPEC")

    def test_runner_source_has_no_external_or_secret_capability(self):
        source = inspect.getsource(runner)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "websockets",
            "socket",
            "API_KEY",
            "API_SECRET",
            "importlib",
            "eval(",
            "exec(",
            "input(",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
