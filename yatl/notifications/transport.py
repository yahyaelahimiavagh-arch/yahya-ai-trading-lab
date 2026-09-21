"""P9-003 narrowly allowlisted outbound-only Telegram sendMessage transport."""

import hashlib
import http.client
import json
import os
import re
import ssl
from dataclasses import dataclass, field
from enum import Enum

from .contracts import NotificationMessage
from .formatter import FormattedNotification, format_notification


TELEGRAM_TRANSPORT_ID = "P9_TELEGRAM_SEND_MESSAGE_V1"
TELEGRAM_HOST = "api.telegram.org"
TELEGRAM_PORT = 443
TELEGRAM_METHOD = "POST"
TELEGRAM_PATH_SUFFIX = "/sendMessage"
TELEGRAM_TOKEN_ENV = "YATL_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "YATL_TELEGRAM_CHAT_ID"
TELEGRAM_TIMEOUT_SECONDS = 10.0
TELEGRAM_MAX_RESPONSE_BYTES = 16_384
TELEGRAM_MAX_REQUEST_BYTES = 20_000
TELEGRAM_MAX_TEXT_CHARS = 4_096

_TOKEN_RE = re.compile(r"^[1-9][0-9]{5,15}:[A-Za-z0-9_-]{20,80}$")
_CHAT_ID_RE = re.compile(r"^-?[1-9][0-9]{0,19}$")
_HEX = frozenset("0123456789abcdef")


def _sha256(value):
    material = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


class TelegramTransportErrorCode(str, Enum):
    CONFIG_MISSING = "TELEGRAM_CONFIG_MISSING"
    CONFIG_INVALID = "TELEGRAM_CONFIG_INVALID"
    REQUEST_INVALID = "TELEGRAM_REQUEST_INVALID"
    NETWORK_ERROR = "TELEGRAM_NETWORK_ERROR"
    HTTP_STATUS = "TELEGRAM_HTTP_STATUS"
    RESPONSE_TOO_LARGE = "TELEGRAM_RESPONSE_TOO_LARGE"
    RESPONSE_INVALID = "TELEGRAM_RESPONSE_INVALID"
    API_REJECTED = "TELEGRAM_API_REJECTED"


class TelegramTransportError(RuntimeError):
    """Stable redacted transport failure. Provider text and credentials are omitted."""

    def __init__(self, code):
        if not isinstance(code, TelegramTransportErrorCode):
            raise TypeError("Telegram transport error code is invalid")
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class TelegramTransportPolicy:
    """Frozen P9-003 network authority, separate from P9 notification contracts."""

    transport_id: str = TELEGRAM_TRANSPORT_ID
    host: str = TELEGRAM_HOST
    port: int = TELEGRAM_PORT
    method: str = TELEGRAM_METHOD
    path_suffix: str = TELEGRAM_PATH_SUFFIX
    tls_required: bool = True
    outbound_only: bool = True
    send_message_only: bool = True
    parse_mode: str = "NONE"
    redirects_allowed: bool = False
    proxies_allowed: bool = False
    inbound_updates_allowed: bool = False
    inbound_commands_allowed: bool = False
    callback_actions_allowed: bool = False
    webhook_receiver_allowed: bool = False
    polling_receiver_allowed: bool = False
    execution_control_allowed: bool = False
    live_control_allowed: bool = False
    trade_permission: bool = False
    order_endpoint: bool = False
    ai_direct_execution: bool = False
    credentials_source: str = "ENVIRONMENT_ONLY"
    timeout_seconds: float = TELEGRAM_TIMEOUT_SECONDS
    max_response_bytes: int = TELEGRAM_MAX_RESPONSE_BYTES
    max_request_bytes: int = TELEGRAM_MAX_REQUEST_BYTES
    max_text_chars: int = TELEGRAM_MAX_TEXT_CHARS

    def __post_init__(self):
        if (
            self.transport_id != TELEGRAM_TRANSPORT_ID
            or self.host != TELEGRAM_HOST
            or self.port != TELEGRAM_PORT
            or self.method != TELEGRAM_METHOD
            or self.path_suffix != TELEGRAM_PATH_SUFFIX
            or self.tls_required is not True
            or self.outbound_only is not True
            or self.send_message_only is not True
            or self.parse_mode != "NONE"
            or self.redirects_allowed is not False
            or self.proxies_allowed is not False
            or self.inbound_updates_allowed is not False
            or self.inbound_commands_allowed is not False
            or self.callback_actions_allowed is not False
            or self.webhook_receiver_allowed is not False
            or self.polling_receiver_allowed is not False
            or self.execution_control_allowed is not False
            or self.live_control_allowed is not False
            or self.trade_permission is not False
            or self.order_endpoint is not False
            or self.ai_direct_execution is not False
            or self.credentials_source != "ENVIRONMENT_ONLY"
            or self.timeout_seconds != TELEGRAM_TIMEOUT_SECONDS
            or self.max_response_bytes != TELEGRAM_MAX_RESPONSE_BYTES
            or self.max_request_bytes != TELEGRAM_MAX_REQUEST_BYTES
            or self.max_text_chars != TELEGRAM_MAX_TEXT_CHARS
        ):
            raise TelegramTransportError(
                TelegramTransportErrorCode.REQUEST_INVALID
            )

    def as_record(self):
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }

    @property
    def policy_sha256(self):
        return _sha256(self.as_record())


