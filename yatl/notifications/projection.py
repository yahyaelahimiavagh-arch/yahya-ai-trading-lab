"""P9 accepted upstream projection into immutable notification contracts."""

import hashlib
import json

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
    SYMBOLS,
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


_P10_NOT_READY_KEYS = {
    "schema_version",
    "command",
    "ok",
    "code",
    "reason",
    "ingestion_snapshot_sha256",
    "generated_at_ms",
    "database_snapshot_sha256",
    "paper_only",
    "live_master_lock",
    "strategy_evidence",
    "p11_unlocked",
}

_P10_READY_KEYS = {
    "schema_version",
    "command",
    "ok",
    "code",
    "ingestion_snapshot_sha256",
    "database_snapshot_sha256",
    "paper_run_sha256",
    "economics_sha256",
    "gate_sha256",
    "sample_status",
    "disposition",
    "paper_only",
    "live_master_lock",
    "strategy_evidence",
    "p11_unlocked",
    "observed_days",
    "observation_start_ms",
    "observation_end_ms",
    "completed_trades",
    "net_pnl_after_costs_quote",
    "net_return_after_costs",
    "profit_factor_after_costs",
    "maximum_validation_drawdown_fraction",
    "criteria",
    "symbols",
}

_P10_SYMBOL_KEYS = {
    "symbol",
    "completed_trades",
    "net_pnl_after_costs_quote",
    "net_return_after_costs",
    "open_positions",
}

_P10_CRITERIA = {
    "NET_PNL_AFTER_COSTS",
    "MAX_DRAWDOWN",
    "SAMPLE_SIZE",
    "CONSISTENCY",
    "REGIME_STABILITY",
    "FAILURE_RECOVERY",
    "RISK_CONTROLS",
}

_HEX = frozenset("0123456789abcdef")


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _record_sha256(record):
    material = json.dumps(
        record,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _p10_common(summary):
    if (
        not isinstance(summary, dict)
        or summary.get("schema_version") != 1
        or summary.get("command") != "summary"
        or summary.get("paper_only") is not True
        or summary.get("live_master_lock") != "OFF"
        or summary.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or summary.get("p11_unlocked") is not False
        or not _valid_sha(summary.get("ingestion_snapshot_sha256"))
        or not _valid_sha(summary.get("database_snapshot_sha256"))
    ):
        raise NotificationProjectionError("P10 validation summary safety/provenance changed")


def project_p10_validation_status(summary, symbol):
    """Project one symbol-scoped P10 status message from accepted validation summary."""

    if symbol not in SYMBOLS:
        raise NotificationProjectionError("P10 notification symbol is unsupported")
    _p10_common(summary)
    code = summary.get("code")
    if code == "NOT_READY":
        if (
            set(summary) != _P10_NOT_READY_KEYS
            or summary.get("ok") is not False
            or summary.get("reason") != "FORWARD_WARMUP_NOT_COMPLETE"
            or type(summary.get("generated_at_ms")) is not int
            or summary["generated_at_ms"] < 0
        ):
            raise NotificationProjectionError("P10 warm-up status is invalid")
        observed_at_ms = summary["generated_at_ms"]
        severity = NotificationSeverity.INFO
        body = (
            f"P10 forward warm-up is not complete for {symbol}; "
            "strategy evidence remains insufficient; P11 remains locked."
        )
    elif code == "SUMMARY_READY":
        if (
            set(summary) != _P10_READY_KEYS
            or summary.get("ok") is not True
            or summary.get("sample_status")
            not in {"INSUFFICIENT_DATA", "MINIMUM_SAMPLE_MET_ONLY"}
            or summary.get("disposition")
            not in {"INSUFFICIENT_DATA", "FAIL", "PASS_CANDIDATE"}
            or type(summary.get("observation_end_ms")) is not int
            or summary["observation_end_ms"] < 0
            or not isinstance(summary.get("criteria"), dict)
            or set(summary["criteria"]) != _P10_CRITERIA
            or not isinstance(summary.get("symbols"), list)
            or len(summary["symbols"]) != len(SYMBOLS)
        ):
            raise NotificationProjectionError("P10 ready summary is invalid")
        by_symbol = {}
        for item in summary["symbols"]:
            if (
                not isinstance(item, dict)
                or set(item) != _P10_SYMBOL_KEYS
                or item.get("symbol") not in SYMBOLS
                or type(item.get("completed_trades")) is not int
                or item["completed_trades"] < 0
                or type(item.get("open_positions")) is not int
                or item["open_positions"] < 0
                or not isinstance(item.get("net_pnl_after_costs_quote"), str)
                or not isinstance(item.get("net_return_after_costs"), str)
            ):
                raise NotificationProjectionError("P10 symbol summary is invalid")
            by_symbol[item["symbol"]] = item
        if set(by_symbol) != set(SYMBOLS):
            raise NotificationProjectionError("P10 symbol summary coverage changed")
        item = by_symbol[symbol]
        observed_at_ms = summary["observation_end_ms"]
        severity = (
            NotificationSeverity.ERROR
            if summary["disposition"] == "FAIL"
            else NotificationSeverity.INFO
        )
        body = (
            f"P10 disposition {summary['disposition']}; {symbol} completed Paper trades "
            f"{item['completed_trades']}; net return after costs "
            f"{item['net_return_after_costs']}; pooled sample {summary['sample_status']}; "
            "P11 remains locked."
        )
    else:
        raise NotificationProjectionError("P10 validation summary code is unsupported")

    digest = _record_sha256(summary)
    source = NotificationSourceIdentity(
        source_id=f"P10_VALIDATION_{symbol}",
        source_phase=NotificationSourcePhase.P10_FORWARD_VALIDATION,
        observed_at_ms=observed_at_ms,
        payload_sha256=digest,
        symbol=symbol,
    )
    return NotificationMessage(
        notification_id=f"NOTICE_P10_{symbol}_{digest[:12].upper()}",
        category=NotificationCategory.P10_VALIDATION_STATUS,
        severity=severity,
        title=f"YATL P10 validation {symbol}",
        body=body,
        source=source,
        event_time_ms=observed_at_ms,
        symbol=symbol,
    )
