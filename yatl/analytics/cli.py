"""Bounded noninteractive P7 analytics validation, views and canonical export."""

import argparse
import hashlib
import json
import os
import tempfile
from enum import Enum
from pathlib import Path

from .contracts import AnalyticsSourceKind
from .ingestion import AnalyticsIngestionError, UpstreamSourceSpec
from .quality import QualityStatus, run_quality_gate


ANALYTICS_CLI_SCHEMA_VERSION = 1
ANALYTICS_SPEC_SCHEMA_VERSION = 1
ANALYTICS_EXPORT_SCHEMA_VERSION = 1
MAX_SPEC_BYTES = 32 * 1024
MAX_CLI_OUTPUT_BYTES = 64 * 1024
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_TRADE_VIEW = 100

EXIT_OK = 0
EXIT_QUALITY = 20
EXIT_INVALID = 21
EXIT_STORAGE = 22
EXIT_EXISTS = 23
EXIT_OUTPUT = 24

_SECRET_MARKERS = (
    '"api_key"',
    '"api_secret"',
    '"password"',
    '"private_key"',
    '"access_token"',
    '"refresh_token"',
    '"credential"',
    '"endpoint_url"',
    '"raw_response"',
    '"account_id"',
)


class AnalyticsCliCode(str, Enum):
    VALIDATED = "VALIDATED"
    SUMMARY_READY = "SUMMARY_READY"
    TRADES_READY = "TRADES_READY"
    EXPORTED = "EXPORTED"
    QUALITY_FAILED = "QUALITY_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_INPUT = "INVALID_INPUT"
    STORAGE_ERROR = "STORAGE_ERROR"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"


class AnalyticsCliError(Exception):
    """Stable local CLI failure that never exposes caller-supplied values."""

    def __init__(self, code):
        if not isinstance(code, AnalyticsCliCode):
            raise TypeError("Analytics CLI error code is invalid")
        self.code = code
        super().__init__(code.value)


class _DuplicateJsonKey(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _exact_keys(record, expected):
    return isinstance(record, dict) and set(record) == set(expected)


def _read_bounded(path, max_bytes):
    if not isinstance(path, (str, Path)) or not str(path):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT) from None
    if not raw or len(raw) > max_bytes:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT) from None


def _reject_secret_like(raw):
    lowered = raw.casefold()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)


def load_analytics_spec(path):
    """Load exactly two trusted local source bindings from bounded JSON."""

    raw = _read_bounded(path, MAX_SPEC_BYTES)
    _reject_secret_like(raw)
    try:
        record = json.loads(raw, object_pairs_hook=_no_duplicate_object)
    except (json.JSONDecodeError, _DuplicateJsonKey):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT) from None
    if _json(record) != raw:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    if not _exact_keys(
        record,
        ("schema_version", "snapshot_time_ms", "sources"),
    ):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    if (
        record["schema_version"] != ANALYTICS_SPEC_SCHEMA_VERSION
        or type(record["snapshot_time_ms"]) is not int
        or record["snapshot_time_ms"] < 0
        or not isinstance(record["sources"], list)
        or len(record["sources"]) != 2
    ):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)

    specs = []
    for item in record["sources"]:
        if not _exact_keys(
            item,
            (
                "source_id",
                "source_kind",
                "symbol",
                "observed_at_ms",
                "database_path",
                "expected_database_sha256",
            ),
        ):
            raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
        if (
            not isinstance(item["database_path"], str)
            or not item["database_path"]
        ):
            raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
        path_text = item["database_path"].casefold()
        if any(
            marker in path_text
            for marker in (
                "api_key",
                "api-secret",
                "api_secret",
                "password",
                "private_key",
                "access_token",
                "refresh_token",
                "credential",
            )
        ):
            raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
        try:
            kind = AnalyticsSourceKind(item["source_kind"])
            spec = UpstreamSourceSpec(
                item["source_id"],
                kind,
                item["symbol"],
                item["observed_at_ms"],
                Path(item["database_path"]),
                item["expected_database_sha256"],
            )
        except (AnalyticsIngestionError, TypeError, ValueError):
            raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT) from None
        specs.append(spec)

    specs = tuple(sorted(specs, key=lambda item: item.source_id))
    if len({item.source_id for item in specs}) != 2:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    return record["snapshot_time_ms"], specs


