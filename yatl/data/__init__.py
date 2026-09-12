"""Public Binance Spot market-data contracts for P1."""

from .config import (
    BINANCE_PUBLIC_BASE_URL,
    DATA_SOURCE,
    INTERVAL_MILLISECONDS,
    SYMBOLS,
    TIMEFRAME_POLICY,
)
from .models import Candle, CandleValidationError
from .rest import BinancePublicRestClient, PublicRestError
from .history import HistoricalBatch, HistoricalDownloadError, download_range
from .normalize import NormalizationError, normalize_rest_kline, normalize_websocket_kline
from .storage import CandleStore, ClosedCandleConflict, StorageError
from .quality import QualityError, RangeQualityReport, analyze_open_times, duplicate_candle_keys
from .stream import PublicKlineStream, StreamError, StreamRunResult, stream_url
from .health import DataHealthReport, HealthError, build_health_report
from .dataset import DatasetError, build_datasets, manifest_json, write_manifest
from .audit import AuditError, P1AuditResult, audit_p1_manifest
from .rebuild import (CheckpointRebuildError, CheckpointRebuildResult,
                      rebuild_accepted_database)

__all__ = [
    "BINANCE_PUBLIC_BASE_URL",
    "AuditError",
    "BinancePublicRestClient",
    "Candle",
    "CandleValidationError",
    "CandleStore",
    "ClosedCandleConflict",
    "CheckpointRebuildError",
    "CheckpointRebuildResult",
    "DATA_SOURCE",
    "DataHealthReport",
    "DatasetError",
    "INTERVAL_MILLISECONDS",
    "HistoricalBatch",
    "HistoricalDownloadError",
    "HealthError",
    "NormalizationError",
    "PublicRestError",
    "P1AuditResult",
    "PublicKlineStream",
    "QualityError",
    "RangeQualityReport",
    "StorageError",
    "StreamError",
    "StreamRunResult",
    "SYMBOLS",
    "TIMEFRAME_POLICY",
    "download_range",
    "analyze_open_times",
    "audit_p1_manifest",
    "build_health_report",
    "build_datasets",
    "rebuild_accepted_database",
    "duplicate_candle_keys",
    "normalize_rest_kline",
    "normalize_websocket_kline",
    "manifest_json",
    "stream_url",
    "write_manifest",
]
