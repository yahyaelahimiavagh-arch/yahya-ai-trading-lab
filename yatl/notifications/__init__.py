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
    project_p10_validation_status,
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
    "project_p10_validation_status",
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


from .delivery import (
    DELIVERY_GUARD_ID,
    DELIVERY_SCHEMA_VERSION,
    MAX_ATTEMPTS,
    MAX_DELIVERY_RECORDS,
    MAX_RATE_LIMIT_WAIT_SECONDS,
    MAX_TOTAL_WAIT_SECONDS,
    NETWORK_BACKOFF_SECONDS,
    DeliveryGuardError,
    DeliveryGuardErrorCode,
    DeliveryGuardPolicy,
    DeliveryRecord,
    DeliveryState,
    DeliveryStatus,
    GuardedDeliveryResult,
    delivery_identity,
    delivery_state_from_record,
    guarded_send,
)

__all__ += [
    "DELIVERY_GUARD_ID",
    "DELIVERY_SCHEMA_VERSION",
    "MAX_ATTEMPTS",
    "MAX_DELIVERY_RECORDS",
    "MAX_RATE_LIMIT_WAIT_SECONDS",
    "MAX_TOTAL_WAIT_SECONDS",
    "NETWORK_BACKOFF_SECONDS",
    "DeliveryGuardError",
    "DeliveryGuardErrorCode",
    "DeliveryGuardPolicy",
    "DeliveryRecord",
    "DeliveryState",
    "DeliveryStatus",
    "GuardedDeliveryResult",
    "delivery_identity",
    "delivery_state_from_record",
    "guarded_send",
]


from .runner import (
    RUNNER_ID,
    RUNNER_SCHEMA_VERSION,
    NotifierRunnerCode,
    NotifierRunnerError,
    load_delivery_state,
    load_notification_source,
    notifier_run,
)
from .scenarios import (
    ARTIFACT_KIND as NOTIFICATION_SCENARIO_ARTIFACT_KIND,
    MATRIX_KIND as NOTIFICATION_SCENARIO_MATRIX_KIND,
    SCENARIOS as NOTIFICATION_SCENARIOS,
    NotificationAcceptedFixture,
    NotificationScenarioError,
    NotificationScenarioMatrixResult,
    NotificationScenarioResult,
    notification_matrix_sha256,
    run_adversarial_notification_matrix,
    scenario_artifact_json,
    write_adversarial_notification_matrix,
)

__all__ += [
    "RUNNER_ID",
    "RUNNER_SCHEMA_VERSION",
    "NotifierRunnerCode",
    "NotifierRunnerError",
    "load_delivery_state",
    "load_notification_source",
    "notifier_run",
    "NOTIFICATION_SCENARIO_ARTIFACT_KIND",
    "NOTIFICATION_SCENARIO_MATRIX_KIND",
    "NOTIFICATION_SCENARIOS",
    "NotificationAcceptedFixture",
    "NotificationScenarioError",
    "NotificationScenarioMatrixResult",
    "NotificationScenarioResult",
    "notification_matrix_sha256",
    "run_adversarial_notification_matrix",
    "scenario_artifact_json",
    "write_adversarial_notification_matrix",
]


from .audit import (
    EXPECTED_DELIVERY_POLICY_SHA256,
    EXPECTED_DELIVERY_REPLAY,
    EXPECTED_DELIVERY_REPLAY_SET_SHA256,
    EXPECTED_IDENTITIES,
    EXPECTED_IDENTITY_SET_SHA256,
    EXPECTED_INDEX_SHA256 as P9_EXPECTED_INDEX_SHA256,
    EXPECTED_NOTIFICATION_POLICY_SHA256,
    EXPECTED_TRANSPORT_POLICY_SHA256,
    P9AuditError,
    P9AuditResult,
    audit_p9,
)

__all__ += [
    "EXPECTED_DELIVERY_POLICY_SHA256",
    "EXPECTED_DELIVERY_REPLAY",
    "EXPECTED_DELIVERY_REPLAY_SET_SHA256",
    "EXPECTED_IDENTITIES",
    "EXPECTED_IDENTITY_SET_SHA256",
    "P9_EXPECTED_INDEX_SHA256",
    "EXPECTED_NOTIFICATION_POLICY_SHA256",
    "EXPECTED_TRANSPORT_POLICY_SHA256",
    "P9AuditError",
    "P9AuditResult",
    "audit_p9",
]
