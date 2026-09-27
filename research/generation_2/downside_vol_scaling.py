"""GEN2-003 source-style monthly volatility scalers; research-only Development runner.

The only registered trials are control, total volatility, and downside volatility.
No market data is loaded during protocol validation or unit-level computations.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from functools import wraps
from pathlib import Path
from typing import Mapping, Sequence

from research.crisis_lab import controls
from research.generation_2 import vol_scaling as shared
from research.historical_strategy_search import survivor_ranking as hsse3
from research.historical_strategy_search import trend_ma as hsse2
from yatl.backtest.costs import DECIMAL_PRECISION

IMPLEMENTATION_ID = "GEN2-003-DOWNSIDE-VOL-SCALING/0.1.0"
PROTOCOL_SHA256 = "2821e5dbcbdbb503ba7e68627ef3eeee1454f9ee268d5af2a5cc564954d5c3bc"
DEFAULT_PROTOCOL_PATH = shared.REPO_ROOT / "docs/research/generation-2/GEN2-003-DOWNSIDE-VOL-SCALING-PROTOCOL-v0.1.0.json"
CONDITIONS = ("CONTROL_UNSCALED", "SOURCE_STYLE_TOTAL_VOL_SCALED_NO_LEVERAGE", "SOURCE_STYLE_DOWNSIDE_VOL_SCALED_NO_LEVERAGE")
ONE = Decimal(1)
ZERO = Decimal(0)


class Gen2DownsideError(RuntimeError):
    """Frozen research boundary or deterministic calculation was violated."""


def _exact(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            return fn(*args, **kwargs)
    return wrapper


def validate_protocol(path: Path = DEFAULT_PROTOCOL_PATH):
    target = path.resolve()
    if not target.is_relative_to(shared.REPO_ROOT.resolve()) or target.is_symlink():
        raise Gen2DownsideError("unsafe protocol path")
    try:
        payload = target.read_bytes()
    except OSError:
        raise Gen2DownsideError("protocol unreadable") from None
    digest = shared._sha256(payload)
    # Entire preregistration is immutable: this binds every field, including gates.
    if digest != PROTOCOL_SHA256:
        raise Gen2DownsideError("GEN2-003 frozen protocol SHA-256 mismatch")
    p = json.loads(payload)
    if (p["protocol_id"] != "GEN2-003-DOWNSIDE-VOL-SCALING-001"
        or p["source_candidate_id"] != "RIE-CAND-0027"
        or p["tested_object_id"] != "GEN2-ADAPT-0003-DOWNSIDE-VOL-SCALING"
        or p["trial_matrix"]["conditions"] != list(CONDITIONS)
        or p["trial_matrix"]["total_conditions"] != 18
        or p["p10_read"] is not False or p["p10_write_allowed"] is not False
        or p["p11_locked"] is not True or p["live_master_lock"] != "OFF"):
        raise Gen2DownsideError("GEN2-003 identity/safety mismatch")
    bound = {}
    for label in ("method_extraction", "survivor_freeze", "gen2_master_protocol", "hsse_search_protocol"):
        try:
            bound[label], _ = shared._read_repo_bound(p["bindings"][label], label)
        except shared.Gen2VolError as exc:
            raise Gen2DownsideError(str(exc)) from None
    freeze = bound["survivor_freeze"]
    if ([s["frozen_id"] for s in freeze["survivors"]] != p["reference_strategies"]["frozen_ids"]
        or len(freeze["survivors"]) != 6
        or bound["method_extraction"]["candidate_id"] != "RIE-CAND-0027"
        or bound["method_extraction"]["performance_run_allowed"] is not False
        or bound["gen2_master_protocol"]["protocol_id"] != "GEN2-MASTER-001"
        or bound["hsse_search_protocol"]["protocol_id"] != "HSSE-001-SEARCH-PROTOCOL"):
        raise Gen2DownsideError("bound source/freeze identity mismatch")
    return p, digest, freeze


def _next_month(ms: int) -> int:
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return int(datetime(dt.year + (dt.month == 12), dt.month % 12 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


@_exact
def _monthly_inputs(*, exact: hsse3.ExactSeries, positions: Sequence[int], start_ms: int, end_ms: int):
    """Complete UTC days only. Any exposed gap poisons its day and whole month."""
    if len(exact.times) != len(positions):
        raise Gen2DownsideError("control positions length mismatch")
    daily = shared._daily_control_returns(exact=exact, positions=positions, warmup_start_ms=start_ms)
    exposed_days = set()
    # A missing bar at timestamp t is exposed when the last observable prior state
    # is long; no return across the gap is synthesized.
    for i in range(1, len(exact.times)):
        prev, now = exact.times[i - 1], exact.times[i]
        if now <= start_ms or prev < start_ms or prev >= end_ms or now == prev + shared.HOUR_MS:
            continue
        if positions[i - 1]:
            for t in range(prev + shared.HOUR_MS, min(now, end_ms - 1) + 1, shared.HOUR_MS):
                exposed_days.add((t // shared.DAY_MS) * shared.DAY_MS)
    months = {}
    for boundary in shared._month_boundaries(start_ms, end_ms):
        finish = _next_month(boundary)
        days = list(range(boundary, finish, shared.DAY_MS))
        valid = all(d in daily for d in days) and not any(d in exposed_days for d in days)
        if valid:
            with localcontext() as ctx:
                ctx.prec = DECIMAL_PRECISION
                compounded = ONE
                for d in days:
                    compounded *= ONE + daily[d]
                f = compounded - ONE
            months[boundary] = (f, [daily[d] for d in days])
        else:
            months[boundary] = None
    return months, len(exposed_days)


@_exact
def _estimators(months: Mapping[int, tuple[Decimal, list[Decimal]] | None]):
    total, down = {}, {}
    keys = sorted(months)
    for index, month in enumerate(keys):
        item = months[month]
        if item is None:
            total[month] = down[month] = None
            continue
        returns = item[1]
        negatives = [r for r in returns if r < ZERO]
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            tsum = sum((r*r for r in returns), ZERO)
            total[month] = tsum.sqrt() if tsum > ZERO else None
            if len(negatives) < 3 and index:
                prior = months[keys[index - 1]]
                if prior is None:
                    down[month] = None
                    continue
                negatives += [r for r in prior[1] if r < ZERO]
            elif len(negatives) < 3:
                # Prior month is outside registered warmup; never invent it.
                down[month] = None
                continue
            dsum = sum((r*r for r in negatives), ZERO)
            down[month] = dsum.sqrt() if dsum > ZERO else None
    return {"total": total, "downside": down}


def _population_stdev(values: Sequence[Decimal]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        mean = sum(values, ZERO) / Decimal(len(values))
        variance = sum(((x - mean)**2 for x in values), ZERO) / Decimal(len(values))
        return variance.sqrt()


@_exact
def _schedule(*, months, estimators, first_managed_ms: int, scored_start_ms: int, end_ms: int, minimum_pairs: int = 6):
    """Expanding, lagged paired f/z samples; unavailable months carry only scale."""
    schedules, counters = {}, {}
    for variant in ("total", "downside"):
        sigma = estimators[variant]
        pairs = []
        scale = ONE
        decisions = {}
        counts = {"valid_new_scale_decisions": 0, "carried_scale_decisions": 0,
                  "unavailable_estimator_months": 0, "unavailable_training_constant_months": 0}
        for t in shared._month_boundaries(first_managed_ms, end_ms):
            prior = shared._month_start_ms(t - 1)
            # The previous month enters training at t, never before it has closed.
            if prior >= first_managed_ms and months.get(prior) is not None:
                before = shared._month_start_ms(prior - 1)
                if sigma.get(before) is not None:
                    with localcontext() as ctx:
                        ctx.prec = DECIMAL_PRECISION
                        f = months[prior][0]
                        pairs.append((f, f / sigma[before]))
            if t < scored_start_ms:
                continue
            current_sigma = sigma.get(prior)
            unavailable_est = current_sigma is None
            constant = None
            if len(pairs) >= minimum_pairs:
                fs, zs = zip(*pairs)
                denominator = _population_stdev(zs)
                if denominator > ZERO:
                    with localcontext() as ctx:
                        ctx.prec = DECIMAL_PRECISION
                        constant = _population_stdev(fs) / denominator
            unavailable_constant = constant is None
            if unavailable_est:
                counts["unavailable_estimator_months"] += 1
            if unavailable_constant:
                counts["unavailable_training_constant_months"] += 1
            fresh = not unavailable_est and not unavailable_constant
            if fresh:
                with localcontext() as ctx:
                    ctx.prec = DECIMAL_PRECISION
                    scale = min(ONE, constant / current_sigma)
                counts["valid_new_scale_decisions"] += 1
            else:
                counts["carried_scale_decisions"] += 1
            if not scale.is_finite() or scale < ZERO or scale > ONE:
                raise Gen2DownsideError("invalid no-leverage scale")
            decisions[t] = {"scale": scale, "new": fresh}
        schedules[variant], counters[variant] = decisions, counts
    return schedules, counters


@_exact
def _simulate_cell(*, signal, exact, short_values, long_values, start_ms, end_ms, policy, decisions, condition):
    """Use frozen crossover and shared exact-Decimal accounts; rebalances are deltas."""
    if signal.times != exact.times:
        raise Gen2DownsideError("signal/exact timestamps differ")
    start, end = bisect.bisect_left(exact.times, start_ms), bisect.bisect_left(exact.times, end_ms)
    if start >= end:
        raise Gen2DownsideError("empty scored cell")
    scaled = condition != CONDITIONS[0]
    quantity = Decimal(policy["base_quantity"])
    initial = Decimal(policy["initial_equity_quote"])
    bf, bs = Decimal(policy["base_fee_bps"]), Decimal(policy["base_adverse_slippage_bps"])
    sf, ss = Decimal(policy["stress_fee_bps"]), Decimal(policy["stress_adverse_slippage_bps"])
    base, stress = shared._new_account(initial), shared._new_account(initial)
    month = shared._month_start_ms(exact.times[start])
    current = decisions[month]["scale"] if scaled else ONE
    logical = False
    peak, drawdown = initial, ZERO
    entries = signals = completed = rebalances = scaled_entries = missing = 0
    active_hours = 0
    exposure = turnover_delta = ZERO
    scales = []
    pending = None
    for i in range(start, end):
        t = exact.times[i]
        close = Decimal(exact.closes[i])
        equity = shared._equity(base, mark=close, fee_bps=bf, slippage_bps=bs)
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak - equity)/peak)
            if logical:
                active_hours += 1
                scales.append(current)
                exposure += base.quantity * close
        if i == 0:
            continue
        vals = (short_values[i], long_values[i], short_values[i-1], long_values[i-1])
        enter = exit_ = False
        if all(math.isfinite(v) for v in vals):
            sn, ln, sp, lp = vals
            enter = not logical and sn > ln and sp <= lp
            exit_ = logical and sn < ln and sp >= lp
            signals += int(enter)
        # Decision timestamp is the UTC boundary. The first eligible fill is
        # strictly later at the next contiguous open, as for frozen crossovers.
        boundary = scaled and t in decisions and decisions[t]["new"]
        newscale = decisions[t]["scale"] if boundary else current
        if boundary and logical and newscale != current:
            pending = newscale
        if not (enter or exit_ or pending is not None):
            if boundary:
                current = newscale
            continue
        fi = i + 1
        if fi >= end:
            missing += 1
            continue
        if fi >= len(exact.times) or exact.times[fi] != t + shared.HOUR_MS:
            raise Gen2DownsideError("required execution fill bar missing; event invalidated")
        price = Decimal(exact.opens[fi])
        if exit_:
            shared._sell(base, reference=price, quantity=base.quantity, fee_bps=bf, slippage_bps=bs, close_cycle=True)
            shared._sell(stress, reference=price, quantity=stress.quantity, fee_bps=sf, slippage_bps=ss, close_cycle=True)
            logical = False
            completed += 1
            pending = None
        elif enter:
            target = quantity * newscale
            shared._buy(base, reference=price, quantity=target, fee_bps=bf, slippage_bps=bs, start_cycle=True)
            shared._buy(stress, reference=price, quantity=target, fee_bps=sf, slippage_bps=ss, start_cycle=True)
            logical = True
            entries += 1
            scaled_entries += int(newscale < ONE)
            pending = None
        elif pending is not None:
            delta = quantity * pending - base.quantity
            if delta > ZERO:
                shared._buy(base, reference=price, quantity=delta, fee_bps=bf, slippage_bps=bs, start_cycle=False)
                shared._buy(stress, reference=price, quantity=delta, fee_bps=sf, slippage_bps=ss, start_cycle=False)
            elif delta < ZERO:
                shared._sell(base, reference=price, quantity=-delta, fee_bps=bf, slippage_bps=bs, close_cycle=False)
                shared._sell(stress, reference=price, quantity=-delta, fee_bps=sf, slippage_bps=ss, close_cycle=False)
            if delta:
                rebalances += 1
                turnover_delta += abs(delta) * price
            pending = None
        if boundary:
            current = newscale
    last = Decimal(exact.closes[end-1])
    base_net = shared._equity(base, mark=last, fee_bps=bf, slippage_bps=bs) - initial
    stress_net = shared._equity(stress, mark=last, fee_bps=sf, slippage_bps=ss) - initial
    drawdown = max(drawdown, (peak - (base_net + initial))/peak)
    gp = hsse3._sum([x for x in base.realized if x > ZERO])
    gl = -hsse3._sum([x for x in base.realized if x < ZERO])
    pf, infinite, _ = hsse3._profit_factor(gp, gl)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        expectancy = hsse3._sum(base.realized) / Decimal(completed) if completed else ZERO
    return {"base_net":base_net, "stress_net":stress_net, "drawdown":drawdown,
            "completed_trades":completed, "entry_signals":signals, "entry_fills":entries,
            "missing_fill_events":missing, "rebalances":rebalances, "rebalance_notional":turnover_delta,
            "scaled_entries":scaled_entries, "active_hours":active_hours, "notional_exposure":exposure,
            "mean_scale":hsse3._sum(scales)/Decimal(len(scales)) if scales else ONE,
            "median_scale":hsse3._median_decimal(scales) if scales else ONE,
            "minimum_scale":min(scales) if scales else ONE,
            "expectancy":expectancy, "profit_factor":pf, "profit_factor_infinite":infinite,
            "gross_profit":gp, "gross_loss":gl,
            "active_scale_observations":scales}


def _finite(value: object) -> bool:
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(_finite(v) for v in value)
    return True


@_exact
def _summary(cells, survivor, condition, decision_counts, exposed_gap_days):
    all_scales = [v for c in cells for v in c.pop("active_scale_observations")]
    completed = sum(c["completed_trades"] for c in cells)
    net = hsse3._sum([c["base_net"] for c in cells])
    stress = hsse3._sum([c["stress_net"] for c in cells])
    active = sum(c["active_hours"] for c in cells)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        expectancy = hsse3._sum([c["expectancy"] * c["completed_trades"] for c in cells]) / Decimal(completed) if completed else ZERO
        fraction = (Decimal(decision_counts["valid_new_scale_decisions"]) /
                    Decimal(decision_counts["valid_new_scale_decisions"]+decision_counts["carried_scale_decisions"])) if decision_counts and (decision_counts["valid_new_scale_decisions"]+decision_counts["carried_scale_decisions"]) else ONE
        mean = hsse3._sum([c["mean_scale"] * c["active_hours"] for c in cells]) / Decimal(active) if active else ONE
    groupings = {}
    for dimension in ("fold_id", "symbol"):
        keys = list(dict.fromkeys(c[dimension] for c in cells))
        groupings[dimension] = [{dimension:key,
            "base_net":hsse3._sum([c["base_net"] for c in cells if c[dimension] == key]),
            "stress_net":hsse3._sum([c["stress_net"] for c in cells if c[dimension] == key]),
            "completed_trades":sum(c["completed_trades"] for c in cells if c[dimension] == key),
            "maximum_drawdown":max(c["drawdown"] for c in cells if c[dimension] == key)} for key in keys]
    return {"frozen_id":survivor["frozen_id"], "family":survivor["family"],
            "parameters":survivor["parameters"], "condition":condition,
            "base_net":net,"stress_net":stress,"maximum_drawdown":max(c["drawdown"] for c in cells),
            "completed_trades":completed,"entry_signals":sum(c["entry_signals"] for c in cells),
            "monthly_rebalance_count":sum(c["rebalances"] for c in cells),
            "total_rebalance_notional":hsse3._sum([c["rebalance_notional"] for c in cells]),
            "scaled_entry_count":sum(c["scaled_entries"] for c in cells),
            "active_hours":active,"notional_exposure":hsse3._sum([c["notional_exposure"] for c in cells]),
            "mean_active_scale":mean,"median_active_scale":hsse3._median_decimal(all_scales) if all_scales else ONE,
            "minimum_active_scale":min(c["minimum_scale"] for c in cells),
            "expectancy_base":expectancy,
            "profit_factor_base":hsse3._profit_factor(hsse3._sum([c["gross_profit"] for c in cells]),
                                                    hsse3._sum([c["gross_loss"] for c in cells]))[0],
            "profit_factor_infinite":hsse3._profit_factor(hsse3._sum([c["gross_profit"] for c in cells]),
                                                        hsse3._sum([c["gross_loss"] for c in cells]))[1],
            "valid_new_scale_decision_fraction":fraction,
            "valid_new_scale_decisions":decision_counts.get("valid_new_scale_decisions",0),
            "carried_scale_decisions":decision_counts.get("carried_scale_decisions",0),
            "unavailable_estimator_months":decision_counts.get("unavailable_estimator_months",0),
            "unavailable_training_constant_months":decision_counts.get("unavailable_training_constant_months",0),
            "exposed_gap_days":exposed_gap_days,
            "per_fold_metrics":groupings["fold_id"],"per_symbol_metrics":groupings["symbol"],
            "cells":cells}


@_exact
def _adjudicate(rows, protocol):
    """Exactly six triples; every registered gate yields a stable failure reason."""
    if len(rows) != 18:
        raise Gen2DownsideError("registered trial matrix incomplete")
    groups = {}
    for row in rows:
        groups.setdefault(row["frozen_id"], {})[row["condition"]] = row
    if len(groups) != 6 or any(set(g) != set(CONDITIONS) for g in groups.values()):
        raise Gen2DownsideError("unregistered or missing condition")
    comparison = []
    failures = []
    aggregate = {k: {"base":ZERO,"stress":ZERO} for k in CONDITIONS}
    base_deltas, stress_deltas, dd_deltas = [], [], []
    activated = events = nonworse = 0
    for fid in [x["frozen_id"] for x in rows[::3]]:
        control, total, down = (groups[fid][k] for k in CONDITIONS)
        for row in (control,total,down):
            aggregate[row["condition"]]["base"] += row["base_net"]
            aggregate[row["condition"]]["stress"] += row["stress_net"]
        base_deltas.append(down["base_net"]-control["base_net"])
        stress_deltas.append(down["stress_net"]-control["stress_net"])
        dd_deltas.append(down["maximum_drawdown"]-control["maximum_drawdown"])
        nonworse += int(down["maximum_drawdown"] <= control["maximum_drawdown"])
        activated += int(down["minimum_active_scale"] < ONE)
        events += down["scaled_entry_count"]+down["monthly_rebalance_count"]
        for scaled in (total,down):
            with localcontext() as ctx:
                ctx.prec = DECIMAL_PRECISION
                active_ratio = Decimal(scaled["active_hours"])/Decimal(control["active_hours"]) if control["active_hours"] else ONE
                notional_ratio = scaled["notional_exposure"]/control["notional_exposure"] if control["notional_exposure"] else ONE
            scaled["active_exposure_hours_fraction_vs_control"] = active_ratio
            scaled["notional_exposure_ratio_vs_control"] = notional_ratio
            reasons = []
            if scaled["entry_signals"] != control["entry_signals"]: reasons.append("DIRECTIONAL_ENTRY_SIGNAL_COUNT_CHANGED")
            if scaled["completed_trades"] != control["completed_trades"]: reasons.append("COMPLETED_DIRECTIONAL_TRADE_COUNT_CHANGED")
            if active_ratio < ONE: reasons.append("ACTIVE_EXPOSURE_HOURS_STARVED")
            if notional_ratio < Decimal("0.25"): reasons.append("NOTIONAL_EXPOSURE_STARVED")
            if scaled["valid_new_scale_decision_fraction"] < Decimal("0.50"): reasons.append("VALID_SCALE_DECISION_FRACTION_LOW")
            comparison.append({"frozen_id":fid,"condition":scaled["condition"],"base_delta_vs_control":scaled["base_net"]-control["base_net"],
                               "stress_delta_vs_control":scaled["stress_net"]-control["stress_net"],
                               "drawdown_delta_vs_control":scaled["maximum_drawdown"]-control["maximum_drawdown"],
                               "base_delta_vs_total":scaled["base_net"]-total["base_net"],
                               "stress_delta_vs_total":scaled["stress_net"]-total["stress_net"],
                               "opportunity_failure_reasons":reasons})
            if scaled is down and reasons: failures.append("OPPORTUNITY_PRESERVATION_FAILED:"+fid)
    g = protocol["proposal_gate"]
    c, t, d = (aggregate[k] for k in CONDITIONS)
    median_base = hsse3._median_decimal(base_deltas)
    median_stress = hsse3._median_decimal(stress_deltas)
    median_dd = hsse3._median_decimal(dd_deltas)
    checks = (
        (activated >= g["minimum_reference_strategies_with_downside_scale_below_one"],"DOWNSIDE_ACTIVATION_REFERENCE_COUNT"),
        (events >= g["minimum_downside_scaled_entry_or_rebalance_events_total"],"DOWNSIDE_ACTIVATION_EVENT_COUNT"),
        (d["base"] > ZERO,"AGGREGATE_DOWNSIDE_BASE_NOT_POSITIVE"),
        (d["stress"] > ZERO,"AGGREGATE_DOWNSIDE_STRESS_NOT_POSITIVE"),
        (d["base"] > c["base"],"DOWNSIDE_BASE_NOT_ABOVE_CONTROL"),
        (d["stress"] > c["stress"],"DOWNSIDE_STRESS_NOT_ABOVE_CONTROL"),
        (d["base"] > t["base"],"DOWNSIDE_BASE_NOT_ABOVE_TOTAL"),
        (d["stress"] > t["stress"],"DOWNSIDE_STRESS_NOT_ABOVE_TOTAL"),
        (median_base > ZERO,"MEDIAN_BASE_DELTA_NOT_POSITIVE"),
        (median_stress > ZERO,"MEDIAN_STRESS_DELTA_NOT_POSITIVE"),
        (median_dd < ZERO,"MEDIAN_DRAWDOWN_DELTA_NOT_NEGATIVE"),
        (nonworse >= g["at_least_reference_strategies_with_nonworse_drawdown_vs_control"],"NONWORSE_DRAWDOWN_REFERENCE_COUNT"),
        (_finite(rows) and _finite(comparison) and _finite(aggregate)
         and not any(c["profit_factor_infinite"] for row in rows for c in row["cells"]),"NONFINITE_METRIC"),
    )
    failures.extend(reason for ok,reason in checks if not ok)
    return {"status":"PASS" if not failures else "FAIL", "failure_reasons":failures,
            "proposal_count":0 if failures else 1,
            "aggregate":aggregate,"median_base_delta":median_base,"median_stress_delta":median_stress,
            "median_drawdown_delta":median_dd,"activated_references":activated,
            "scaled_entry_or_rebalance_events":events,"nonworse_drawdown_references":nonworse,
            "comparisons":comparison}


def _serialize(value):
    if isinstance(value, Decimal):
        return shared._plain(value)
    if isinstance(value, dict):
        return {k:_serialize(v) for k,v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def run(*, runtime_root: Path, protocol_path: Path = DEFAULT_PROTOCOL_PATH):
    """Explicitly authorized Development entrypoint; never called from tests."""
    p, digest, freeze = validate_protocol(protocol_path)
    q = p["bindings"]["development_quality_manifest"]
    try:
        corpus = controls._load_control_corpus(runtime_root=runtime_root,
            quality_manifest_relative_path=q["relative_path"], quality_manifest_file_sha256=q["file_sha256"])
    except controls.ControlError as exc:
        raise Gen2DownsideError(str(exc)) from None
    if corpus.event_id != p["development_scope"]["corpus_id"]:
        raise Gen2DownsideError("Development corpus identity mismatch")
    signals, exacts = {}, {}
    for symbol in ("BTCUSDT","ETHUSDT"):
        signals[symbol], exacts[symbol] = shared._series(corpus,symbol)
    scope = p["development_scope"]
    start = shared._time_ms(scope["estimator_warmup_start_utc"],"warmup")
    scored = shared._time_ms(scope["scored_analysis_start_utc"],"scored")
    end = shared._time_ms(scope["analysis_end_exclusive_utc"],"end")
    first = shared._time_ms(p["expanding_scale_normalization"]["first_historical_managed_month"],"first managed")
    cache, rows = {}, []
    for survivor in freeze["survivors"]:
        family = survivor["family"]
        n1,n2 = survivor["parameters"]["n1"], survivor["parameters"]["n2"]
        cells_by_condition = {k:[] for k in CONDITIONS}
        counters = {k:{"valid_new_scale_decisions":0,"carried_scale_decisions":0,
                       "unavailable_estimator_months":0,"unavailable_training_constant_months":0} for k in CONDITIONS}
        gaps = 0
        for symbol in ("BTCUSDT","ETHUSDT"):
            signal, exact = signals[symbol], exacts[symbol]
            for window in (n1,n2):
                key = symbol,family,window
                if key not in cache:
                    cache[key] = hsse2._indicator_series(signal,family,window)
            short,long = cache[symbol,family,n1],cache[symbol,family,n2]
            positions = shared._control_positions(signal=signal,short_values=short,long_values=long,reset_ms=start)
            months, exposed = _monthly_inputs(exact=exact,positions=positions,start_ms=start,end_ms=end)
            gaps += exposed
            schedules, counts = _schedule(months=months,estimators=_estimators(months),
                                          first_managed_ms=first,scored_start_ms=scored,end_ms=end,
                                          minimum_pairs=p["expanding_scale_normalization"]["minimum_valid_training_pairs"])
            for variant, condition in (("total",CONDITIONS[1]),("downside",CONDITIONS[2])):
                for key in counts[variant]: counters[condition][key] += counts[variant][key]
            for variant in ("total", "downside"):
                for boundary, decision in schedules[variant].items():
                    if not decision["new"]:
                        continue
                    j = bisect.bisect_left(exact.times, boundary)
                    if j >= len(exact.times) or exact.times[j] != boundary:
                        # A new scale while exposed requires a real contiguous
                        # boundary bar and the next open, never a synthetic fill.
                        if j and positions[j - 1]:
                            raise Gen2DownsideError("required month-boundary execution bar missing")
            for fold in scope["development_folds"]:
                a = shared._time_ms(fold["evaluation_start_utc"],"fold start")
                b = shared._time_ms(fold["evaluation_end_exclusive_utc"],"fold end")
                for condition in CONDITIONS:
                    variant = "total" if condition == CONDITIONS[1] else "downside"
                    decisions = schedules[variant] if condition != CONDITIONS[0] else {}
                    cell = _simulate_cell(signal=signal,exact=exact,short_values=short,long_values=long,
                                          start_ms=a,end_ms=b,policy=p["execution"],decisions=decisions,condition=condition)
                    cell["fold_id"],cell["symbol"] = fold["fold_id"],symbol
                    cells_by_condition[condition].append(cell)
        for condition in CONDITIONS:
            rows.append(_summary(cells_by_condition[condition],survivor,condition,counters[condition],gaps))
    verdict = _adjudicate(rows,p)
    record = {"schema":"YATL_GEN2_DOWNSIDE_VOL_SCALING_RESULT","implementation_id":IMPLEMENTATION_ID,
              "protocol_id":p["protocol_id"],"protocol_sha256":digest,
              "development_corpus_id":scope["corpus_id"],"condition_count":18,
              "reference_strategies":rows,"verdict":verdict,"performance_outcome_computed":True,
              "fresh_oos_read":False,"recent_reserve_read":False,"p10_read":False,"p10_write":False,
              "research_only":True,"p11_locked":True,"live_master_lock":"OFF"}
    safe = runtime_root.resolve()
    if safe.is_symlink(): raise Gen2DownsideError("unsafe runtime root")
    output = safe / "generation-2" / "gen2-003"
    output.mkdir(parents=True,exist_ok=True)
    payload = shared._canonical_json(_serialize(record))
    sha = shared._sha256(payload)
    path = output / ("downside-vol-scaling-"+sha[:24]+".json")
    if path.exists():
        if path.read_bytes() != payload: raise Gen2DownsideError("artifact collision")
    else:
        import os
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as file:
            file.write(payload);file.flush();os.fsync(file.fileno())
    return {"implementation_id":IMPLEMENTATION_ID,"protocol_sha256":digest,
            "status":verdict["status"],"failure_reasons":verdict["failure_reasons"],
            "condition_count":18,"artifact_relative_path":path.relative_to(safe).as_posix(),
            "artifact_file_sha256":sha,"fresh_oos_read":False,"recent_reserve_read":False,
            "p10_read":False,"p10_write":False,"p11_locked":True}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root",type=Path)
    parser.add_argument("--protocol",type=Path,default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--validate-protocol-only",action="store_true")
    args = parser.parse_args(argv)
    if args.validate_protocol_only:
        p, sha, freeze = validate_protocol(args.protocol)
        print(shared._json({"implementation_id":IMPLEMENTATION_ID,"protocol_id":p["protocol_id"],
                            "protocol_sha256":sha,"survivor_count":len(freeze["survivors"]),
                            "condition_count":18,"performance_run_executed":False,"p10_read":False}))
        return 0
    if args.runtime_root is None:
        parser.error("--runtime-root required for explicitly authorized run")
    print(shared._json(run(runtime_root=args.runtime_root,protocol_path=args.protocol)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
