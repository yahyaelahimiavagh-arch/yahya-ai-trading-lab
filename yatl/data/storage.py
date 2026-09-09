"""Versioned SQLite persistence for canonical public Spot candles."""

import sqlite3
from pathlib import Path

from .models import Candle


SCHEMA_VERSION = 1
CANDLE_COLUMNS = (
    "source", "symbol", "interval", "open_time_ms", "close_time_ms",
    "open", "high", "low", "close", "base_volume", "quote_volume",
    "trade_count", "is_closed",
)
MAX_BATCH_SIZE = 100_000


class StorageError(Exception):
    """SQLite operation failed without exposing local paths or SQL details."""


class ClosedCandleConflict(StorageError):
    """A finalized candle cannot be changed or downgraded to open."""


class CandleStore:
    def __init__(self, path):
        if path == ":memory:":
            target = path
        elif isinstance(path, (str, Path)) and str(path):
            target_path = Path(path)
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise StorageError("Cannot prepare the database directory") from None
            target = str(target_path)
        else:
            raise StorageError("A database path is required")
        self._connection = None
        try:
            self._connection = sqlite3.connect(target, timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            if target != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except StorageError:
            if self._connection is not None:
                self._connection.close()
            raise
        except sqlite3.Error:
            if self._connection is not None:
                self._connection.close()
            raise StorageError("Cannot open or migrate the candle database") from None

    def _migrate(self):
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
            )
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
            current = row["version"]
            if current > SCHEMA_VERSION:
                raise StorageError("Database schema is newer than this application")
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE candles (
                        source TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        open_time_ms INTEGER NOT NULL,
                        close_time_ms INTEGER NOT NULL,
                        open TEXT NOT NULL,
                        high TEXT NOT NULL,
                        low TEXT NOT NULL,
                        close TEXT NOT NULL,
                        base_volume TEXT NOT NULL,
                        quote_volume TEXT NOT NULL,
                        trade_count INTEGER NOT NULL CHECK (trade_count >= 0),
                        is_closed INTEGER NOT NULL CHECK (is_closed IN (0, 1)),
                        PRIMARY KEY (source, symbol, interval, open_time_ms)
                    )
                    """
                )
                self._connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES (?)", (1,)
                )

    @staticmethod
    def _values(candle):
        if not isinstance(candle, Candle):
            raise StorageError("Only canonical Candle values can be stored")
        record = candle.as_record()
        return tuple(int(record[name]) if name == "is_closed" else record[name]
                     for name in CANDLE_COLUMNS)

    @staticmethod
    def _same(row, values):
        return all(row[name] == value for name, value in zip(CANDLE_COLUMNS, values))

    def _write(self, candle):
        values = self._values(candle)
        key = candle.key
        existing = self._connection.execute(
            """SELECT source, symbol, interval, open_time_ms, close_time_ms,
                      open, high, low, close, base_volume, quote_volume,
                      trade_count, is_closed
               FROM candles
               WHERE source = ? AND symbol = ? AND interval = ? AND open_time_ms = ?""",
            key,
        ).fetchone()
        if existing is None:
            placeholders = ", ".join("?" for _ in CANDLE_COLUMNS)
            columns = ", ".join(CANDLE_COLUMNS)
            self._connection.execute(
                f"INSERT INTO candles ({columns}) VALUES ({placeholders})", values
            )
            return "inserted"
        if self._same(existing, values):
            return "unchanged"
        if existing["is_closed"]:
            raise ClosedCandleConflict("A closed candle conflicts with stored data")
        assignments = ", ".join(f"{name} = ?" for name in CANDLE_COLUMNS[4:])
        self._connection.execute(
            f"UPDATE candles SET {assignments} "
            "WHERE source = ? AND symbol = ? AND interval = ? AND open_time_ms = ?",
            values[4:] + key,
        )
        return "finalized" if candle.is_closed else "updated"

    def write(self, candle):
        try:
            with self._connection:
                return self._write(candle)
        except StorageError:
            raise
        except sqlite3.Error:
            raise StorageError("Cannot store the candle") from None

    def write_many(self, candles):
        if not isinstance(candles, (list, tuple)) or not 1 <= len(candles) <= MAX_BATCH_SIZE:
            raise StorageError("Candle batch size is invalid")
        try:
            with self._connection:
                return tuple(self._write(candle) for candle in candles)
        except StorageError:
            raise
        except sqlite3.Error:
            raise StorageError("Cannot store the candle batch") from None

    def get(self, key):
        if not isinstance(key, tuple) or len(key) != 4:
            raise StorageError("Candle key is invalid")
        try:
            row = self._connection.execute(
                """SELECT source, symbol, interval, open_time_ms, close_time_ms,
                          open, high, low, close, base_volume, quote_volume,
                          trade_count, is_closed
                   FROM candles
                   WHERE source = ? AND symbol = ? AND interval = ? AND open_time_ms = ?""",
                key,
            ).fetchone()
        except sqlite3.Error:
            raise StorageError("Cannot read the candle") from None
        if row is None:
            return None
        values = {name: row[name] for name in CANDLE_COLUMNS}
        values["is_closed"] = bool(values["is_closed"])
        try:
            return Candle(**values)
        except (TypeError, ValueError):
            raise StorageError("Stored candle violates the canonical contract") from None

    def count(self):
        try:
            return self._connection.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        except sqlite3.Error:
            raise StorageError("Cannot count stored candles") from None

    def known_open_times(self, source, symbol, interval, start_time_ms, end_time_ms):
        try:
            rows = self._connection.execute(
                """SELECT open_time_ms FROM candles
                   WHERE source = ? AND symbol = ? AND interval = ?
                     AND open_time_ms >= ? AND open_time_ms < ?
                   ORDER BY open_time_ms""",
                (source, symbol, interval, start_time_ms, end_time_ms),
            ).fetchall()
            return tuple(row[0] for row in rows)
        except sqlite3.Error:
            raise StorageError("Cannot read known candle timestamps") from None

    def candles_between(self, source, symbol, interval, start_time_ms, end_time_ms):
        try:
            rows = self._connection.execute(
                """SELECT source, symbol, interval, open_time_ms, close_time_ms,
                          open, high, low, close, base_volume, quote_volume,
                          trade_count, is_closed
                   FROM candles
                   WHERE source = ? AND symbol = ? AND interval = ?
                     AND open_time_ms >= ? AND open_time_ms < ?
                   ORDER BY open_time_ms""",
                (source, symbol, interval, start_time_ms, end_time_ms),
            ).fetchall()
        except sqlite3.Error:
            raise StorageError("Cannot read the candle range") from None
        candles = []
        for row in rows:
            values = {name: row[name] for name in CANDLE_COLUMNS}
            values["is_closed"] = bool(values["is_closed"])
            try:
                candles.append(Candle(**values))
            except (TypeError, ValueError):
                raise StorageError("Stored candle violates the canonical contract") from None
        return tuple(candles)

    def schema_version(self):
        try:
            return self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise StorageError("Cannot read database schema version") from None

    def close(self):
        try:
            self._connection.close()
        except sqlite3.Error:
            raise StorageError("Cannot close the candle database") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
