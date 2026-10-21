"""Byte-preserved PR186 _simulate reference for synthetic-only replay parity.

Source: production.py at merge commit 026489f5ae1790d6661ab302c77aa8308422e34b.
NEVER import this module from production or use it for real Development data.
"""
from __future__ import annotations

from bisect import bisect_right
from decimal import Decimal, localcontext
from research.mass_candidate_factory.production import (
    CADENCE_MS, DAY_MS, DEVELOPMENT_START_MS, DEVELOPMENT_END_MS,
    ProductionSeries, ProductionUniverseBinding, ProductionCostPolicy,
)


def baseline_simulate(series: ProductionSeries, binding: ProductionUniverseBinding,
              policy: ProductionCostPolicy, *, stress: bool) -> dict:
    series.validate()
    binding.validate()
    policy.validate()
    cadence = CADENCE_MS[series.timeframe]
    initial = Decimal(policy.initial_equity)
    target = Decimal(policy.target_entry_notional)
    fee = Decimal(policy.stress_fee_bps if stress else policy.base_fee_bps) / Decimal(10_000)
    slip = Decimal(policy.stress_slippage_bps if stress else policy.base_slippage_bps) / Decimal(10_000)

    with localcontext() as ctx:
        ctx.prec = 34
        cash = initial
        qty: Decimal | None = None
        peak = initial
        max_dd = Decimal(0)
        completed_trades = fills = failed_entries = 0
        exposure_bars = evaluable_bars = 0
        source_gap_cancellations = forced_membership_exits = 0
        forced_exit_days: list[int] = []
        turnover_notional = Decimal(0)
        marks: list[tuple[int, Decimal]] = []
        member_marks: list[tuple[int, Decimal]] = []

        scored = [i for i, t in enumerate(series.times) if DEVELOPMENT_START_MS <= t < DEVELOPMENT_END_MS]
        if not scored:
            return {
                "symbol": series.symbol, "evaluable": False, "completed_trades": 0,
                "fills": 0, "failed_entries": 0, "turnover": "0",
                "exposure_coverage": "0", "maximum_drawdown_fraction": "0",
                "net_return": "0", "source_gap_cancellations": 0,
                "forced_membership_exits": 0, "forced_exit_days": (),
                "timeframe": series.timeframe, "cadence_ms": cadence,
                "marks": (), "member_marks": (),
            }

        previous_scored: int | None = None
        previous_member = False
        snapshot_times = tuple(x.effective_ms for x in binding.membership_snapshots)
        snapshot_symbols = tuple(x.symbols for x in binding.membership_snapshots)

        def member_at(timestamp_ms: int) -> bool:
            index = bisect_right(snapshot_times, timestamp_ms) - 1
            return index >= 0 and series.symbol in snapshot_symbols[index]

        def left_membership_between(start_ms: int, end_ms: int) -> bool:
            """Detect any member->nonmember boundary between observed bars."""
            start_index = bisect_right(snapshot_times, start_ms) - 1
            end_index = bisect_right(snapshot_times, end_ms) - 1
            if start_index < 0 or end_index <= start_index:
                return False
            state = series.symbol in snapshot_symbols[start_index]
            for index in range(start_index + 1, end_index + 1):
                next_state = series.symbol in snapshot_symbols[index]
                if state and not next_state:
                    return True
                state = next_state
            return False

        for i in scored:
            t = series.times[i]
            current_member = member_at(t)
            held_before = qty is not None

            left_since_previous = (
                held_before
                and previous_scored is not None
                and left_membership_between(series.times[previous_scored], t)
            )
            if left_since_previous:
                ref = Decimal(str(series.opens[i]))
                exec_price = ref * (Decimal(1) - slip)
                gross = qty * exec_price
                cash += gross - gross * fee
                turnover_notional += gross
                qty = None
                fills += 1
                completed_trades += 1
                forced_membership_exits += 1
                forced_exit_days.append(t // DAY_MS)
            elif previous_scored is not None:
                j = previous_scored
                immediate = series.times[i] == series.times[j] + cadence
                if not immediate:
                    if series.feature_available[j] and (
                        (qty is None and series.desired_state[j] and previous_member)
                        or (qty is not None and not series.desired_state[j])
                    ):
                        source_gap_cancellations += 1
                elif series.feature_available[j]:
                    target_held = series.desired_state[j]
                    if qty is not None and not target_held:
                        ref = Decimal(str(series.opens[i]))
                        exec_price = ref * (Decimal(1) - slip)
                        gross = qty * exec_price
                        cash += gross - gross * fee
                        turnover_notional += gross
                        qty = None
                        fills += 1
                        completed_trades += 1
                    elif qty is None and target_held and previous_member and current_member:
                        ref = Decimal(str(series.opens[i]))
                        candidate_qty = target / ref
                        exec_price = ref * (Decimal(1) + slip)
                        gross = candidate_qty * exec_price
                        debit = gross + gross * fee
                        if debit > cash:
                            failed_entries += 1
                        else:
                            cash -= debit
                            turnover_notional += gross
                            qty = candidate_qty
                            fills += 1

            close = Decimal(str(series.closes[i]))
            if qty is None:
                equity = cash
            else:
                liquidation = qty * close * (Decimal(1) - slip)
                equity = cash + liquidation * (Decimal(1) - fee)
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
            marks.append((t, equity))

            if current_member or held_before:
                member_marks.append((t, equity))
                evaluable_bars += 1
                if qty is not None:
                    exposure_bars += 1

            previous_scored = i
            previous_member = current_member

        final_equity = marks[-1][1]
        return {
            "symbol": series.symbol,
            "evaluable": bool(member_marks),
            "completed_trades": completed_trades,
            "fills": fills,
            "failed_entries": failed_entries,
            "turnover": str(turnover_notional / initial),
            "exposure_coverage": str(Decimal(exposure_bars) / Decimal(evaluable_bars) if evaluable_bars else Decimal(0)),
            "maximum_drawdown_fraction": str(max_dd),
            "net_return": str(final_equity / initial - Decimal(1)),
            "source_gap_cancellations": source_gap_cancellations,
            "forced_membership_exits": forced_membership_exits,
            "forced_exit_days": tuple(sorted(set(forced_exit_days))),
            "timeframe": series.timeframe,
            "cadence_ms": cadence,
            "marks": tuple((t, str(v)) for t, v in marks),
            "member_marks": tuple((t, str(v)) for t, v in member_marks),
        }


