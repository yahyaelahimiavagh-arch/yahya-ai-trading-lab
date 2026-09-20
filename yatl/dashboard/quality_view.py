"""Deterministic P8-006 quality and diagnostic display projection."""

import hashlib
import json
from dataclasses import dataclass

from .contracts import DashboardDiagnostic, DiagnosticSeverity
from .loader import LoadedP7Export


QUALITY_VIEW_SCHEMA_VERSION = 1
P7_QUALITY_SCHEMA_VERSION = 1
MAX_P7_DIAGNOSTICS = 8
MAX_P7_PASSED_CHECKS = 16

_QUALITY_KEYS = frozenset((
    "schema_version",
    "snapshot_time_ms",
    "status",
    "publication_allowed",
    "diagnostics",
    "passed_checks",
    "accepted_chain",
    "strategy_evidence",
    "safety",
))
_DIAGNOSTIC_KEYS = frozenset(("code", "component"))
_CHAIN_KEYS = frozenset((
    "symbol",
    "ingestion_manifest_sha256",
    "timeline_sha256",
    "reconstruction_sha256",
    "metrics_sha256",
    "segmentation_sha256",
    "completed_trade_count",
    "analyst_trace_count",
))
_SAFETY = {
    "descriptive_only": True,
    "read_only": True,
    "paper_only": True,
    "live_master_lock": "OFF",
    "partial_publication_on_failure": False,
    "strategy_evidence_upgrade": False,
    "upstream_mutation": False,
    "trade_permission": False,
    "order_endpoints": False,
    "quantity_authority": False,
    "risk_authorization_mutation": False,
    "ai_direct_execution": False,
}

QUALITY_CODES = (
    "ANALYTICS_CHAIN_INVALID",
    "DUPLICATE_IDENTITY",
    "FUTURE_TIMESTAMP",
    "INCONSISTENT_TOTALS",
    "MISSING_SOURCE",
    "ORPHAN_RELATIONSHIP",
    "REPORT_ARITHMETIC",
    "SOURCE_IDENTITY_INVALID",
    "TIMELINE_GAP",
    "UPSTREAM_DIGEST_CHANGED",
    "UPSTREAM_MUTATION",
)
QUALITY_COMPONENTS = (
    "GATE",
    "METRICS",
    "SEGMENTATION",
    "SOURCE",
    "TIMELINE",
    "TRADES",
)
QUALITY_CHECKS = (
    "METRICS_ARITHMETIC",
    "REPORT_BINDINGS",
    "SEGMENT_PARTITIONS",
    "SEGMENT_TOTALS",
    "SOURCE_COVERAGE",
    "SOURCE_DIGESTS",
    "SOURCE_NO_WRITE",
    "SOURCE_POINT_IN_TIME",
    "TIMELINE_IDENTITIES",
    "TIMELINE_RELATIONSHIPS",
    "TIMELINE_SEQUENCE",
    "TRADE_RECONCILIATION",
)

_MESSAGE_BY_CODE = {
    "MISSING_SOURCE": "A required P7 source is unavailable.",
    "SOURCE_IDENTITY_INVALID": "P7 source identity validation failed.",
    "UPSTREAM_DIGEST_CHANGED": "An accepted upstream digest no longer matches.",
    "FUTURE_TIMESTAMP": "P7 point-in-time validation found a future timestamp.",
    "DUPLICATE_IDENTITY": "P7 quality validation found a duplicate identity.",
    "ORPHAN_RELATIONSHIP": "P7 relationship validation found an orphaned reference.",
    "TIMELINE_GAP": "P7 timeline sequence validation found a gap.",
    "INCONSISTENT_TOTALS": "P7 conserved totals validation failed.",
    "REPORT_ARITHMETIC": "P7 report arithmetic validation failed.",
    "ANALYTICS_CHAIN_INVALID": "P7 analytics chain validation failed.",
    "UPSTREAM_MUTATION": "P7 detected upstream mutation during validation.",
}
_SEVERITY_BY_CODE = {
    code: DiagnosticSeverity.ERROR
    for code in QUALITY_CODES
}
_STATUS_MESSAGE = {
    "PASS": "Accepted P7 quality state is PASS.",
    "FAIL": "P7 quality state is FAIL; analytics presentation is blocked.",
    "ABSENT": "P7 quality state is unavailable; analytics presentation is blocked.",
}
_HEX = frozenset("0123456789abcdef")


