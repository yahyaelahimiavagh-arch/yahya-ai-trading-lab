"""P10-008 bounded local status/summary/export for frozen validation evidence.

The CLI never collects market data, changes candidate/gates, or opens the upstream
P10 SQLite database writable. It copies existing local evidence into a temporary
workspace, recomputes the accepted P10 chain there, and exports only a bounded
canonical audit package.
"""

import argparse
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .economics import ForwardEconomicsError, calculate_forward_economics
from .forward_store import ForwardCandleStore, ForwardStoreError
from .gate import ForwardGateError, evaluate_forward_gate
from .ingestion import ForwardIngestionError, snapshot_from_record
from .paper_runner import (
    REGIME_WARMUP_BARS,
    ForwardPaperRunnerError,
    _verify_snapshot_store,
    run_forward_paper,
)
from .registration import CandidateFreeze, EconomicGateRegistry
from .window import ForwardWindowSeal


VALIDATION_CLI_SCHEMA_VERSION = 1
VALIDATION_EXPORT_SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 128 * 1024
MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_CLI_OUTPUT_BYTES = 32 * 1024
MAX_EXPORT_BYTES = 2 * 1024 * 1024

EXIT_OK = 0
EXIT_NOT_READY = 40
EXIT_INVALID = 41
EXIT_SOURCE = 42
EXIT_STORAGE = 43
EXIT_EXISTS = 44
EXIT_OUTPUT = 45
EXIT_INTERNAL = 46

_SECRET_MARKERS = (
    '"api_key"',
    '"api_secret"',
    '"password"',
    '"private_key"',
    '"access_token"',
    '"refresh_token"',
    '"credential"',
    '"credentials"',
    '"account_id"',
)


class ValidationCliCode(str, Enum):
    STATUS_READY = "STATUS_READY"
    SUMMARY_READY = "SUMMARY_READY"
    EXPORTED = "EXPORTED"
    NOT_READY = "NOT_READY"
    INVALID_REQUEST = "INVALID_REQUEST"
    SOURCE_REJECTED = "SOURCE_REJECTED"
    STORAGE_ERROR = "STORAGE_ERROR"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ValidationCliError(Exception):
    """Stable local failure that never includes caller-supplied paths or payloads."""

    def __init__(self, code):
        if not isinstance(code, ValidationCliCode):
            raise TypeError("P10 validation CLI error code is invalid")
        self.code = code
        super().__init__(code.value)


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationEvidenceBundle:
    snapshot: object
    database_snapshot_sha256: str
    ready: bool
    run: object | None = None
    economics: object | None = None
    gate: object | None = None

    def __post_init__(self):
        if (
            type(self.database_snapshot_sha256) is not str
            or len(self.database_snapshot_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.database_snapshot_sha256)
            or type(self.ready) is not bool
            or self.ready != (self.run is not None and self.economics is not None and self.gate is not None)
        ):
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _valid_path(value):
    return isinstance(value, (str, os.PathLike)) and bool(str(value))