@dataclass(frozen=True, slots=True)
class TelegramCredentials:
    """Dedicated Telegram transport credentials; repr deliberately hides values."""

    bot_token: str = field(repr=False)
    chat_id: str = field(repr=False)

    def __post_init__(self):
        if (
            not isinstance(self.bot_token, str)
            or _TOKEN_RE.fullmatch(self.bot_token) is None
            or not isinstance(self.chat_id, str)
            or _CHAT_ID_RE.fullmatch(self.chat_id) is None
        ):
            raise TelegramTransportError(
                TelegramTransportErrorCode.CONFIG_INVALID
            )


@dataclass(frozen=True, slots=True)
class TelegramDeliveryReceipt:
    """Secret-free acknowledgement identity for one successful sendMessage call."""

    notification_sha256: str
    formatted_sha256: str
    telegram_message_id: int
    policy_sha256: str
    transport_id: str = TELEGRAM_TRANSPORT_ID

    def __post_init__(self):
        if (
            not _valid_sha(self.notification_sha256)
            or not _valid_sha(self.formatted_sha256)
            or type(self.telegram_message_id) is not int
            or self.telegram_message_id <= 0
            or not _valid_sha(self.policy_sha256)
            or self.transport_id != TELEGRAM_TRANSPORT_ID
        ):
            raise TelegramTransportError(
                TelegramTransportErrorCode.RESPONSE_INVALID
            )

    def as_record(self):
        return {
            "notification_sha256": self.notification_sha256,
            "formatted_sha256": self.formatted_sha256,
            "telegram_message_id": self.telegram_message_id,
            "policy_sha256": self.policy_sha256,
            "transport_id": self.transport_id,
        }

    @property
    def receipt_sha256(self):
        return _sha256(self.as_record())


def load_telegram_credentials(environ=None):
    """Load only the two dedicated P9 Telegram variables at the transport boundary."""

    source = os.environ if environ is None else environ
    try:
        token = source[TELEGRAM_TOKEN_ENV]
        chat_id = source[TELEGRAM_CHAT_ID_ENV]
    except (KeyError, TypeError):
        raise TelegramTransportError(
            TelegramTransportErrorCode.CONFIG_MISSING
        ) from None
    return TelegramCredentials(token, chat_id)


def _request_path(credentials):
    if not isinstance(credentials, TelegramCredentials):
        raise TelegramTransportError(
            TelegramTransportErrorCode.CONFIG_INVALID
        )
    return f"/bot{credentials.bot_token}{TELEGRAM_PATH_SUFFIX}"


