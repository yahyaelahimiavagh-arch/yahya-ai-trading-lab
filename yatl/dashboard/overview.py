"""Deterministic P8-003 system/safety/quality overview projection."""

import hashlib
import json
from dataclasses import dataclass

from .contracts import (
    DashboardOverviewCard,
    DashboardSourceIdentity,
    OverviewDisplayKind,
)
from .loader import LoadedP7Export


OVERVIEW_SCHEMA_VERSION = 1
UNKNOWN_VALUE = "UNKNOWN"
UNKNOWN_FIELDS = ("open_trade_count", "snapshot_freshness")
EXPECTED_CARD_IDS = (
    "CARD_01_SYMBOL",
    "CARD_02_EXPORT_SHA256",
    "CARD_03_SNAPSHOT_TIME_MS",
    "CARD_04_PAPER_STATE",
    "CARD_05_LIVE_MASTER_LOCK",
    "CARD_06_STRATEGY_EVIDENCE",
    "CARD_07_QUALITY_STATUS",
    "CARD_08_COMPLETED_TRADE_COUNT",
    "CARD_09_OPEN_TRADE_COUNT",
    "CARD_10_SNAPSHOT_FRESHNESS",
    "CARD_11_INGESTION_MANIFEST_SHA256",
    "CARD_12_TIMELINE_SHA256",
    "CARD_13_RECONSTRUCTION_SHA256",
    "CARD_14_METRICS_SHA256",
    "CARD_15_SEGMENTATION_SHA256",
)
EXPECTED_FIELD_KEYS = (
    "symbol",
    "export_sha256",
    "snapshot_time_ms",
    "paper_state",
    "live_master_lock",
    "strategy_evidence",
    "quality_status",
    "completed_trade_count",
    "open_trade_count",
    "snapshot_freshness",
    "ingestion_manifest_sha256",
    "timeline_sha256",
    "reconstruction_sha256",
    "metrics_sha256",
    "segmentation_sha256",
)


