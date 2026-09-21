"""P9 read-only notifications with bounded outbound-only Telegram delivery."""

from .contracts import (
    MAX_BODY_CHARS,
    MAX_NOTIFICATIONS,
    MAX_TITLE_CHARS,
    NOTIFICATION_POLICY_ID,
    NOTIFICATION_SCHEMA_VERSION,
    NotificationBatch,
    NotificationCategory,
    NotificationContractError,
    NotificationMessage,
    NotificationPolicy,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    StrategyEvidenceState,
    build_notification_batch,
    notification_batch_from_record,
)

__all__ = [
    "MAX_BODY_CHARS",
    "MAX_NOTIFICATIONS",
    "MAX_TITLE_CHARS",
    "NOTIFICATION_POLICY_ID",
    "NOTIFICATION_SCHEMA_VERSION",
    "NotificationBatch",
    "NotificationCategory",
    "NotificationContractError",
    "NotificationMessage",
    "NotificationPolicy",
    "NotificationSeverity",
    "NotificationSourceIdentity",
    "NotificationSourcePhase",
    "StrategyEvidenceState",
    "build_notification_batch",
    "notification_batch_from_record",
]


from .projection import (
    NotificationProjectionError,
    project_data_quality_alert,
    project_system_status,
)
from .formatter import (
    FORMAT_MODE,
    FORMAT_SCHEMA_VERSION,
    MAX_FORMATTED_CHARS,
    FormattedNotification,
    NotificationFormatError,
    format_notification,
)

__all__ += [
    "NotificationProjectionError",
    "project_data_quality_alert",
    "project_system_status",
    "FORMAT_MODE",
    "FORMAT_SCHEMA_VERSION",
    "MAX_FORMATTED_CHARS",
    "FormattedNotification",
    "NotificationFormatError",
    "format_notification",
]


from .transport import (
    TELEGRAM_CHAT_ID_ENV,
    TELEGRAM_HOST,
    TELEGRAM_MAX_RESPONSE_BYTES,
    TELEGRAM_MAX_TEXT_CHARS,
    TELEGRAM_METHOD,
    TELEGRAM_PATH_SUFFIX,
    TELEGRAM_PORT,
    TELEGRAM_TIMEOUT_SECONDS,
    TELEGRAM_TOKEN_ENV,
    TELEGRAM_TRANSPORT_ID,
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportError,
    TelegramTransportErrorCode,
    TelegramTransportPolicy,
    load_telegram_credentials,
    send_formatted_notification,
)

__all__ += [
    "TELEGRAM_CHAT_ID_ENV",
    "TELEGRAM_HOST",
    "TELEGRAM_MAX_RESPONSE_BYTES",
    "TELEGRAM_MAX_TEXT_CHARS",
    "TELEGRAM_METHOD",
    "TELEGRAM_PATH_SUFFIX",
    "TELEGRAM_PORT",
    "TELEGRAM_TIMEOUT_SECONDS",
    "TELEGRAM_TOKEN_ENV",
    "TELEGRAM_TRANSPORT_ID",
    "TelegramCredentials",
    "TelegramDeliveryReceipt",
    "TelegramTransportError",
    "TelegramTransportErrorCode",
    "TelegramTransportPolicy",
    "load_telegram_credentials",
    "send_formatted_notification",
]
