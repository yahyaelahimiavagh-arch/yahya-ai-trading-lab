"""Deterministic bounded offline formatter for P9 notification messages."""

import hashlib
from dataclasses import dataclass

from .contracts import NotificationMessage


FORMAT_SCHEMA_VERSION = 1
FORMAT_MODE = "PLAIN_TEXT_NO_PARSE_MODE"
MAX_FORMATTED_CHARS = 3500


class NotificationFormatError(ValueError):
    """A validated notification cannot be rendered within the P9-002 boundary."""


def _escape(value):
    if not isinstance(value, str):
        raise NotificationFormatError("Formatted value must be text")
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FormattedNotification:
    text: str
    notification_sha256: str
    formatted_sha256: str
    char_count: int
    format_mode: str = FORMAT_MODE
    schema_version: int = FORMAT_SCHEMA_VERSION

    def __post_init__(self):
        if (
            not isinstance(self.text, str)
            or not self.text
            or len(self.text) > MAX_FORMATTED_CHARS
            or self.char_count != len(self.text)
            or len(self.notification_sha256) != 64
            or len(self.formatted_sha256) != 64
            or self.formatted_sha256 != _sha256_text(self.text)
            or self.format_mode != FORMAT_MODE
            or self.schema_version != FORMAT_SCHEMA_VERSION
            or any(character < " " and character not in "\n" for character in self.text)
        ):
            raise NotificationFormatError("Formatted notification is invalid")


def format_notification(message):
    """Render canonical information-only plain text; no network or Telegram API call."""

    if not isinstance(message, NotificationMessage):
        raise NotificationFormatError("Formatter requires validated notification")
    symbol = message.symbol if message.symbol is not None else "NONE"
    lines = (
        f"[YATL] {_escape(message.severity.value)} | {_escape(message.category.value)}",
        f"Title: {_escape(message.title)}",
        f"Message: {_escape(message.body)}",
        f"Symbol: {_escape(symbol)}",
        f"Event time ms UTC: {message.event_time_ms}",
        f"Mode: {_escape(message.paper_label)}",
        f"Live lock: {_escape(message.live_lock_label)}",
        f"Evidence: {_escape(message.evidence_label)}",
        f"Actionability: {_escape(message.actionability)}",
        f"Source phase: {_escape(message.source.source_phase.value)}",
        f"Source SHA-256: {message.source.payload_sha256}",
        f"Notification SHA-256: {message.message_sha256}",
    )
    text = "\n".join(lines)
    if len(text) > MAX_FORMATTED_CHARS:
        raise NotificationFormatError("Formatted notification exceeds P9 bound")
    return FormattedNotification(
        text=text,
        notification_sha256=message.message_sha256,
        formatted_sha256=_sha256_text(text),
        char_count=len(text),
    )
