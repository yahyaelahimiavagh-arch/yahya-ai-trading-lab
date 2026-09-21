import hashlib
import inspect
import json
import unittest

from yatl.notifications import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    format_notification,
)
from yatl.notifications.delivery import (
    DELIVERY_GUARD_ID,
    MAX_ATTEMPTS,
    MAX_DELIVERY_RECORDS,
    MAX_RATE_LIMIT_WAIT_SECONDS,
    DeliveryGuardError,
    DeliveryGuardErrorCode,
    DeliveryGuardPolicy,
    DeliveryRecord,
    DeliveryState,
    DeliveryStatus,
    delivery_identity,
    delivery_state_from_record,
    guarded_send,
)
from yatl.notifications.transport import (
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportError,
    TelegramTransportErrorCode,
    TelegramTransportPolicy,
    send_formatted_notification,
)


OBSERVED_AT_MS = 1_800_000_000_000


def _credentials():
    token = "".join(("123456789", ":", "A" * 30))
    chat_id = "".join(("-", "100", "1234567890"))
    return TelegramCredentials(token, chat_id)


def _message(symbol="BTCUSDT", suffix="A"):
    source = NotificationSourceIdentity(
        source_id=f"P8_OVERVIEW_{symbol}",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=OBSERVED_AT_MS,
        payload_sha256=(suffix.lower() if suffix.lower() in "abcdef" else "7") * 64,
        symbol=symbol,
    )
    return NotificationMessage(
        notification_id=f"NOTICE_STATUS_{symbol}_{suffix * 12}",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title=f"YATL Paper status {symbol}",
        body=(
            f"Symbol {symbol}; P7 quality PASS; completed Paper trades 3; "
            "open trade count UNKNOWN; snapshot freshness UNKNOWN."
        ),
        source=source,
        event_time_ms=OBSERVED_AT_MS,
        symbol=symbol,
    )


def _receipt(message, formatted, message_id=42):
    return TelegramDeliveryReceipt(
        notification_sha256=message.message_sha256,
        formatted_sha256=formatted.formatted_sha256,
        telegram_message_id=message_id,
        policy_sha256=TelegramTransportPolicy().policy_sha256,
    )


