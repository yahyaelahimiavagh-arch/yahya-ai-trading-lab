"""P9-005 minimal noninteractive guarded notifier runner."""

import argparse
import hashlib
import json
import os
import time
from enum import Enum
from pathlib import Path
from uuid import uuid4

from .contracts import (
    NotificationContractError,
    SYMBOLS,
    notification_batch_from_record,
)
from .delivery import (
    DeliveryGuardError,
    DeliveryState,
    DeliveryStatus,
    delivery_identity,
    delivery_state_from_record,
    guarded_send,
)
from .formatter import format_notification
from .transport import (
    TelegramTransportError,
    load_telegram_credentials,
    send_formatted_notification,
)


RUNNER_ID = "P9_NOTIFIER_RUNNER_V1"
RUNNER_SCHEMA_VERSION = 1
MAX_NOTIFICATION_INPUT_BYTES = 256 * 1024
MAX_DELIVERY_STATE_BYTES = 512 * 1024
MAX_RUNNER_OUTPUT_BYTES = 32 * 1024

EXIT_OK = 0
EXIT_INVALID = 20
EXIT_SOURCE = 21
EXIT_STATE = 22
EXIT_CONFIG = 23
EXIT_DELIVERY = 24
EXIT_STORAGE = 25
EXIT_OUTPUT = 26
EXIT_INTERNAL = 27

_HEX = frozenset("0123456789abcdef")


class NotifierRunnerCode(str, Enum):
    DELIVERED = "DELIVERED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    INVALID_REQUEST = "INVALID_REQUEST"
    SOURCE_REJECTED = "SOURCE_REJECTED"
    SOURCE_MUTATED = "SOURCE_MUTATED"
    STATE_REJECTED = "STATE_REJECTED"
    CONFIG_REJECTED = "CONFIG_REJECTED"
    DELIVERY_REJECTED = "DELIVERY_REJECTED"
    STORAGE_ERROR = "STORAGE_ERROR"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class NotifierRunnerError(RuntimeError):
    """Stable runner failure that never echoes paths, source text or credentials."""

    def __init__(self, code):
        if not isinstance(code, NotifierRunnerCode):
            raise TypeError("Notifier runner error code is invalid")
        self.code = code
        super().__init__(code.value)


class _DuplicateJsonKey(ValueError):
    pass


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _path(value, code):
    if not isinstance(value, (str, Path)) or not str(value):
        raise NotifierRunnerError(code)
    return Path(value)


def _read_regular_file(path, maximum, code):
    target = _path(path, code)
    try:
        if target.is_symlink() or not target.is_file():
            raise NotifierRunnerError(code)
        with target.open("rb") as handle:
            payload = handle.read(maximum + 1)
    except NotifierRunnerError:
        raise
    except OSError:
        raise NotifierRunnerError(code) from None
    if not payload or len(payload) > maximum:
        raise NotifierRunnerError(code)
    return payload


def _parse_json(payload, code):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey):
        raise NotifierRunnerError(code) from None
    return text, record


def load_notification_source(path, expected_batch_sha256, symbol):
    """Load one exact canonical accepted notification without mutating its source."""

    if not _valid_sha(expected_batch_sha256) or symbol not in SYMBOLS:
        raise NotifierRunnerError(NotifierRunnerCode.INVALID_REQUEST)
    payload = _read_regular_file(
        path,
        MAX_NOTIFICATION_INPUT_BYTES,
        NotifierRunnerCode.SOURCE_REJECTED,
    )
    text, record = _parse_json(payload, NotifierRunnerCode.SOURCE_REJECTED)
    try:
        batch = notification_batch_from_record(record)
    except (NotificationContractError, TypeError, ValueError):
        raise NotifierRunnerError(NotifierRunnerCode.SOURCE_REJECTED) from None

    if (
        len(batch.notifications) != 1
        or batch.batch_sha256 != expected_batch_sha256
        or batch.notifications[0].symbol != symbol
        or _json(batch.as_record()) != text
    ):
        raise NotifierRunnerError(NotifierRunnerCode.SOURCE_REJECTED)
    return batch, payload


