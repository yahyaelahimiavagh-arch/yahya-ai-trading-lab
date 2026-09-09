"""Bounded public Binance Spot kline stream with deterministic REST handoff."""

import json
import time
from dataclasses import dataclass

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import connect

from .config import INTERVAL_MILLISECONDS, SYMBOLS
from .history import HistoricalDownloadError, download_range
from .normalize import NormalizationError, normalize_rest_kline, normalize_websocket_kline
from .rest import BinancePublicRestClient, PublicRestError
from .storage import StorageError


STREAM_BASE_URL = "wss://data-stream.binance.vision/stream?streams="
MAX_STREAMS = len(SYMBOLS) * len(INTERVAL_MILLISECONDS)
MAX_MESSAGE_BYTES = 64 * 1024
MAX_BACKFILL_CANDLES = 1_000


class StreamError(Exception):
    """Public stream stopped safely without exposing network payloads."""


class _Reconnect(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StreamRunResult:
    messages: int
    reconnects: int
    backfilled_rows: int


def stream_url(subscriptions):
    if (not isinstance(subscriptions, (list, tuple)) or not subscriptions
            or len(subscriptions) > MAX_STREAMS):
        raise StreamError("Stream subscription count is invalid")
    names = []
    seen = set()
    for item in subscriptions:
        if not isinstance(item, tuple) or len(item) != 2:
            raise StreamError("Stream subscription is invalid")
        symbol, interval = item
        if symbol not in SYMBOLS or interval not in INTERVAL_MILLISECONDS:
            raise StreamError("Stream symbol or interval is not approved")
        name = f"{symbol.lower()}@kline_{interval}"
        if name in seen:
            raise StreamError("Duplicate stream subscription")
        seen.add(name)
        names.append(name)
    return STREAM_BASE_URL + "/".join(names)


class PublicKlineStream:
    def __init__(self, subscriptions, store, *, connector=connect, rest_client=None,
                 sleeper=time.sleep, receive_timeout=10, max_reconnects=2):
        self.subscriptions = tuple(subscriptions) if isinstance(subscriptions, (list, tuple)) else subscriptions
        self.url = stream_url(self.subscriptions)
        if not hasattr(store, "write"):
            raise StreamError("A candle store is required")
        if (type(receive_timeout) not in (int, float) or receive_timeout <= 0
                or type(max_reconnects) is not int or not 0 <= max_reconnects <= 5):
            raise StreamError("Stream limits are invalid")
        self.store = store
        self.connector = connector
        self.rest_client = rest_client or BinancePublicRestClient()
        self.sleeper = sleeper
        self.receive_timeout = receive_timeout
        self.max_reconnects = max_reconnects
        self._last_open = {}

    def _connect(self):
        return self.connector(
            self.url,
            proxy=None,
            open_timeout=10,
            close_timeout=5,
            ping_interval=None,
            compression=None,
            max_size=MAX_MESSAGE_BYTES,
            max_queue=16,
        )

    def _consume(self, message):
        if not isinstance(message, str):
            raise StreamError("Stream message type or size is invalid")
        try:
            if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
                raise StreamError("Stream message type or size is invalid")
        except UnicodeError:
            raise StreamError("Stream message encoding is invalid") from None
        try:
            payload = json.loads(message)
        except (json.JSONDecodeError, UnicodeError):
            raise StreamError("Stream message is not valid JSON") from None
        event = payload.get("data", payload) if isinstance(payload, dict) else None
        if isinstance(event, dict) and event.get("e") == "serverShutdown":
            raise _Reconnect
        try:
            candle = normalize_websocket_kline(payload)
        except NormalizationError:
            raise StreamError("Stream kline failed canonical validation") from None
        pair = (candle.symbol, candle.interval)
        if pair not in self.subscriptions:
            raise StreamError("Stream returned an unsubscribed candle")
        previous = self._last_open.get(pair)
        if previous is not None and candle.open_time_ms < previous:
            raise StreamError("Stream candle arrived out of order")
        try:
            self.store.write(candle)
        except StorageError:
            raise StreamError("Stream candle could not be stored safely") from None
        self._last_open[pair] = candle.open_time_ms

    def _backfill(self):
        total = 0
        if not self._last_open:
            return total
        try:
            server_time = self.rest_client.server_time()
            for symbol, interval in self.subscriptions:
                start = self._last_open.get((symbol, interval))
                if start is None:
                    continue
                duration = INTERVAL_MILLISECONDS[interval]
                end = (server_time // duration) * duration
                if end <= start:
                    continue
                if (end - start) // duration > MAX_BACKFILL_CANDLES:
                    raise StreamError("Disconnect backfill exceeds the fixed limit")
                batch = download_range(self.rest_client, symbol, interval, start, end)
                for row in batch.rows:
                    candle = normalize_rest_kline(symbol, interval, row, server_time)
                    self.store.write(candle)
                    self._last_open[(symbol, interval)] = candle.open_time_ms
                    total += 1
        except StreamError:
            raise
        except (HistoricalDownloadError, NormalizationError, PublicRestError, StorageError):
            raise StreamError("Disconnect backfill failed safely") from None
        return total

    def run(self, max_messages):
        if type(max_messages) is not int or not 1 <= max_messages <= 100:
            raise StreamError("Stream message limit is invalid")
        messages = reconnects = backfilled = 0
        while messages < max_messages:
            try:
                if reconnects:
                    backfilled += self._backfill()
                with self._connect() as websocket:
                    while messages < max_messages:
                        self._consume(websocket.recv(timeout=self.receive_timeout))
                        messages += 1
            except StreamError:
                raise
            except (_Reconnect, ConnectionClosed, WebSocketException, OSError, TimeoutError):
                if reconnects >= self.max_reconnects:
                    raise StreamError("Public stream reconnect limit reached") from None
                reconnects += 1
                self.sleeper(min(2 ** (reconnects - 1), 4))
        return StreamRunResult(messages, reconnects, backfilled)
