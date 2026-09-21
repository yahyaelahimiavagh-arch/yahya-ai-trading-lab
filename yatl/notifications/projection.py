"""P9-002 accepted upstream projection into immutable notification contracts."""

from yatl.dashboard import (
    DashboardOverviewProjection,
    QualityDiagnosticProjection,
)

from .contracts import (
    NotificationCategory,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
)


class NotificationProjectionError(ValueError):
    """Accepted upstream material cannot be projected without changing semantics."""


def _overview_cards(overview):
    if not isinstance(overview, DashboardOverviewProjection):
        raise NotificationProjectionError("System status requires accepted P8 overview")
    cards = {item.field_key: item for item in overview.cards}
    required = (
        "symbol",
        "snapshot_time_ms",
        "paper_state",
        "live_master_lock",
        "strategy_evidence",
        "quality_status",
        "completed_trade_count",
        "open_trade_count",
        "snapshot_freshness",
    )
    if any(key not in cards for key in required):
        raise NotificationProjectionError("P8 overview is missing required status fields")
    if (
        cards["paper_state"].value != "PAPER ONLY"
        or cards["live_master_lock"].value != "OFF"
        or cards["strategy_evidence"].value != "INSUFFICIENT_EVIDENCE"
        or cards["quality_status"].value != "PASS"
        or cards["symbol"].value != overview.source.symbol
        or cards["open_trade_count"].value != "UNKNOWN"
        or cards["snapshot_freshness"].value != "UNKNOWN"
    ):
        raise NotificationProjectionError("P8 overview safety/status semantics changed")
    try:
        snapshot_time_ms = int(cards["snapshot_time_ms"].value)
        completed = int(cards["completed_trade_count"].value)
    except (TypeError, ValueError):
        raise NotificationProjectionError("P8 overview numeric status is invalid") from None
    if snapshot_time_ms != overview.source.observed_at_ms or completed < 0:
        raise NotificationProjectionError("P8 overview provenance changed")
    return cards, snapshot_time_ms, completed


def project_system_status(overview):
    """Project a conservative system-status notification from accepted P8 overview."""

    cards, snapshot_time_ms, completed = _overview_cards(overview)
    digest = overview.overview_sha256
    source = NotificationSourceIdentity(
        source_id=f"P8_OVERVIEW_{overview.source.symbol}",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=snapshot_time_ms,
        payload_sha256=digest,
        symbol=overview.source.symbol,
    )
    body = (
        f"Symbol {overview.source.symbol}; P7 quality PASS; "
        f"completed Paper trades {completed}; "
        f"open trade count {cards['open_trade_count'].value}; "
        f"snapshot freshness {cards['snapshot_freshness'].value}."
    )
    return NotificationMessage(
        notification_id=(
            f"NOTICE_STATUS_{overview.source.symbol}_{digest[:12].upper()}"
        ),
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title=f"YATL Paper status {overview.source.symbol}",
        body=body,
        source=source,
        event_time_ms=snapshot_time_ms,
        symbol=overview.source.symbol,
    )


def project_data_quality_alert(quality):
    """Project only a validated sanitized FAIL quality projection as an alert."""

    if not isinstance(quality, QualityDiagnosticProjection):
        raise NotificationProjectionError(
            "Data-quality alert requires P8 quality projection"
        )
    if (
        quality.quality_status != "FAIL"
        or quality.status_severity.value != "ERROR"
        or quality.publication_allowed is not False
        or quality.analytics_presentation_allowed is not False
        or quality.partial_analytics_visible is not False
        or not quality.diagnostics
        or quality.source_mode != "SANITIZED_P7_QUALITY_REPORT"
        or not isinstance(quality.source_quality_sha256, str)
        or len(quality.source_quality_sha256) != 64
        or quality.source_export_sha256 is not None
        or type(quality.snapshot_time_ms) is not int
        or quality.snapshot_time_ms < 0
        or quality.strategy_evidence != "INSUFFICIENT_EVIDENCE"
    ):
        raise NotificationProjectionError(
            "Quality projection is not a sanitized fail-closed alert source"
        )
    codes = ",".join(item.code for item in quality.diagnostics)
    digest = quality.projection_sha256
    source = NotificationSourceIdentity(
        source_id="P8_QUALITY_FAIL",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=quality.snapshot_time_ms,
        payload_sha256=digest,
        symbol=None,
    )
    return NotificationMessage(
        notification_id=f"NOTICE_QUALITY_{digest[:12].upper()}",
        category=NotificationCategory.DATA_QUALITY_ALERT,
        severity=NotificationSeverity.ERROR,
        title="YATL data quality alert",
        body=(
            "P7 quality FAIL; analytics presentation blocked; "
            f"diagnostics {codes}."
        ),
        source=source,
        event_time_ms=quality.snapshot_time_ms,
        symbol=None,
    )