class QualityDiagnosticProjectionError(ValueError):
    """P7 quality state cannot be projected without violating the P8 boundary."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    material = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _expect_keys(value, expected):
    if not isinstance(value, dict) or frozenset(value) != expected:
        raise QualityDiagnosticProjectionError("P7 quality schema is invalid")


def _validate_checks(checks, *, require_complete):
    if (
        type(checks) is not list
        or len(checks) > MAX_P7_PASSED_CHECKS
        or any(not isinstance(item, str) for item in checks)
        or checks != sorted(checks)
        or len(checks) != len(set(checks))
        or any(item not in QUALITY_CHECKS for item in checks)
    ):
        raise QualityDiagnosticProjectionError("P7 passed-check set is invalid")
    if require_complete and tuple(checks) != QUALITY_CHECKS:
        raise QualityDiagnosticProjectionError("PASS quality report is missing checks")
    return tuple(checks)


def _validate_chain(chain, loaded):
    _expect_keys(chain, _CHAIN_KEYS)
    if (
        chain["symbol"] != loaded.source.symbol
        or chain["segmentation_sha256"] != loaded.segmentation_sha256
        or type(chain["completed_trade_count"]) is not int
        or chain["completed_trade_count"] < 0
        or type(chain["analyst_trace_count"]) is not int
        or chain["analyst_trace_count"] < 0
        or any(
            not _valid_sha(chain[name])
            for name in (
                "ingestion_manifest_sha256",
                "timeline_sha256",
                "reconstruction_sha256",
                "metrics_sha256",
                "segmentation_sha256",
            )
        )
    ):
        raise QualityDiagnosticProjectionError("P7 accepted quality chain is invalid")


def _validate_diagnostics(diagnostics):
    if (
        type(diagnostics) is not list
        or not 1 <= len(diagnostics) <= MAX_P7_DIAGNOSTICS
    ):
        raise QualityDiagnosticProjectionError("FAIL quality diagnostics are invalid")
    identities = []
    for item in diagnostics:
        _expect_keys(item, _DIAGNOSTIC_KEYS)
        code = item["code"]
        component = item["component"]
        if code not in QUALITY_CODES or component not in QUALITY_COMPONENTS:
            raise QualityDiagnosticProjectionError("Unknown P7 diagnostic code")
        identities.append((code, component))
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise QualityDiagnosticProjectionError(
            "P7 diagnostics are duplicate or unordered"
        )
    return tuple(diagnostics)


def _validate_common_quality(record):
    _expect_keys(record, _QUALITY_KEYS)
    if (
        record["schema_version"] != P7_QUALITY_SCHEMA_VERSION
        or type(record["snapshot_time_ms"]) is not int
        or record["snapshot_time_ms"] < 0
        or record["strategy_evidence"] != "INSUFFICIENT_EVIDENCE"
        or record["safety"] != _SAFETY
    ):
        raise QualityDiagnosticProjectionError("P7 quality identity is invalid")


def _validate_pass_quality(record, loaded):
    _validate_common_quality(record)
    if (
        record["status"] != "PASS"
        or record["publication_allowed"] is not True
        or record["diagnostics"] != []
        or not isinstance(record["accepted_chain"], dict)
    ):
        raise QualityDiagnosticProjectionError("Accepted P7 quality is not PASS")
    checks = _validate_checks(record["passed_checks"], require_complete=True)
    _validate_chain(record["accepted_chain"], loaded)
    return checks


def _validate_fail_quality(record):
    _validate_common_quality(record)
    if (
        record["status"] != "FAIL"
        or record["publication_allowed"] is not False
        or record["accepted_chain"] is not None
    ):
        raise QualityDiagnosticProjectionError(
            "Failed P7 quality attempted partial publication"
        )
    checks = _validate_checks(record["passed_checks"], require_complete=False)
    diagnostics = _validate_diagnostics(record["diagnostics"])
    return checks, diagnostics


def _diagnostic_rows(items):
    rows = []
    for index, item in enumerate(items):
        source_sha = _digest({
            "schema_version": P7_QUALITY_SCHEMA_VERSION,
            "diagnostic": item,
        })
        code = item["code"]
        component = item["component"]
        rows.append(
            DashboardDiagnostic(
                diagnostic_id=f"DIAGNOSTIC_{index:03d}_{code}_{component}",
                code=code,
                severity=_SEVERITY_BY_CODE[code],
                message=f"{_MESSAGE_BY_CODE[code]} Component: {component}.",
                source_diagnostic_sha256=source_sha,
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class QualityDiagnosticProjection:
    """Quality-gated display state with no analytics payload or execution authority."""

    quality_status: str
    status_severity: DiagnosticSeverity
    status_message: str
    publication_allowed: bool
    analytics_presentation_allowed: bool
    partial_analytics_visible: bool
    diagnostics: tuple[DashboardDiagnostic, ...]
    passed_checks: tuple[str, ...]
    source_quality_sha256: str | None
    source_export_sha256: str | None
    snapshot_time_ms: int | None
    source_mode: str
    strategy_evidence: str = "INSUFFICIENT_EVIDENCE"
    display_only: bool = True
    schema_version: int = QUALITY_VIEW_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.quality_status not in ("PASS", "FAIL", "ABSENT")
            or not isinstance(self.status_severity, DiagnosticSeverity)
            or self.status_message != _STATUS_MESSAGE[self.quality_status]
            or type(self.publication_allowed) is not bool
            or type(self.analytics_presentation_allowed) is not bool
            or self.analytics_presentation_allowed != self.publication_allowed
            or self.partial_analytics_visible is not False
            or type(self.diagnostics) is not tuple
            or len(self.diagnostics) > MAX_P7_DIAGNOSTICS
            or any(not isinstance(item, DashboardDiagnostic) for item in self.diagnostics)
            or tuple(item.diagnostic_id for item in self.diagnostics)
            != tuple(sorted(item.diagnostic_id for item in self.diagnostics))
            or type(self.passed_checks) is not tuple
            or len(self.passed_checks) > MAX_P7_PASSED_CHECKS
            or tuple(sorted(set(self.passed_checks))) != self.passed_checks
            or any(item not in QUALITY_CHECKS for item in self.passed_checks)
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or self.display_only is not True
            or self.schema_version != QUALITY_VIEW_SCHEMA_VERSION
        ):
            raise QualityDiagnosticProjectionError(
                "Quality diagnostic projection is invalid"
            )

        if self.quality_status == "PASS":
            if (
                self.status_severity is not DiagnosticSeverity.INFO
                or self.publication_allowed is not True
                or self.diagnostics
                or self.passed_checks != QUALITY_CHECKS
                or not _valid_sha(self.source_quality_sha256)
                or not _valid_sha(self.source_export_sha256)
                or type(self.snapshot_time_ms) is not int
                or self.snapshot_time_ms < 0
                or self.source_mode != "ACCEPTED_P7_EXPORT"
            ):
                raise QualityDiagnosticProjectionError(
                    "PASS quality projection is incomplete"
                )
        elif self.quality_status == "FAIL":
            if (
                self.status_severity is not DiagnosticSeverity.ERROR
                or self.publication_allowed is not False
                or not self.diagnostics
                or not _valid_sha(self.source_quality_sha256)
                or self.source_export_sha256 is not None
                or type(self.snapshot_time_ms) is not int
                or self.snapshot_time_ms < 0
                or self.source_mode != "SANITIZED_P7_QUALITY_REPORT"
            ):
                raise QualityDiagnosticProjectionError(
                    "FAIL quality projection exposed invalid state"
                )
        else:
            if (
                self.status_severity is not DiagnosticSeverity.ERROR
                or self.publication_allowed is not False
                or self.diagnostics
                or self.passed_checks
                or self.source_quality_sha256 is not None
                or self.source_export_sha256 is not None
                or self.snapshot_time_ms is not None
                or self.source_mode != "QUALITY_ABSENT"
            ):
                raise QualityDiagnosticProjectionError(
                    "ABSENT quality projection exposed invalid state"
                )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "quality_status": self.quality_status,
            "status_severity": self.status_severity.value,
            "status_message": self.status_message,
            "publication_allowed": self.publication_allowed,
            "analytics_presentation_allowed": self.analytics_presentation_allowed,
            "partial_analytics_visible": self.partial_analytics_visible,
            "diagnostics": [item.as_record() for item in self.diagnostics],
            "passed_checks": list(self.passed_checks),
            "source_quality_sha256": self.source_quality_sha256,
            "source_export_sha256": self.source_export_sha256,
            "snapshot_time_ms": self.snapshot_time_ms,
            "source_mode": self.source_mode,
            "strategy_evidence": self.strategy_evidence,
            "display_only": self.display_only,
        }

    @property
    def projection_sha256(self):
        return _digest(self.as_record())


def _project_pass(loaded):
    if not isinstance(loaded, LoadedP7Export):
        raise QualityDiagnosticProjectionError(
            "PASS quality projection requires accepted P7 export"
        )
    try:
        record = loaded.record()
        quality = record["quality"]
        analytics = record["analytics"]
        material = {
            "schema_version": record["schema_version"],
            "quality": quality,
            "analytics": analytics,
        }
    except (KeyError, TypeError, ValueError):
        raise QualityDiagnosticProjectionError(
            "Accepted P7 export quality binding is invalid"
        ) from None

    if (
        record.get("export_sha256") != loaded.export_sha256
        or _digest(material) != loaded.export_sha256
        or _digest(quality) != loaded.quality_sha256
        or loaded.source.export_sha256 != loaded.export_sha256
        or loaded.source.observed_at_ms != quality.get("snapshot_time_ms")
    ):
        raise QualityDiagnosticProjectionError(
            "Accepted P7 export quality provenance changed"
        )

    checks = _validate_pass_quality(quality, loaded)
    return QualityDiagnosticProjection(
        quality_status="PASS",
        status_severity=DiagnosticSeverity.INFO,
        status_message=_STATUS_MESSAGE["PASS"],
        publication_allowed=True,
        analytics_presentation_allowed=True,
        partial_analytics_visible=False,
        diagnostics=(),
        passed_checks=checks,
        source_quality_sha256=loaded.quality_sha256,
        source_export_sha256=loaded.export_sha256,
        snapshot_time_ms=quality["snapshot_time_ms"],
        source_mode="ACCEPTED_P7_EXPORT",
    )


def _project_fail(quality_record):
    if not isinstance(quality_record, dict):
        raise QualityDiagnosticProjectionError(
            "FAIL quality projection requires sanitized P7 quality report"
        )
    checks, diagnostics = _validate_fail_quality(quality_record)
    quality_sha = _digest(quality_record)
    return QualityDiagnosticProjection(
        quality_status="FAIL",
        status_severity=DiagnosticSeverity.ERROR,
        status_message=_STATUS_MESSAGE["FAIL"],
        publication_allowed=False,
        analytics_presentation_allowed=False,
        partial_analytics_visible=False,
        diagnostics=_diagnostic_rows(diagnostics),
        passed_checks=checks,
        source_quality_sha256=quality_sha,
        source_export_sha256=None,
        snapshot_time_ms=quality_record["snapshot_time_ms"],
        source_mode="SANITIZED_P7_QUALITY_REPORT",
    )


def project_quality_diagnostics(loaded=None, quality_record=None):
    """Project PASS/FAIL/ABSENT P7 quality without exposing partial analytics."""

    if loaded is not None and quality_record is not None:
        raise QualityDiagnosticProjectionError(
            "Quality projection accepts exactly one source mode"
        )
    if loaded is not None:
        return _project_pass(loaded)
    if quality_record is not None:
        return _project_fail(quality_record)
    return QualityDiagnosticProjection(
        quality_status="ABSENT",
        status_severity=DiagnosticSeverity.ERROR,
        status_message=_STATUS_MESSAGE["ABSENT"],
        publication_allowed=False,
        analytics_presentation_allowed=False,
        partial_analytics_visible=False,
        diagnostics=(),
        passed_checks=(),
        source_quality_sha256=None,
        source_export_sha256=None,
        snapshot_time_ms=None,
        source_mode="QUALITY_ABSENT",
    )
