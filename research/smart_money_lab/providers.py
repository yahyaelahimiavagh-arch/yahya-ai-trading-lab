"""Bounded public market-data readers; observation only, never wallet keys/orders."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from .engine import Trade, dec

HELIUS_BASE = "https://api-mainnet.helius-rpc.com"
DEX_BASE = "https://api.dexscreener.com"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"
# Safest starting scope: USDC and SOL settled Solana swaps. No sponsored
# token leaderboard is treated as proof of trading skill.
QUOTE_MINTS = {USDC: "USDC", SOL: "SOL"}
ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def valid_address(address: str) -> str:
    if not isinstance(address, str) or not ADDRESS.fullmatch(address):
        raise ValueError("invalid Solana base58 address")
    return address


def get_json(url: str, *, timeout: int = 12):
    """Reject non-JSON/large responses; sanitize URL-bearing errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "YATL-SmartMoney-Paper/1.0",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(5_000_001)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"read-only data provider HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("read-only data provider unavailable") from None
    if len(raw) > 5_000_000:
        raise ValueError("provider response too large")
    try:
        return json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("provider returned invalid JSON") from None


class Helius:
    def __init__(self, api_key: str):
        if not api_key or len(api_key) < 8 or any(x in api_key for x in "&/?# "):
            raise ValueError("HELIUS_API_KEY missing or malformed")
        self.key = api_key
        self._budget_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._next_request_at = 0.0
        # Enhanced endpoints have tighter limits than ordinary RPCs on Free.
        # 1.2 sec spacing (<=0.84 RPS) leaves headroom below documented 2 RPS.
        self._min_request_interval_seconds = 1.2
        self._budget_file = Path('data/smart_money/helius_budget.json')

    def _reserve_request(self):
        # One SML process only; persistent over restarts.
        with self._budget_lock:
            p = self._budget_file
            try:
                old = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'calls': 0}
                count = old['calls']
                if type(count) is not int or count < 0:
                    raise ValueError('invalid counter')
            except (ValueError, KeyError, TypeError) as exc:
                raise RuntimeError('invalid persisted Helius budget state') from exc
            if count >= 5000:
                raise RuntimeError('Helius 5000-call safety cap reached')
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_suffix('.tmp')
            temp.write_text(json.dumps({'calls': count + 1, 'max_calls': 5000}), encoding='utf-8')
            temp.replace(p)

    def _paced_request(self, url: str):
        # Shared across this Helius instance, including concurrent wallet
        # polling threads. Every attempt consumes a reserved budget entry.
        with self._rate_lock:
            delay = self._next_request_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._reserve_request()
            self._next_request_at = time.monotonic() + self._min_request_interval_seconds
        return get_json(url)

    def transactions(self, address: str, *, before: str = "", limit: int = 100) -> list[dict]:
        valid_address(address)
        if not (1 <= limit <= 100):
            raise ValueError("invalid provider page size")
        params = {"api-key": self.key, "limit": limit, "sort-order": "desc"}
        if before:
            params["before-signature"] = before
        url = f"{HELIUS_BASE}/v0/addresses/{address}/transactions?" + urllib.parse.urlencode(params)
        for attempt in range(3):
            try:
                data = self._paced_request(url)
                if not isinstance(data, list):
                    raise ValueError("unexpected Helius history response")
                return [x for x in data if isinstance(x, dict)]
            except RuntimeError as exc:
                # Do not repeat 400/401/403/500 or budget failures.
                if "HTTP 429" not in str(exc) or attempt == 2:
                    raise
                time.sleep((5, 12)[attempt])
        raise AssertionError("unreachable")

    def history(self, address: str, *, earliest_ts: int, max_pages: int = 20):
        """(transactions, complete_to_earliest): fail closed on page exhaustion."""
        rows = []
        before = ""
        seen = set()
        for _ in range(max_pages):
            page = self.transactions(address, before=before)
            if not page:
                return rows, True
            new = [x for x in page if x.get("signature") not in seen]
            for tx in new:
                if tx.get("signature"):
                    seen.add(tx["signature"])
            if not new:
                raise ValueError("repeated Helius pagination page")
            rows.extend(new)
            times = [x.get("timestamp") for x in page if isinstance(x.get("timestamp"), int)]
            if times and min(times) < earliest_ts:
                return rows, True
            last = page[-1].get("signature")
            if not isinstance(last, str) or last == before:
                raise ValueError("missing signature cursor")
            before = last
            if len(page) < 100:
                return rows, True
        return rows, False


def _token_amount(t: dict):
    # Enhanced SwapEvent uses signed balance DELTAS; explicit inputs are often
    # negative. Sign is encoded by tokenInputs vs tokenOutputs, not magnitude.
    raw = t.get("rawTokenAmount")
    if isinstance(raw, dict) and raw.get("tokenAmount") is not None:
        amount = Decimal(str(raw["tokenAmount"]))
        digits = int(raw.get("decimals", 0))
        if not amount.is_finite() or not 0 <= digits <= 18:
            raise ValueError("invalid signed balance delta")
        return abs(amount) / (Decimal(10) ** digits)
    amount = Decimal(str(t.get("tokenAmount", t.get("amount", 0))))
    if not amount.is_finite():
        raise ValueError("invalid balance delta")
    return abs(amount)


