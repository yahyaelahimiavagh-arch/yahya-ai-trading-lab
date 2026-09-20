"""Strict read-only loader for accepted canonical P7 analytics exports."""

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from .contracts import DashboardSourceIdentity


P7_EXPORT_SCHEMA_VERSION = 1
P7_QUALITY_SCHEMA_VERSION = 1
P7_SEGMENTATION_SCHEMA_VERSION = 1
MAX_P7_EXPORT_BYTES = 8 * 1024 * 1024
MAX_P7_TRADE_METRICS = 4096
MAX_P7_ANALYST_TRACES = 4096
MAX_P7_SEGMENTS = 4096
SYMBOLS = ("BTCUSDT", "ETHUSDT")
_HEX = frozenset("0123456789abcdef")
_SECRET_KEYS = frozenset((
    "api_key",
    "api_secret",
    "password",
    "private_key",
    "access_token",
    "refresh_token",
    "credential",
    "credentials",
    "endpoint_url",
    "raw_response",
    "account_id",
))
_SECRET_VALUE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)

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
_ANALYTICS_KEYS = frozenset((
    "schema_version",
    "metrics_sha256",
    "reconstruction_sha256",
    "timeline_sha256",
    "analyst_source_sha256",
    "symbol",
    "strategy_evidence",
    "strategy_attribution_status",
    "trade_metrics",
    "analyst_traces",
    "trade_segments",
    "analyst_segments",
    "interpretation",
    "safety",
))
_TRADE_METRIC_KEYS = frozenset((
    "trade_index",
    "trade_sha256",
    "realized_pnl_quote",
    "entry_gross_quote",
    "exit_gross_quote",
    "entry_cash_out_quote",
    "gross_return",
    "net_return",
    "total_fee_quote",
    "total_slippage_quote",
    "holding_time_ms",
))
_ANALYST_TRACE_KEYS = frozenset((
    "trace_sha256",
    "disposition",
    "grounding_code",
    "accepted",
))
_TRADE_SEGMENT_KEYS = frozenset((
    "segment_id",
    "population",
    "dimension",
    "value",
    "member_trade_sha256",
    "member_count",
    "realized_pnl_quote",
    "total_cost_quote",
    "winning_trades",
    "losing_trades",
    "breakeven_trades",
    "segment_sha256",
))
_ANALYST_SEGMENT_KEYS = frozenset((
    "segment_id",
    "population",
    "dimension",
    "value",
    "member_trace_sha256",
    "member_count",
    "segment_sha256",
))
_INTERPRETATION_KEYS = frozenset((
    "trade_to_strategy_attribution",
    "trade_to_analyst_disposition_attribution",
    "causality_claim",
    "correlation_only",
    "reason",
))
_QUALITY_SAFETY = {
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
_ANALYTICS_SAFETY = {
    "descriptive_only": True,
    "read_only": True,
    "paper_only": True,
    "live_master_lock": "OFF",
    "strategy_evidence_upgrade": False,
    "upstream_mutation": False,
    "trade_permission": False,
    "order_endpoints": False,
    "quantity_authority": False,
    "risk_authorization_mutation": False,
    "ai_direct_execution": False,
}


class P7ExportLoadCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    STORAGE_ERROR = "STORAGE_ERROR"
    TOO_LARGE = "TOO_LARGE"
    INVALID_UTF8 = "INVALID_UTF8"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    NONCANONICAL = "NONCANONICAL"
    SECRET_BEARING = "SECRET_BEARING"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    QUALITY_REJECTED = "QUALITY_REJECTED"
    SAFETY_MISMATCH = "SAFETY_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"


class P7ExportLoadError(Exception):
    """Stable fail-closed loader error that never exposes caller-supplied paths."""

    def __init__(self, code):
        if not isinstance(code, P7ExportLoadCode):
            raise TypeError("P7 export loader error code is invalid")
        self.code = code
        super().__init__(code.value)


class _DuplicateJsonKey(ValueError):
    pass


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


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


def _valid_decimal(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite()


def _expect_keys(value, expected):
    if not isinstance(value, dict) or frozenset(value) != expected:
        raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)


def _bounded_list(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)


def _scan_secret_material(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
            if key.lower() in _SECRET_KEYS:
                raise P7ExportLoadError(P7ExportLoadCode.SECRET_BEARING)
            _scan_secret_material(item)
    elif isinstance(value, list):
        for item in value:
            _scan_secret_material(item)
    elif isinstance(value, str):
        upper = value.upper()
        if any(marker in upper for marker in _SECRET_VALUE_MARKERS):
            raise P7ExportLoadError(P7ExportLoadCode.SECRET_BEARING)


def _validate_quality(quality):
    _expect_keys(quality, _QUALITY_KEYS)
    if quality["schema_version"] != P7_QUALITY_SCHEMA_VERSION:
        raise P7ExportLoadError(P7ExportLoadCode.UNSUPPORTED_VERSION)
    if (
        type(quality["snapshot_time_ms"]) is not int
        or quality["snapshot_time_ms"] < 0
        or quality["status"] != "PASS"
        or quality["publication_allowed"] is not True
        or quality["diagnostics"] != []
        or type(quality["passed_checks"]) is not list
        or any(not isinstance(item, str) or not item for item in quality["passed_checks"])
        or len(set(quality["passed_checks"])) != len(quality["passed_checks"])
        or quality["passed_checks"] != sorted(quality["passed_checks"])
        or quality["strategy_evidence"] != "INSUFFICIENT_EVIDENCE"
    ):
        raise P7ExportLoadError(P7ExportLoadCode.QUALITY_REJECTED)
    if quality["safety"] != _QUALITY_SAFETY:
        raise P7ExportLoadError(P7ExportLoadCode.SAFETY_MISMATCH)

    chain = quality["accepted_chain"]
    _expect_keys(chain, _CHAIN_KEYS)
    if (
        chain["symbol"] not in SYMBOLS
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
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)
    return chain


def _validate_trade_metrics(items):
    _bounded_list(items, MAX_P7_TRADE_METRICS)
    identities = []
    previous_index = -1
    for item in items:
        _expect_keys(item, _TRADE_METRIC_KEYS)
        if (
            type(item["trade_index"]) is not int
            or item["trade_index"] < 0
            or item["trade_index"] <= previous_index
            or not _valid_sha(item["trade_sha256"])
            or type(item["holding_time_ms"]) is not int
            or item["holding_time_ms"] < 0
            or any(
                not _valid_decimal(item[name])
                for name in (
                    "realized_pnl_quote",
                    "entry_gross_quote",
                    "exit_gross_quote",
                    "entry_cash_out_quote",
                    "gross_return",
                    "net_return",
                    "total_fee_quote",
                    "total_slippage_quote",
                )
            )
        ):
            raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
        identities.append(item["trade_sha256"])
        previous_index = item["trade_index"]
    if len(set(identities)) != len(identities):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)


def _validate_analyst_traces(items):
    _bounded_list(items, MAX_P7_ANALYST_TRACES)
    identities = []
    for item in items:
        _expect_keys(item, _ANALYST_TRACE_KEYS)
        if (
            not _valid_sha(item["trace_sha256"])
            or item["disposition"] not in ("REVIEW", "INSUFFICIENT_DATA")
            or not isinstance(item["grounding_code"], str)
            or not item["grounding_code"]
            or type(item["accepted"]) is not bool
        ):
            raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
        if item["accepted"]:
            if item["disposition"] != "REVIEW" or item["grounding_code"] != "GROUNDED":
                raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)
        elif item["disposition"] != "INSUFFICIENT_DATA" or item["grounding_code"] == "GROUNDED":
            raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)
        identities.append(item["trace_sha256"])
    if identities != sorted(identities) or len(set(identities)) != len(identities):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)