def _quality(spec_path):
    snapshot_time_ms, specs = load_analytics_spec(spec_path)
    return run_quality_gate(snapshot_time_ms, specs)


def _quality_failure(command, gate):
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": AnalyticsCliCode.QUALITY_FAILED.value,
        "quality": gate.report.as_record(),
    }


def analytics_validate(spec_path):
    gate = _quality(spec_path)
    if gate.report.status is not QualityStatus.PASS:
        return _quality_failure("validate", gate)
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": "validate",
        "ok": True,
        "code": AnalyticsCliCode.VALIDATED.value,
        "quality": gate.report.as_record(),
        "quality_sha256": gate.report.quality_sha256,
    }


def analytics_summary(spec_path):
    gate = _quality(spec_path)
    if gate.report.status is not QualityStatus.PASS:
        return _quality_failure("summary", gate)
    segmentation = gate.accepted_segmentation
    metrics = segmentation.source_metrics
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": "summary",
        "ok": True,
        "code": AnalyticsCliCode.SUMMARY_READY.value,
        "symbol": metrics.symbol,
        "metrics_status": metrics.status.value,
        "completed_trade_count": metrics.completed_trade_count,
        "open_trade_present": metrics.open_trade_present,
        "realized_pnl_quote": metrics.realized_pnl_quote,
        "gross_pnl_quote": metrics.gross_pnl_quote,
        "gross_return": metrics.gross_return,
        "net_return": metrics.net_return,
        "total_fee_quote": metrics.total_fee_quote,
        "total_slippage_quote": metrics.total_slippage_quote,
        "total_cost_quote": metrics.total_cost_quote,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "breakeven_trades": metrics.breakeven_trades,
        "win_rate": metrics.win_rate,
        "maximum_realized_drawdown_quote":
            metrics.maximum_realized_drawdown_quote,
        "strategy_evidence": metrics.strategy_evidence.value,
        "quality_sha256": gate.report.quality_sha256,
        "segmentation_sha256": segmentation.segmentation_sha256,
    }


def analytics_trades(spec_path, limit=50):
    if type(limit) is not int or not 1 <= limit <= MAX_TRADE_VIEW:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    gate = _quality(spec_path)
    if gate.report.status is not QualityStatus.PASS:
        return _quality_failure("trades", gate)
    metrics = gate.accepted_segmentation.source_metrics
    selected = metrics.trades[:limit]
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": "trades",
        "ok": True,
        "code": AnalyticsCliCode.TRADES_READY.value,
        "symbol": metrics.symbol,
        "total_completed_trades": metrics.completed_trade_count,
        "returned_trades": len(selected),
        "limit": limit,
        "trades": [item.as_record() for item in selected],
        "quality_sha256": gate.report.quality_sha256,
        "metrics_sha256": metrics.metrics_sha256,
    }


def _export_payload(gate):
    if (
        gate.report.status is not QualityStatus.PASS
        or gate.accepted_segmentation is None
    ):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    material = {
        "schema_version": ANALYTICS_EXPORT_SCHEMA_VERSION,
        "quality": gate.report.as_record(),
        "analytics": gate.accepted_segmentation.as_record(),
    }
    material_json = _json(material)
    export_sha256 = _digest_text(material_json)
    record = {
        **material,
        "export_sha256": export_sha256,
    }
    encoded = _json(record) + "\n"
    if len(encoded.encode("utf-8")) > MAX_EXPORT_BYTES:
        raise AnalyticsCliError(AnalyticsCliCode.OUTPUT_TOO_LARGE)
    return record, encoded