class OverviewProjectionError(ValueError):
    """Accepted P7 export cannot be projected without changing source semantics."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    material = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _field_sha256(path, value):
    return _digest({
        "source_path": path,
        "source_value": value,
    })


def _unknown_sha256(field_key, reason):
    return _digest({
        "field_key": field_key,
        "state": UNKNOWN_VALUE,
        "reason": reason,
    })


def _verify_loaded_export(loaded):
    if not isinstance(loaded, LoadedP7Export):
        raise OverviewProjectionError("Overview requires one validated P7 export")

    try:
        record = loaded.record()
        material = {
            "schema_version": record["schema_version"],
            "quality": record["quality"],
            "analytics": record["analytics"],
        }
        export_sha256 = _digest(material)
        quality_sha256 = _digest(record["quality"])
        segmentation_sha256 = _digest(record["analytics"])
        quality = record["quality"]
        analytics = record["analytics"]
        chain = quality["accepted_chain"]
    except (KeyError, TypeError, ValueError):
        raise OverviewProjectionError("Loaded P7 export binding is invalid") from None

    if (
        record.get("export_sha256") != loaded.export_sha256
        or export_sha256 != loaded.export_sha256
        or quality_sha256 != loaded.quality_sha256
        or segmentation_sha256 != loaded.segmentation_sha256
        or loaded.source.export_sha256 != loaded.export_sha256
        or loaded.source.symbol != analytics.get("symbol")
        or loaded.source.observed_at_ms != quality.get("snapshot_time_ms")
        or quality.get("status") != "PASS"
        or quality.get("publication_allowed") is not True
        or quality.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or analytics.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or not isinstance(chain, dict)
        or chain.get("symbol") != loaded.source.symbol
        or chain.get("segmentation_sha256") != loaded.segmentation_sha256
    ):
        raise OverviewProjectionError("Loaded P7 export provenance changed")

    quality_safety = quality.get("safety")
    analytics_safety = analytics.get("safety")
    if not isinstance(quality_safety, dict) or not isinstance(analytics_safety, dict):
        raise OverviewProjectionError("Accepted P7 safety material is missing")
    if (
        quality_safety.get("paper_only") is not True
        or analytics_safety.get("paper_only") is not True
        or quality_safety.get("live_master_lock") != "OFF"
        or analytics_safety.get("live_master_lock") != "OFF"
        or quality_safety.get("trade_permission") is not False
        or analytics_safety.get("trade_permission") is not False
        or quality_safety.get("order_endpoints") is not False
        or analytics_safety.get("order_endpoints") is not False
        or quality_safety.get("quantity_authority") is not False
        or analytics_safety.get("quantity_authority") is not False
        or quality_safety.get("risk_authorization_mutation") is not False
        or analytics_safety.get("risk_authorization_mutation") is not False
        or quality_safety.get("ai_direct_execution") is not False
        or analytics_safety.get("ai_direct_execution") is not False
    ):
        raise OverviewProjectionError("Accepted P7 safety boundary changed")

    completed = chain.get("completed_trade_count")
    if type(completed) is not int or completed < 0:
        raise OverviewProjectionError("Completed trade count is invalid")
    return record, quality, analytics, chain


def _card(card_id, field_key, label, value, display_kind, source_sha256):
    return DashboardOverviewCard(
        card_id,
        field_key,
        label,
        value,
        display_kind,
        source_sha256,
    )


@dataclass(frozen=True, slots=True)
class DashboardOverviewProjection:
    """Bounded P8 overview that conserves accepted P7 source semantics exactly."""

    source: DashboardSourceIdentity
    cards: tuple[DashboardOverviewCard, ...]
    unknown_fields: tuple[str, ...] = UNKNOWN_FIELDS
    schema_version: int = OVERVIEW_SCHEMA_VERSION

    def __post_init__(self):
        if (
            not isinstance(self.source, DashboardSourceIdentity)
            or type(self.cards) is not tuple
            or tuple(item.card_id for item in self.cards) != EXPECTED_CARD_IDS
            or tuple(item.field_key for item in self.cards) != EXPECTED_FIELD_KEYS
            or any(not isinstance(item, DashboardOverviewCard) for item in self.cards)
            or self.unknown_fields != UNKNOWN_FIELDS
            or self.schema_version != OVERVIEW_SCHEMA_VERSION
        ):
            raise OverviewProjectionError("Dashboard overview projection is invalid")
        by_key = {item.field_key: item for item in self.cards}
        if len(by_key) != len(self.cards):
            raise OverviewProjectionError("Dashboard overview fields are duplicate")
        if (
            by_key["open_trade_count"].value != UNKNOWN_VALUE
            or by_key["snapshot_freshness"].value != UNKNOWN_VALUE
            or by_key["paper_state"].value != "PAPER ONLY"
            or by_key["live_master_lock"].value != "OFF"
            or by_key["strategy_evidence"].value != "INSUFFICIENT_EVIDENCE"
            or by_key["quality_status"].value != "PASS"
        ):
            raise OverviewProjectionError("Dashboard overview safety state was weakened")

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "source": self.source.as_record(),
            "cards": [item.as_record() for item in self.cards],
            "unknown_fields": list(self.unknown_fields),
        }

    @property
    def overview_sha256(self):
        return _digest(self.as_record())


def project_overview(loaded):
    """Project only accepted P7 source fields; never infer readiness or freshness."""

    _, quality, analytics, chain = _verify_loaded_export(loaded)
    snapshot_time_ms = quality["snapshot_time_ms"]
    completed_trade_count = chain["completed_trade_count"]

    cards = (
        _card(
            "CARD_01_SYMBOL",
            "symbol",
            "Symbol",
            analytics["symbol"],
            OverviewDisplayKind.TEXT,
            _field_sha256("analytics.symbol", analytics["symbol"]),
        ),
        _card(
            "CARD_02_EXPORT_SHA256",
            "export_sha256",
            "Accepted P7 Export SHA-256",
            loaded.export_sha256,
            OverviewDisplayKind.HASH,
            _field_sha256("export_sha256", loaded.export_sha256),
        ),
        _card(
            "CARD_03_SNAPSHOT_TIME_MS",
            "snapshot_time_ms",
            "Snapshot Time (ms UTC)",
            str(snapshot_time_ms),
            OverviewDisplayKind.TEXT,
            _field_sha256("quality.snapshot_time_ms", snapshot_time_ms),
        ),
        _card(
            "CARD_04_PAPER_STATE",
            "paper_state",
            "Mode",
            "PAPER ONLY",
            OverviewDisplayKind.STATUS,
            _field_sha256("quality.safety.paper_only", True),
        ),
        _card(
            "CARD_05_LIVE_MASTER_LOCK",
            "live_master_lock",
            "Live Master Lock",
            quality["safety"]["live_master_lock"],
            OverviewDisplayKind.STATUS,
            _field_sha256(
                "quality.safety.live_master_lock",
                quality["safety"]["live_master_lock"],
            ),
        ),
        _card(
            "CARD_06_STRATEGY_EVIDENCE",
            "strategy_evidence",
            "Strategy Evidence",
            analytics["strategy_evidence"],
            OverviewDisplayKind.STATUS,
            _field_sha256(
                "analytics.strategy_evidence",
                analytics["strategy_evidence"],
            ),
        ),
        _card(
            "CARD_07_QUALITY_STATUS",
            "quality_status",
            "P7 Quality",
            quality["status"],
            OverviewDisplayKind.STATUS,
            _field_sha256("quality.status", quality["status"]),
        ),
        _card(
            "CARD_08_COMPLETED_TRADE_COUNT",
            "completed_trade_count",
            "Completed Paper Trades",
            str(completed_trade_count),
            OverviewDisplayKind.COUNT,
            _field_sha256(
                "quality.accepted_chain.completed_trade_count",
                completed_trade_count,
            ),
        ),
        _card(
            "CARD_09_OPEN_TRADE_COUNT",
            "open_trade_count",
            "Open Trade Count",
            UNKNOWN_VALUE,
            OverviewDisplayKind.STATUS,
            _unknown_sha256(
                "open_trade_count",
                "NOT_EXPORTED_BY_ACCEPTED_P7_SEGMENTATION",
            ),
        ),
        _card(
            "CARD_10_SNAPSHOT_FRESHNESS",
            "snapshot_freshness",
            "Snapshot Freshness",
            UNKNOWN_VALUE,
            OverviewDisplayKind.STATUS,
            _unknown_sha256(
                "snapshot_freshness",
                "NO_CLOCK_OR_STALENESS_THRESHOLD_IN_P8_003",
            ),
        ),
        _card(
            "CARD_11_INGESTION_MANIFEST_SHA256",
            "ingestion_manifest_sha256",
            "Ingestion Manifest SHA-256",
            chain["ingestion_manifest_sha256"],
            OverviewDisplayKind.HASH,
            _field_sha256(
                "quality.accepted_chain.ingestion_manifest_sha256",
                chain["ingestion_manifest_sha256"],
            ),
        ),
        _card(
            "CARD_12_TIMELINE_SHA256",
            "timeline_sha256",
            "Timeline SHA-256",
            chain["timeline_sha256"],
            OverviewDisplayKind.HASH,
            _field_sha256(
                "quality.accepted_chain.timeline_sha256",
                chain["timeline_sha256"],
            ),
        ),
        _card(
            "CARD_13_RECONSTRUCTION_SHA256",
            "reconstruction_sha256",
            "Reconstruction SHA-256",
            chain["reconstruction_sha256"],
            OverviewDisplayKind.HASH,
            _field_sha256(
                "quality.accepted_chain.reconstruction_sha256",
                chain["reconstruction_sha256"],
            ),
        ),
        _card(
            "CARD_14_METRICS_SHA256",
            "metrics_sha256",
            "Metrics SHA-256",
            chain["metrics_sha256"],
            OverviewDisplayKind.HASH,
            _field_sha256(
                "quality.accepted_chain.metrics_sha256",
                chain["metrics_sha256"],
            ),
        ),
        _card(
            "CARD_15_SEGMENTATION_SHA256",
            "segmentation_sha256",
            "Segmentation SHA-256",
            chain["segmentation_sha256"],
            OverviewDisplayKind.HASH,
            _field_sha256(
                "quality.accepted_chain.segmentation_sha256",
                chain["segmentation_sha256"],
            ),
        ),
    )
    return DashboardOverviewProjection(loaded.source, cards)