class _RateLimitResponse:
    status = 429

    def __init__(self, retry_after):
        self.body = json.dumps(
            {
                "ok": False,
                "description": "rate limited provider detail",
                "parameters": {"retry_after": retry_after},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.read_limit = None

    def getheader(self, name):
        if name == "Content-Length":
            return str(len(self.body))
        return None

    def read(self, limit):
        self.read_limit = limit
        return self.body


class _RateLimitConnection:
    def __init__(self, host, port, *, timeout, context, response):
        self.response = response
        self.closed = False

    def request(self, method, path, *, body, headers):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class DeliveryGuardTests(unittest.TestCase):
    def test_policy_is_frozen_and_bounded(self):
        first = DeliveryGuardPolicy()
        second = DeliveryGuardPolicy()
        self.assertEqual(first, second)
        self.assertEqual(first.guard_id, DELIVERY_GUARD_ID)
        self.assertEqual(first.max_attempts, 3)
        self.assertEqual(first.network_backoff_seconds, (1, 2))
        self.assertEqual(first.max_rate_limit_wait_seconds, 30)
        self.assertEqual(first.max_total_wait_seconds, 60)
        self.assertFalse(first.persistent_storage)
        self.assertTrue(first.caller_managed_snapshot)
        self.assertFalse(first.upstream_mutation)
        self.assertFalse(first.control_loop)
        self.assertFalse(first.trade_permission)
        self.assertFalse(first.order_endpoint)
        self.assertFalse(first.ai_direct_execution)
        self.assertEqual(first.policy_sha256, second.policy_sha256)

    def test_delivery_identity_is_deterministic_and_canonical(self):
        message = _message()
        formatted = format_notification(message)
        first = delivery_identity(message, formatted)
        second = delivery_identity(message, formatted)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_delivery_identity_rejects_noncanonical_format(self):
        message = _message()
        formatted = format_notification(message)
        forged = type(formatted)(
            text=formatted.text + "x",
            notification_sha256=formatted.notification_sha256,
            formatted_sha256=hashlib.sha256(
                (formatted.text + "x").encode("utf-8")
            ).hexdigest(),
            char_count=formatted.char_count + 1,
        )
        with self.assertRaises(DeliveryGuardError) as caught:
            delivery_identity(message, forged)
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.INVALID_REQUEST,
        )

    def test_success_adds_one_secret_free_record_without_wait(self):
        message = _message()
        formatted = format_notification(message)
        calls = []

        def sender(item, rendered, credentials):
            calls.append(1)
            return _receipt(item, rendered)

        result = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=sender,
            sleep_fn=lambda seconds: self.fail("unexpected sleep"),
        )
        self.assertEqual(result.status, DeliveryStatus.DELIVERED)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.wait_seconds, ())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result.state.records), 1)
        record = result.state.records[0]
        self.assertEqual(record.delivery_id, result.delivery_id)
        self.assertEqual(record.receipt_sha256, result.receipt_sha256)
        material = json.dumps(result.state.as_record(), sort_keys=True)
        self.assertNotIn(_credentials().bot_token, material)
        self.assertNotIn(_credentials().chat_id, material)

    def test_duplicate_is_suppressed_before_sender(self):
        message = _message()
        formatted = format_notification(message)
        first = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=lambda item, rendered, credentials: _receipt(item, rendered),
            sleep_fn=lambda seconds: None,
        )

        def forbidden(*args, **kwargs):
            self.fail("duplicate attempted transport")

        duplicate = guarded_send(
            message,
            formatted,
            _credentials(),
            state=first.state,
            sender=forbidden,
            sleep_fn=lambda seconds: self.fail("duplicate slept"),
        )
        self.assertEqual(
            duplicate.status,
            DeliveryStatus.DUPLICATE_SUPPRESSED,
        )
        self.assertEqual(duplicate.attempts, 0)
        self.assertEqual(duplicate.wait_seconds, ())
        self.assertEqual(duplicate.delivery_id, first.delivery_id)
        self.assertEqual(duplicate.state, first.state)

    def test_reconstructed_snapshot_suppresses_duplicate_after_restart(self):
        message = _message()
        formatted = format_notification(message)
        first = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=lambda item, rendered, credentials: _receipt(item, rendered),
            sleep_fn=lambda seconds: None,
        )
        restored = delivery_state_from_record(first.state.as_record())
        self.assertEqual(restored, first.state)
        self.assertEqual(restored.state_sha256, first.state.state_sha256)

        duplicate = guarded_send(
            message,
            formatted,
            _credentials(),
            state=restored,
            sender=lambda *args, **kwargs: self.fail("restart duplicate sent"),
            sleep_fn=lambda seconds: self.fail("restart duplicate slept"),
        )
        self.assertEqual(
            duplicate.status,
            DeliveryStatus.DUPLICATE_SUPPRESSED,
        )

    def test_network_error_retries_with_fixed_backoff_then_succeeds(self):
        message = _message()
        formatted = format_notification(message)
        calls = []
        sleeps = []

        def sender(item, rendered, credentials):
            calls.append(1)
            if len(calls) < 3:
                raise TelegramTransportError(
                    TelegramTransportErrorCode.NETWORK_ERROR
                )
            return _receipt(item, rendered, message_id=99)

        result = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=sender,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(result.attempts, 3)
        self.assertEqual(result.wait_seconds, (1, 2))
        self.assertEqual(sleeps, [1, 2])
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.telegram_message_id, 99)

    def test_network_error_never_exceeds_max_attempts(self):
        message = _message()
        formatted = format_notification(message)
        calls = []
        sleeps = []

        def sender(item, rendered, credentials):
            calls.append(1)
            raise TelegramTransportError(
                TelegramTransportErrorCode.NETWORK_ERROR
            )

        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                message,
                formatted,
                _credentials(),
                sender=sender,
                sleep_fn=sleeps.append,
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.RETRY_EXHAUSTED,
        )
        self.assertEqual(len(calls), MAX_ATTEMPTS)
        self.assertEqual(sleeps, [1, 2])

    def test_rate_limit_waits_exact_safe_retry_after_then_succeeds(self):
        message = _message()
        formatted = format_notification(message)
        calls = []
        sleeps = []

        def sender(item, rendered, credentials):
            calls.append(1)
            if len(calls) == 1:
                raise TelegramTransportError(
                    TelegramTransportErrorCode.RATE_LIMITED,
                    retry_after_seconds=7,
                )
            return _receipt(item, rendered)

        result = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=sender,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.wait_seconds, (7,))
        self.assertEqual(sleeps, [7])

    def test_rate_limit_above_bound_fails_without_sleep_or_retry(self):
        message = _message()
        formatted = format_notification(message)
        calls = []
        sleeps = []

        def sender(item, rendered, credentials):
            calls.append(1)
            raise TelegramTransportError(
                TelegramTransportErrorCode.RATE_LIMITED,
                retry_after_seconds=MAX_RATE_LIMIT_WAIT_SECONDS + 1,
            )

        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                message,
                formatted,
                _credentials(),
                sender=sender,
                sleep_fn=sleeps.append,
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.WAIT_BOUND_EXCEEDED,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_rate_limit_at_final_attempt_is_not_extended(self):
        message = _message()
        formatted = format_notification(message)
        calls = []
        sleeps = []

        def sender(item, rendered, credentials):
            calls.append(1)
            if len(calls) < 3:
                raise TelegramTransportError(
                    TelegramTransportErrorCode.NETWORK_ERROR
                )
            raise TelegramTransportError(
                TelegramTransportErrorCode.RATE_LIMITED,
                retry_after_seconds=1,
            )

        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                message,
                formatted,
                _credentials(),
                sender=sender,
                sleep_fn=sleeps.append,
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.RETRY_EXHAUSTED,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1, 2])

    def test_nonretryable_transport_errors_fail_immediately(self):
        codes = (
            TelegramTransportErrorCode.HTTP_STATUS,
            TelegramTransportErrorCode.RESPONSE_TOO_LARGE,
            TelegramTransportErrorCode.RESPONSE_INVALID,
            TelegramTransportErrorCode.API_REJECTED,
            TelegramTransportErrorCode.CONFIG_MISSING,
            TelegramTransportErrorCode.CONFIG_INVALID,
            TelegramTransportErrorCode.REQUEST_INVALID,
        )
        for code in codes:
            with self.subTest(code=code):
                calls = []
                sleeps = []

                def sender(item, rendered, credentials, selected=code):
                    calls.append(1)
                    raise TelegramTransportError(selected)

                with self.assertRaises(DeliveryGuardError) as caught:
                    guarded_send(
                        _message(),
                        format_notification(_message()),
                        _credentials(),
                        sender=sender,
                        sleep_fn=sleeps.append,
                    )
                self.assertEqual(
                    caught.exception.code,
                    DeliveryGuardErrorCode.TRANSPORT_REJECTED,
                )
                self.assertEqual(len(calls), 1)
                self.assertEqual(sleeps, [])

    def test_forged_receipt_is_rejected_and_not_recorded(self):
        message = _message()
        formatted = format_notification(message)

        def sender(item, rendered, credentials):
            return TelegramDeliveryReceipt(
                notification_sha256=item.message_sha256,
                formatted_sha256=rendered.formatted_sha256,
                telegram_message_id=42,
                policy_sha256="0" * 64,
            )

        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                message,
                formatted,
                _credentials(),
                sender=sender,
                sleep_fn=lambda seconds: None,
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.RECEIPT_INVALID,
        )

    def test_state_reconstruction_rejects_unknown_fields(self):
        record = DeliveryState().as_record()
        record["authority"] = "TRADE"
        with self.assertRaises(DeliveryGuardError) as caught:
            delivery_state_from_record(record)
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.STATE_INVALID,
        )

    def test_state_reconstruction_rejects_record_schema_smuggling(self):
        message = _message()
        formatted = format_notification(message)
        first = guarded_send(
            message,
            formatted,
            _credentials(),
            sender=lambda item, rendered, credentials: _receipt(item, rendered),
            sleep_fn=lambda seconds: None,
        )
        record = first.state.as_record()
        record["records"][0]["trade_permission"] = True
        with self.assertRaises(DeliveryGuardError) as caught:
            delivery_state_from_record(record)
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.STATE_INVALID,
        )

    def test_state_rejects_duplicate_and_unordered_identities(self):
        def record(identity):
            return DeliveryRecord(
                delivery_id=identity,
                notification_sha256="1" * 64,
                formatted_sha256="2" * 64,
                receipt_sha256="3" * 64,
                telegram_message_id=1,
                attempts=1,
                total_wait_seconds=0,
            )

        a = "a" * 64
        b = "b" * 64
        with self.assertRaises(DeliveryGuardError):
            DeliveryState((record(a), record(a)))
        with self.assertRaises(DeliveryGuardError):
            DeliveryState((record(b), record(a)))

    def test_full_state_fails_before_transport(self):
        records = []
        for index in range(MAX_DELIVERY_RECORDS):
            identity = hashlib.sha256(str(index).encode("utf-8")).hexdigest()
            records.append(
                DeliveryRecord(
                    delivery_id=identity,
                    notification_sha256="1" * 64,
                    formatted_sha256="2" * 64,
                    receipt_sha256="3" * 64,
                    telegram_message_id=index + 1,
                    attempts=1,
                    total_wait_seconds=0,
                )
            )
        state = DeliveryState(tuple(sorted(records, key=lambda item: item.delivery_id)))
        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                _message(),
                format_notification(_message()),
                _credentials(),
                state=state,
                sender=lambda *args, **kwargs: self.fail("full state sent"),
                sleep_fn=lambda seconds: self.fail("full state slept"),
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.STATE_FULL,
        )

    def test_invalid_state_type_is_rejected_before_transport(self):
        with self.assertRaises(DeliveryGuardError) as caught:
            guarded_send(
                _message(),
                format_notification(_message()),
                _credentials(),
                state={},
                sender=lambda *args, **kwargs: self.fail("invalid state sent"),
                sleep_fn=lambda seconds: None,
            )
        self.assertEqual(
            caught.exception.code,
            DeliveryGuardErrorCode.INVALID_REQUEST,
        )

    def test_transport_parses_429_retry_after_without_exposing_provider_text(self):
        response = _RateLimitResponse(9)
        bucket = {}

        def factory(host, port, *, timeout, context):
            connection = _RateLimitConnection(
                host,
                port,
                timeout=timeout,
                context=context,
                response=response,
            )
            bucket["connection"] = connection
            return connection

        message = _message()
        formatted = format_notification(message)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message,
                formatted,
                _credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.RATE_LIMITED,
        )
        self.assertEqual(caught.exception.retry_after_seconds, 9)
        self.assertEqual(str(caught.exception), "TELEGRAM_RATE_LIMITED")
        self.assertNotIn("provider detail", str(caught.exception))
        self.assertTrue(bucket["connection"].closed)

    def test_transport_rejects_malformed_429_retry_after(self):
        response = _RateLimitResponse(0)

        def factory(host, port, *, timeout, context):
            return _RateLimitConnection(
                host,
                port,
                timeout=timeout,
                context=context,
                response=response,
            )

        message = _message()
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message,
                format_notification(message),
                _credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.RESPONSE_INVALID,
        )

    def test_delivery_source_has_no_network_env_or_filesystem_authority(self):
        import yatl.notifications.delivery as delivery

        source = inspect.getsource(delivery)
        forbidden = (
            "http.client",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "ssl.",
            "os.environ",
            "os.getenv",
            "pathlib",
            "sqlite3",
            "open(",
            "write_text",
            "write_bytes",
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "openai",
            "anthropic",
        )
        for item in forbidden:
            with self.subTest(item=item):
                self.assertNotIn(item, source)

    def test_delivery_source_has_no_unbounded_control_loop(self):
        import yatl.notifications.delivery as delivery

        source = inspect.getsource(delivery)
        self.assertNotIn("while ", source)
        self.assertIn("range(1, policy.max_attempts + 1)", source)


if __name__ == "__main__":
    unittest.main()
