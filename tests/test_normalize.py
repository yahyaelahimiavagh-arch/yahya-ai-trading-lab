import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from yatl.__main__ import main
from yatl.data import DATA_SOURCE
from yatl.data.normalize import (
    NormalizationError,
    normalize_rest_kline,
    normalize_websocket_kline,
)


OPEN_TIME = 1_699_999_200_000
CLOSE_TIME = OPEN_TIME + 3_600_000 - 1


def rest_row():
    return [OPEN_TIME, "26000.10000000", "26250.00000000", "25900.00000000",
            "26100.25000000", "123.45000000", CLOSE_TIME, "3210000.12345678",
            1234, "60.00000000", "1560000.00000000", "0"]


def websocket_event(*, closed=True):
    return {
        "e": "kline", "E": CLOSE_TIME + 1, "s": "BTCUSDT",
        "k": {
            "t": OPEN_TIME, "T": CLOSE_TIME, "s": "BTCUSDT", "i": "1h",
            "f": 1, "L": 1234, "o": "26000.10000000", "h": "26250.00000000",
            "l": "25900.00000000", "c": "26100.25000000", "v": "123.45000000",
            "n": 1234, "x": closed, "q": "3210000.12345678",
            "V": "60.00000000", "Q": "1560000.00000000", "B": "0",
        },
    }


class NormalizationTests(unittest.TestCase):
    def test_rest_and_websocket_produce_identical_closed_candle(self):
        rest = normalize_rest_kline("BTCUSDT", "1h", rest_row(), CLOSE_TIME + 1)
        stream = normalize_websocket_kline(websocket_event(closed=True))
        self.assertEqual(rest, stream)
        self.assertEqual(rest.source, DATA_SOURCE)
        self.assertTrue(rest.is_closed)

    def test_rest_uses_exchange_time_at_exact_boundary(self):
        self.assertFalse(normalize_rest_kline(
            "BTCUSDT", "1h", rest_row(), CLOSE_TIME).is_closed)
        self.assertTrue(normalize_rest_kline(
            "BTCUSDT", "1h", rest_row(), CLOSE_TIME + 1).is_closed)

    def test_rest_accepts_immutable_download_rows_and_preserves_open_candle(self):
        value = normalize_rest_kline("BTCUSDT", "1h", tuple(rest_row()), OPEN_TIME)
        self.assertFalse(value.is_closed)
        self.assertEqual(value.open, "26000.10000000")

    def test_raw_and_combined_websocket_events_match(self):
        event = websocket_event(closed=False)
        raw = normalize_websocket_kline(event)
        combined = normalize_websocket_kline({
            "stream": "btcusdt@kline_1h", "data": event,
        })
        self.assertEqual(raw, combined)
        self.assertFalse(raw.is_closed)

    def test_rest_identity_shape_clock_and_reserved_field_fail_closed(self):
        cases = [
            ("XRPUSDT", "1h", rest_row(), CLOSE_TIME + 1),
            ("BTCUSDT", "5m", rest_row(), CLOSE_TIME + 1),
            ("BTCUSDT", "1h", rest_row()[:-1], CLOSE_TIME + 1),
            ("BTCUSDT", "1h", rest_row(), True),
        ]
        bad_reserved = rest_row(); bad_reserved[11] = "unexpected"
        cases.append(("BTCUSDT", "1h", bad_reserved, CLOSE_TIME + 1))
        for args in cases:
            with self.subTest(), self.assertRaises(NormalizationError):
                normalize_rest_kline(*args)

    def test_rest_contract_errors_are_redacted(self):
        row = rest_row()
        row[1] = "sensitive-invalid-price"
        with self.assertRaises(NormalizationError) as caught:
            normalize_rest_kline("BTCUSDT", "1h", row, CLOSE_TIME + 1)
        self.assertNotIn("sensitive", str(caught.exception))

    def test_websocket_identity_and_required_fields_fail_closed(self):
        variants = [None, {}, {"e": "trade", "E": 1}, websocket_event()]
        variants[-1]["E"] = "1"
        event = websocket_event(); event["s"] = "XRPUSDT"; variants.append(event)
        event = websocket_event(); del event["k"]["q"]; variants.append(event)
        event = websocket_event(); event["k"]["s"] = "ETHUSDT"; variants.append(event)
        event = websocket_event(); event["k"]["i"] = "5m"; variants.append(event)
        event = websocket_event(); event["k"]["x"] = 1; variants.append(event)
        variants.append({"stream": "ethusdt@kline_1h", "data": websocket_event()})
        variants.append({"stream": 1, "data": websocket_event()})
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(NormalizationError):
                normalize_websocket_kline(payload)

    @patch("yatl.__main__.BinancePublicRestClient")
    @patch("yatl.__main__.normalize_rest_kline")
    @patch("sys.argv", ["yatl", "normalize-check"])
    def test_runtime_cli_checks_six_pairs_without_persistence(self, normalize, client_type):
        client = client_type.return_value
        client.server_time.return_value = CLOSE_TIME + 1
        client.klines.return_value = [[1] * 12, [2] * 12]
        normalize.side_effect = [MagicMock(is_closed=True), MagicMock(is_closed=False)] * 6
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(client.klines.call_count, 6)
        self.assertEqual(normalize.call_count, 12)
        self.assertIn("No persistence", output.getvalue())
        self.assertIn("No credentials", output.getvalue())


if __name__ == "__main__":
    unittest.main()
