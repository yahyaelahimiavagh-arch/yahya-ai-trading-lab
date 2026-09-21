import inspect
import json
import os
import unittest
from unittest.mock import patch

from yatl.notifications import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    format_notification,
)
from yatl.notifications.transport import (
    TELEGRAM_CHAT_ID_ENV,
    TELEGRAM_HOST,
    TELEGRAM_MAX_RESPONSE_BYTES,
    TELEGRAM_METHOD,
    TELEGRAM_PATH_SUFFIX,
    TELEGRAM_PORT,
    TELEGRAM_TIMEOUT_SECONDS,
    TELEGRAM_TOKEN_ENV,
    TelegramCredentials,
    TelegramTransportError,
    TelegramTransportErrorCode,
    TelegramTransportPolicy,
    load_telegram_credentials,
    send_formatted_notification,
)


TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
CHAT_ID = "-1001234567890"
OBSERVED_AT_MS = 1_800_000_000_000


def message():
    source = NotificationSourceIdentity(
        source_id="P8_OVERVIEW_BTCUSDT",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=OBSERVED_AT_MS,
        payload_sha256="7" * 64,
        symbol="BTCUSDT",
    )
    return NotificationMessage(
        notification_id="NOTICE_STATUS_BTCUSDT_777777777777",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title="YATL Paper status BTCUSDT",
        body=(
            "Symbol BTCUSDT; P7 quality PASS; completed Paper trades 3; "
            "open trade count UNKNOWN; snapshot freshness UNKNOWN."
        ),
        source=source,
        event_time_ms=OBSERVED_AT_MS,
        symbol="BTCUSDT",
    )


