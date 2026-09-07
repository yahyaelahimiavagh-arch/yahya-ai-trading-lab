import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from yatl.account import (ACCOUNT_URL, AccountError, Credentials, NoAccountRedirects,
                          _summary, load_credentials, read_account, sign_query, validate_target)
from yatl.__main__ import main

KEY = "K" * 64
SECRET = "S" * 64
ENV = f"YATL_ENVIRONMENT=testnet\nLIVE_MASTER_LOCK=OFF\nBINANCE_TESTNET_API_KEY={KEY}\nBINANCE_TESTNET_API_SECRET={SECRET}\n"


def payload():
    return {"accountType": "SPOT", "permissions": ["SPOT"], "canTrade": True,
            "canWithdraw": False, "canDeposit": False,
            "balances": [{"asset": "BTC", "free": "1.00000000", "locked": "0.00000000"}]}


class AccountTests(unittest.TestCase):
    def load(self, content=ENV):
        with patch("yatl.account.Path.open", return_value=io.BytesIO(content.encode("utf-8-sig"))):
            return load_credentials()

    def test_hmac_rfc4231_known_vector(self):
        self.assertEqual(sign_query("Jefe", "what do ya want for nothing?"),
                         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843")

    @patch.dict(os.environ, {}, clear=True)
    def test_env_bom_quotes_comments_and_no_mutation(self):
        before = dict(os.environ)
        creds = self.load("# local\n" + ENV.replace("=testnet", "='testnet'").replace("=OFF", '=\"OFF\"'))
        self.assertEqual(creds.api_key, KEY)
        self.assertEqual(creds.api_secret, SECRET)
        self.assertEqual(dict(os.environ), before)
        self.assertNotIn(KEY, repr(creds))
        self.assertNotIn(SECRET, repr(creds))

    @patch.dict(os.environ, {}, clear=True)
    def test_env_fails_closed_and_redacts_values(self):
        for content in ("", ENV.replace("testnet", "public"), ENV.replace("OFF", "ON"),
                        ENV + "LIVE_MASTER_LOCK=OFF\n", ENV + "UNKNOWN=hidden\n",
                        ENV.replace(KEY, "${SECRET}"), ENV.replace(SECRET, ""),
                        ENV.replace(KEY, "'" + KEY), ENV + "x" * 16_385):
            with self.subTest(), self.assertRaises(AccountError) as caught:
                self.load(content)
            self.assertNotIn(KEY, str(caught.exception))
            self.assertNotIn(SECRET, str(caught.exception))

    @patch.dict(os.environ, {"LIVE_MASTER_LOCK": "ON"}, clear=True)
    def test_conflicting_process_environment_rejected(self):
        with self.assertRaisesRegex(AccountError, "conflicts"):
            self.load()

    def test_missing_or_unreadable_env(self):
        with patch("yatl.account.Path.open", side_effect=OSError(SECRET)):
            with self.assertRaisesRegex(AccountError, "Cannot read environment file"):
                load_credentials()

    def test_credentials_reject_header_injection(self):
        for value in ("", KEY + "\r\nX: value", "example", None):
            with self.assertRaises(AccountError):
                Credentials(value, SECRET)

    def test_exact_host_path_and_method_allowlist(self):
        validate_target(ACCOUNT_URL, "GET")
        for url in (ACCOUNT_URL.replace("https:", "http:"),
                    ACCOUNT_URL.replace("testnet.binance.vision", "api.binance.com"),
                    ACCOUNT_URL.replace("testnet.binance.vision", "testnet.binance.vision.evil.com"),
                    ACCOUNT_URL.replace("/account", "/order"),
                    ACCOUNT_URL.replace("/api/v3", "/fapi/v1"),
                    ACCOUNT_URL.replace(".vision", ".vision:443"),
                    ACCOUNT_URL.replace("https://", "https://user@"),
                    ACCOUNT_URL + "#fragment", ACCOUNT_URL + "?x=y"):
            with self.subTest(url=url), self.assertRaises(AccountError):
                validate_target(url, "GET")
        for method in ("POST", "DELETE", "PUT", "get"):
            with self.assertRaises(AccountError):
                validate_target(ACCOUNT_URL, method)

    @patch("yatl.account.load_credentials")
    @patch("yatl.account.build_opener")
    def test_public_account_rejected_before_credentials_or_network(self, opener, loader):
        with self.assertRaises(AccountError):
            read_account(environment="public")
        opener.assert_not_called()
        loader.assert_not_called()

    def test_redirects_rejected(self):
        for code in (301, 302, 303, 307, 308):
            with self.assertRaises(AccountError):
                NoAccountRedirects().redirect_request(None, None, code, "", {}, ACCOUNT_URL)

    @patch("yatl.account.time.time_ns", return_value=1_700_000_000_123_000_000)
    @patch("yatl.account.load_credentials", return_value=Credentials(KEY, SECRET))
    @patch("yatl.account.build_opener")
    def test_signed_get_safe_summary_and_transport(self, opener, loader, clock):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps(payload()).encode()
        self.assertEqual(read_account(), {"account_type": "SPOT", "assets": 1, "nonzero_assets": 1})
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("X-mbx-apikey"), KEY)
        parts = urlsplit(request.full_url)
        self.assertEqual(parts.scheme + "://" + parts.netloc + parts.path, ACCOUNT_URL)
        query, signature = parts.query.rsplit("&signature=", 1)
        self.assertEqual(parse_qs(query), {"timestamp": ["1700000000123"], "recvWindow": ["5000"]})
        self.assertEqual(signature, sign_query(SECRET, query))
        self.assertNotIn(SECRET, request.full_url)
        self.assertEqual(opener.call_args.args[0].proxies, {})
        self.assertIsInstance(opener.call_args.args[1], NoAccountRedirects)
        self.assertEqual(opener.return_value.open.call_args.kwargs, {"timeout": 15})

    @patch("yatl.account.load_credentials", return_value=Credentials(KEY, SECRET))
    @patch("yatl.account.build_opener")
    def test_transport_errors_redacted_without_retry(self, opener, loader):
        for error in (HTTPError(SECRET, 401, KEY, {}, None),
                      HTTPError(SECRET, 429, KEY, {}, None), URLError(SECRET), TimeoutError(KEY)):
            opener.return_value.open.reset_mock()
            opener.return_value.open.side_effect = error
            with self.assertRaises(AccountError) as caught:
                read_account()
            self.assertNotIn(KEY, str(caught.exception))
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertEqual(opener.return_value.open.call_count, 1)

    @patch("yatl.account.load_credentials", return_value=Credentials(KEY, SECRET))
    @patch("yatl.account.build_opener")
    def test_bad_network_payload_rejected(self, opener, loader):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        for raw in (b"not json", b"\xff", b"x" * 2_000_001, b"{}"):
            response.read.return_value = raw
            with self.assertRaises(AccountError):
                read_account()

    def test_account_schema_validation(self):
        cases = [None, {}, dict(payload(), accountType="MARGIN"),
                 dict(payload(), permissions=["SPOT", "MARGIN"]), dict(payload(), canTrade=1),
                 dict(payload(), balances=None)]
        for amount in ("NaN", "Infinity", "-1", 1, "1e9"):
            cases.append(dict(payload(), balances=[{"asset": "BTC", "free": amount, "locked": "0"}]))
        cases.append(dict(payload(), balances=payload()["balances"] * 2))
        for value in cases:
            with self.subTest(), self.assertRaises(AccountError):
                _summary(value)

    def test_unicode_assets_and_control_character_rejection(self):
        value = payload()
        value["balances"][0]["asset"] = "测试币"
        self.assertEqual(_summary(value)["assets"], 1)
        value["balances"][0]["asset"] = "BTC\n"
        with self.assertRaises(AccountError):
            _summary(value)

    @patch("yatl.__main__.read_account", return_value={"account_type": "SPOT", "assets": 1, "nonzero_assets": 1})
    @patch("sys.argv", ["yatl", "account"])
    def test_cli_safe_output(self, read):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("LIVE_MASTER_LOCK=OFF", output.getvalue())
        self.assertNotIn(KEY, output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())
