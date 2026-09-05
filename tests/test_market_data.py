import csv
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from yatl.market_data import MarketDataError, _get, candles, ping, save_csv


def row():
    return [1000, "100.00", "110.00", "90.00", "105.00", "2.50", 1999, "255.00", 4, "1.0", "105.00", "0"]


class MarketDataTests(unittest.TestCase):
    @patch("yatl.market_data._get", return_value={})
    def test_ping_defaults_to_testnet(self, request):
        ping()
        request.assert_called_once_with("testnet", "ping")

    @patch("yatl.market_data._get")
    def test_invalid_inputs_make_no_request(self, request):
        for kwargs in ({"symbol": "BTC/USDT"}, {"limit": 0}, {"limit": 1001}, {"interval": "bad"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                candles(**kwargs)
        request.assert_not_called()

    @patch("yatl.market_data._get")
    def test_preserves_decimal_precision_and_query(self, request):
        request.return_value = [row()]
        self.assertEqual(candles(symbol="btcusdt")[0][1], "100.00")
        request.assert_called_once_with("testnet", "klines", {"symbol": "BTCUSDT", "interval": "1h", "limit": 100})

    @patch("yatl.market_data._get")
    def test_rejects_malformed_or_inconsistent_data(self, request):
        invalid = row()
        invalid[2] = "50"
        nonfinite = row()
        nonfinite[1] = "NaN"
        for payload in ({"code": -1}, [], [[1]], [invalid], [nonfinite], [row(), row()]):
            with self.subTest(payload=payload), self.assertRaises(MarketDataError):
                request.return_value = payload
                candles()

    @patch("yatl.market_data.build_opener")
    def test_rate_limit_is_not_retried(self, opener):
        opener.return_value.open.side_effect = HTTPError("https://example.invalid", 429, "limited", {}, None)
        with self.assertRaisesRegex(MarketDataError, "rate limit"):
            _get("testnet", "ping")
        self.assertEqual(opener.return_value.open.call_count, 1)

    def test_only_allowed_hosts_and_endpoints(self):
        for environment, endpoint in (("other", "ping"), ("public", "order"), ("testnet", "account")):
            with self.assertRaises(ValueError):
                _get(environment, endpoint)

    def test_csv_round_trip_and_overwrite_protection(self):
        path = Path(tempfile.gettempdir()) / f"yatl-{uuid.uuid4().hex}.csv"
        try:
            save_csv([row()], path)
            with path.open(newline="", encoding="utf-8") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(records[0]["open"], "100.00")
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_csv([row()], path)
            self.assertEqual(path.read_bytes(), original)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