def _entries(event: dict, side: str):
    result = []
    for t in event.get(side, []) or []:
        if isinstance(t, dict) and isinstance(t.get("mint"), str):
            try:
                n = _token_amount(t)
                if n > 0:
                    result.append((t["mint"], n))
            except (ValueError, ArithmeticError, OverflowError):
                continue
    native = event.get("nativeInput" if side == "tokenInputs" else "nativeOutput")
    if isinstance(native, dict) and native.get("amount"):
        try:
            signed = Decimal(str(native["amount"]))
            if not signed.is_finite():
                raise ValueError("invalid native delta")
            n = abs(signed) / Decimal(1_000_000_000)
            # Do not double-count wrapped SOL and native SOL if both present.
            if n > 0 and not any(m == SOL for m, _ in result):
                result.append((SOL, n))
        except (ValueError, ArithmeticError):
            pass
    return result


def parse_swap(tx: dict, *, wallet: str, observed_at: int,
               historical_sol_usd: Decimal | None = None) -> Trade | None:
    """Parse only simple direct swap event; refuse ambiguous multi-asset swaps."""
    if tx.get("type") != "SWAP" or tx.get("feePayer") != wallet:
        return None
    swap = (tx.get("events") or {}).get("swap")
    if not isinstance(swap, dict):
        return None
    ins = _entries(swap, "tokenInputs")
    outs = _entries(swap, "tokenOutputs")
    if len(ins) != 1 or len(outs) != 1:
        return None
    spent_mint, spent_qty = ins[0]
    got_mint, got_qty = outs[0]
    if spent_mint in QUOTE_MINTS and got_mint not in QUOTE_MINTS:
        mint, side, qty, quote, q_qty = got_mint, "BUY", got_qty, spent_mint, spent_qty
    elif got_mint in QUOTE_MINTS and spent_mint not in QUOTE_MINTS:
        mint, side, qty, quote, q_qty = spent_mint, "SELL", spent_qty, got_mint, got_qty
    else:
        return None
    chain_ts, signature = tx.get("timestamp"), tx.get("signature")
    if not isinstance(chain_ts, int) or not isinstance(signature, str):
        return None
    if chain_ts > observed_at or observed_at - chain_ts > 86400 * 180:
        return None
    if quote == SOL and historical_sol_usd is None:
        return None
    usd = q_qty if quote == USDC else q_qty * dec(historical_sol_usd)
    try:
        return Trade(wallet, mint, side, signature, chain_ts, observed_at,
                     qty, usd, QUOTE_MINTS[quote])
    except ValueError:
        return None



def classify_swap(tx: dict, *, wallet: str, observed_at: int,
                  historical_sol_usd: Decimal | None = None) -> tuple[Trade | None, str]:
    """Explain why a candidate could not safely become a trade.

    No heuristics, inferred token legs, third-party transfers or route guesses.
    Reasons are aggregate-only diagnostics and contain no wallet/signature.
    """
    if tx.get("type") != "SWAP":
        return None, "not_swap"
    if tx.get("feePayer") != wallet:
        return None, "other_fee_payer"
    swap = (tx.get("events") or {}).get("swap")
    if not isinstance(swap, dict):
        return None, "missing_swap_event"
    ins, outs = _entries(swap, "tokenInputs"), _entries(swap, "tokenOutputs")
    if len(ins) != 1 or len(outs) != 1:
        return None, "ambiguous_legs"
    in_mint, _ = ins[0]
    out_mint, _ = outs[0]
    direct = ((in_mint in QUOTE_MINTS and out_mint not in QUOTE_MINTS)
              or (out_mint in QUOTE_MINTS and in_mint not in QUOTE_MINTS))
    if not direct:
        return None, "unsupported_quote_pair"
    if historical_sol_usd is None and (in_mint == SOL or out_mint == SOL):
        return None, "missing_sol_reference_price"
    parsed = parse_swap(tx, wallet=wallet, observed_at=observed_at,
                        historical_sol_usd=historical_sol_usd)
    return (parsed, "ok") if parsed is not None else (None, "invalid_amount_or_timestamp")