def _read_regular_bounded(path, max_bytes):
    if not _valid_path(path) or type(max_bytes) is not int or max_bytes <= 0:
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(os.fspath(path), flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > max_bytes
        ):
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
        chunks = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size:
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
        return raw
    except ValidationCliError:
        raise
    except OSError:
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _stream_digest_regular(path, max_bytes, *, target=None):
    if not _valid_path(path) or type(max_bytes) is not int or max_bytes <= 0:
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    source_fd = None
    target_handle = None
    try:
        source_fd = os.open(os.fspath(path), flags)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > max_bytes
        ):
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
        if target is not None:
            target_handle = Path(target).open("xb")
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(source_fd, min(remaining, 64 * 1024))
            if not chunk:
                raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
            digest.update(chunk)
            if target_handle is not None:
                target_handle.write(chunk)
            remaining -= len(chunk)
        after = os.fstat(source_fd)
        if (
            after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
        if target_handle is not None:
            target_handle.flush()
            os.fsync(target_handle.fileno())
        return digest.hexdigest()
    except ValidationCliError:
        raise
    except OSError:
        code = (
            ValidationCliCode.STORAGE_ERROR
            if target is not None
            else ValidationCliCode.SOURCE_REJECTED
        )
        raise ValidationCliError(code) from None
    finally:
        if target_handle is not None:
            target_handle.close()
        if source_fd is not None:
            os.close(source_fd)


def _active_sqlite_sidecar(source):
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        try:
            if sidecar.is_symlink() or sidecar.exists():
                return True
        except OSError:
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    return False

def _load_snapshot(path):
    raw = _read_regular_bounded(path, MAX_SNAPSHOT_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    lowered = text.casefold()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
    try:
        record = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (json.JSONDecodeError, _DuplicateJsonKey):
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    if text != _json(record) + "\n":
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
    try:
        snapshot = snapshot_from_record(record)
    except ForwardIngestionError:
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    return snapshot, _sha256_bytes(raw)


def snapshot_json(snapshot):
    """Canonical file representation expected by the P10-008 CLI."""
    record = snapshot.as_record()
    return _json(record) + "\n"


def _warmup_ready(snapshot):
    if not snapshot.datasets:
        return False
    cutoff = min(item.requested_end_time_ms for item in snapshot.datasets)
    first_decision = (
        ForwardWindowSeal().forward_window_start_ms
        + REGIME_WARMUP_BARS * 14_400_000
    )
    return cutoff > first_decision


def _copy_database_family(database_path, directory):
    if not _valid_path(database_path):
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)
    source = Path(database_path)
    target = Path(directory) / "p10-forward.sqlite3"
    try:
        if source.is_symlink() or not source.exists() or not source.is_file():
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
    except ValidationCliError:
        raise
    except OSError:
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None

    # A live WAL/SHM means the evidence may still be changing. P10-008 never
    # tries to reconstruct across a concurrent writer; the operator must retry
    # after the collector closes its transaction/store.
    if _active_sqlite_sidecar(source):
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)

    copied_sha = _stream_digest_regular(
        source,
        MAX_DATABASE_BYTES,
        target=target,
    )
    if _active_sqlite_sidecar(source):
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)

    replay_sha = _stream_digest_regular(source, MAX_DATABASE_BYTES)
    if replay_sha != copied_sha or _active_sqlite_sidecar(source):
        raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED)
    return target, copied_sha


def _pipeline(database_path, snapshot_path):
    snapshot, _ = _load_snapshot(snapshot_path)
    with tempfile.TemporaryDirectory(prefix="yatl-p10-cli-") as directory:
        copied_database, database_sha = _copy_database_family(database_path, directory)
        try:
            with ForwardCandleStore(copied_database) as store:
                _verify_snapshot_store(store, snapshot)
                if not _warmup_ready(snapshot):
                    return ValidationEvidenceBundle(snapshot, database_sha, False)
                run = run_forward_paper(store, snapshot)
                economics = calculate_forward_economics(store, snapshot, run)
                gate = evaluate_forward_gate(store, snapshot, run, economics)
        except (ForwardStoreError, ForwardPaperRunnerError, ForwardEconomicsError, ForwardGateError):
            raise ValidationCliError(ValidationCliCode.SOURCE_REJECTED) from None
    return ValidationEvidenceBundle(
        snapshot=snapshot,
        database_snapshot_sha256=database_sha,
        ready=True,
        run=run,
        economics=economics,
        gate=gate,
    )


def _not_ready(command, bundle):
    snapshot = bundle.snapshot
    return {
        "schema_version": VALIDATION_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": ValidationCliCode.NOT_READY.value,
        "reason": "FORWARD_WARMUP_NOT_COMPLETE",
        "ingestion_snapshot_sha256": snapshot.snapshot_sha256,
        "generated_at_ms": snapshot.generated_at_ms,
        "database_snapshot_sha256": bundle.database_snapshot_sha256,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
    }


def _base_ready(command, code, bundle):
    economics = bundle.economics.as_record()
    gate = bundle.gate.as_record()
    return {
        "schema_version": VALIDATION_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "code": code.value,
        "ingestion_snapshot_sha256": bundle.snapshot.snapshot_sha256,
        "database_snapshot_sha256": bundle.database_snapshot_sha256,
        "paper_run_sha256": bundle.run.run_sha256,
        "economics_sha256": bundle.economics.report_sha256,
        "gate_sha256": bundle.gate.report_sha256,
        "sample_status": economics["sample_status"],
        "disposition": gate["disposition"],
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
    }


def _status_from_bundle(bundle):
    if not bundle.ready:
        return _not_ready("status", bundle)
    return _base_ready("status", ValidationCliCode.STATUS_READY, bundle)