def load_delivery_state(path):
    """Load strict canonical state; a missing state file means an empty state."""

    target = _path(path, NotifierRunnerCode.STATE_REJECTED)
    try:
        exists = target.exists()
    except OSError:
        raise NotifierRunnerError(NotifierRunnerCode.STATE_REJECTED) from None
    if not exists:
        return DeliveryState()
    payload = _read_regular_file(
        target,
        MAX_DELIVERY_STATE_BYTES,
        NotifierRunnerCode.STATE_REJECTED,
    )
    text, record = _parse_json(payload, NotifierRunnerCode.STATE_REJECTED)
    try:
        state = delivery_state_from_record(record)
    except (DeliveryGuardError, TypeError, ValueError):
        raise NotifierRunnerError(NotifierRunnerCode.STATE_REJECTED) from None
    if _json(state.as_record()) != text:
        raise NotifierRunnerError(NotifierRunnerCode.STATE_REJECTED)
    return state


def _same_path(first, second):
    try:
        return _path(first, NotifierRunnerCode.INVALID_REQUEST).absolute() == _path(
            second,
            NotifierRunnerCode.INVALID_REQUEST,
        ).absolute()
    except OSError:
        raise NotifierRunnerError(NotifierRunnerCode.INVALID_REQUEST) from None


def _write_delivery_state(path, state):
    if not isinstance(state, DeliveryState):
        raise NotifierRunnerError(NotifierRunnerCode.STORAGE_ERROR)
    target = _path(path, NotifierRunnerCode.STORAGE_ERROR)
    parent = target.parent
    encoded = _json(state.as_record()).encode("utf-8")
    if len(encoded) > MAX_DELIVERY_STATE_BYTES:
        raise NotifierRunnerError(NotifierRunnerCode.STORAGE_ERROR)
    try:
        if (
            not parent.exists()
            or not parent.is_dir()
            or parent.is_symlink()
            or target.is_symlink()
        ):
            raise NotifierRunnerError(NotifierRunnerCode.STORAGE_ERROR)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
    except NotifierRunnerError:
        raise
    except OSError:
        raise NotifierRunnerError(NotifierRunnerCode.STORAGE_ERROR) from None


def _source_unchanged(path, before):
    try:
        after = _read_regular_file(
            path,
            MAX_NOTIFICATION_INPUT_BYTES,
            NotifierRunnerCode.SOURCE_MUTATED,
        )
    except NotifierRunnerError:
        return False
    return after == before


def notifier_run(
    input_path,
    expected_batch_sha256,
    state_path,
    symbol,
    *,
    environ=None,
    credentials=None,
    sender=send_formatted_notification,
    sleep_fn=time.sleep,
):
    """Send exactly one accepted notification and persist only delivery state."""

    if (
        symbol not in SYMBOLS
        or not _valid_sha(expected_batch_sha256)
        or not callable(sender)
        or not callable(sleep_fn)
        or _same_path(input_path, state_path)
    ):
        raise NotifierRunnerError(NotifierRunnerCode.INVALID_REQUEST)

    batch, source_before = load_notification_source(
        input_path,
        expected_batch_sha256,
        symbol,
    )
    state = load_delivery_state(state_path)
    message = batch.notifications[0]
    formatted = format_notification(message)
    identity = delivery_identity(message, formatted)
    existing = state.find(identity)

    if existing is not None:
        if not _source_unchanged(input_path, source_before):
            raise NotifierRunnerError(NotifierRunnerCode.SOURCE_MUTATED)
        return {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "runner_id": RUNNER_ID,
            "ok": True,
            "code": NotifierRunnerCode.DUPLICATE_SUPPRESSED.value,
            "symbol": symbol,
            "source_file_sha256": _sha256_bytes(source_before),
            "batch_sha256": batch.batch_sha256,
            "notification_sha256": existing.notification_sha256,
            "formatted_sha256": existing.formatted_sha256,
            "delivery_id": existing.delivery_id,
            "delivery_state_sha256": state.state_sha256,
            "receipt_sha256": existing.receipt_sha256,
            "telegram_message_id": existing.telegram_message_id,
            "attempts": 0,
            "wait_seconds": [],
            "duplicate_suppressed": True,
            "source_unchanged": True,
            "paper_only": True,
            "live_master_lock": "OFF",
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "trade_permission": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
        }

    if credentials is None:
        try:
            credentials = load_telegram_credentials(environ)
        except TelegramTransportError:
            raise NotifierRunnerError(NotifierRunnerCode.CONFIG_REJECTED) from None

    try:
        result = guarded_send(
            message,
            formatted,
            credentials,
            state=state,
            sender=sender,
            sleep_fn=sleep_fn,
        )
    except DeliveryGuardError:
        raise NotifierRunnerError(NotifierRunnerCode.DELIVERY_REJECTED) from None

    source_unchanged = _source_unchanged(input_path, source_before)
    if result.status is DeliveryStatus.DELIVERED:
        _write_delivery_state(state_path, result.state)

    if not source_unchanged:
        raise NotifierRunnerError(NotifierRunnerCode.SOURCE_MUTATED)

    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "ok": True,
        "code": NotifierRunnerCode.DELIVERED.value,
        "symbol": symbol,
        "source_file_sha256": _sha256_bytes(source_before),
        "batch_sha256": batch.batch_sha256,
        "notification_sha256": result.notification_sha256,
        "formatted_sha256": result.formatted_sha256,
        "delivery_id": result.delivery_id,
        "delivery_state_sha256": result.state.state_sha256,
        "receipt_sha256": result.receipt_sha256,
        "telegram_message_id": result.telegram_message_id,
        "attempts": result.attempts,
        "wait_seconds": list(result.wait_seconds),
        "duplicate_suppressed": False,
        "source_unchanged": True,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }


