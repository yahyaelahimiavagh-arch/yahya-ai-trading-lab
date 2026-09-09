import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from yatl.__main__ import main
from yatl.data import CandleStore
from yatl.data.history import HistoricalBatch
from yatl.data.stream import (
    MAX_BACKFILL_CANDLES,
    MAX_MESSAGE_BYTES,
    PublicKlineStream,
    StreamError,
    stream_url,
)


HOUR = 3_600_000
START = 1_699_999_200_000


def event(open_time=START, *, symbol="BTCUSDT", closed=False, close="26100.0"):
    payload = {
        "e": "kline", "E": open_time + 1, "s": symbol,
        "k": {
            "t": open_time, "T": open_time + HOUR - 1, "s": symbol, "i": "1h",
            "f": 1, "L": 2, "o": "26000.0", "h": "26250.0", "l": "25900.0",
            "c": close, "v": "123.0", "n": 2, "x": closed, "q": "3210000.0",
            "V": "60.0", "Q": "1560000.0", "B": "0",
        },
    }
    return json.dumps({"stream": f"{symbol.lower()}@kline_1h", "data": payload})


def rest_row(open_time=START):
    return [open_time, "26000.0", "26250.0", "25900.0", "26100.0", "123.0",
            open_time + HOUR - 1, "3210000.0", 2, "60.0", "1560000.0", "0"]


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def recv(self, timeout):
        value = self.messages.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class StreamTests(unittest.TestCase):
    def test_url_is_exact_market_only_combined_stream(self):
        self.assertEqual(
            stream_url([("BTCUSDT", "1h"), ("ETHUSDT", "15m")]),
            "wss://data-stream.binance.vision/stream?streams="
            "btcusdt@kline_1h/ethusdt@kline_15m",
        )
        for value in ([], [("XRPUSDT", "1h")], [("BTCUSDT", "5m")],
                      [("BTCUSDT", "1h"), ("BTCUSDT", "1h")], ["BTCUSDT"]):
            with self.subTest(value=value), self.assertRaises(StreamError):
                stream_url(value)

    def test_connector_limits_and_idempotent_messages(self):
        connector = MagicMock(return_value=FakeSocket([event(), event()]))
        with CandleStore(":memory:") as store:
            result = PublicKlineStream([("BTCUSDT", "1h")], store,
                                       connector=connector).run(2)
            self.assertEqual(store.count(), 1)
        self.assertEqual(result.messages, 2)
        kwargs = connector.call_args.kwargs
        self.assertIsNone(kwargs["proxy"])
        self.assertIsNone(kwargs["ping_interval"])
        self.assertIsNone(kwargs["compression"])
        self.assertEqual(kwargs["max_size"], MAX_MESSAGE_BYTES)
        self.assertEqual(kwargs["max_queue"], 16)

    def test_open_candle_updates_and_finalizes(self):
        messages = [event(), event(close="26150.0"), event(closed=True, close="26150.0")]
        with CandleStore(":memory:") as store:
            PublicKlineStream([("BTCUSDT", "1h")], store,
                              connector=lambda *a, **k: FakeSocket(messages)).run(3)
            stored = store.get(("BINANCE_SPOT_PUBLIC", "BTCUSDT", "1h", START))
            self.assertTrue(stored.is_closed)
            self.assertEqual(stored.close, "26150.0")

    def test_out_of_order_and_malformed_messages_fail_closed(self):
        cases = [
            [event(START + HOUR), event(START)],
            ["not-json"],
            [b"binary"],
            [event(symbol="ETHUSDT")],
        ]
        for messages in cases:
            with CandleStore(":memory:") as store:
                stream = PublicKlineStream([("BTCUSDT", "1h")], store,
                                           connector=lambda *a, **k: FakeSocket(messages))
                with self.subTest(messages=messages), self.assertRaises(StreamError):
                    stream.run(len(messages))

    @patch("yatl.data.stream.download_range")
    def test_reconnect_runs_bounded_rest_backfill_before_resume(self, download):
        download.return_value = HistoricalBatch(
            symbol="BTCUSDT", interval="1h", start_time_ms=START,
            end_time_ms=START + HOUR, rows=(tuple(rest_row()),), pages=1,
            skipped_known_rows=0,
        )
        rest = MagicMock()
        rest.server_time.return_value = START + HOUR
        sockets = [FakeSocket([event(), OSError("disconnect")]),
                   FakeSocket([event(START + HOUR)])]
        connector = MagicMock(side_effect=sockets)
        sleeps = []
        with CandleStore(":memory:") as store:
            result = PublicKlineStream(
                [("BTCUSDT", "1h")], store, connector=connector,
                rest_client=rest, sleeper=sleeps.append, max_reconnects=1,
            ).run(2)
            self.assertEqual(store.count(), 2)
            self.assertTrue(store.get(
                ("BINANCE_SPOT_PUBLIC", "BTCUSDT", "1h", START)).is_closed)
        self.assertEqual((result.reconnects, result.backfilled_rows), (1, 1))
        self.assertEqual(sleeps, [1])
        download.assert_called_once_with(rest, "BTCUSDT", "1h", START, START + HOUR)

    def test_reconnect_and_backfill_limits_fail_closed(self):
        connector = MagicMock(side_effect=[FakeSocket([OSError()]), FakeSocket([OSError()])])
        with CandleStore(":memory:") as store:
            stream = PublicKlineStream([("BTCUSDT", "1h")], store,
                                       connector=connector, sleeper=lambda _: None,
                                       max_reconnects=1)
            with self.assertRaisesRegex(StreamError, "reconnect limit"):
                stream.run(1)

        rest = MagicMock()
        rest.server_time.return_value = START + (MAX_BACKFILL_CANDLES + 1) * HOUR
        with CandleStore(":memory:") as store:
            stream = PublicKlineStream([("BTCUSDT", "1h")], store, rest_client=rest)
            stream._last_open[("BTCUSDT", "1h")] = START
            with self.assertRaisesRegex(StreamError, "exceeds"):
                stream._backfill()

    def test_server_shutdown_requests_bounded_reconnect(self):
        shutdown = json.dumps({"stream": "!serverShutdown",
                               "data": {"e": "serverShutdown", "E": START}})
        sockets = [FakeSocket([shutdown]), FakeSocket([event()])]
        rest = MagicMock()
        with CandleStore(":memory:") as store:
            result = PublicKlineStream(
                [("BTCUSDT", "1h")], store,
                connector=MagicMock(side_effect=sockets), sleeper=lambda _: None,
                rest_client=rest, max_reconnects=1,
            ).run(1)
        self.assertEqual(result.reconnects, 1)
        rest.server_time.assert_not_called()

    def test_constructor_and_run_limits(self):
        with CandleStore(":memory:") as store:
            for kwargs in ({"receive_timeout": 0}, {"max_reconnects": -1},
                           {"max_reconnects": 6}):
                with self.subTest(kwargs=kwargs), self.assertRaises(StreamError):
                    PublicKlineStream([("BTCUSDT", "1h")], store, **kwargs)
            stream = PublicKlineStream([("BTCUSDT", "1h")], store)
            for count in (0, 101, True):
                with self.subTest(count=count), self.assertRaises(StreamError):
                    stream.run(count)

    @patch("yatl.__main__.PublicKlineStream")
    @patch("sys.argv", ["yatl", "stream-check", "--messages", "1"])
    def test_cli_output_is_public_and_bounded(self, stream_type):
        stream_type.return_value.run.return_value = MagicMock(
            messages=1, reconnects=0, backfilled_rows=0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        text = output.getvalue()
        self.assertIn("messages=1", text)
        self.assertIn("PUBLIC MARKET DATA ONLY", text)
        self.assertIn("No credentials", text)
        self.assertIn("No execution", text)


if __name__ == "__main__":
    unittest.main()
