"""Credential-free production collector for the sealed P10 forward window.

This operational entrypoint is intentionally separate from P11. It only reads
allowlisted Binance Spot public market data, writes the P10-owned candle store,
and atomically advances the canonical ingestion snapshot.
"""

import argparse
try:
    import fcntl
except ImportError:  # Windows/dev import remains safe; collector itself is Linux-only.
    fcntl = None
import json
import os
import stat
import tempfile
from enum import Enum
from pathlib import Path

from yatl.data import BinancePublicRestClient

from .cli import MAX_SNAPSHOT_BYTES, snapshot_json
from .forward_store import ForwardCandleStore, ForwardStoreError
from .ingestion import (
    ForwardIngestionError,
    collect_forward_snapshot,
    snapshot_from_record,
)


COLLECTOR_SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_NOT_READY = 40
EXIT_INVALID = 41
EXIT_SOURCE = 42
EXIT_STORAGE = 43
EXIT_LOCKED = 44
EXIT_INTERNAL = 46
MAX_OUTPUT_BYTES = 32 * 1024


class CollectorCode(str, Enum):
    COLLECTED = "COLLECTED"
    NOT_READY = "NOT_READY"
    INVALID_REQUEST = "INVALID_REQUEST"
    SOURCE_REJECTED = "SOURCE_REJECTED"
    STORAGE_ERROR = "STORAGE_ERROR"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class CollectorError(Exception):
    def __init__(self, code):
        if not isinstance(code, CollectorCode):
            raise TypeError("Collector error code is invalid")
        self.code = code
        super().__init__(code.value)


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _valid_path(value):
    return isinstance(value, (str, os.PathLike)) and bool(str(value))


def _real_parent(path):
    if not _valid_path(path):
        raise CollectorError(CollectorCode.INVALID_REQUEST)
    target = Path(path)
    parent = target.parent
    try:
        if (
            target.is_symlink()
            or not parent.exists()
            or not parent.is_dir()
            or parent.is_symlink()
        ):
            raise CollectorError(CollectorCode.SOURCE_REJECTED)
    except CollectorError:
        raise
    except OSError:
        raise CollectorError(CollectorCode.SOURCE_REJECTED) from None
    return target


def _database_target(path):
    if not _valid_path(path):
        raise CollectorError(CollectorCode.INVALID_REQUEST)
    target = Path(path)
    parent = target.parent
    try:
        if (
            target.is_symlink()
            or not parent.exists()
            or not parent.is_dir()
            or parent.is_symlink()
            or (target.exists() and not target.is_file())
        ):
            raise CollectorError(CollectorCode.SOURCE_REJECTED)
    except CollectorError:
        raise
    except OSError:
        raise CollectorError(CollectorCode.SOURCE_REJECTED) from None
    return target


def _existing_snapshot(path):
    target = Path(path)
    try:
        if not target.exists():
            return None
        if target.is_symlink() or not target.is_file():
            raise CollectorError(CollectorCode.SOURCE_REJECTED)
        metadata = target.stat()
        if metadata.st_size <= 0 or metadata.st_size > MAX_SNAPSHOT_BYTES:
            raise CollectorError(CollectorCode.SOURCE_REJECTED)
        raw = target.read_bytes()
    except CollectorError:
        raise
    except OSError:
        raise CollectorError(CollectorCode.SOURCE_REJECTED) from None

    try:
        text = raw.decode("utf-8")
        record = json.loads(text)
        snapshot = snapshot_from_record(record)
    except (UnicodeDecodeError, json.JSONDecodeError, ForwardIngestionError):
        raise CollectorError(CollectorCode.SOURCE_REJECTED) from None
    if text != snapshot_json(snapshot):
        raise CollectorError(CollectorCode.SOURCE_REJECTED)
    return snapshot