def _compact_error(code):
    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "ok": False,
        "code": code.value,
    }


def _render(record):
    encoded = _json(record)
    if len(encoded.encode("utf-8")) > MAX_RUNNER_OUTPUT_BYTES:
        raise NotifierRunnerError(NotifierRunnerCode.OUTPUT_TOO_LARGE)
    lowered = encoded.lower()
    forbidden = (
        "bot_token",
        "bot token",
        "api_key",
        "api_secret",
        "authorization:",
        "bearer ",
        "password",
        "private_key",
        "traceback",
    )
    if any(marker in lowered for marker in forbidden):
        raise NotifierRunnerError(NotifierRunnerCode.OUTPUT_TOO_LARGE)
    return encoded


def _exit_code(record):
    code = record.get("code")
    if code in {
        NotifierRunnerCode.DELIVERED.value,
        NotifierRunnerCode.DUPLICATE_SUPPRESSED.value,
    }:
        return EXIT_OK
    if code == NotifierRunnerCode.INVALID_REQUEST.value:
        return EXIT_INVALID
    if code in {
        NotifierRunnerCode.SOURCE_REJECTED.value,
        NotifierRunnerCode.SOURCE_MUTATED.value,
    }:
        return EXIT_SOURCE
    if code == NotifierRunnerCode.STATE_REJECTED.value:
        return EXIT_STATE
    if code == NotifierRunnerCode.CONFIG_REJECTED.value:
        return EXIT_CONFIG
    if code == NotifierRunnerCode.DELIVERY_REJECTED.value:
        return EXIT_DELIVERY
    if code == NotifierRunnerCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == NotifierRunnerCode.INTERNAL_ERROR.value:
        return EXIT_INTERNAL
    return EXIT_OUTPUT


class SafeArgumentParser(argparse.ArgumentParser):
    """Argparse variant that never echoes rejected caller-supplied values."""

    def error(self, message):
        raise NotifierRunnerError(NotifierRunnerCode.INVALID_REQUEST)


def _parser():
    parser = SafeArgumentParser(
        description="One-shot P9 accepted-notification sender; no command surface"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected-batch-sha256", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--symbol", required=True, choices=SYMBOLS)
    return parser


def main(
    argv=None,
    *,
    environ=None,
    credentials=None,
    sender=send_formatted_notification,
    sleep_fn=time.sleep,
):
    code = NotifierRunnerCode.INVALID_REQUEST
    try:
        args = _parser().parse_args(argv)
        record = notifier_run(
            args.input,
            args.expected_batch_sha256,
            args.state,
            args.symbol,
            environ=environ,
            credentials=credentials,
            sender=sender,
            sleep_fn=sleep_fn,
        )
        output = _render(record)
    except NotifierRunnerError as exc:
        code = exc.code
        record = _compact_error(code)
        try:
            output = _render(record)
        except NotifierRunnerError:
            code = NotifierRunnerCode.OUTPUT_TOO_LARGE
            record = _compact_error(code)
            output = _json(record)
    except Exception:
        code = NotifierRunnerCode.INTERNAL_ERROR
        record = _compact_error(code)
        output = _json(record)
    print(output, end="")
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
