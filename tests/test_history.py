import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from yatl.__main__ import main
from yatl.data import BinancePublicRestClient, PublicRestError
from yatl.data.history import MAX_RANGE_CANDLES, HistoricalDownloadError, download_range


DURATION = 900_000
START = 1_699_999_200_000


def row(open_time):
    return [open_time, "1", "2", "0.5", "1.5", "10",
            open_time + DURATION - 1, "12", 2, "4", "5", "0"]


class HistoricalDownloadTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock(spec=BinancePublicRestClient)

    def test_paginated_explicit_half_open_range(self):
        rows = [row(START + index * DURATION) for index in range(5)]
        self.client.klines.side_effect = [rows[:3], rows[3:]]
        end = START + 5 * DURATION
        batch = download_range(self.client, "BTCUSDT", "15m", START, end, page_limit=3)
        self.assertEqual(batch.rows, tuple(tuple(value) for value in rows))
        self.assertEqual(batch.pages, 2)
        self.assertEqual(batch.skipped_known_rows, 0)
        self.assertEqual(self.client.klines.call_args_list[0].kwargs, {
            "limit": 3, "start_time": START, "end_time": end - 1,
        })
        self.assertEqual(self.client.klines.call_args_list[1].kwargs, {
            "limit": 2, "start_time": START + 3 * DURATION, "end_time": end - 1,
        })

    def test_known_rows_make_repeated_collection_idempotent(self):
        rows = [row(START), row(START + DURATION)]
        self.client.klines.return_value = rows
        batch = download_range(self.client, "ETHUSDT", "15m", START,
                               START + 2 * DURATION,
                               known_open_times=[value[0] for value in rows])
        self.assertEqual(batch.rows, ())
        self.assertEqual(batch.skipped_known_rows, 2)

    def test_partial_page_advances_and_empty_page_stops(self):
        later = row(START + DURATION)
        self.client.klines.side_effect = [[later], []]
        batch = download_range(self.client, "BTCUSDT", "15m", START,
                               START + 4 * DURATION, page_limit=3)
        self.assertEqual(batch.rows, (tuple(later),))
        self.assertEqual(batch.pages, 2)
        self.assertEqual(self.client.klines.call_args_list[1].kwargs["start_time"],
                         START + 2 * DURATION)

    def test_invalid_inputs_make_no_request(self):
        cases = [
            ("XRPUSDT", "15m", START, START + DURATION, {}),
            ("BTCUSDT", "5m", START, START + DURATION, {}),
            ("BTCUSDT", "15m", START + 1, START + DURATION, {}),
            ("BTCUSDT", "15m", START, START, {}),
            ("BTCUSDT", "15m", START, START + DURATION, {"page_limit": 0}),
            ("BTCUSDT", "15m", START, START + DURATION, {"page_limit": True}),
            ("BTCUSDT", "15m", START, START + DURATION,
             {"known_open_times": [START + 1]}),
        ]
        for symbol, interval, start, end, kwargs in cases:
            with self.subTest(), self.assertRaises(HistoricalDownloadError):
                download_range(self.client, symbol, interval, start, end, **kwargs)
        with self.assertRaises(HistoricalDownloadError):
            download_range(object(), "BTCUSDT", "15m", START, START + DURATION)
        self.client.klines.assert_not_called()

    def test_range_size_is_bounded(self):
        end = START + (MAX_RANGE_CANDLES + 1) * DURATION
        with self.assertRaisesRegex(HistoricalDownloadError, "exceeds"):
            download_range(self.client, "BTCUSDT", "15m", START, end)
        self.client.klines.assert_not_called()

    def test_malformed_order_and_boundary_rows_fail_closed(self):
        bad_pages = [
            [[1]],
            [row(START), row(START)],
            [row(START + DURATION), row(START)],
            [row(START - DURATION)],
            [row(START + 2 * DURATION)],
        ]
        bad_close = row(START)
        bad_close[6] += 1
        bad_pages.append([bad_close])
        for page in bad_pages:
            self.client.reset_mock()
            self.client.klines.return_value = page
            with self.subTest(page=page), self.assertRaises(HistoricalDownloadError):
                download_range(self.client, "BTCUSDT", "15m", START,
                               START + 2 * DURATION)

    def test_rest_failure_is_wrapped_without_payload(self):
        self.client.klines.side_effect = PublicRestError("sensitive upstream text")
        with self.assertRaises(HistoricalDownloadError) as caught:
            download_range(self.client, "BTCUSDT", "15m", START, START + DURATION)
        self.assertNotIn("sensitive", str(caught.exception))

    @patch("yatl.__main__.BinancePublicRestClient")
    @patch("yatl.__main__.download_range")
    @patch("sys.argv", ["yatl", "history-check"])
    def test_runtime_cli_is_bounded_and_has_no_persistence(self, download, client_type):
        client_type.return_value.server_time.return_value = START + 10 * 14_400_000
        download.return_value = MagicMock(rows=((1,), (2,)), pages=2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(download.call_count, 6)
        self.assertTrue(all(call.kwargs["page_limit"] == 1 for call in download.call_args_list))
        self.assertIn("No persistence", output.getvalue())
        self.assertIn("No credentials", output.getvalue())


if __name__ == "__main__":
    unittest.main()
