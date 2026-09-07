"""Read-only Spot Testnet account access. No configurable trading transport."""

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ACCOUNT_URL = "https://testnet.binance.vision/api/v3/account"
ENV_KEYS = frozenset({"YATL_ENVIRONMENT", "LIVE_MASTER_LOCK",
                      "BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"})


class AccountError(Exception):
    """Only fixed, credential-free messages may cross the CLI boundary."""


@dataclass(frozen=True)
class Credentials:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self):
        for value in (self.api_key, self.api_secret):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{32,128}", value):
                raise AccountError("Missing or invalid Testnet HMAC credentials")


def load_credentials(path=Path(".env")):
    """Read one explicit file; no shell evaluation, interpolation or env mutation.

    Process values must agree with file values: conflicting configuration fails.
    """
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(16_385)
        if len(raw) > 16_384:
            raise AccountError("Environment file exceeds size limit")
        content = raw.decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise AccountError("Cannot read environment file") from None
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in ENV_KEYS or key in values:
            raise AccountError("Invalid, unknown or duplicate environment entry")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise AccountError("Invalid environment quoting")
            value = value[1:-1]
        values[key] = value
    if set(values) != ENV_KEYS:
        raise AccountError("Environment file must contain all four required entries")
    if any(key in os.environ and os.environ[key] != value for key, value in values.items()):
        raise AccountError("Process environment conflicts with environment file")
    if values["YATL_ENVIRONMENT"] != "testnet" or values["LIVE_MASTER_LOCK"] != "OFF":
        raise AccountError("Account access requires testnet and LIVE_MASTER_LOCK=OFF")
    return Credentials(values["BINANCE_TESTNET_API_KEY"], values["BINANCE_TESTNET_API_SECRET"])


def sign_query(secret, query):
    return hmac.new(secret.encode("ascii"), query.encode("ascii"), hashlib.sha256).hexdigest()


def validate_target(url, method):
    # Exact equality also rejects ports, userinfo, encoded paths and fragments.
    if url != ACCOUNT_URL or method != "GET":
        raise AccountError("Only GET Spot Testnet account access is allowed")


class NoAccountRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AccountError("Account redirects are forbidden")


def _summary(payload):
    if not isinstance(payload, dict) or payload.get("accountType") != "SPOT":
        raise AccountError("Unexpected Spot account response")
    if payload.get("permissions") != ["SPOT"]:
        raise AccountError("Unexpected account permissions")
    for flag in ("canTrade", "canWithdraw", "canDeposit"):
        if type(payload.get(flag)) is not bool:
            raise AccountError("Invalid account capability response")
    balances = payload.get("balances")
    if not isinstance(balances, list) or len(balances) > 10_000:
        raise AccountError("Invalid account balances")
    seen = set()
    nonzero = 0
    for balance in balances:
        if not isinstance(balance, dict):
            raise AccountError("Invalid account balance")
        asset = balance.get("asset")
        if (not isinstance(asset, str) or not 1 <= len(asset) <= 128
                or not all(c.isalnum() or c == "_" for c in asset) or asset in seen):
            raise AccountError("Invalid account asset")
        seen.add(asset)
        amounts = [balance.get("free"), balance.get("locked")]
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9]{1,30}(\.[0-9]{1,30})?", v) for v in amounts):
            raise AccountError("Invalid account amount")
        nonzero += any(any(c in "123456789" for c in v) for v in amounts)
    # Do not return raw account identifiers, balance amounts or server messages.
    return {"account_type": "SPOT", "assets": len(balances), "nonzero_assets": nonzero}


def read_account(env_file=Path(".env"), environment="testnet"):
    if environment != "testnet":
        raise AccountError("Authenticated account access is Testnet only")
    credentials = load_credentials(env_file)
    validate_target(ACCOUNT_URL, "GET")
    timestamp = time.time_ns() // 1_000_000
    if timestamp <= 0:
        raise AccountError("Invalid system clock")
    query = urlencode({"timestamp": timestamp, "recvWindow": 5000})
    signature = sign_query(credentials.api_secret, query)
    request = Request(ACCOUNT_URL + "?" + query + "&signature=" + signature,
                      headers={"X-MBX-APIKEY": credentials.api_key}, method="GET")
    try:
        # Ignore ambient proxies for this credential-bearing request. TLS uses
        # Python's default certificate and hostname verification.
        with build_opener(ProxyHandler({}), NoAccountRedirects()).open(request, timeout=15) as response:
            if response.status != 200:
                raise AccountError("Unexpected account HTTP status")
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise AccountError("Account response exceeds size limit")
            return _summary(json.loads(raw))
    except HTTPError as exc:
        code = exc.code
        exc.close()
        if code in {418, 429}:
            raise AccountError("Account rate limit; stop and retry later") from None
        raise AccountError("Account request rejected; check key, USER_DATA permission and system clock") from None
    except (URLError, OSError, TimeoutError):
        raise AccountError("Account connection failed; check network and TLS") from None
    except (ValueError, UnicodeError):
        raise AccountError("Invalid account response") from None