def _validate_trade_segments(items):
    _bounded_list(items, MAX_P7_SEGMENTS)
    segment_ids = []
    for item in items:
        _expect_keys(item, _TRADE_SEGMENT_KEYS)
        members = item["member_trade_sha256"]
        if (
            not _valid_sha(item["segment_id"])
            or item["population"] != "COMPLETED_TRADES"
            or item["dimension"] not in (
                "SYMBOL",
                "STRATEGY_IDENTITY",
                "EVIDENCE_LABEL",
            )
            or not isinstance(item["value"], str)
            or not item["value"]
            or type(members) is not list
            or len(members) > MAX_P7_TRADE_METRICS
            or members != sorted(members)
            or len(set(members)) != len(members)
            or any(not _valid_sha(member) for member in members)
            or type(item["member_count"]) is not int
            or item["member_count"] != len(members)
            or any(
                type(item[name]) is not int or item[name] < 0
                for name in ("winning_trades", "losing_trades", "breakeven_trades")
            )
            or item["winning_trades"] + item["losing_trades"] + item["breakeven_trades"]
            != item["member_count"]
            or not _valid_decimal(item["realized_pnl_quote"])
            or not _valid_decimal(item["total_cost_quote"])
            or Decimal(item["total_cost_quote"]) < 0
            or not _valid_sha(item["segment_sha256"])
        ):
            raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
        base = {key: value for key, value in item.items() if key != "segment_sha256"}
        expected = _digest({
            "schema_version": P7_SEGMENTATION_SCHEMA_VERSION,
            "segment": base,
        })
        if item["segment_sha256"] != expected:
            raise P7ExportLoadError(P7ExportLoadCode.DIGEST_MISMATCH)
        segment_ids.append(item["segment_id"])
    if len(set(segment_ids)) != len(segment_ids):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)


