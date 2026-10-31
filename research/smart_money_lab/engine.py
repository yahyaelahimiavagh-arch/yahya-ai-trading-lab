"""Isolated, strictly paper-only smart money research engine (no order interface).

Inputs are observations, not executable trade instructions. Every portfolio has
an independent USD balance; costs and signal/price timestamps are explicit.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from typing import Any

D = Decimal
DELAYS = (1, 3, 10)
STRATEGIES = ("blind", "smart", "consensus")
START_USD = D("1000")
MAX_ORDER_USD = D("30")
MAX_OPEN = 6
MAX_EXPOSURE_USD = D("180")
MAX_DRAWDOWN = D("0.05")
FEE_BPS = D("20")
BASE_SLIP_BPS = D("50")
MAX_PRICE_AGE_SECONDS = 30
CONSENSUS_SECONDS = 120


def dec(value: Any) -> Decimal:
    try:
        number = D(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("non-numeric amount") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("amount must be nonnegative and finite")
    return number


@dataclass(frozen=True)
class Trade:
    wallet: str
    mint: str
    side: str
    signature: str
    chain_time: int
    observed_at: int
    amount: Decimal
    usd_notional: Decimal
    # Historical scoring only supports swaps settled in a USD stablecoin.
    quote_mint: str = ""

    def __post_init__(self):
        if self.side not in ("BUY", "SELL") or not self.wallet or not self.mint or not self.signature:
            raise ValueError("malformed trade")
        if self.chain_time <= 0 or self.observed_at < self.chain_time:
            raise ValueError("observed time must follow onchain time")
        if dec(self.amount) <= 0 or dec(self.usd_notional) <= 0:
            raise ValueError("positive trade values required")

    @property
    def key(self) -> str:
        return f"{self.signature}|{self.wallet}|{self.mint}|{self.side}"


def score_wallet(wallet: str, trades: list[Trade], *, cutoff: int,
                 min_closed: int = 50, min_days: int = 15) -> dict:
    """Realized FIFO-cost-basis approximation; excludes unknown-basis sells.

    A score cannot be trusted for truncated histories. The caller must set
    history_complete=True separately; this function never asserts completeness.
    """
    selected = sorted((t for t in trades if t.wallet == wallet and
                       t.chain_time < cutoff and t.quote_mint in ("USDC", "USDT", "SOL")),
                      key=lambda t: (t.chain_time, t.signature))
    lots: dict[str, list[list[Decimal]]] = defaultdict(list)
    pnl = D("0")
    realized = []
    days = set()
    unmatched = 0
    for t in selected:
        days.add(t.chain_time // 86400)
        if t.side == "BUY":
            lots[t.mint].append([t.amount, t.usd_notional / t.amount])
            continue
        qty = t.amount
        cost = D("0")
        consumed = D("0")
        while qty > 0 and lots[t.mint]:
            lot = lots[t.mint][0]
            used = min(qty, lot[0])
            cost += used * lot[1]
            consumed += used
            qty -= used
            lot[0] -= used
            if lot[0] == 0:
                lots[t.mint].pop(0)
        if qty > 0:
            unmatched += 1
        if consumed <= 0:
            continue
        # Unmatched sell volume is not counted as profit.
        revenue = t.usd_notional * consumed / t.amount
        result = revenue - cost - (revenue + cost) * D("0.002")
        pnl += result
        realized.append(result)
    wins = sum(x > 0 for x in realized)
    closed = len(realized)
    peak = D("0")
    running = D("0")
    max_dd = D("0")
    for result in realized:
        running += result
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    active = len(days)
    stable = closed >= min_closed and active >= min_days and unmatched == 0
    win_rate = D(wins) / D(closed) if closed else D("0")
    # Score is intentionally conservative and is not a probabilistic estimate.
    profitability = max(D("0"), min(D("25"), pnl / D("20")))
    consistency = min(D("20"), D(closed) / D("5")) * min(D("1"), D(active) / D("20"))
    drawdown_score = max(D("0"), D("15") - max_dd / D("20"))
    score = profitability + consistency + drawdown_score
    return {
        "wallet": wallet, "closed": closed, "active_days": active,
        "net_realized_usd": str(pnl), "win_rate": str(win_rate),
        "max_realized_drawdown_usd": str(max_dd), "unmatched_sells": unmatched,
        "history_complete": False, "eligible": False,
        "preliminary_score": str(score),
        "meets_activity_thresholds": stable,
    }


def rank_wallets(scored: list[dict], *, min_liquidity_usd: Decimal = D("20000")) -> tuple[list[str], list[str]]:
    """Never rank incomplete histories or fabricated copyability measurements."""
    valid = [r for r in scored if r.get("history_complete") is True and
             r.get("meets_activity_thresholds") is True and
             r.get("copyable") is True and
             dec(r.get("min_liquidity_usd", "0")) >= min_liquidity_usd and
             int(r.get("unmatched_sells", 1)) == 0]
    blind = sorted(valid, key=lambda r: (dec(r["net_realized_usd"]), r["wallet"]), reverse=True)
    smart = sorted(valid, key=lambda r: (
        dec(r.get("copyability_score", "0")), dec(r["preliminary_score"]), r["wallet"]), reverse=True)
    return [r["wallet"] for r in blind[:15]], [r["wallet"] for r in smart[:15]]


@dataclass
class Holding:
    wallet: str
    mint: str
    qty: Decimal
    cost: Decimal


@dataclass
class Portfolio:
    strategy: str
    delay: int
    cash: Decimal = START_USD
    holdings: dict[str, Holding] = field(default_factory=dict)
    fills: list[dict] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    peak_equity: Decimal = START_USD
    halted: bool = False

    @property
    def id(self):
        return f"{self.strategy}_{self.delay}s"

    def reject(self, why: str):
        self.rejected[why] = self.rejected.get(why, 0) + 1

    def equity(self, quotes: dict[str, dict], now: int) -> Decimal | None:
        result = self.cash
        for h in self.holdings.values():
            q = quotes.get(h.mint)
            if not q or now - int(q["ts"]) > MAX_PRICE_AGE_SECONDS or int(q["ts"]) > now:
                return None
            result += h.qty * dec(q["price_usd"]) * (D("1") - FEE_BPS / D("10000"))
        return result

    def apply(self, signal: Trade, *, price: Decimal, liquidity_usd: Decimal,
              quote_ts: int, now: int, source: str = "") -> bool:
        if now < quote_ts or now - quote_ts > MAX_PRICE_AGE_SECONDS:
            self.reject("stale_quote")
            return False
        if now < signal.observed_at + self.delay:
            self.reject("not_due")
            return False
        if now - signal.chain_time > 120:
            self.reject("signal_too_old")
            return False
        if liquidity_usd < D("20000") or price <= 0:
            self.reject("illiquid")
            return False
        if self.halted and signal.side == "BUY":
            self.reject("risk_halted")
            return False
        owner = source or signal.wallet
        key = f"{owner}|{signal.mint}"
        fee = FEE_BPS / D("10000")
        if signal.side == "BUY":
            if key not in self.holdings and len(self.holdings) >= MAX_OPEN:
                self.reject("max_positions")
                return False
            exposure = sum(x.cost for x in self.holdings.values())
            available = min(MAX_ORDER_USD, MAX_EXPOSURE_USD - exposure, self.cash)
            if available <= D("1"):
                self.reject("max_exposure_or_cash")
                return False
            # Slippage includes a simple size/liquidity stress term, not a live route quote.
            slip = BASE_SLIP_BPS / D("10000") + available / liquidity_usd
            total = available
            qty = total * (D("1") - fee) / (price * (D("1") + slip))
            self.cash -= total
            if key in self.holdings:
                h = self.holdings[key]
                h.qty += qty
                h.cost += total
            else:
                self.holdings[key] = Holding(owner, signal.mint, qty, total)
        else:
            h = self.holdings.get(key)
            if h is None:
                self.reject("no_matching_position")
                return False
            # Exit-policy experiment: first matching leader sell fully closes
            # our corresponding paper lot; not an exact proportional copy.
            qty = h.qty
            slip = BASE_SLIP_BPS / D("10000") + (qty * price) / liquidity_usd
            proceeds = qty * price * max(D("0"), D("1") - slip) * (D("1") - fee)
            self.cash += proceeds
            self.holdings.pop(key)
        self.fills.append({
            "time": now, "signature": signal.signature, "wallet": signal.wallet,
            "mint": signal.mint, "side": signal.side, "usd_price": str(price),
            "cash_after": str(self.cash), "signal_to_fill_seconds": now - signal.chain_time
        })
        return True

    def mark(self, quotes: dict[str, dict], now: int):
        equity = self.equity(quotes, now)
        if equity is not None:
            self.peak_equity = max(self.peak_equity, equity)
            if self.peak_equity > 0 and equity / self.peak_equity <= D("1") - MAX_DRAWDOWN:
                self.halted = True
                # Emergency exit uses the current observed quote and adverse
                # friction; price gaps can exceed the 5% threshold.
                for key, holding in list(self.holdings.items()):
                    quote = quotes.get(holding.mint)
                    if not quote or now - int(quote["ts"]) > MAX_PRICE_AGE_SECONDS:
                        continue
                    p = dec(quote["price_usd"])
                    liq = dec(quote["liquidity_usd"])
                    slip = BASE_SLIP_BPS / D("10000") + holding.qty * p / max(liq, D("1"))
                    proceeds = holding.qty * p * max(D("0"), D("1") - slip) * (D("1") - FEE_BPS / D("10000"))
                    self.cash += proceeds
                    self.fills.append({"time": now, "signature": "RISK_EXIT",
                                       "wallet": holding.wallet, "mint": holding.mint,
                                       "side": "RISK_EXIT", "usd_price": str(p),
                                       "cash_after": str(self.cash),
                                       "signal_to_fill_seconds": None})
                    del self.holdings[key]

    def to_dict(self, quotes: dict[str, dict], now: int) -> dict:
        equity = self.equity(quotes, now)
        return {
            "id": self.id, "cash_usd": str(self.cash),
            "equity_usd": str(equity) if equity is not None else None,
            "unpriced_holdings": equity is None,
            "halted": self.halted, "fills": self.fills,
            "open_positions": [
                {"wallet": h.wallet, "mint": h.mint, "qty": str(h.qty), "cost_usd": str(h.cost)}
                for h in self.holdings.values()
            ], "rejected": self.rejected,
        }


class PaperLab:
    def __init__(self, start_at: int, blind: list[str], smart: list[str]):
        if start_at <= 0:
            raise ValueError("start time required")
        self.start_at = start_at
        self.blind = set(blind[:15])
        self.smart = set(smart[:15])
        self.portfolios = {f"{s}_{d}s": Portfolio(s, d) for s in STRATEGIES for d in DELAYS}
        self.seen: set[str] = set()
        self.pending: list[tuple[int, str, Trade, str]] = []
        self.vote_log: dict[str, list[Trade]] = defaultdict(list)

    def ingest(self, trade: Trade):
        if trade.key in self.seen:
            return
        self.seen.add(trade.key)
        # Point-in-time rule: no backfilled observation can enter forward portfolios.
        if trade.chain_time < self.start_at or trade.observed_at < self.start_at:
            return
        for strategy, allowed in (("blind", self.blind), ("smart", self.smart)):
            if trade.wallet in allowed:
                for delay in DELAYS:
                    self.pending.append((trade.observed_at + delay, f"{strategy}_{delay}s", trade, ""))
        if trade.wallet not in self.smart:
            return
        key = f"{trade.mint}|{trade.side}"
        self.vote_log[key] = [x for x in self.vote_log[key] if
                              trade.observed_at - x.observed_at <= CONSENSUS_SECONDS]
        self.vote_log[key].append(trade)
        voters = {x.wallet for x in self.vote_log[key]}
        # Two independent smart wallets in the window; duplicate wallet is not a vote.
        if len(voters) >= 2:
            for delay in DELAYS:
                self.pending.append((trade.observed_at + delay, f"consensus_{delay}s", trade, "consensus"))
            self.vote_log[key] = []

    def process(self, now: int, quotes: dict[str, dict]):
        remaining = []
        for due, portfolio_id, trade, owner in sorted(self.pending, key=lambda x: x[0]):
            if due > now:
                remaining.append((due, portfolio_id, trade, owner))
                continue
            q = quotes.get(trade.mint)
            portfolio = self.portfolios[portfolio_id]
            if not q:
                portfolio.reject("missing_quote")
                continue
            portfolio.apply(
                trade, price=dec(q["price_usd"]),
                liquidity_usd=dec(q["liquidity_usd"]),
                quote_ts=int(q["ts"]), now=now, source=owner,
            )
        self.pending = remaining
        for p in self.portfolios.values():
            p.mark(quotes, now)

    def report(self, quotes: dict[str, dict], now: int):
        return {
            "kind": "YATL_SMART_MONEY_PAPER_ONLY",
            "start_at": self.start_at, "as_of": now,
            "elapsed_seconds": max(0, now - self.start_at),
            "initial_usd_per_portfolio": "1000",
            "note": "Nine independent ledgers: 3 strategies x 3 fill delays; no real orders.",
            "wallets_blind": sorted(self.blind), "wallets_smart": sorted(self.smart),
            "unique_signals_seen": len(self.seen), "pending": len(self.pending),
            "portfolios": [p.to_dict(quotes, now) for p in self.portfolios.values()],
        }