def validation_status(database_path, snapshot_path):
    return _status_from_bundle(_pipeline(database_path, snapshot_path))


def _summary_from_bundle(bundle):
    if not bundle.ready:
        return _not_ready("summary", bundle)
    record = _base_ready("summary", ValidationCliCode.SUMMARY_READY, bundle)
    economics = bundle.economics.as_record()
    gate = bundle.gate.as_record()
    pooled = economics["pooled"]
    record.update({
        "observed_days": economics["observed_days"],
        "observation_start_ms": economics["observation_start_ms"],
        "observation_end_ms": economics["observation_end_ms"],
        "completed_trades": pooled["completed_trades"],
        "net_pnl_after_costs_quote": pooled["net_pnl_after_costs_quote"],
        "net_return_after_costs": pooled["net_return_after_costs"],
        "profit_factor_after_costs": pooled["profit_factor_after_costs"],
        "maximum_validation_drawdown_fraction": max(
            (
                pooled["realized_drawdown"]["maximum_drawdown_fraction"],
                pooled["sampled_liquidation_drawdown"]["maximum_drawdown_fraction"],
            ),
            key=Decimal,
        ),
        "criteria": {
            item["criterion"]: item["status"]
            for item in gate["criteria"]
        },
        "symbols": [
            {
                "symbol": item["symbol"],
                "completed_trades": item["completed_trades"],
                "net_pnl_after_costs_quote": item["net_pnl_after_costs_quote"],
                "net_return_after_costs": item["net_return_after_costs"],
                "open_positions": item["open_positions"],
            }
            for item in economics["symbols"]
        ],
    })
    return record


def validation_summary(database_path, snapshot_path):
    return _summary_from_bundle(_pipeline(database_path, snapshot_path))


def _paper_summary(run):
    return {
        "runner_id": run.runner_id,
        "run_sha256": run.run_sha256,
        "ingestion_snapshot_sha256": run.ingestion_snapshot_sha256,
        "window_sha256": run.window_sha256,
        "candidate_sha256": run.candidate_sha256,
        "gate_registry_sha256": run.gate_registry_sha256,
        "execution_policy_id": run.execution_policy_id,
        "fixed_research_quantity": run.fixed_research_quantity,
        "p3_adapter_git_blob_sha1": run.p3_adapter_git_blob_sha1,
        "symbols": [
            {
                "symbol": item.symbol,
                "result_sha256": item.result_sha256,
                "first_decision_time_ms": item.first_decision_time_ms,
                "end_time_ms": item.end_time_ms,
                "event_count": item.event_count,
                "entry_signals": item.entry_signals,
                "entries_allowed": item.entries_allowed,
                "entries_blocked": item.entries_blocked,
                "exit_signals": item.exit_signals,
                "no_trade_signals": item.no_trade_signals,
                "kill_switch_latched": item.kill_switch_latched,
                "fill_count": len(item.fills),
                "final_portfolio": item.final_portfolio,
                "point_in_time_verified": item.point_in_time_verified,
                "replay_from_start": item.replay_from_start,
            }
            for item in run.symbols
        ],
        "safety": run.as_record()["safety"],
    }


def _export_payload(bundle):
    if not bundle.ready:
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)
    material = {
        "schema_version": VALIDATION_EXPORT_SCHEMA_VERSION,
        "candidate": CandidateFreeze().as_record(),
        "gate_registry": EconomicGateRegistry().as_record(),
        "window": ForwardWindowSeal().as_record(),
        "provenance": {
            "database_snapshot_sha256": bundle.database_snapshot_sha256,
            "ingestion": bundle.snapshot.as_record(),
        },
        "forward_paper": _paper_summary(bundle.run),
        "economics": bundle.economics.as_record(),
        "gate": bundle.gate.as_record(),
    }
    material_json = _json(material)
    audit_sha256 = _sha256_text(material_json)
    record = {**material, "audit_sha256": audit_sha256}
    encoded = _json(record) + "\n"
    lowered = encoded.casefold()
    if (
        len(encoded.encode("utf-8")) > MAX_EXPORT_BYTES
        or any(marker in lowered for marker in _SECRET_MARKERS)
    ):
        raise ValidationCliError(ValidationCliCode.OUTPUT_TOO_LARGE)
    return record, encoded