def _validate_analyst_segments(items):
    _bounded_list(items, MAX_P7_SEGMENTS)
    segment_ids = []
    for item in items:
        _expect_keys(item, _ANALYST_SEGMENT_KEYS)
        members = item["member_trace_sha256"]
        if (
            not _valid_sha(item["segment_id"])
            or item["population"] != "ANALYST_TRACES"
            or item["dimension"] not in (
                "ANALYST_DISPOSITION",
                "GROUNDING_CODE",
                "TRACE_ACCEPTANCE",
            )
            or not isinstance(item["value"], str)
            or not item["value"]
            or type(members) is not list
            or len(members) > MAX_P7_ANALYST_TRACES
            or members != sorted(members)
            or len(set(members)) != len(members)
            or any(not _valid_sha(member) for member in members)
            or type(item["member_count"]) is not int
            or item["member_count"] != len(members)
            or not _valid_sha(item["segment_sha256"])
        ):
            raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
        base = {key: value for key, value in item.items() if key != "segment_sha256"}
        expected = _digest({
            "schema_version": P7_SEGMENTATION_SCHEMA_VERSION,
            "segment": base,
        })
        if item["segment_sha256"] != expected:
            raise P7ExportLoadError(P7ExportLoadCode.DIGEST_MISMATCH)
        segment_ids.append(item["segment_id"])
    if len(set(segment_ids)) != len(segment_ids):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)


def _validate_analytics(analytics):
    _expect_keys(analytics, _ANALYTICS_KEYS)
    if analytics["schema_version"] != P7_SEGMENTATION_SCHEMA_VERSION:
        raise P7ExportLoadError(P7ExportLoadCode.UNSUPPORTED_VERSION)
    if (
        analytics["symbol"] not in SYMBOLS
        or analytics["strategy_evidence"] != "INSUFFICIENT_EVIDENCE"
        or analytics["strategy_attribution_status"]
        != "UNAVAILABLE_IN_ACCEPTED_DURABLE_P5"
        or any(
            not _valid_sha(analytics[name])
            for name in (
                "metrics_sha256",
                "reconstruction_sha256",
                "timeline_sha256",
                "analyst_source_sha256",
            )
        )
    ):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)
    if analytics["safety"] != _ANALYTICS_SAFETY:
        raise P7ExportLoadError(P7ExportLoadCode.SAFETY_MISMATCH)

    interpretation = analytics["interpretation"]
    _expect_keys(interpretation, _INTERPRETATION_KEYS)
    if (
        interpretation["trade_to_strategy_attribution"] is not False
        or interpretation["trade_to_analyst_disposition_attribution"] is not False
        or interpretation["causality_claim"] is not False
        or interpretation["correlation_only"] is not True
        or not isinstance(interpretation["reason"], str)
        or not interpretation["reason"]
        or len(interpretation["reason"]) > 512
    ):
        raise P7ExportLoadError(P7ExportLoadCode.SAFETY_MISMATCH)

    _validate_trade_metrics(analytics["trade_metrics"])
    _validate_analyst_traces(analytics["analyst_traces"])
    _validate_trade_segments(analytics["trade_segments"])
    _validate_analyst_segments(analytics["analyst_segments"])


def _validate_binding(quality, analytics):
    chain = quality["accepted_chain"]
    if (
        chain["symbol"] != analytics["symbol"]
        or chain["timeline_sha256"] != analytics["timeline_sha256"]
        or chain["reconstruction_sha256"] != analytics["reconstruction_sha256"]
        or chain["metrics_sha256"] != analytics["metrics_sha256"]
        or chain["completed_trade_count"] != len(analytics["trade_metrics"])
        or chain["analyst_trace_count"] != len(analytics["analyst_traces"])
    ):
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)

    segmentation_sha256 = _digest(analytics)
    if chain["segmentation_sha256"] != segmentation_sha256:
        raise P7ExportLoadError(P7ExportLoadCode.DIGEST_MISMATCH)
    return segmentation_sha256


