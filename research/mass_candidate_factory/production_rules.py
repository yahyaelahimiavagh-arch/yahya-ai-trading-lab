"""Exact typed rule compiler for executable MCF-PROD-001 families.

Families whose frozen prose is insufficient for one deterministic
implementation are blocked before performance rather than approximated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from .models import MCFError
from .production import ProductionSeries, ProductionUniverseBinding
from .production_features import ProductionFeatureCache
from .production_generator import SEARCH_BUDGET

VERSION = "MCF_PRODUCTION_RULES/1.0.0"

BLOCKED_FAMILIES = {
    "CRASH_REBOUND": (
        "Frozen rule says exit at max_hold_bars or recovery rule, but the "
        "recovery exit is not numerically specified."
    ),
    "RANGE_COMPRESSION_BREAKOUT": (
        "Frozen rule does not specify the rolling sample used for the "
        "compression quantile/lagged median range well enough to choose one "
        "without adding a degree of freedom."
    ),
}


class ProductionRuleBlocked(MCFError):
    """A frozen family cannot be implemented faithfully before performance."""


def _num(value) -> float:
    try:
        result = float(Decimal(str(value)))
    except Exception as exc:
        raise MCFError("nonnumeric production parameter") from exc
    if not result == result or result in (float("inf"), float("-inf")):
        raise MCFError("nonfinite production parameter")
    return result


def _integer(value) -> int:
    x = _num(value)
    if int(x) != x or x < 1:
        raise MCFError("invalid integer production parameter")
    return int(x)


def _state(entry: Sequence[bool], exit_: Sequence[bool], available: Sequence[bool]) -> tuple[bool, ...]:
    if not (len(entry) == len(exit_) == len(available)):
        raise MCFError("production rule length mismatch")
    held = False
    out = []
    for ent, ex, valid in zip(entry, exit_, available):
        if valid:
            if held and ex:
                held = False
            elif not held and ent:
                held = True
        out.append(held)
    return tuple(out)


def _cross_state(fast: Sequence[float | None], slow: Sequence[float | None]) -> tuple[tuple[bool, ...], tuple[bool, ...]]:
    n = len(fast)
    entry = [False] * n
    exit_ = [False] * n
    available = [False] * n
    for i in range(1, n):
        vals = (fast[i - 1], slow[i - 1], fast[i], slow[i])
        if any(v is None for v in vals):
            continue
        available[i] = True
        entry[i] = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
        exit_[i] = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
    return _state(entry, exit_, available), tuple(available)


def _condition_state(condition: Sequence[bool], available: Sequence[bool]) -> tuple[bool, ...]:
    return _state(condition, [not x for x in condition], available)


def compile_candidate(candidate: Mapping[str, object], cache: ProductionFeatureCache, *,
                      liquidity_percentile: Sequence[float | None] | None = None,
                      universe_binding: ProductionUniverseBinding | None = None) -> ProductionSeries:
    """Compile a registered production candidate to completed-bar desired state."""
    family = str(candidate.get("family", ""))
    if family in BLOCKED_FAMILIES:
        raise ProductionRuleBlocked(f"{family}: {BLOCKED_FAMILIES[family]}")
    if family not in set(SEARCH_BUDGET["allowed_initial_families"]):
        raise MCFError("candidate family outside frozen MCF-PROD-001 budget")
    if candidate.get("state") != "PRE_OUTCOME_REGISTERED":
        raise MCFError("candidate not registered before outcome")
    if candidate.get("timeframe") != cache.bars.timeframe:
        raise MCFError("candidate/data timeframe mismatch")

    p = dict(candidate["parameter_vector"])
    n = len(cache.bars.times)
    entry = [False] * n
    exit_ = [False] * n
    available = [False] * n

    if family == "TREND_CROSSOVER":
        fast = cache.rolling("closes", _integer(p["fast_window"]), lag=0, statistic="mean")
        slow = cache.rolling("closes", _integer(p["slow_window"]), lag=0, statistic="mean")
        desired, valid = _cross_state(fast, slow)
        return ProductionSeries(
            cache.bars.symbol, cache.bars.timeframe, cache.bars.times,
            cache.bars.opens, cache.bars.closes, desired, valid,
        )

    if family == "BREAKOUT_CHANNEL":
        high = cache.rolling("highs", _integer(p["entry_window"]), lag=1, statistic="max")
        low = cache.rolling("lows", _integer(p["exit_window"]), lag=1, statistic="min")
        buffer_ = _num(p["breakout_buffer_fraction"])
        for i in range(n):
            if high[i] is None or low[i] is None:
                continue
            available[i] = True
            close = float(cache.bars.closes[i])
            entry[i] = close > high[i] * (1.0 + buffer_)
            exit_[i] = close < low[i]

    elif family in ("SHORT_HORIZON_MEAN_REVERSION", "SIMPLE_STATISTICAL_DEVIATION"):
        window = _integer(p["lookback"])
        z = cache.zscore_vs_lagged(window)
        entry_z = _num(p["entry_z"])
        exit_z = _num(p["exit_z"])
        trend_filter = p.get("trend_filter", "NONE")
        lagged_ma200 = cache.rolling("closes", 200, lag=1, statistic="mean") if trend_filter == "MA200_UP_ONLY" else None
        for i in range(n):
            if z[i] is None:
                continue
            trend_ok = True
            if lagged_ma200 is not None:
                if i < 1 or lagged_ma200[i] is None:
                    continue
                trend_ok = float(cache.bars.closes[i - 1]) > lagged_ma200[i]
            available[i] = True
            entry[i] = z[i] <= -entry_z and trend_ok
            exit_[i] = z[i] >= -exit_z or not trend_ok

    elif family == "VOLUME_CONFIRMED_DIRECTION":
        ret = cache.lagged_return(_integer(p["return_lookback"]))
        volume_mean = cache.rolling("base_volume", _integer(p["volume_window"]), lag=1, statistic="mean")
        threshold = _num(p["return_threshold"])
        multiple = _num(p["volume_multiple"])
        for i in range(n):
            if ret[i] is None or volume_mean[i] is None:
                continue
            available[i] = True
            entry[i] = ret[i] > threshold and float(cache.bars.base_volume[i]) > multiple * volume_mean[i]
            exit_[i] = not entry[i]

    elif family == "SESSION_TIME_EFFECT":
        ret = cache.lagged_return(_integer(p["return_lookback"]))
        threshold = _num(p["return_threshold"])
        start = int(_num(p["session_start_utc"]))
        length = _integer(p["session_length_hours"])
        end = start + length
        if not 0 <= start < end <= 24:
            raise MCFError("invalid frozen UTC session")
        for i, timestamp in enumerate(cache.bars.times):
            if ret[i] is None:
                continue
            hour = datetime.fromtimestamp(timestamp / 1000, timezone.utc).hour
            available[i] = True
            entry[i] = start <= hour < end and ret[i] > threshold
            exit_[i] = not entry[i]

    elif family == "LIQUIDITY_CONDITIONED_ENTRY":
        if liquidity_percentile is None or len(liquidity_percentile) != n:
            raise MCFError("liquidity-conditioned family requires bound percentile series")
        ret = cache.lagged_return(_integer(p["signal_lookback"]))
        floor = _num(p["liquidity_rank_floor"])
        for i in range(n):
            rank = liquidity_percentile[i]
            if ret[i] is None or rank is None:
                continue
            available[i] = True
            entry[i] = ret[i] > 0.0 and float(rank) >= floor
            exit_[i] = not entry[i]

    elif family == "LEAD_LAG":
        peer = str(p["peer"])
        lag = _integer(p["lag_bars"])
        threshold = _num(p["peer_return_threshold"])
        mode = str(p["response_mode"])
        if peer == cache.bars.symbol:
            # Frozen family is explicitly for non-peer target symbols.
            return ProductionSeries(
                cache.bars.symbol, cache.bars.timeframe, cache.bars.times,
                cache.bars.opens, cache.bars.closes, (False,) * n, (False,) * n,
            )
        if universe_binding is None:
            raise MCFError("lead-lag family requires point-in-time universe binding")
        universe_binding.validate()
        peer_return = cache.peer_return(peer, lag)
        if mode not in {"MOMENTUM", "REVERSAL"}:
            raise MCFError("invalid lead-lag response mode")
        for i, timestamp in enumerate(cache.bars.times):
            if (
                peer_return[i] is None
                or not universe_binding.is_member(cache.bars.symbol, timestamp)
                or not universe_binding.is_member(peer, timestamp)
            ):
                continue
            available[i] = True
            if mode == "MOMENTUM":
                entry[i] = peer_return[i] > threshold
            else:
                entry[i] = peer_return[i] < -threshold
            exit_[i] = not entry[i]

    elif family == "PRICE_VOLUME_INTERACTION":
        ret = cache.lagged_return(_integer(p["price_lookback"]))
        volume_mean = cache.rolling("base_volume", _integer(p["volume_window"]), lag=1, statistic="mean")
        threshold = _num(p["price_threshold"])
        multiple = _num(p["volume_multiple"])
        for i in range(n):
            if ret[i] is None or volume_mean[i] is None:
                continue
            available[i] = True
            entry[i] = ret[i] > threshold and float(cache.bars.base_volume[i]) > multiple * volume_mean[i]
            exit_[i] = not entry[i]

    elif family == "TRADE_COUNT_CONFIRMED_DIRECTION":
        ret = cache.lagged_return(_integer(p["return_lookback"]))
        count_mean = cache.rolling("trade_count", _integer(p["trade_count_window"]), lag=1, statistic="mean")
        threshold = _num(p["return_threshold"])
        multiple = _num(p["trade_count_multiple"])
        for i in range(n):
            if ret[i] is None or count_mean[i] is None:
                continue
            available[i] = True
            entry[i] = ret[i] > threshold and float(cache.bars.trade_count[i]) > multiple * count_mean[i]
            exit_[i] = not entry[i]

    else:
        raise ProductionRuleBlocked(f"{family}: no exact production rule compiler")

    desired = _state(entry, exit_, available)
    return ProductionSeries(
        cache.bars.symbol,
        cache.bars.timeframe,
        cache.bars.times,
        cache.bars.opens,
        cache.bars.closes,
        desired,
        tuple(available),
    )


def implementation_audit(valid_candidates: Sequence[Mapping[str, object]]) -> dict:
    """Pre-performance family blocker accounting for the canonical generation."""
    counts: dict[str, int] = {}
    for row in valid_candidates:
        counts[str(row["family"])] = counts.get(str(row["family"]), 0) + 1

    blocked = {family: reason for family, reason in BLOCKED_FAMILIES.items() if family in counts}
    executable_counts = {family: count for family, count in counts.items() if family not in blocked}
    total = sum(executable_counts.values())
    if len(executable_counts) < SEARCH_BUDGET["minimum_executable_mechanism_families"]:
        raise MCFError("implementation blockers reduce family breadth below frozen minimum")
    if total <= 0:
        raise MCFError("no executable production candidates")

    max_fraction = max(executable_counts.values()) / total
    trend_fraction = (
        executable_counts.get("TREND_CROSSOVER", 0)
        + executable_counts.get("BREAKOUT_CHANNEL", 0)
    ) / total
    if max_fraction > float(SEARCH_BUDGET["maximum_single_family_fraction"]):
        raise MCFError("implementation blockers violate single-family concentration cap")
    if trend_fraction > float(SEARCH_BUDGET["maximum_combined_trend_breakout_fraction"]):
        raise MCFError("implementation blockers violate trend/breakout concentration cap")

    return {
        "schema": "MCF_PRODUCTION_IMPLEMENTATION_AUDIT/1.0.0",
        "status": "PASS_WITH_IMPLEMENTATION_BLOCKERS" if blocked else "PASS",
        "blocked_families": tuple(sorted(blocked.items())),
        "executable_family_counts": tuple(sorted(executable_counts.items())),
        "executable_candidate_count": total,
        "maximum_single_family_fraction": max_fraction,
        "combined_trend_breakout_fraction": trend_fraction,
        "performance_read": False,
    }
