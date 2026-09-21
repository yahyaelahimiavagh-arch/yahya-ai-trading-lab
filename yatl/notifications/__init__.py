"""P9 read-only notification contracts. No Telegram transport or command capability."""

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