def _read_readonly_file(path):
    if not isinstance(path, (str, os.PathLike)) or not str(path):
        raise P7ExportLoadError(P7ExportLoadCode.INVALID_REQUEST)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise P7ExportLoadError(P7ExportLoadCode.NOT_FOUND) from None
    except OSError:
        raise P7ExportLoadError(P7ExportLoadCode.STORAGE_ERROR) from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise P7ExportLoadError(P7ExportLoadCode.STORAGE_ERROR)
        if metadata.st_size <= 0:
            raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
        if metadata.st_size > MAX_P7_EXPORT_BYTES:
            raise P7ExportLoadError(P7ExportLoadCode.TOO_LARGE)
        data = os.read(descriptor, MAX_P7_EXPORT_BYTES + 1)
        if len(data) > MAX_P7_EXPORT_BYTES:
            raise P7ExportLoadError(P7ExportLoadCode.TOO_LARGE)
        if len(data) != metadata.st_size:
            raise P7ExportLoadError(P7ExportLoadCode.STORAGE_ERROR)
        return data
    except P7ExportLoadError:
        raise
    except OSError:
        raise P7ExportLoadError(P7ExportLoadCode.STORAGE_ERROR) from None
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class LoadedP7Export:
    """Immutable provenance binding to one accepted canonical P7 export."""

    source: DashboardSourceIdentity
    quality_sha256: str
    segmentation_sha256: str
    export_sha256: str
    raw_file_sha256: str
    byte_length: int
    canonical_json: str

    def __post_init__(self):
        if (
            not isinstance(self.source, DashboardSourceIdentity)
            or any(
                not _valid_sha(value)
                for value in (
                    self.quality_sha256,
                    self.segmentation_sha256,
                    self.export_sha256,
                    self.raw_file_sha256,
                )
            )
            or self.source.export_sha256 != self.export_sha256
            or type(self.byte_length) is not int
            or not 1 <= self.byte_length <= MAX_P7_EXPORT_BYTES
            or not isinstance(self.canonical_json, str)
            or not self.canonical_json.endswith("\n")
        ):
            raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)

    def record(self):
        return json.loads(self.canonical_json)


def load_p7_export(path, expected_export_sha256):
    """Load one exact accepted P7 export without modifying or resolving its source."""

    if not _valid_sha(expected_export_sha256):
        raise P7ExportLoadError(P7ExportLoadCode.INVALID_REQUEST)

    raw = _read_readonly_file(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise P7ExportLoadError(P7ExportLoadCode.INVALID_UTF8) from None

    try:
        record = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except _DuplicateJsonKey:
        raise P7ExportLoadError(P7ExportLoadCode.DUPLICATE_KEY) from None
    except (json.JSONDecodeError, TypeError, ValueError):
        raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID) from None

    if not isinstance(record, dict):
        raise P7ExportLoadError(P7ExportLoadCode.SCHEMA_INVALID)
    _scan_secret_material(record)

    _expect_keys(
        record,
        frozenset(("schema_version", "quality", "analytics", "export_sha256")),
    )
    if record["schema_version"] != P7_EXPORT_SCHEMA_VERSION:
        raise P7ExportLoadError(P7ExportLoadCode.UNSUPPORTED_VERSION)
    if not _valid_sha(record["export_sha256"]):
        raise P7ExportLoadError(P7ExportLoadCode.DIGEST_MISMATCH)

    canonical = _json(record) + "\n"
    if text != canonical:
        raise P7ExportLoadError(P7ExportLoadCode.NONCANONICAL)

    material = {
        "schema_version": record["schema_version"],
        "quality": record["quality"],
        "analytics": record["analytics"],
    }
    computed_export_sha256 = _digest(material)
    if (
        record["export_sha256"] != computed_export_sha256
        or expected_export_sha256 != computed_export_sha256
    ):
        raise P7ExportLoadError(P7ExportLoadCode.DIGEST_MISMATCH)

    chain = _validate_quality(record["quality"])
    _validate_analytics(record["analytics"])
    segmentation_sha256 = _validate_binding(
        record["quality"],
        record["analytics"],
    )
    quality_sha256 = _digest(record["quality"])

    source = DashboardSourceIdentity(
        "P7_EXPORT_" + computed_export_sha256[:16].upper(),
        record["analytics"]["symbol"],
        record["schema_version"],
        record["quality"]["snapshot_time_ms"],
        computed_export_sha256,
    )
    if source.symbol != chain["symbol"]:
        raise P7ExportLoadError(P7ExportLoadCode.IDENTITY_MISMATCH)

    return LoadedP7Export(
        source=source,
        quality_sha256=quality_sha256,
        segmentation_sha256=segmentation_sha256,
        export_sha256=computed_export_sha256,
        raw_file_sha256=hashlib.sha256(raw).hexdigest(),
        byte_length=len(raw),
        canonical_json=canonical,
    )
