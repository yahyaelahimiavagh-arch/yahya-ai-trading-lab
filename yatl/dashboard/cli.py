"""Guarded noninteractive P8-008 dashboard CLI and atomic publication."""

import argparse
import hashlib
import json
import os
import stat
import tempfile
from enum import Enum
from pathlib import Path

from .loader import LoadedP7Export, P7ExportLoadError, load_p7_export
from .overview import OverviewProjectionError, project_overview
from .performance_views import (
    PerformanceViewProjectionError,
    project_performance_segmentation,
)
from .quality_view import (
    QualityDiagnosticProjectionError,
    project_quality_diagnostics,
)
from .renderer import (
    MAX_DASHBOARD_BYTES,
    DashboardRenderError,
    RenderedDashboardArtifact,
    render_dashboard,
)
from .trade_table import TradeTableProjectionError, project_completed_trade_table


DASHBOARD_CLI_SCHEMA_VERSION = 1
MAX_CLI_OUTPUT_BYTES = 32 * 1024

EXIT_OK = 0
EXIT_INVALID = 31
EXIT_SOURCE = 32
EXIT_STORAGE = 33
EXIT_EXISTS = 34
EXIT_OUTPUT = 35
EXIT_INTERNAL = 36

_HEX = frozenset("0123456789abcdef")
_SECRET_MARKERS = (
    '"api_key"',
    '"api_secret"',
    '"password"',
    '"private_key"',
    '"access_token"',
    '"refresh_token"',
    '"credential"',
    '"credentials"',
    '"endpoint_url"',
    '"raw_response"',
    '"account_id"',
)


class DashboardCliCode(str, Enum):
    VALIDATED = "VALIDATED"
    SUMMARY_READY = "SUMMARY_READY"
    BUILT = "BUILT"
    INVALID_REQUEST = "INVALID_REQUEST"
    SOURCE_REJECTED = "SOURCE_REJECTED"
    SOURCE_MUTATED = "SOURCE_MUTATED"
    STORAGE_ERROR = "STORAGE_ERROR"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DashboardCliError(Exception):
    """Stable local CLI failure that never echoes caller-supplied values."""

    def __init__(self, code):
        if not isinstance(code, DashboardCliCode):
            raise TypeError("Dashboard CLI error code is invalid")
        self.code = code
        super().__init__(code.value)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _validate_request(input_path, expected_export_sha256):
    if (
        not isinstance(input_path, (str, os.PathLike))
        or not str(input_path)
        or not _valid_sha(expected_export_sha256)
    ):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)


def _pipeline(input_path, expected_export_sha256):
    _validate_request(input_path, expected_export_sha256)
    try:
        loaded = load_p7_export(input_path, expected_export_sha256)
        quality = project_quality_diagnostics(loaded=loaded)
        overview = project_overview(loaded)
        trades = project_completed_trade_table(loaded)
        performance = project_performance_segmentation(loaded)
        artifact = render_dashboard(
            quality,
            overview=overview,
            trades=trades,
            performance=performance,
        )
    except P7ExportLoadError:
        raise DashboardCliError(DashboardCliCode.SOURCE_REJECTED) from None
    except (
        QualityDiagnosticProjectionError,
        OverviewProjectionError,
        TradeTableProjectionError,
        PerformanceViewProjectionError,
        DashboardRenderError,
    ):
        raise DashboardCliError(DashboardCliCode.SOURCE_REJECTED) from None

    if (
        not isinstance(loaded, LoadedP7Export)
        or not isinstance(artifact, RenderedDashboardArtifact)
        or artifact.quality_status != "PASS"
        or artifact.artifact_kind != "FULL"
        or artifact.source_export_sha256 != loaded.export_sha256
        or artifact.byte_length > MAX_DASHBOARD_BYTES
    ):
        raise DashboardCliError(DashboardCliCode.OUTPUT_MISMATCH)

    return loaded, quality, overview, trades, performance, artifact


def _assert_source_unchanged(initial, input_path, expected_export_sha256):
    try:
        replay = load_p7_export(input_path, expected_export_sha256)
    except P7ExportLoadError:
        raise DashboardCliError(DashboardCliCode.SOURCE_MUTATED) from None
    if replay != initial:
        raise DashboardCliError(DashboardCliCode.SOURCE_MUTATED)


