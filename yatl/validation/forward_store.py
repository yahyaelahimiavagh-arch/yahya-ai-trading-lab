"""P10-owned SQLite persistence bound to one sealed forward window."""

import sqlite3
from pathlib import Path

from yatl.data import (
    Candle,
    CandleStore,
    DATA_SOURCE,
    INTERVAL_MILLISECONDS,
    SYMBOLS,
    StorageError,
)

from .window import ForwardObservationIdentity, ForwardWindowSeal


FORWARD_STORE_SCHEMA_VERSION = 1
FORWARD_STORE_KIND = "P10_WINDOW_BOUND_SQLITE"


class ForwardStoreError(Exception):
    """The P10 store is not isolated, window-bound or safely writable."""


class ForwardCandleStore:
    """Dedicated P10 candle store that refuses non-empty untagged databases."""

    def __init__(self, path, window=None):
        if path == ":memory:" or not isinstance(path, (str, Path)) or not str(path):
            raise ForwardStoreError("A persistent P10 store path is required")
        self._path = Path(path)
        self._window = window or ForwardWindowSeal()
        if not isinstance(self._window, ForwardWindowSeal):
            raise ForwardStoreError("A sealed P10 forward window is required")

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._bind_metadata()
            self._store = CandleStore(self._path)
        except ForwardStoreError:
            raise
        except (OSError, sqlite3.Error, StorageError):
            raise ForwardStoreError("Cannot open or bind the P10 forward store") from None

    def _bind_metadata(self):
        connection = sqlite3.connect(str(self._path), timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "p10_forward_metadata" not in tables:
                if "candles" in tables:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM candles"
                    ).fetchone()[0]
                    if count:
                        raise ForwardStoreError(
                            "Refusing to tag a non-empty unowned candle database"
                        )
                with connection:
                    connection.execute(
                        """
                        CREATE TABLE p10_forward_metadata (
                            schema_version INTEGER PRIMARY KEY,
                            store_kind TEXT NOT NULL,
                            window_sha256 TEXT NOT NULL,
                            source TEXT NOT NULL,
                            forward_start_ms INTEGER NOT NULL,
                            candidate_sha256 TEXT NOT NULL,
                            gate_registry_sha256 TEXT NOT NULL,
                            registration_sha256 TEXT NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO p10_forward_metadata(
                            schema_version, store_kind, window_sha256, source,
                            forward_start_ms, candidate_sha256,
                            gate_registry_sha256, registration_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        self._metadata_values(),
                    )
            row = connection.execute(
                """
                SELECT schema_version, store_kind, window_sha256, source,
                       forward_start_ms, candidate_sha256,
                       gate_registry_sha256, registration_sha256
                FROM p10_forward_metadata
                """
            ).fetchall()
            if len(row) != 1 or tuple(row[0]) != self._metadata_values():
                raise ForwardStoreError(
                    "P10 store metadata does not match the sealed window"
                )
        finally:
            connection.close()

    def _metadata_values(self):
        return (
            FORWARD_STORE_SCHEMA_VERSION,
            FORWARD_STORE_KIND,
            self._window.window_sha256,
            DATA_SOURCE,
            self._window.forward_window_start_ms,
            self._window.candidate_sha256,
            self._window.gate_registry_sha256,
            self._window.p10_002_registration_sha256,
        )

    @property
    def window_sha256(self):
        return self._window.window_sha256

    @property
    def store_kind(self):
        return FORWARD_STORE_KIND

    def count(self):
        try:
            return self._store.count()
        except StorageError:
            raise ForwardStoreError("Cannot count P10 forward candles") from None

    def known_open_times(self, symbol, interval, start_time_ms, end_time_ms):
        self._validate_range(symbol, interval, start_time_ms, end_time_ms)
        try:
            return self._store.known_open_times(
                DATA_SOURCE,
                symbol,
                interval,
                start_time_ms,
                end_time_ms,
            )
        except StorageError:
            raise ForwardStoreError(
                "Cannot read P10 known candle timestamps"
            ) from None

    def candles_between(self, symbol, interval, start_time_ms, end_time_ms):
        self._validate_range(symbol, interval, start_time_ms, end_time_ms)
        try:
            values = self._store.candles_between(
                DATA_SOURCE,
                symbol,
                interval,
                start_time_ms,
                end_time_ms,
            )
        except StorageError:
            raise ForwardStoreError("Cannot read P10 candle range") from None
        for candle in values:
            self._validate_candle(candle)
        return values

    def write_many(self, candles):
        if not isinstance(candles, (list, tuple)) or not candles:
            raise ForwardStoreError("P10 forward candle batch is empty or invalid")
        for candle in candles:
            self._validate_candle(candle)
        try:
            return self._store.write_many(candles)
        except StorageError:
            raise ForwardStoreError("Cannot write the P10 forward candle batch") from None

    def _validate_range(self, symbol, interval, start_time_ms, end_time_ms):
        if (
            symbol not in SYMBOLS
            or interval not in INTERVAL_MILLISECONDS
            or type(start_time_ms) is not int
            or type(end_time_ms) is not int
            or start_time_ms < self._window.forward_window_start_ms
            or start_time_ms >= end_time_ms
        ):
            raise ForwardStoreError("P10 forward store range is outside the seal")
        duration = INTERVAL_MILLISECONDS[interval]
        if start_time_ms % duration or end_time_ms % duration:
            raise ForwardStoreError("P10 forward store range is not UTC aligned")

    def _validate_candle(self, candle):
        if (
            not isinstance(candle, Candle)
            or candle.source != DATA_SOURCE
            or candle.symbol not in SYMBOLS
            or candle.interval not in INTERVAL_MILLISECONDS
            or not candle.is_closed
        ):
            raise ForwardStoreError("P10 store accepts only closed canonical candles")
        try:
            ForwardObservationIdentity(
                source_id=candle.source,
                symbol=candle.symbol,
                interval=candle.interval,
                open_time_ms=candle.open_time_ms,
                close_time_ms=candle.close_time_ms,
                is_closed=candle.is_closed,
                window_sha256=self._window.window_sha256,
            )
        except ValueError:
            raise ForwardStoreError(
                "Candle identity violates the sealed P10 window"
            ) from None

    def close(self):
        try:
            self._store.close()
        except StorageError:
            raise ForwardStoreError("Cannot close the P10 forward store") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