def _request_body(formatted, credentials):
    if (
        not isinstance(formatted, FormattedNotification)
        or not isinstance(credentials, TelegramCredentials)
        or formatted.char_count > TELEGRAM_MAX_TEXT_CHARS
    ):
        raise TelegramTransportError(
            TelegramTransportErrorCode.REQUEST_INVALID
        )
    body = json.dumps(
        {
            "chat_id": credentials.chat_id,
            "text": formatted.text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not body or len(body) > TELEGRAM_MAX_REQUEST_BYTES:
        raise TelegramTransportError(
            TelegramTransportErrorCode.REQUEST_INVALID
        )
    return body


def _read_success_response(response):
    if type(response.status) is not int or response.status != 200:
        raise TelegramTransportError(
            TelegramTransportErrorCode.HTTP_STATUS
        )

    content_length = response.getheader("Content-Length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except (TypeError, ValueError):
            raise TelegramTransportError(
                TelegramTransportErrorCode.RESPONSE_INVALID
            ) from None
        if declared < 0:
            raise TelegramTransportError(
                TelegramTransportErrorCode.RESPONSE_INVALID
            )
        if declared > TELEGRAM_MAX_RESPONSE_BYTES:
            raise TelegramTransportError(
                TelegramTransportErrorCode.RESPONSE_TOO_LARGE
            )

    raw = response.read(TELEGRAM_MAX_RESPONSE_BYTES + 1)
    if len(raw) > TELEGRAM_MAX_RESPONSE_BYTES:
        raise TelegramTransportError(
            TelegramTransportErrorCode.RESPONSE_TOO_LARGE
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TelegramTransportError(
            TelegramTransportErrorCode.RESPONSE_INVALID
        ) from None

    if not isinstance(payload, dict):
        raise TelegramTransportError(
            TelegramTransportErrorCode.RESPONSE_INVALID
        )
    if payload.get("ok") is not True:
        raise TelegramTransportError(
            TelegramTransportErrorCode.API_REJECTED
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise TelegramTransportError(
            TelegramTransportErrorCode.RESPONSE_INVALID
        )
    message_id = result.get("message_id")
    if type(message_id) is not int or message_id <= 0:
        raise TelegramTransportError(
            TelegramTransportErrorCode.RESPONSE_INVALID
        )
    return message_id


def send_formatted_notification(
    message,
    formatted,
    credentials,
    *,
    connection_factory=None,
):
    """Send exactly one canonical P9 message through the fixed Telegram path."""

    if not isinstance(message, NotificationMessage):
        raise TelegramTransportError(
            TelegramTransportErrorCode.REQUEST_INVALID
        )
    if not isinstance(formatted, FormattedNotification):
        raise TelegramTransportError(
            TelegramTransportErrorCode.REQUEST_INVALID
        )
    canonical = format_notification(message)
    if formatted != canonical:
        raise TelegramTransportError(
            TelegramTransportErrorCode.REQUEST_INVALID
        )
    if not isinstance(credentials, TelegramCredentials):
        raise TelegramTransportError(
            TelegramTransportErrorCode.CONFIG_INVALID
        )

    policy = TelegramTransportPolicy()
    body = _request_body(formatted, credentials)
    path = _request_path(credentials)
    context = ssl.create_default_context()
    if (
        context.check_hostname is not True
        or context.verify_mode != ssl.CERT_REQUIRED
    ):
        raise TelegramTransportError(
            TelegramTransportErrorCode.NETWORK_ERROR
        )

    factory = (
        http.client.HTTPSConnection
        if connection_factory is None
        else connection_factory
    )
    connection = None
    try:
        connection = factory(
            policy.host,
            policy.port,
            timeout=policy.timeout_seconds,
            context=context,
        )
        connection.request(
            policy.method,
            path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        message_id = _read_success_response(response)
    except TelegramTransportError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException):
        raise TelegramTransportError(
            TelegramTransportErrorCode.NETWORK_ERROR
        ) from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass

    return TelegramDeliveryReceipt(
        notification_sha256=message.message_sha256,
        formatted_sha256=formatted.formatted_sha256,
        telegram_message_id=message_id,
        policy_sha256=policy.policy_sha256,
    )