def _atomic_write(output_path, encoded, *, overwrite):
    if type(overwrite) is not bool:
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_REQUEST)
    if not isinstance(output_path, (str, Path)) or not str(output_path):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_INPUT)
    target = Path(output_path)
    parent = target.parent
    try:
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise AnalyticsCliError(AnalyticsCliCode.STORAGE_ERROR)
        if target.is_symlink():
            raise AnalyticsCliError(AnalyticsCliCode.STORAGE_ERROR)
        if target.exists() and not overwrite:
            raise AnalyticsCliError(AnalyticsCliCode.OUTPUT_EXISTS)
    except OSError:
        raise AnalyticsCliError(AnalyticsCliCode.STORAGE_ERROR) from None

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".yatl-p7-export-",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(encoded.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())

        if overwrite:
            os.replace(temp_path, target)
            temp_path = None
        else:
            try:
                os.link(temp_path, target)
            except FileExistsError:
                raise AnalyticsCliError(AnalyticsCliCode.OUTPUT_EXISTS) from None
            temp_path.unlink()
            temp_path = None
    except AnalyticsCliError:
        raise
    except OSError:
        raise AnalyticsCliError(AnalyticsCliCode.STORAGE_ERROR) from None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def analytics_export(spec_path, output_path, *, overwrite=False):
    gate = _quality(spec_path)
    if gate.report.status is not QualityStatus.PASS:
        return _quality_failure("export", gate)
    record, encoded = _export_payload(gate)
    _atomic_write(output_path, encoded, overwrite=overwrite)
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": "export",
        "ok": True,
        "code": AnalyticsCliCode.EXPORTED.value,
        "export_sha256": record["export_sha256"],
        "quality_sha256": gate.report.quality_sha256,
        "segmentation_sha256":
            gate.accepted_segmentation.segmentation_sha256,
        "bytes": len(encoded.encode("utf-8")),
        "overwritten": overwrite,
    }


def _exit_code(record):
    code = record.get("code")
    if code in {
        AnalyticsCliCode.VALIDATED.value,
        AnalyticsCliCode.SUMMARY_READY.value,
        AnalyticsCliCode.TRADES_READY.value,
        AnalyticsCliCode.EXPORTED.value,
    }:
        return EXIT_OK
    if code == AnalyticsCliCode.QUALITY_FAILED.value:
        return EXIT_QUALITY
    if code in {
        AnalyticsCliCode.INVALID_REQUEST.value,
        AnalyticsCliCode.INVALID_INPUT.value,
    }:
        return EXIT_INVALID
    if code == AnalyticsCliCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == AnalyticsCliCode.OUTPUT_EXISTS.value:
        return EXIT_EXISTS
    return EXIT_OUTPUT


def _compact_error(command, code):
    return {
        "schema_version": ANALYTICS_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": code.value,
    }


def _render(record):
    encoded = _json(record)
    if len(encoded.encode("utf-8")) > MAX_CLI_OUTPUT_BYTES:
        raise AnalyticsCliError(AnalyticsCliCode.OUTPUT_TOO_LARGE)
    return encoded


class SafeArgumentParser(argparse.ArgumentParser):
    """Argparse without echoing rejected analytics-supplied values."""

    def error(self, message):
        raise AnalyticsCliError(AnalyticsCliCode.INVALID_REQUEST)


def _parser():
    parser = SafeArgumentParser(
        description="Bounded local P7 read-only analytics commands"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--spec", required=True)

    summary = commands.add_parser("summary")
    summary.add_argument("--spec", required=True)

    trades = commands.add_parser("trades")
    trades.add_argument("--spec", required=True)
    trades.add_argument("--limit", type=int, default=50)

    export = commands.add_parser("export")
    export.add_argument("--spec", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--overwrite", action="store_true")

    return parser


def main(argv=None):
    command = "invalid"
    try:
        args = _parser().parse_args(argv)
        command = args.command
        if command == "validate":
            record = analytics_validate(args.spec)
        elif command == "summary":
            record = analytics_summary(args.spec)
        elif command == "trades":
            record = analytics_trades(args.spec, args.limit)
        else:
            record = analytics_export(
                args.spec,
                args.output,
                overwrite=args.overwrite,
            )
        output = _render(record)
    except AnalyticsCliError as exc:
        record = _compact_error(command, exc.code)
        try:
            output = _render(record)
        except AnalyticsCliError:
            record = _compact_error(
                "invalid",
                AnalyticsCliCode.OUTPUT_TOO_LARGE,
            )
            output = _json(record)
    print(output)
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