class FakeResponse:
    def __init__(self, *, status=200, payload=None, raw=None, content_length=True):
        self.status = status
        if raw is None:
            raw = json.dumps(
                payload
                if payload is not None
                else {"ok": True, "result": {"message_id": 42}},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        self.raw = raw
        self.content_length = content_length
        self.read_limit = None

    def getheader(self, name):
        if name != "Content-Length" or self.content_length is False:
            return None
        if isinstance(self.content_length, str):
            return self.content_length
        return str(len(self.raw))

    def read(self, limit):
        self.read_limit = limit
        return self.raw


class FakeConnection:
    def __init__(self, host, port, *, timeout, context, response=None, request_error=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.response = response or FakeResponse()
        self.request_error = request_error
        self.request_record = None
        self.closed = False

    def request(self, method, path, *, body, headers):
        if self.request_error is not None:
            raise self.request_error
        self.request_record = {
            "method": method,
            "path": path,
            "body": body,
            "headers": headers,
        }

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def factory_for(response=None, request_error=None, bucket=None):
    bucket = {} if bucket is None else bucket

    def factory(host, port, *, timeout, context):
        connection = FakeConnection(
            host,
            port,
            timeout=timeout,
            context=context,
            response=response,
            request_error=request_error,
        )
        bucket["connection"] = connection
        return connection

    return factory, bucket


class TelegramTransportTests(unittest.TestCase):
    def credentials(self):
        return TelegramCredentials(TOKEN, CHAT_ID)

    def test_policy_is_frozen_send_only_and_deterministic(self):
        first = TelegramTransportPolicy()
        second = TelegramTransportPolicy()
        self.assertEqual(first, second)
        self.assertEqual(first.policy_sha256, second.policy_sha256)
        self.assertEqual(first.host, TELEGRAM_HOST)
        self.assertEqual(first.port, TELEGRAM_PORT)
        self.assertEqual(first.method, TELEGRAM_METHOD)
        self.assertEqual(first.path_suffix, TELEGRAM_PATH_SUFFIX)
        self.assertTrue(first.tls_required)
        self.assertTrue(first.outbound_only)
        self.assertTrue(first.send_message_only)
        self.assertEqual(first.parse_mode, "NONE")
        self.assertFalse(first.redirects_allowed)
        self.assertFalse(first.proxies_allowed)
        self.assertFalse(first.inbound_updates_allowed)
        self.assertFalse(first.inbound_commands_allowed)
        self.assertFalse(first.callback_actions_allowed)
        self.assertFalse(first.webhook_receiver_allowed)
        self.assertFalse(first.polling_receiver_allowed)
        self.assertFalse(first.execution_control_allowed)
        self.assertFalse(first.live_control_allowed)
        self.assertFalse(first.trade_permission)
        self.assertFalse(first.order_endpoint)
        self.assertFalse(first.ai_direct_execution)

    def test_credentials_repr_hides_token_and_chat_id(self):
        credentials = self.credentials()
        rendered = repr(credentials)
        self.assertNotIn(TOKEN, rendered)
        self.assertNotIn(CHAT_ID, rendered)

    def test_credentials_reject_invalid_token_or_chat_id_with_stable_error(self):
        for token, chat_id in (
            ("bad-token", CHAT_ID),
            (TOKEN, "not-a-chat"),
            (TOKEN + "/extra", CHAT_ID),
            (TOKEN, "@channel"),
        ):
            with self.subTest(token=token[:8], chat_id=chat_id):
                with self.assertRaises(TelegramTransportError) as caught:
                    TelegramCredentials(token, chat_id)
                self.assertEqual(
                    caught.exception.code,
                    TelegramTransportErrorCode.CONFIG_INVALID,
                )
                self.assertEqual(str(caught.exception), "TELEGRAM_CONFIG_INVALID")
                self.assertNotIn(token, str(caught.exception))
                self.assertNotIn(chat_id, str(caught.exception))

    def test_loader_reads_only_dedicated_environment_values(self):
        credentials = load_telegram_credentials(
            {
                TELEGRAM_TOKEN_ENV: TOKEN,
                TELEGRAM_CHAT_ID_ENV: CHAT_ID,
                "UNRELATED_SECRET": "do-not-read",
            }
        )
        self.assertEqual(credentials, self.credentials())

    def test_loader_supports_real_environment_boundary_without_logging(self):
        with patch.dict(
            os.environ,
            {
                TELEGRAM_TOKEN_ENV: TOKEN,
                TELEGRAM_CHAT_ID_ENV: CHAT_ID,
            },
            clear=True,
        ):
            credentials = load_telegram_credentials()
        self.assertEqual(credentials, self.credentials())
        self.assertNotIn(TOKEN, repr(credentials))
        self.assertNotIn(CHAT_ID, repr(credentials))

    def test_loader_missing_configuration_is_stable_and_redacted(self):
        with self.assertRaises(TelegramTransportError) as caught:
            load_telegram_credentials({})
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.CONFIG_MISSING,
        )
        self.assertEqual(str(caught.exception), "TELEGRAM_CONFIG_MISSING")

    def test_success_uses_exact_host_method_path_json_and_tls(self):
        formatted = format_notification(message())
        factory, bucket = factory_for()
        receipt = send_formatted_notification(
            message(),
            formatted,
            self.credentials(),
            connection_factory=factory,
        )
        connection = bucket["connection"]
        request = connection.request_record
        self.assertEqual(connection.host, TELEGRAM_HOST)
        self.assertEqual(connection.port, TELEGRAM_PORT)
        self.assertEqual(connection.timeout, TELEGRAM_TIMEOUT_SECONDS)
        self.assertTrue(connection.context.check_hostname)
        self.assertEqual(request["method"], TELEGRAM_METHOD)
        self.assertEqual(
            request["path"],
            f"/bot{TOKEN}{TELEGRAM_PATH_SUFFIX}",
        )
        body = json.loads(request["body"].decode("utf-8"))
        self.assertEqual(body, {"chat_id": CHAT_ID, "text": formatted.text})
        self.assertNotIn("parse_mode", body)
        self.assertEqual(
            request["headers"]["Content-Type"],
            "application/json; charset=utf-8",
        )
        self.assertEqual(request["headers"]["Accept"], "application/json")
        self.assertEqual(request["headers"]["Connection"], "close")
        self.assertTrue(connection.closed)
        self.assertEqual(receipt.notification_sha256, message().message_sha256)
        self.assertEqual(receipt.formatted_sha256, formatted.formatted_sha256)
        self.assertEqual(receipt.telegram_message_id, 42)
        self.assertNotIn(TOKEN, json.dumps(receipt.as_record()))
        self.assertNotIn(CHAT_ID, json.dumps(receipt.as_record()))

    def test_transport_rejects_noncanonical_formatted_message(self):
        original = message()
        formatted = format_notification(original)
        forged = type(formatted)(
            text=formatted.text + "x",
            notification_sha256=formatted.notification_sha256,
            formatted_sha256=__import__("hashlib").sha256(
                (formatted.text + "x").encode("utf-8")
            ).hexdigest(),
            char_count=formatted.char_count + 1,
        )
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                original,
                forged,
                self.credentials(),
                connection_factory=factory_for()[0],
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.REQUEST_INVALID,
        )

    def test_transport_rejects_non_notification_or_non_formatted_input(self):
        formatted = format_notification(message())
        with self.assertRaises(TelegramTransportError):
            send_formatted_notification(
                object(),
                formatted,
                self.credentials(),
                connection_factory=factory_for()[0],
            )
        with self.assertRaises(TelegramTransportError):
            send_formatted_notification(
                message(),
                object(),
                self.credentials(),
                connection_factory=factory_for()[0],
            )

    def test_redirect_status_fails_without_following(self):
        response = FakeResponse(status=302, raw=b"redirect")
        factory, bucket = factory_for(response=response)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.HTTP_STATUS,
        )
        self.assertIsNone(response.read_limit)
        self.assertTrue(bucket["connection"].closed)

    def test_non_200_provider_body_is_never_exposed(self):
        provider_secret = f"provider says token={TOKEN} chat={CHAT_ID}"
        response = FakeResponse(status=401, raw=provider_secret.encode("utf-8"))
        factory, _ = factory_for(response=response)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        rendered = str(caught.exception)
        self.assertEqual(rendered, "TELEGRAM_HTTP_STATUS")
        self.assertNotIn(TOKEN, rendered)
        self.assertNotIn(CHAT_ID, rendered)
        self.assertNotIn(provider_secret, rendered)

    def test_api_rejection_description_is_redacted(self):
        response = FakeResponse(
            payload={
                "ok": False,
                "description": f"bad token {TOKEN} for {CHAT_ID}",
            }
        )
        factory, _ = factory_for(response=response)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.API_REJECTED,
        )
        self.assertEqual(str(caught.exception), "TELEGRAM_API_REJECTED")
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(CHAT_ID, str(caught.exception))

    def test_network_failure_is_stable_redacted_and_connection_closes(self):
        factory, bucket = factory_for(
            request_error=OSError(f"network path included {TOKEN}")
        )
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.NETWORK_ERROR,
        )
        self.assertEqual(str(caught.exception), "TELEGRAM_NETWORK_ERROR")
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertTrue(bucket["connection"].closed)

    def test_declared_response_too_large_fails_before_read(self):
        response = FakeResponse(
            raw=b"{}",
            content_length=str(TELEGRAM_MAX_RESPONSE_BYTES + 1),
        )
        factory, _ = factory_for(response=response)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.RESPONSE_TOO_LARGE,
        )
        self.assertIsNone(response.read_limit)

    def test_actual_response_too_large_is_rejected(self):
        response = FakeResponse(
            raw=b"x" * (TELEGRAM_MAX_RESPONSE_BYTES + 1),
            content_length=False,
        )
        factory, _ = factory_for(response=response)
        with self.assertRaises(TelegramTransportError) as caught:
            send_formatted_notification(
                message(),
                format_notification(message()),
                self.credentials(),
                connection_factory=factory,
            )
        self.assertEqual(
            caught.exception.code,
            TelegramTransportErrorCode.RESPONSE_TOO_LARGE,
        )
        self.assertEqual(
            response.read_limit,
            TELEGRAM_MAX_RESPONSE_BYTES + 1,
        )

    def test_invalid_content_length_json_utf8_and_result_fail_closed(self):
        cases = (
            FakeResponse(raw=b"{}", content_length="not-a-number"),
            FakeResponse(raw=b"{broken"),
            FakeResponse(raw=b"\xff"),
            FakeResponse(payload={"ok": True, "result": {}}),
            FakeResponse(payload={"ok": True, "result": {"message_id": True}}),
        )
        for response in cases:
            with self.subTest(raw=response.raw[:20]):
                factory, _ = factory_for(response=response)
                with self.assertRaises(TelegramTransportError) as caught:
                    send_formatted_notification(
                        message(),
                        format_notification(message()),
                        self.credentials(),
                        connection_factory=factory,
                    )
                self.assertEqual(
                    caught.exception.code,
                    TelegramTransportErrorCode.RESPONSE_INVALID,
                )

    def test_receipt_is_deterministic_for_same_ack_and_contains_no_credentials(self):
        formatted = format_notification(message())
        first = send_formatted_notification(
            message(),
            formatted,
            self.credentials(),
            connection_factory=factory_for()[0],
        )
        second = send_formatted_notification(
            message(),
            formatted,
            self.credentials(),
            connection_factory=factory_for()[0],
        )
        self.assertEqual(first, second)
        self.assertEqual(first.receipt_sha256, second.receipt_sha256)
        material = json.dumps(first.as_record(), sort_keys=True)
        self.assertNotIn(TOKEN, material)
        self.assertNotIn(CHAT_ID, material)

    def test_transport_source_has_only_intended_network_and_no_control_imports(self):
        import yatl.notifications.transport as transport

        source = inspect.getsource(transport)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "websockets",
            "requests",
            "httpx",
            "aiohttp",
            "urllib",
            "openai",
            "anthropic",
            "input(",
            "eval(",
            "exec(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_transport_source_contains_no_inbound_or_other_bot_method_names(self):
        import yatl.notifications.transport as transport

        source = inspect.getsource(transport)
        forbidden_methods = (
            "getUpdates",
            "setWebhook",
            "deleteWebhook",
            "answerCallbackQuery",
            "editMessageText",
            "sendPhoto",
            "sendDocument",
            "forwardMessage",
        )
        for forbidden in forbidden_methods:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
