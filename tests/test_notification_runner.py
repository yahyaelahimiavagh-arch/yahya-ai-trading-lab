import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from yatl.notifications import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    build_notification_batch,
)
from yatl.notifications.delivery import DeliveryState
from yatl.notifications.runner import (
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_SOURCE,
    NotifierRunnerCode,
    NotifierRunnerError,
    load_delivery_state,
    load_notification_source,
    main,
    notifier_run,
)
from yatl.notifications.transport import (
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportPolicy,
)


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _credentials():
    return TelegramCredentials(
        "".join(("123456789", ":", "A" * 30)),
        "".join(("-", "100", "1234567890")),
    )


def _batch(symbol="BTCUSDT", suffix="8"):
    source = NotificationSourceIdentity(
        source_id=f"P8_STATUS_{symbol}",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=1_800_000_000_000,
        payload_sha256=suffix * 64,
        symbol=symbol,
    )
    message = NotificationMessage(
        notification_id=f"NOTICE_STATUS_{symbol}",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title=f"YATL Paper status {symbol}",
        body=f"Accepted {symbol} Paper status is ready for information-only delivery.",
        source=source,
        event_time_ms=1_799_999_999_000,
        symbol=symbol,
    )
    return build_notification_batch(message)


def _sender(message_id=42):
    def sender(message, formatted, credentials):
        return TelegramDeliveryReceipt(
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            telegram_message_id=message_id,
            policy_sha256=TelegramTransportPolicy().policy_sha256,
        )
    return sender