def _atomic_replace_snapshot(path, encoded):
    target = _real_parent(path)
    raw = encoded.encode("utf-8")
    if not raw or len(raw) > MAX_SNAPSHOT_BYTES:
        raise CollectorError(CollectorCode.STORAGE_ERROR)

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        directory_fd = os.open(os.fspath(target.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if target.read_bytes() != raw:
            raise CollectorError(CollectorCode.STORAGE_ERROR)
    except CollectorError:
        raise
    except OSError:
        raise CollectorError(CollectorCode.STORAGE_ERROR) from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class _CollectorLock:
    def __init__(self, snapshot_path):
        target = _real_parent(snapshot_path)
        self._path = target.with_name(f".{target.name}.lock")
        self._fd = None

    def __enter__(self):
        if fcntl is None:
            raise CollectorError(CollectorCode.STORAGE_ERROR)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            self._fd = os.open(os.fspath(self._path), flags, 0o600)
            metadata = os.fstat(self._fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise CollectorError(CollectorCode.SOURCE_REJECTED)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise CollectorError(CollectorCode.ALREADY_RUNNING) from None
        except CollectorError:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise
        except OSError:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise CollectorError(CollectorCode.STORAGE_ERROR) from None
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


def collect_once(database_path, snapshot_path, *, client=None):
    """Collect one bounded forward snapshot and publish it atomically."""
    database_target = _database_target(database_path)
    snapshot_target = _real_parent(snapshot_path)

    with _CollectorLock(snapshot_target):
        previous = _existing_snapshot(snapshot_target)
        public_client = client or BinancePublicRestClient()

        try:
            with ForwardCandleStore(database_target) as store:
                snapshot = collect_forward_snapshot(store, public_client)
                store_count = store.count()
        except ForwardIngestionError as exc:
            message = str(exc)
            if message == "Forward window has not produced a closed candle for every interval":
                raise CollectorError(CollectorCode.NOT_READY) from None
            raise CollectorError(CollectorCode.SOURCE_REJECTED) from None
        except ForwardStoreError:
            raise CollectorError(CollectorCode.STORAGE_ERROR) from None

        if previous is not None:
            if snapshot.generated_at_ms < previous.generated_at_ms:
                raise CollectorError(CollectorCode.SOURCE_REJECTED)
            if (
                snapshot.generated_at_ms == previous.generated_at_ms
                and snapshot.snapshot_sha256 != previous.snapshot_sha256
            ):
                raise CollectorError(CollectorCode.SOURCE_REJECTED)

        encoded = snapshot_json(snapshot)
        _atomic_replace_snapshot(snapshot_target, encoded)

        return {
            "schema_version": COLLECTOR_SCHEMA_VERSION,
            "ok": True,
            "code": CollectorCode.COLLECTED.value,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "generated_at_ms": snapshot.generated_at_ms,
            "dataset_count": len(snapshot.datasets),
            "store_count": store_count,
            "quality_pass": snapshot.quality_pass,
            "paper_only": snapshot.paper_only,
            "live_master_lock": snapshot.live_master_lock,
            "strategy_evidence": snapshot.strategy_evidence,
            "trade_permission": snapshot.trade_permission,
            "order_endpoint": snapshot.order_endpoint,
            "ai_direct_execution": snapshot.ai_direct_execution,
            "public_market_data_only": True,
        }


def _compact_error(code):
    return {
        "schema_version": COLLECTOR_SCHEMA_VERSION,
        "ok": False,
        "code": code.value,
    }


def _exit_code(record):
    code = record.get("code")
    if code == CollectorCode.COLLECTED.value:
        return EXIT_OK
    if code == CollectorCode.NOT_READY.value:
        return EXIT_NOT_READY
    if code == CollectorCode.INVALID_REQUEST.value:
        return EXIT_INVALID
    if code == CollectorCode.SOURCE_REJECTED.value:
        return EXIT_SOURCE
    if code == CollectorCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == CollectorCode.ALREADY_RUNNING.value:
        return EXIT_LOCKED
    return EXIT_INTERNAL


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CollectorError(CollectorCode.INVALID_REQUEST)


def _parser():
    parser = SafeArgumentParser(
        description="Credential-free P10 forward market-data collector"
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--snapshot", required=True)
    return parser


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        record = collect_once(args.database, args.snapshot)
    except CollectorError as exc:
        record = _compact_error(exc.code)
    except Exception:
        record = _compact_error(CollectorCode.INTERNAL_ERROR)

    encoded = _json(record)
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        record = _compact_error(CollectorCode.INTERNAL_ERROR)
        encoded = _json(record)
    print(encoded)
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