def _same_input_output(input_path, output_path):
    if (
        not isinstance(output_path, (str, os.PathLike))
        or not str(output_path)
    ):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)

    try:
        source_abs = os.path.normcase(os.path.abspath(os.fspath(input_path)))
        target_abs = os.path.normcase(os.path.abspath(os.fspath(output_path)))
        if source_abs == target_abs:
            return True
        target = Path(output_path)
        if target.exists() and os.path.samefile(input_path, output_path):
            return True
        return False
    except OSError:
        raise DashboardCliError(DashboardCliCode.STORAGE_ERROR) from None


def _read_published(path):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise DashboardCliError(DashboardCliCode.STORAGE_ERROR) from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > MAX_DASHBOARD_BYTES
        ):
            raise DashboardCliError(DashboardCliCode.OUTPUT_MISMATCH)
        data = os.read(descriptor, MAX_DASHBOARD_BYTES + 1)
        if len(data) != metadata.st_size or len(data) > MAX_DASHBOARD_BYTES:
            raise DashboardCliError(DashboardCliCode.OUTPUT_MISMATCH)
        return data
    except DashboardCliError:
        raise
    except OSError:
        raise DashboardCliError(DashboardCliCode.STORAGE_ERROR) from None
    finally:
        os.close(descriptor)


def _atomic_publish(output_path, artifact, *, overwrite):
    if type(overwrite) is not bool or not isinstance(
        artifact,
        RenderedDashboardArtifact,
    ):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)
    if (
        not isinstance(output_path, (str, os.PathLike))
        or not str(output_path)
    ):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)

    target = Path(output_path)
    parent = target.parent
    try:
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise DashboardCliError(DashboardCliCode.STORAGE_ERROR)
        if target.is_symlink():
            raise DashboardCliError(DashboardCliCode.STORAGE_ERROR)
        existed = target.exists()
        if existed:
            mode = target.stat().st_mode
            if not stat.S_ISREG(mode):
                raise DashboardCliError(DashboardCliCode.STORAGE_ERROR)
            if not overwrite:
                raise DashboardCliError(DashboardCliCode.OUTPUT_EXISTS)
    except DashboardCliError:
        raise
    except OSError:
        raise DashboardCliError(DashboardCliCode.STORAGE_ERROR) from None

    encoded = artifact.html.encode("utf-8")
    if (
        len(encoded) != artifact.byte_length
        or len(encoded) > MAX_DASHBOARD_BYTES
        or hashlib.sha256(encoded).hexdigest() != artifact.dashboard_sha256
    ):
        raise DashboardCliError(DashboardCliCode.OUTPUT_MISMATCH)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".yatl-p8-dashboard-",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        if overwrite:
            os.replace(temp_path, target)
            temp_path = None
        else:
            try:
                os.link(temp_path, target)
            except FileExistsError:
                raise DashboardCliError(DashboardCliCode.OUTPUT_EXISTS) from None
            temp_path.unlink()
            temp_path = None

        published = _read_published(target)
        if (
            published != encoded
            or hashlib.sha256(published).hexdigest() != artifact.dashboard_sha256
        ):
            raise DashboardCliError(DashboardCliCode.OUTPUT_MISMATCH)
        return existed
    except DashboardCliError:
        raise
    except OSError:
        raise DashboardCliError(DashboardCliCode.STORAGE_ERROR) from None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _base_success(command, code, loaded, quality, artifact):
    return {
        "schema_version": DASHBOARD_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "code": code.value,
        "source_export_sha256": loaded.export_sha256,
        "quality_sha256": loaded.quality_sha256,
        "quality_status": quality.quality_status,
        "strategy_evidence": quality.strategy_evidence,
        "view_model_sha256": artifact.view_model_sha256,
        "dashboard_sha256": artifact.dashboard_sha256,
        "bytes": artifact.byte_length,
        "self_contained": artifact.self_contained,
        "paper_only": True,
        "live_master_lock": "OFF",
    }


def dashboard_validate(input_path, expected_export_sha256):
    loaded, quality, _, _, _, artifact = _pipeline(
        input_path,
        expected_export_sha256,
    )
    _assert_source_unchanged(loaded, input_path, expected_export_sha256)
    return _base_success(
        "validate",
        DashboardCliCode.VALIDATED,
        loaded,
        quality,
        artifact,
    )