class NotifierRunnerTests(unittest.TestCase):
    def _source(self, root, batch=None):
        batch = _batch() if batch is None else batch
        path = root / "notification.json"
        path.write_text(_json(batch.as_record()), encoding="utf-8", newline="")
        return batch, path

    def test_loads_one_exact_canonical_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            loaded, raw = load_notification_source(
                source,
                batch.batch_sha256,
                "BTCUSDT",
            )
            self.assertEqual(loaded, batch)
            self.assertEqual(raw, source.read_bytes())

    def test_rejects_noncanonical_source_even_if_semantics_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = _batch()
            source = root / "notification.json"
            source.write_text(
                json.dumps(batch.as_record(), indent=2),
                encoding="utf-8",
            )
            with self.assertRaises(NotifierRunnerError) as caught:
                load_notification_source(
                    source,
                    batch.batch_sha256,
                    "BTCUSDT",
                )
            self.assertEqual(
                caught.exception.code,
                NotifierRunnerCode.SOURCE_REJECTED,
            )

    def test_rejects_expected_hash_mismatch_and_cross_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            with self.assertRaises(NotifierRunnerError):
                load_notification_source(source, "0" * 64, "BTCUSDT")
            with self.assertRaises(NotifierRunnerError):
                load_notification_source(source, batch.batch_sha256, "ETHUSDT")

    def test_rejects_batch_with_more_than_one_notification(self):
        first = _batch("BTCUSDT").notifications[0]
        second = NotificationMessage(
            notification_id="NOTICE_STATUS_BTC_SECOND",
            category=first.category,
            severity=first.severity,
            title=first.title,
            body=first.body,
            source=first.source,
            event_time_ms=first.event_time_ms,
            symbol=first.symbol,
        )
        batch = build_notification_batch(first, second)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, source = self._source(root, batch)
            with self.assertRaises(NotifierRunnerError) as caught:
                load_notification_source(source, batch.batch_sha256, "BTCUSDT")
            self.assertEqual(
                caught.exception.code,
                NotifierRunnerCode.SOURCE_REJECTED,
            )

    def test_missing_state_is_empty_and_noncanonical_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            self.assertEqual(load_delivery_state(state), DeliveryState())
            state.write_text('{"records": [], "schema_version": 1}', encoding="utf-8")
            with self.assertRaises(NotifierRunnerError) as caught:
                load_delivery_state(state)
            self.assertEqual(
                caught.exception.code,
                NotifierRunnerCode.STATE_REJECTED,
            )

    def test_success_persists_state_atomically_and_never_mutates_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            state = root / "state.json"
            source_before = source.read_bytes()
            result = notifier_run(
                source,
                batch.batch_sha256,
                state,
                "BTCUSDT",
                credentials=_credentials(),
                sender=_sender(1001),
                sleep_fn=lambda seconds: None,
            )
            self.assertEqual(result["code"], NotifierRunnerCode.DELIVERED.value)
            self.assertEqual(result["attempts"], 1)
            self.assertFalse(result["duplicate_suppressed"])
            self.assertTrue(state.is_file())
            restored = load_delivery_state(state)
            self.assertEqual(restored.state_sha256, result["delivery_state_sha256"])
            self.assertEqual(source.read_bytes(), source_before)
            leftovers = [
                item for item in root.iterdir()
                if item.name.startswith(".state.json.")
            ]
            self.assertEqual(leftovers, [])

    def test_duplicate_suppression_happens_before_credentials_and_sender(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            state = root / "state.json"
            first = notifier_run(
                source,
                batch.batch_sha256,
                state,
                "BTCUSDT",
                credentials=_credentials(),
                sender=_sender(1002),
                sleep_fn=lambda seconds: None,
            )
            state_before = state.read_bytes()

            def forbidden(*args, **kwargs):
                self.fail("duplicate reached sender")

            second = notifier_run(
                source,
                batch.batch_sha256,
                state,
                "BTCUSDT",
                environ={},
                sender=forbidden,
                sleep_fn=lambda seconds: self.fail("duplicate slept"),
            )
            self.assertEqual(
                second["code"],
                NotifierRunnerCode.DUPLICATE_SUPPRESSED.value,
            )
            self.assertEqual(second["attempts"], 0)
            self.assertEqual(second["delivery_id"], first["delivery_id"])
            self.assertEqual(state.read_bytes(), state_before)

    def test_same_input_and_state_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            with self.assertRaises(NotifierRunnerError) as caught:
                notifier_run(
                    source,
                    batch.batch_sha256,
                    source,
                    "BTCUSDT",
                    credentials=_credentials(),
                    sender=_sender(),
                    sleep_fn=lambda seconds: None,
                )
            self.assertEqual(
                caught.exception.code,
                NotifierRunnerCode.INVALID_REQUEST,
            )

    def test_source_mutation_is_detected_but_success_state_is_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            state = root / "state.json"

            def mutating_sender(message, formatted, credentials):
                source.write_bytes(source.read_bytes() + b" ")
                return _sender(1003)(message, formatted, credentials)

            with self.assertRaises(NotifierRunnerError) as caught:
                notifier_run(
                    source,
                    batch.batch_sha256,
                    state,
                    "BTCUSDT",
                    credentials=_credentials(),
                    sender=mutating_sender,
                    sleep_fn=lambda seconds: None,
                )
            self.assertEqual(
                caught.exception.code,
                NotifierRunnerCode.SOURCE_MUTATED,
            )
            self.assertTrue(state.is_file())
            self.assertEqual(len(load_delivery_state(state).records), 1)

    def test_cli_success_duplicate_and_config_exit_codes_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            state = root / "state.json"
            argv = [
                "--input", str(source),
                "--expected-batch-sha256", batch.batch_sha256,
                "--state", str(state),
                "--symbol", "BTCUSDT",
            ]
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                first = main(
                    argv,
                    credentials=_credentials(),
                    sender=_sender(1004),
                    sleep_fn=lambda seconds: None,
                )
            first_record = json.loads(stream.getvalue())
            self.assertEqual(first, EXIT_OK)
            self.assertEqual(first_record["code"], "DELIVERED")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                duplicate = main(
                    argv,
                    environ={},
                    sender=lambda *args, **kwargs: self.fail("duplicate sent"),
                    sleep_fn=lambda seconds: None,
                )
            duplicate_record = json.loads(stream.getvalue())
            self.assertEqual(duplicate, EXIT_OK)
            self.assertEqual(duplicate_record["code"], "DUPLICATE_SUPPRESSED")

            state.unlink()
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                config = main(
                    argv,
                    environ={},
                    sender=_sender(),
                    sleep_fn=lambda seconds: None,
                )
            config_record = json.loads(stream.getvalue())
            self.assertEqual(config, EXIT_CONFIG)
            self.assertEqual(config_record["code"], "CONFIG_REJECTED")

    def test_cli_invalid_request_and_secret_source_are_redacted(self):
        secret_marker = "SENSITIVE_LOCAL_SECRET"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / f"{secret_marker}.json"
            state = root / "state.json"
            source.write_text(
                '{"body":"bot token SENSITIVE_LOCAL_SECRET"}\n',
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                exit_code = main([
                    "--input", str(source),
                    "--expected-batch-sha256", "0" * 64,
                    "--state", str(state),
                    "--symbol", "BTCUSDT",
                ])
            output = stream.getvalue()
            self.assertEqual(exit_code, EXIT_SOURCE)
            self.assertNotIn(secret_marker, output)
            self.assertNotIn(str(source), output)
            self.assertEqual(json.loads(output)["code"], "SOURCE_REJECTED")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                invalid = main(["--unexpected", secret_marker])
            output = stream.getvalue()
            self.assertEqual(invalid, EXIT_INVALID)
            self.assertNotIn(secret_marker, output)
            self.assertEqual(json.loads(output)["code"], "INVALID_REQUEST")

    def test_cli_unexpected_sender_failure_is_redacted_internal_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, source = self._source(root)
            state = root / "state.json"
            marker = "SENSITIVE_RUNTIME_DETAIL"

            def broken_sender(*args, **kwargs):
                raise RuntimeError(marker)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                exit_code = main(
                    [
                        "--input", str(source),
                        "--expected-batch-sha256", batch.batch_sha256,
                        "--state", str(state),
                        "--symbol", "BTCUSDT",
                    ],
                    credentials=_credentials(),
                    sender=broken_sender,
                    sleep_fn=lambda seconds: None,
                )
            output = stream.getvalue()
            self.assertEqual(exit_code, EXIT_INTERNAL)
            self.assertEqual(json.loads(output)["code"], "INTERNAL_ERROR")
            self.assertNotIn(marker, output)
            self.assertNotIn(str(source), output)
            self.assertFalse(state.exists())

    def test_runner_source_has_no_direct_network_or_control_surface(self):
        import inspect
        import yatl.notifications.runner as runner

        source = inspect.getsource(runner)
        for forbidden in (
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "ssl.",
            "add_subparsers",
            "input(",
            "eval(",
            "exec(",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "getUpdates",
            "setWebhook",
            "answerCallbackQuery",
            "openai",
            "anthropic",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
