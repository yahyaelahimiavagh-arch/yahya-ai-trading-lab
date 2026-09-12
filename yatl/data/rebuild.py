"""Atomic reconstruction of one already-accepted public P1 dataset checkpoint."""

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .audit import AuditError, MAX_MANIFEST_BYTES, audit_p1_manifest
from .config import (BINANCE_MARKET_DATA_BASE_URL, DATA_SOURCE,
                     INTERVAL_MILLISECONDS, SYMBOLS)
from .health import HealthError, build_health_report
from .history import HistoricalDownloadError, download_range
from .normalize import NormalizationError, normalize_rest_kline
from .rest import BinancePublicRestClient, PublicRestError
from .storage import CandleStore, StorageError


class CheckpointRebuildError(Exception):
    """The accepted public checkpoint could not be reconstructed safely."""


@dataclass(frozen=True, slots=True)
class CheckpointRebuildResult:
    datasets: int
    closed_rows: int
    manifest_generated_at_ms: int

    def __post_init__(self):
        if (self.datasets != len(SYMBOLS) * len(INTERVAL_MILLISECONDS)
                or self.closed_rows <= 0
                or self.manifest_generated_at_ms <= 0):
            raise CheckpointRebuildError("Checkpoint rebuild result is invalid")


def _manifest_snapshot(path):
    target = Path(path) if isinstance(path, (str, Path)) and str(path) else None
    if target is None:
        raise CheckpointRebuildError("Manifest path is invalid")
    try:
        before = target.read_bytes()
        if not before or len(before) > MAX_MANIFEST_BYTES:
            raise CheckpointRebuildError("Manifest size is invalid")
        audit_p1_manifest(target)
        after = target.read_bytes()
        if before != after:
            raise CheckpointRebuildError("Manifest changed during validation")
        return json.loads(after.decode("utf-8-sig"))
    except CheckpointRebuildError:
        raise
    except (AuditError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise CheckpointRebuildError("Manifest acceptance gate failed") from None


def rebuild_accepted_database(database_path, manifest_path, *, client=None):
    """Recreate one immutable manifest range without replacing an existing file."""
    target = (Path(database_path)
              if isinstance(database_path, (str, Path)) and str(database_path)
              else None)
    if target is None:
        raise CheckpointRebuildError("Database path is invalid")
    if target.exists():
        raise CheckpointRebuildError("Existing database will not be overwritten")
    manifest = _manifest_snapshot(manifest_path)
    client = client or BinancePublicRestClient(
        base_url=BINANCE_MARKET_DATA_BASE_URL)
    if not isinstance(client, BinancePublicRestClient):
        raise CheckpointRebuildError("A Binance public REST client is required")

    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    sidecars = (temporary, Path(f"{temporary}-wal"), Path(f"{temporary}-shm"))
    try:
        with CandleStore(temporary) as store:
            for expected in manifest["datasets"]:
                batch = download_range(
                    client, expected["symbol"], expected["interval"],
                    expected["requested_start_time_ms"],
                    expected["requested_end_time_ms"],
                )
                candles = tuple(normalize_rest_kline(
                    expected["symbol"], expected["interval"], row,
                    manifest["generated_at_ms"],
                ) for row in batch.rows)
                if candles:
                    store.write_many(candles)
                stored = store.candles_between(
                    DATA_SOURCE, expected["symbol"], expected["interval"],
                    expected["requested_start_time_ms"],
                    expected["requested_end_time_ms"],
                )
                actual = json.loads(build_health_report(
                    DATA_SOURCE, expected["symbol"], expected["interval"],
                    expected["requested_start_time_ms"],
                    expected["requested_end_time_ms"], stored,
                    manifest["generated_at_ms"],
                ).to_json())
                if actual != expected:
                    raise CheckpointRebuildError(
                        "Rebuilt dataset differs from accepted manifest")
            expected_rows = sum(item["closed_rows"] for item in manifest["datasets"])
            if store.count() != expected_rows:
                raise CheckpointRebuildError(
                    "Rebuilt database row count is inconsistent")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except CheckpointRebuildError:
        raise
    except (HistoricalDownloadError, HealthError, NormalizationError,
            PublicRestError, StorageError, OSError, TypeError, ValueError):
        raise CheckpointRebuildError(
            "Accepted checkpoint rebuild failed safely") from None
    finally:
        for path in sidecars:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return CheckpointRebuildResult(
        len(manifest["datasets"]),
        sum(item["closed_rows"] for item in manifest["datasets"]),
        manifest["generated_at_ms"],
    )
