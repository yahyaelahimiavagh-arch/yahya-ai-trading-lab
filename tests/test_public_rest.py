import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from yatl.__main__ import main
from yatl.data.rest import (
    MAX_RESPONSE_BYTES,
    BinancePublicRestClient,
    NoPublicRedirects,
    PublicRestError,
)


def response(payload):
    value = MagicMock()
    opened = value.__enter__.return_value
    opened.status = 200
    opened.read.return_value = json.dumps(payload).encode()
    return value


class PublicRestTests(unittest.TestCase):
    def setUp(self):
        self.opener = MagicMock()
        self.sleep = MagicMock()
        self.client = BinancePublicRestClient(opener=self.opener, sleeper=self.sleep)

    def test_server_time_uses_exact_public_get_without_credentials(self):
        self.opener.open.return_value = response({"serverTime": 1_700_000_000_000})
        self.assertEqual(self.client.server_time(), 1_700_000_000_000)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.binance.com/api/v3/time")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header("X-mbx-apikey"))
        self.assertEqual(self.opener.open.call_args.kwargs, {"timeout": 15})

    def test_exchange_info_is_symbol_bounded_and_summarized(self):
        payload = {"timezone": "UTC", "symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}]}
        self.opener.open.return_value = response(payload)
        self.assertEqual(self.client.exchange_info("BTCUSDT"), {
            "symbol": "BTCUSDT", "status": "TRADING", "timezone": "UTC",
        })
        self.assertEqual(self.opener.open.call_args.args[0].full_url,
                         "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT")

    def test_klines_builds_bounded_query(self):
        row = [0, "1", "2", "0.5", "1.5", "10", 899999, "12", 2, "4", "5", "0"]
        self.opener.open.return_value = response([row])
        result = self.client.klines("ETHUSDT", "15m", limit=10,
                                   start_time=1_700_000_000_000, end_time=1_700_000_900_000)
        self.assertEqual(result, [row])
        self.assertEqual(
            self.opener.open.call_args.args[0].full_url,
            "https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=15m&limit=10&startTime=1700000000000&endTime=1700000900000",
        )

    def test_invalid_inputs_make_no_request(self):
        calls = [
            lambda: self.client.exchange_info("XRPUSDT"),
            lambda: self.client.klines("btcusdt", "1h"),
            lambda: self.client.klines("BTCUSDT", "5m"),
            lambda: self.client.klines("BTCUSDT", "1h", limit=True),
            lambda: self.client.klines("BTCUSDT", "1h", limit=1001),
            lambda: self.client.klines("BTCUSDT", "1h", start_time=20, end_time=10),
            lambda: self.client._get("/api/v3/order"),
            lambda: self.client._get("/api/v3/time", {"symbol": "BTCUSDT"}),
        ]
        for call in calls:
            with self.subTest(), self.assertRaises(PublicRestError):
                call()
        self.opener.open.assert_not_called()

    def test_redirects_are_forbidden(self):
        with self.assertRaises(PublicRestError):
            NoPublicRedirects().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_rate_limit_uses_retry_after_then_succeeds(self):
        limited = HTTPError("redacted", 429, "limited", {"Retry-After": "2"}, None)
        self.opener.open.side_effect = [limited, response({"serverTime": 1_700_000_000_000})]
        self.assertEqual(self.client.server_time(), 1_700_000_000_000)
        self.sleep.assert_called_once_with(2)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_ip_ban_and_client_errors_are_not_retried(self):
        for code in (400, 401, 403, 418):
            self.opener.reset_mock()
            self.opener.open.side_effect = HTTPError("secret-url", code, "server-message", {}, None)
            with self.subTest(code=code), self.assertRaises(PublicRestError) as caught:
                self.client.server_time()
            self.assertNotIn("secret-url", str(caught.exception))
            self.assertNotIn("server-message", str(caught.exception))
            self.assertEqual(self.opener.open.call_count, 1)

    def test_transient_errors_have_bounded_backoff(self):
        for error in (HTTPError("x", 500, "x", {}, None), URLError("x"), TimeoutError("x")):
            opener = MagicMock()
            sleeper = MagicMock()
            opener.open.side_effect = error
            client = BinancePublicRestClient(opener=opener, sleeper=sleeper)
            with self.subTest(type=type(error)), self.assertRaises(PublicRestError):
                client.server_time()
            self.assertEqual(opener.open.call_count, 3)
            self.assertEqual([call.args[0] for call in sleeper.call_args_list], [0.25, 0.5])

    def test_invalid_json_size_and_schemas_fail_closed_without_retry(self):
        invalid_responses = []
        bad_json = response({}); bad_json.__enter__.return_value.read.return_value = b"{"; invalid_responses.append(bad_json)
        huge = response({}); huge.__enter__.return_value.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1); invalid_responses.append(huge)
        for value in invalid_responses:
            self.opener.reset_mock(); self.opener.open.side_effect = None; self.opener.open.return_value = value
            with self.subTest(), self.assertRaises(PublicRestError):
                self.client.server_time()
            self.assertEqual(self.opener.open.call_count, 1)
        for payload in ({}, {"serverTime": "1"}, {"serverTime": 1, "extra": 2}):
            self.opener.open.return_value = response(payload)
            with self.assertRaises(PublicRestError):
                self.client.server_time()

    def test_exchange_and_kline_schema_checks(self):
        for payload in ({}, {"timezone": "UTC", "symbols": []},
                        {"timezone": "UTC", "symbols": [{"symbol": "ETHUSDT", "status": "TRADING"}]}):
            self.opener.open.return_value = response(payload)
            with self.assertRaises(PublicRestError):
                self.client.exchange_info("BTCUSDT")
        for payload in ({}, [[1]], [[0] * 12, [0] * 12]):
            self.opener.open.return_value = response(payload)
            limit = 1 if isinstance(payload, list) and len(payload) == 2 else 10
            with self.assertRaises(PublicRestError):
                self.client.klines("BTCUSDT", "1h", limit=limit)

    def test_constructor_limits(self):
        for kwargs in ({"timeout": 0}, {"timeout": True}, {"max_attempts": 0}, {"max_attempts": 4}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BinancePublicRestClient(**kwargs)
        with self.assertRaises(ValueError):
            BinancePublicRestClient(base_url="https://example.com")

    def test_official_market_data_only_host_is_explicitly_allowlisted(self):
        from yatl.data import BINANCE_MARKET_DATA_BASE_URL
        client = BinancePublicRestClient(
            opener=self.opener, sleeper=self.sleep,
            base_url=BINANCE_MARKET_DATA_BASE_URL)
        self.opener.open.return_value = response({"serverTime": 1_700_000_000_000})
        self.assertEqual(client.server_time(), 1700000000000)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://data-api.binance.vision/api/v3/time")

    @patch("yatl.__main__.BinancePublicRestClient")
    @patch("sys.argv", ["yatl", "data-check"])
    def test_cli_safe_summary(self, client_type):
        client = client_type.return_value
        client.server_time.return_value = 1_700_000_000_000
        client.exchange_info.side_effect = lambda symbol: {"symbol": symbol, "status": "TRADING", "timezone": "UTC"}
        client.klines.return_value = [[0] * 12]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("PUBLIC DATA ONLY", output.getvalue())
        self.assertNotIn("API key", output.getvalue())


if __name__ == "__main__":
    unittest.main()