def _atomic_no_overwrite(output_path, encoded):
    if not _valid_path(output_path) or not isinstance(encoded, str):
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)
    target = Path(output_path)
    parent = target.parent
    try:
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            raise ValidationCliError(ValidationCliCode.STORAGE_ERROR)
        if target.is_symlink():
            raise ValidationCliError(ValidationCliCode.STORAGE_ERROR)
        if target.exists():
            raise ValidationCliError(ValidationCliCode.OUTPUT_EXISTS)
    except ValidationCliError:
        raise
    except OSError:
        raise ValidationCliError(ValidationCliCode.STORAGE_ERROR) from None

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".yatl-p10-export-",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(encoded.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            raise ValidationCliError(ValidationCliCode.OUTPUT_EXISTS) from None
        temp_path.unlink()
        temp_path = None
        published = _read_regular_bounded(target, MAX_EXPORT_BYTES)
        if published != encoded.encode("utf-8"):
            raise ValidationCliError(ValidationCliCode.STORAGE_ERROR)
    except ValidationCliError:
        raise
    except OSError:
        raise ValidationCliError(ValidationCliCode.STORAGE_ERROR) from None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _export_from_bundle(bundle, output_path):
    if not bundle.ready:
        return _not_ready("export", bundle)
    record, encoded = _export_payload(bundle)
    _atomic_no_overwrite(output_path, encoded)
    result = _base_ready("export", ValidationCliCode.EXPORTED, bundle)
    result.update({
        "audit_sha256": record["audit_sha256"],
        "bytes": len(encoded.encode("utf-8")),
        "atomic": True,
        "overwrite_allowed": False,
    })
    return result


def validation_export(database_path, snapshot_path, output_path):
    return _export_from_bundle(
        _pipeline(database_path, snapshot_path),
        output_path,
    )


def _compact_error(command, code):
    return {
        "schema_version": VALIDATION_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": code.value,
    }


def _exit_code(record):
    code = record.get("code")
    if code in {
        ValidationCliCode.STATUS_READY.value,
        ValidationCliCode.SUMMARY_READY.value,
        ValidationCliCode.EXPORTED.value,
    }:
        return EXIT_OK
    if code == ValidationCliCode.NOT_READY.value:
        return EXIT_NOT_READY
    if code == ValidationCliCode.INVALID_REQUEST.value:
        return EXIT_INVALID
    if code == ValidationCliCode.SOURCE_REJECTED.value:
        return EXIT_SOURCE
    if code == ValidationCliCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == ValidationCliCode.OUTPUT_EXISTS.value:
        return EXIT_EXISTS
    if code == ValidationCliCode.INTERNAL_ERROR.value:
        return EXIT_INTERNAL
    return EXIT_OUTPUT


def _render(record):
    encoded = _json(record)
    lowered = encoded.casefold()
    if (
        len(encoded.encode("utf-8")) > MAX_CLI_OUTPUT_BYTES
        or any(marker in lowered for marker in _SECRET_MARKERS)
    ):
        raise ValidationCliError(ValidationCliCode.OUTPUT_TOO_LARGE)
    return encoded


class SafeArgumentParser(argparse.ArgumentParser):
    """Argument parser that never echoes rejected caller values."""

    def error(self, message):
        raise ValidationCliError(ValidationCliCode.INVALID_REQUEST)


def _add_source_args(parser):
    parser.add_argument("--database", required=True)
    parser.add_argument("--snapshot", required=True)


def _parser():
    parser = SafeArgumentParser(
        description="Bounded local P10 forward validation evidence commands"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status_parser = commands.add_parser("status")
    _add_source_args(status_parser)

    summary_parser = commands.add_parser("summary")
    _add_source_args(summary_parser)

    export_parser = commands.add_parser("export")
    _add_source_args(export_parser)
    export_parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    command = "invalid"
    try:
        args = _parser().parse_args(argv)
        command = args.command
        if command == "status":
            record = validation_status(args.database, args.snapshot)
        elif command == "summary":
            record = validation_summary(args.database, args.snapshot)
        else:
            record = validation_export(args.database, args.snapshot, args.output)
        output = _render(record)
    except ValidationCliError as exc:
        record = _compact_error(command, exc.code)
        try:
            output = _render(record)
        except ValidationCliError:
            record = _compact_error("invalid", ValidationCliCode.OUTPUT_TOO_LARGE)
            output = _json(record)
    except Exception:
        record = _compact_error(command, ValidationCliCode.INTERNAL_ERROR)
        output = _json(record)
    print(output)
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