class Market:
    def token(self, mint: str, *, now: int):
        valid_address(mint)
        url = f"{DEX_BASE}/token-pairs/v1/solana/{mint}"
        pairs = get_json(url)
        if not isinstance(pairs, list):
            return None
        options = []
        for pair in pairs:
            if (not isinstance(pair, dict) or pair.get("chainId") != "solana"
                    or (pair.get("baseToken") or {}).get("address") != mint):
                continue
            # DEX Screener priceUsd always prices the BASE asset, not the quote.
            try:
                price = dec(pair.get("priceUsd"))
                liquidity = dec((pair.get("liquidity") or {}).get("usd", 0))
                if price > 0 and liquidity > 0:
                    options.append((liquidity, price))
            except ValueError:
                continue
        if not options:
            return None
        liquidity, price = max(options)
        return {"price_usd": str(price), "liquidity_usd": str(liquidity), "ts": now}

    def tokens(self, mints: set[str], *, now: int, fallback_limit: int = 0):
        """Batch indicative quotes: at most 30 token addresses per public call."""
        result = {}
        addresses = sorted(valid_address(m) for m in mints)
        for offset in range(0, len(addresses), 30):
            subset = addresses[offset:offset + 30]
            payload = get_json(f"{DEX_BASE}/tokens/v1/solana/" + ",".join(subset))
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict) or item.get("chainId") != "solana":
                    continue
                try:
                    price = dec(item.get("priceUsd"))
                    liquidity = dec((item.get("liquidity") or {}).get("usd", 0))
                except ValueError:
                    continue
                if price <= 0 or liquidity <= 0:
                    continue
                mint = (item.get("baseToken") or {}).get("address")
                # DEX pair priceUsd is for the base token, NEVER the quote.
                # A high-liquidity quote-side pair must not mask a correct
                # lower-liquidity base-side price for the requested mint.
                if mint not in subset:
                    continue
                if mint not in result or liquidity > dec(result[mint]["liquidity_usd"]):
                    result[mint] = {"price_usd": str(price),
                                    "liquidity_usd": str(liquidity), "ts": now}
        # Batch lookup may omit thinly indexed tokens. Make at most three
        # single-token DEX lookups, preserving the exact base-mint and
        # $20k real-time fill guard. A missing quote is NEVER fabricated.
        if not 0 <= fallback_limit <= 3:
            raise ValueError("DEX quote fallback must be between zero and three")
        misses = [mint for mint in addresses if mint not in result]
        for mint in misses[:fallback_limit]:
            try:
                quote = self.token(mint, now=now)
            except (ValueError, RuntimeError):
                quote = None
            if quote is not None:
                result[mint] = quote
        return result

    def sol_usd(self, *, now: int) -> Decimal | None:
        q = self.token(SOL, now=now)
        return dec(q["price_usd"]) if q else None


def discover_candidates(helius: Helius, market: Market, *,
                        max_pools: int = 5, per_pool: int = 30,
                        source: str = "boosts") -> list[dict]:
    """Find CANDIDATES, not vetted winners, via promoted tokens' swap payers.

    Promoted token sampling is heavily biased: candidates are never automatically
    eligible until sufficient independent transaction history passes screening.
    """
    if source not in ("boosts", "profiles"):
        raise ValueError("unsupported candidate discovery feed")
    feed = "token-profiles/latest/v1" if source == "profiles" else "token-boosts/latest/v1"
    promotions = get_json(f"{DEX_BASE}/{feed}")
    if not isinstance(promotions, list):
        raise ValueError("invalid discovery feed")
    wallets: dict[str, dict] = {}
    used = 0
    for token in promotions:
        if used >= max_pools:
            break
        if token.get("chainId") != "solana":
            continue
        address = token.get("tokenAddress", "")
        try:
            valid_address(address)
            pairs = get_json(f"{DEX_BASE}/token-pairs/v1/solana/{address}")
        except (ValueError, RuntimeError):
            continue
        if not isinstance(pairs, list):
            continue
        safe_pairs = [p for p in pairs if isinstance(p, dict) and p.get("pairAddress")]
        if source == "profiles":
            # A quality-first *pool sample*, never verified trader selection.
            # Reject new/illiquid/untraded pools before spending Helius calls.
            cutoff_ms = int(time.time() * 1000) - 7 * 86400 * 1000
            filtered = []
            for p in safe_pairs:
                try:
                    liq = dec((p.get("liquidity") or {}).get("usd", 0))
                    volume = dec((p.get("volume") or {}).get("h24", 0))
                    created = int(p.get("pairCreatedAt") or 0)
                    if (p.get("chainId") == "solana" and liq >= Decimal("200000")
                            and volume >= Decimal("30000") and 0 < created < cutoff_ms):
                        filtered.append(p)
                except (ValueError, TypeError, OverflowError):
                    continue
            safe_pairs = filtered
        pool = next((p["pairAddress"] for p in sorted(
            safe_pairs, key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0),
            reverse=True
        )), None)
        if not pool:
            continue
        try:
            transactions = helius.transactions(valid_address(pool), limit=min(per_pool, 100))
        except (ValueError, RuntimeError):
            continue
        used += 1
        for tx in transactions:
            payer = tx.get("feePayer")
            if tx.get("type") == "SWAP" and isinstance(payer, str) and ADDRESS.fullmatch(payer):
                wallets[payer] = {"wallet": payer,
                                  "source": ("liquid_profile_pool_swap_payer"
                                             if source == "profiles" else
                                             "promoted_pool_swap_payer"),
                                  "verified": False}
    return list(wallets.values())
