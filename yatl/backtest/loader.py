"""Read-only, manifest-gated access to accepted P1 candle datasets."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from yatl.data import (AuditError, Candle, DATA_SOURCE, INTERVAL_MILLISECONDS,
                       audit_p1_manifest)
from yatl.data.audit import MAX_MANIFEST_BYTES

from .config import (BacktestSpec, CONTEXT_INTERVAL, PRIMARY_INTERVAL,
                     REGIME_INTERVAL)
from .models import BacktestContractError, MarketSnapshot


INTERVALS = (PRIMARY_INTERVAL, CONTEXT_INTERVAL, REGIME_INTERVAL)
MAX_LOADED_ROWS = 100_000


class BacktestLoadError(Exception):
    """Accepted P1 data could not be loaded without weakening a gate."""


def _manifest_snapshot(path):
    target = Path(path) if isinstance(path, (str, Path)) and str(path) else None
    if target is None:
        raise BacktestLoadError("Manifest path is invalid")
    try:
        before = target.read_bytes()
        if not before or len(before) > MAX_MANIFEST_BYTES:
            raise BacktestLoadError("Manifest size is invalid")
        audit_p1_manifest(target)
        after = target.read_bytes()
        if before != after:
            raise BacktestLoadError("Manifest changed during validation")
        return json.loads(after.decode("utf-8-sig"))
    except BacktestLoadError:
        raise
    except (AuditError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BacktestLoadError("Manifest acceptance gate failed") from None


def _reports_for(manifest, symbol):
    reports = {item.get("interval"): item for item in manifest["datasets"]
               if item.get("symbol") == symbol}
    if set(reports) != set(INTERVALS):
        raise BacktestLoadError("Accepted dataset coverage is incomplete")
    return reports


def latest_spec_from_manifest(path, symbol, *, hours=24):
    if type(hours) is not int or not 1 <= hours <= 24 * 365:
        raise BacktestLoadError("Requested backtest hours are invalid")
    manifest = _manifest_snapshot(path)
    reports = _reports_for(manifest, symbol)
    primary = INTERVAL_MILLISECONDS[PRIMARY_INTERVAL]
    earliest = max(item["requested_start_time_ms"] for item in reports.values())
    latest = min(item["requested_end_time_ms"] for item in reports.values())
    end = (latest // primary) * primary
    start = end - hours * primary
    # One completed regime candle must exist before the first decision.
    regime_warmup = INTERVAL_MILLISECONDS[REGIME_INTERVAL]
    if start < earliest + regime_warmup:
        raise BacktestLoadError("Accepted dataset lacks the requested warmup range")
    try:
        return BacktestSpec(symbol, start, end)
    except ValueError:
        raise BacktestLoadError("Accepted manifest cannot form a backtest range") from None


def _read_rows(connection, report):
    try:
        rows = connection.execute(
            """SELECT source, symbol, interval, open_time_ms, close_time_ms,
                      open, high, low, close, base_volume, quote_volume,
                      trade_count, is_closed
               FROM candles
               WHERE source = ? AND symbol = ? AND interval = ?
                 AND open_time_ms >= ? AND open_time_ms < ?
               ORDER BY open_time_ms""",
            (DATA_SOURCE, report["symbol"], report["interval"],
             report["requested_start_time_ms"], report["requested_end_time_ms"]),
        ).fetchall()
    except sqlite3.Error:
        raise BacktestLoadError("Cannot read the accepted candle range") from None
    if len(rows) != report["total_rows"] or len(rows) > MAX_LOADED_ROWS:
        raise BacktestLoadError("Database and accepted manifest row counts differ")
    candles = []
    try:
        for row in rows:
            values = dict(row)
            if type(values["is_closed"]) is not int or values["is_closed"] not in (0, 1):
                raise BacktestLoadError("Database candle state is invalid")
            values["is_closed"] = bool(values["is_closed"])
            candle = Candle(**values)
            if not candle.is_closed:
                raise BacktestLoadError("Accepted backtest data contains an open candle")
            candles.append(candle)
    except BacktestLoadError:
        raise
    except (TypeError, ValueError):
        raise BacktestLoadError("Database row violates the canonical candle contract") from None
    duration = INTERVAL_MILLISECONDS[report["interval"]]
    expected = tuple(range(report["requested_start_time_ms"],
                           report["requested_end_time_ms"], duration))
    if tuple(item.open_time_ms for item in candles) != expected:
        raise BacktestLoadError("Database candle coverage differs from the accepted manifest")
    return tuple(candles)


@dataclass(frozen=True, slots=True)
class AcceptedBacktestDataset:
    spec: BacktestSpec
    manifest_generated_at_ms: int
    primary: tuple[Candle, ...]
    context: tuple[Candle, ...]
    regime: tuple[Candle, ...]

    def snapshot_at(self, decision_time_ms):
        if (type(decision_time_ms) is not int
                or not self.spec.start_time_ms <= decision_time_ms < self.spec.end_time_ms):
            raise BacktestLoadError("Decision time is outside the backtest range")

        def visible(values):
            return tuple(item for item in values if item.close_time_ms < decision_time_ms)

        try:
            return MarketSnapshot(self.spec.symbol, decision_time_ms,
                                  visible(self.primary), visible(self.context),
                                  visible(self.regime))
        except BacktestContractError:
            raise BacktestLoadError("Point-in-time snapshot cannot be built safely") from None


def load_accepted_dataset(database_path, manifest_path, spec):
    if not isinstance(spec, BacktestSpec):
        raise BacktestLoadError("Backtest specification is invalid")
    manifest = _manifest_snapshot(manifest_path)
    reports = _reports_for(manifest, spec.symbol)
    for report in reports.values():
        if (spec.start_time_ms < report["requested_start_time_ms"]
                or spec.end_time_ms > report["requested_end_time_ms"]):
            raise BacktestLoadError("Backtest range is outside the accepted dataset")

    if not isinstance(database_path, (str, Path)) or not str(database_path):
        raise BacktestLoadError("Database path is invalid")
    target = Path(database_path)
    try:
        if not target.is_file():
            raise BacktestLoadError("Accepted database cannot be read")
        uri = f"file:{quote(target.resolve().as_posix(), safe='/:')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
    except BacktestLoadError:
        raise
    except (OSError, sqlite3.Error):
        raise BacktestLoadError("Accepted database cannot be opened read-only") from None
    try:
        try:
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise BacktestLoadError("Accepted database schema cannot be verified") from None
        if version != manifest["database_schema_version"]:
            raise BacktestLoadError("Database schema and accepted manifest differ")
        loaded = {interval: _read_rows(connection, reports[interval])
                  for interval in INTERVALS}
    finally:
        connection.close()
    return AcceptedBacktestDataset(
        spec=spec, manifest_generated_at_ms=manifest["generated_at_ms"],
        primary=loaded[PRIMARY_INTERVAL], context=loaded[CONTEXT_INTERVAL],
        regime=loaded[REGIME_INTERVAL],
    )