def dashboard_summary(input_path, expected_export_sha256):
    loaded, quality, overview, trades, performance, artifact = _pipeline(
        input_path,
        expected_export_sha256,
    )
    _assert_source_unchanged(loaded, input_path, expected_export_sha256)
    record = _base_success(
        "summary",
        DashboardCliCode.SUMMARY_READY,
        loaded,
        quality,
        artifact,
    )
    record.update({
        "overview_card_count": len(overview.cards),
        "completed_trade_count": trades.total_completed,
        "rendered_trade_count": trades.returned_count,
        "performance_metric_count": len(performance.metrics),
        "trade_segment_count": len(performance.trade_segments),
        "analyst_segment_count": len(performance.analyst_segments),
    })
    return record


def dashboard_build(
    input_path,
    expected_export_sha256,
    output_path,
    *,
    overwrite=False,
):
    if _same_input_output(input_path, output_path):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)

    loaded, quality, _, _, _, artifact = _pipeline(
        input_path,
        expected_export_sha256,
    )
    _assert_source_unchanged(loaded, input_path, expected_export_sha256)
    replaced_existing = _atomic_publish(
        output_path,
        artifact,
        overwrite=overwrite,
    )
    record = _base_success(
        "build",
        DashboardCliCode.BUILT,
        loaded,
        quality,
        artifact,
    )
    record.update({
        "atomic": True,
        "source_unchanged": True,
        "overwrite_requested": overwrite,
        "replaced_existing": replaced_existing,
    })
    return record


def _exit_code(record):
    code = record.get("code")
    if code in {
        DashboardCliCode.VALIDATED.value,
        DashboardCliCode.SUMMARY_READY.value,
        DashboardCliCode.BUILT.value,
    }:
        return EXIT_OK
    if code == DashboardCliCode.INVALID_REQUEST.value:
        return EXIT_INVALID
    if code in {
        DashboardCliCode.SOURCE_REJECTED.value,
        DashboardCliCode.SOURCE_MUTATED.value,
    }:
        return EXIT_SOURCE
    if code == DashboardCliCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == DashboardCliCode.OUTPUT_EXISTS.value:
        return EXIT_EXISTS
    if code == DashboardCliCode.INTERNAL_ERROR.value:
        return EXIT_INTERNAL
    return EXIT_OUTPUT


def _compact_error(command, code):
    return {
        "schema_version": DASHBOARD_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": code.value,
    }


def _render_record(record):
    encoded = _json(record)
    lowered = encoded.lower()
    if (
        len(encoded.encode("utf-8")) > MAX_CLI_OUTPUT_BYTES
        or any(marker in lowered for marker in _SECRET_MARKERS)
    ):
        raise DashboardCliError(DashboardCliCode.OUTPUT_TOO_LARGE)
    return encoded


class SafeArgumentParser(argparse.ArgumentParser):
    """Argparse variant that never echoes rejected caller-supplied values."""

    def error(self, message):
        raise DashboardCliError(DashboardCliCode.INVALID_REQUEST)


def _add_source_args(parser):
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected-export-sha256", required=True)


def _parser():
    parser = SafeArgumentParser(
        description="Bounded local P8 dashboard validation and publication commands"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    _add_source_args(validate)

    summary = commands.add_parser("summary")
    _add_source_args(summary)

    build = commands.add_parser("build")
    _add_source_args(build)
    build.add_argument("--output", required=True)
    build.add_argument("--overwrite", action="store_true")

    return parser


def main(argv=None):
    command = "invalid"
    try:
        args = _parser().parse_args(argv)
        command = args.command
        if command == "validate":
            record = dashboard_validate(
                args.input,
                args.expected_export_sha256,
            )
        elif command == "summary":
            record = dashboard_summary(
                args.input,
                args.expected_export_sha256,
            )
        else:
            record = dashboard_build(
                args.input,
                args.expected_export_sha256,
                args.output,
                overwrite=args.overwrite,
            )
        output = _render_record(record)
    except DashboardCliError as exc:
        record = _compact_error(command, exc.code)
        try:
            output = _render_record(record)
        except DashboardCliError:
            record = _compact_error(
                "invalid",
                DashboardCliCode.OUTPUT_TOO_LARGE,
            )
            output = _json(record)
    except Exception:
        record = _compact_error(command, DashboardCliCode.INTERNAL_ERROR)
        output = _json(record)

    print(output)
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
