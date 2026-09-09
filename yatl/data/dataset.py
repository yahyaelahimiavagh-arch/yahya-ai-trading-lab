"""Bounded public-real dataset build for the fixed P1 market policy."""

import json
from pathlib import Path
from uuid import uuid4

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS
from .health import HealthError, build_health_report
from .history import HistoricalDownloadError, download_range
from .normalize import NormalizationError, normalize_rest_kline
from .rest import BinancePublicRestClient, PublicRestError
from .storage import CandleStore, StorageError


MILLISECONDS_PER_DAY = 86_400_000


class DatasetError(Exception):
    """Dataset build failed without publishing a partial manifest."""


def build_datasets(store, *, client=None, days=30):
    if not isinstance(store, CandleStore) or type(days) is not int or not 1 <= days <= 365:
        raise DatasetError("Dataset store or day range is invalid")
    client = client or BinancePublicRestClient()
    try:
        server_time = client.server_time()
        reports = []
        for symbol in SYMBOLS:
            for interval, duration in INTERVAL_MILLISECONDS.items():
                end = (server_time // duration) * duration
                start = end - days * MILLISECONDS_PER_DAY
                known = store.known_open_times(DATA_SOURCE, symbol, interval, start, end)
                batch = download_range(client, symbol, interval, start, end,
                                       known_open_times=known)
                candles = [normalize_rest_kline(symbol, interval, row, server_time)
                           for row in batch.rows]
                if candles:
                    store.write_many(candles)
                stored = store.candles_between(DATA_SOURCE, symbol, interval, start, end)
                report = build_health_report(DATA_SOURCE, symbol, interval, start, end,
                                             stored, server_time)
                if not report.backtest_ready or report.open_rows:
                    raise DatasetError("Dataset health gate failed")
                reports.append(json.loads(report.to_json()))
    except DatasetError:
        raise
    except (HealthError, HistoricalDownloadError, NormalizationError,
            PublicRestError, StorageError):
        raise DatasetError("Dataset build failed safely") from None
    return {
        "schema_version": 1,
        "dataset_kind": "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV",
        "generated_at_ms": server_time,
        "range_days": days,
        "database_schema_version": store.schema_version(),
        "datasets": reports,
    }


def manifest_json(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise DatasetError("Dataset manifest is invalid")
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"


def write_manifest(manifest, path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise DatasetError("Manifest path is required")
    target = Path(path)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(manifest_json(manifest), encoding="utf-8", newline="\n")
        temporary.replace(target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DatasetError("Cannot write the dataset manifest") from None
    return target
