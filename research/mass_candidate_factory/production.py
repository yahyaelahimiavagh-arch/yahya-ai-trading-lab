"""MCF-03 production Development runner.

This module is separate from the accepted MCF-02 engineering engine. It
implements the frozen MCF-03 v1 accounting and dynamic-universe semantics
without opening Fresh OOS, P10, Futures, leverage, shorting or Live.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from decimal import Decimal, localcontext
from datetime import datetime, timezone
from statistics import median
from typing import Mapping, Sequence

from .models import MCFError, digest

VERSION = "MCF_PRODUCTION/1.0.0"
BINDING_VERSION = "MCF_PRODUCTION_BINDING/1.0.0"
FREEZE_VERSION = "MCF_PRE_OUTCOME_FREEZE/1.0.0"
COST_POLICY_REF = "MCF-SPOT-COST/v1"
UNIVERSE_EVIDENCE_ID = "MCF-PROD-001-UNIVERSE-EVIDENCE"

DAY_MS = 86_400_000
CADENCE_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": DAY_MS}


def _utc_ms(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)


DEVELOPMENT_START_MS = _utc_ms("2020-03-01T00:00:00Z")
DEVELOPMENT_END_MS = _utc_ms("2023-01-01T00:00:00Z")
FOLDS = (
    (_utc_ms("2020-03-01T00:00:00Z"), _utc_ms("2020-09-01T00:00:00Z")),
    (_utc_ms("2020-09-01T00:00:00Z"), _utc_ms("2021-03-01T00:00:00Z")),
    (_utc_ms("2021-03-01T00:00:00Z"), _utc_ms("2021-09-01T00:00:00Z")),
    (_utc_ms("2021-09-01T00:00:00Z"), _utc_ms("2022-03-01T00:00:00Z")),
    (_utc_ms("2022-03-01T00:00:00Z"), _utc_ms("2022-09-01T00:00:00Z")),
    (_utc_ms("2022-09-01T00:00:00Z"), _utc_ms("2023-01-01T00:00:00Z")),
)


def _sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _safe_identity(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    lowered = value.lower()
    return not any(x in lowered for x in ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve", "live"))


@dataclass(frozen=True)
class MembershipSnapshot:
    effective_ms: int
    symbols: tuple[str, ...]
    eligibility_sha256: str

    def validate(self) -> None:
        if self.effective_ms < 0 or not _sha(self.eligibility_sha256):
            raise MCFError("invalid membership snapshot")
        if not self.symbols or tuple(sorted(set(self.symbols))) != self.symbols:
            raise MCFError("membership symbols must be sorted and unique")
        dt = datetime.fromtimestamp(self.effective_ms / 1000, timezone.utc)
        if not (dt.day == 1 and dt.hour == dt.minute == dt.second == dt.microsecond == 0):
            raise MCFError("membership snapshot must be a UTC month boundary")
        if any(not s or not s.endswith("USDT") for s in self.symbols):
            raise MCFError("unadmitted production symbol")


@dataclass(frozen=True)
class ProductionUniverseBinding:
    universe_evidence_id: str
    population_manifest_sha256: str
    quality_index_sha256: str
    universe_policy_sha256: str
    membership_snapshots: tuple[MembershipSnapshot, ...]
    evidence_partition: str = "DEVELOPMENT"

    def validate(self) -> None:
        if self.universe_evidence_id != UNIVERSE_EVIDENCE_ID or self.evidence_partition != "DEVELOPMENT":
            raise MCFError("unbound production universe/evidence partition")
        for value in (self.population_manifest_sha256, self.quality_index_sha256, self.universe_policy_sha256):
            if not _sha(value):
                raise MCFError("invalid universe binding digest")
        if not self.membership_snapshots:
            raise MCFError("missing membership snapshots")
        last = -1
        for snapshot in self.membership_snapshots:
            snapshot.validate()
            if snapshot.effective_ms <= last:
                raise MCFError("nonmonotonic membership snapshots")
            last = snapshot.effective_ms
        if self.membership_snapshots[0].effective_ms > DEVELOPMENT_START_MS:
            raise MCFError("membership history does not cover Development start")

    def symbols_at(self, timestamp_ms: int) -> tuple[str, ...]:
        times = tuple(snapshot.effective_ms for snapshot in self.membership_snapshots)
        index = bisect_right(times, timestamp_ms) - 1
        return () if index < 0 else self.membership_snapshots[index].symbols

    def is_member(self, symbol: str, timestamp_ms: int) -> bool:
        return symbol in self.symbols_at(timestamp_ms)


@dataclass(frozen=True)
class ProductionCostPolicy:
    ref: str = COST_POLICY_REF
    initial_equity: str = "10000"
    target_entry_notional: str = "1000"
    base_fee_bps: str = "10"
    base_slippage_bps: str = "5"
    stress_fee_bps: str = "20"
    stress_slippage_bps: str = "10"

    def validate(self) -> None:
        values = [Decimal(getattr(self, name)) for name in (
            "initial_equity", "target_entry_notional", "base_fee_bps",
            "base_slippage_bps", "stress_fee_bps", "stress_slippage_bps"
        )]
        if self.ref != COST_POLICY_REF or not all(v.is_finite() for v in values):
            raise MCFError("invalid MCF-03 cost policy")
        if values[0] <= 0 or values[1] <= 0 or values[1] > values[0] or any(v < 0 for v in values[2:]):
            raise MCFError("unsafe MCF-03 cost policy")


@dataclass(frozen=True)
class PreOutcomeFreeze:
    batch_id: str
    registered_candidates: tuple[tuple[str, str], ...]
    candidate_ledger_sha256: str
    family_manifest_sha256s: tuple[str, ...]
    neighbor_graph_sha256: str
    evidence_binding_sha256: str
    cost_policy_sha256: str
    version: str = FREEZE_VERSION

    def validate(self) -> None:
        if self.version != FREEZE_VERSION or not _safe_identity(self.batch_id):
            raise MCFError("invalid pre-outcome freeze identity")
        if not self.registered_candidates:
            raise MCFError("empty frozen candidate set")
        ids = [x[0] for x in self.registered_candidates]
        if len(set(ids)) != len(ids) or tuple(sorted(self.registered_candidates)) != self.registered_candidates:
            raise MCFError("candidate freeze must be sorted and unique")
        if any(not _safe_identity(cid) or not _sha(spec) for cid, spec in self.registered_candidates):
            raise MCFError("invalid frozen candidate identity")
        for value in (
            self.candidate_ledger_sha256, self.neighbor_graph_sha256,
            self.evidence_binding_sha256, self.cost_policy_sha256,
        ):
            if not _sha(value):
                raise MCFError("invalid pre-outcome digest")
        if not self.family_manifest_sha256s or tuple(sorted(set(self.family_manifest_sha256s))) != self.family_manifest_sha256s:
            raise MCFError("family manifest freeze must be sorted and unique")
        if any(not _sha(x) for x in self.family_manifest_sha256s):
            raise MCFError("invalid family manifest digest")
        expected = digest([
            {"candidate_id": cid, "candidate_spec_sha256": spec}
            for cid, spec in self.registered_candidates
        ])
        if expected != self.candidate_ledger_sha256:
            raise MCFError("candidate ledger freeze mismatch")

    def require_candidate(self, candidate_id: str, candidate_spec_sha256: str) -> None:
        self.validate()
        if (candidate_id, candidate_spec_sha256) not in self.registered_candidates:
            raise MCFError("candidate not in frozen pre-outcome ledger")


@dataclass(frozen=True)
class FrozenCandidateBinding:
    candidate_id: str
    candidate_spec_sha256: str
    family_id: str
    economic_mechanism_id: str
    family_spec_sha256: str
    parameter_neighbor_ids: tuple[str, ...]
    neighbor_graph_sha256: str
    free_parameter_dimensions: int

    def validate(self, freeze: PreOutcomeFreeze) -> None:
        freeze.require_candidate(self.candidate_id, self.candidate_spec_sha256)
        if not _safe_identity(self.family_id) or not _safe_identity(self.economic_mechanism_id):
            raise MCFError("invalid frozen candidate family identity")
        if not _sha(self.family_spec_sha256) or self.family_spec_sha256 not in freeze.family_manifest_sha256s:
            raise MCFError("candidate family spec not in pre-outcome freeze")
        if not _sha(self.neighbor_graph_sha256) or self.neighbor_graph_sha256 != freeze.neighbor_graph_sha256:
            raise MCFError("candidate neighbor graph binding mismatch")
        if self.free_parameter_dimensions < 0:
            raise MCFError("invalid free parameter dimension count")
        if tuple(sorted(set(self.parameter_neighbor_ids))) != self.parameter_neighbor_ids:
            raise MCFError("parameter neighbors must be sorted and unique")
        if self.candidate_id in self.parameter_neighbor_ids or any(not _safe_identity(x) for x in self.parameter_neighbor_ids):
            raise MCFError("invalid parameter neighbor identity")


@dataclass(frozen=True)
class ProductionSeries:
    symbol: str
    timeframe: str
    times: tuple[int, ...]
    opens: tuple[str | float | int, ...]
    closes: tuple[str | float | int, ...]
    desired_state: tuple[bool, ...]
    feature_available: tuple[bool, ...]

    def validate(self) -> None:
        n = len(self.times)
        if not self.symbol.endswith("USDT") or self.timeframe not in CADENCE_MS or n < 2:
            raise MCFError("invalid production series identity")
        if any(len(x) != n for x in (self.opens, self.closes, self.desired_state, self.feature_available)):
            raise MCFError("production series length mismatch")
        if any(a >= b for a, b in zip(self.times, self.times[1:])):
            raise MCFError("production series must be strictly increasing")
        cadence = CADENCE_MS[self.timeframe]
        if any(t % cadence != 0 for t in self.times):
            raise MCFError("production timestamps must align to timeframe cadence")
        for seq in (self.opens, self.closes):
            vals = [Decimal(str(v)) for v in seq]
            if any(not v.is_finite() or v <= 0 for v in vals):
                raise MCFError("invalid production prices")
        if any(type(v) is not bool for v in self.desired_state + self.feature_available):
            raise MCFError("nonboolean production state")


def freeze_digest(binding: ProductionUniverseBinding, cost: ProductionCostPolicy) -> tuple[str, str]:
    binding.validate()
    cost.validate()
    binding_payload = {
        "version": BINDING_VERSION,
        "universe_evidence_id": binding.universe_evidence_id,
        "population_manifest_sha256": binding.population_manifest_sha256,
        "quality_index_sha256": binding.quality_index_sha256,
        "universe_policy_sha256": binding.universe_policy_sha256,
        "membership_snapshots": [
            {
                "effective_ms": x.effective_ms,
                "symbols": x.symbols,
                "eligibility_sha256": x.eligibility_sha256,
            }
            for x in binding.membership_snapshots
        ],
        "evidence_partition": binding.evidence_partition,
    }
    cost_payload = {
        "ref": cost.ref,
        "initial_equity": cost.initial_equity,
        "target_entry_notional": cost.target_entry_notional,
        "base_fee_bps": cost.base_fee_bps,
        "base_slippage_bps": cost.base_slippage_bps,
        "stress_fee_bps": cost.stress_fee_bps,
        "stress_slippage_bps": cost.stress_slippage_bps,
    }
    return digest(binding_payload), digest(cost_payload)


def _simulate(series: ProductionSeries, binding: ProductionUniverseBinding,
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


def _fold_return(result: Mapping[str, object], start_ms: int, end_ms: int,
                 initial_equity: Decimal) -> Decimal | None:
    marks = [(int(t), Decimal(v)) for t, v in result["marks"]]
    in_fold = [(t, v) for t, v in marks if start_ms <= t < end_ms]
    if not in_fold:
        return None
    prior = [v for t, v in marks if t < start_ms]
    start_equity = prior[-1] if prior else initial_equity
    if start_equity <= 0:
        raise MCFError("nonpositive fold starting equity")
    return in_fold[-1][1] / start_equity - Decimal(1)


def _daily_symbol_returns(result: Mapping[str, object],
                          initial_equity: Decimal) -> dict[int, Decimal | None]:
    """Build true one-calendar-day returns without bridging source gaps."""
    cadence = int(result["cadence_ms"])
    if cadence <= 0 or DAY_MS % cadence != 0:
        raise MCFError("invalid result cadence for daily normalization")
    expected = DAY_MS // cadence
    daily_equity: dict[int, Decimal] = {}
    counts: dict[int, int] = {}
    for timestamp, value in result["marks"]:
        day = int(timestamp) // DAY_MS
        daily_equity[day] = Decimal(value)
        counts[day] = counts.get(day, 0) + 1

    first_day = DEVELOPMENT_START_MS // DAY_MS
    final_day = DEVELOPMENT_END_MS // DAY_MS
    out: dict[int, Decimal | None] = {}
    for day in range(first_day, final_day):
        equity = daily_equity.get(day)
        complete = counts.get(day, 0) == expected
        if equity is None or not complete:
            out[day] = None
            continue
        if day == first_day:
            prior_equity = initial_equity
        else:
            prior_equity = daily_equity.get(day - 1)
            prior_complete = counts.get(day - 1, 0) == expected
            if prior_equity is None or not prior_complete:
                out[day] = None
                continue
        if prior_equity <= 0:
            raise MCFError("nonpositive prior equity in daily normalization")
        out[day] = equity / prior_equity - Decimal(1)
    return out


def _daily_candidate_returns(results: Sequence[Mapping[str, object]],
                             binding: ProductionUniverseBinding,
                             initial_equity: Decimal) -> dict:
    """Equal-weight daily return with explicit invalid source-day masking."""
    by_symbol = {
        str(result["symbol"]): _daily_symbol_returns(result, initial_equity)
        for result in results
    }
    transition_days = {
        str(result["symbol"]): set(int(day) for day in result.get("forced_exit_days", ()))
        for result in results
    }

    first_day = DEVELOPMENT_START_MS // DAY_MS
    final_day = DEVELOPMENT_END_MS // DAY_MS
    calendar_days = tuple(range(first_day, final_day))
    returns: list[str | None] = []
    valid: list[bool] = []

    for day in calendar_days:
        members = set(binding.symbols_at(day * DAY_MS))
        transition = {
            symbol for symbol, days in transition_days.items()
            if day in days and symbol not in members
        }
        active = sorted(members | transition)
        values = [
            by_symbol.get(symbol, {}).get(day)
            for symbol in active
        ]
        if not active or any(value is None for value in values):
            returns.append(None)
            valid.append(False)
            continue
        returns.append(str(sum(values, Decimal(0)) / Decimal(len(values))))
        valid.append(True)

    return {
        "calendar_days": calendar_days,
        "returns": tuple(returns),
        "valid_mask": tuple(valid),
    }


def _daily_per_symbol_returns(results: Sequence[Mapping[str, object]],
                              initial_equity: Decimal) -> tuple[dict, ...]:
    first_day = DEVELOPMENT_START_MS // DAY_MS
    final_day = DEVELOPMENT_END_MS // DAY_MS
    calendar = tuple(range(first_day, final_day))
    artifacts = []
    for result in results:
        daily = _daily_symbol_returns(result, initial_equity)
        returns = tuple(None if daily[day] is None else str(daily[day]) for day in calendar)
        valid = tuple(daily[day] is not None for day in calendar)
        artifacts.append({
            "symbol": result["symbol"],
            "calendar_days": calendar,
            "returns": returns,
            "valid_mask": valid,
        })
    return tuple(sorted(artifacts, key=lambda x: x["symbol"]))


def run_candidate(*, candidate: FrozenCandidateBinding,
                  freeze: PreOutcomeFreeze, binding: ProductionUniverseBinding,
                  series_by_symbol: Mapping[str, ProductionSeries],
                  cost_policy: ProductionCostPolicy | None = None) -> dict:
    """Run one frozen candidate on Development only."""
    policy = cost_policy or ProductionCostPolicy()
    candidate.validate(freeze)
    binding.validate()
    policy.validate()
    binding_sha, cost_sha = freeze_digest(binding, policy)
    if binding_sha != freeze.evidence_binding_sha256 or cost_sha != freeze.cost_policy_sha256:
        raise MCFError("runtime binding differs from frozen pre-outcome evidence")

    universe_symbols = sorted({s for snap in binding.membership_snapshots for s in snap.symbols})
    if set(series_by_symbol) - set(universe_symbols):
        raise MCFError("series contains symbol outside frozen universe")

    base_results = []
    stress_results = []
    missing_symbols = []
    for symbol in universe_symbols:
        series = series_by_symbol.get(symbol)
        if series is None:
            missing_symbols.append(symbol)
            continue
        if series.symbol != symbol:
            raise MCFError("series map/symbol mismatch")
        base_results.append(_simulate(series, binding, policy, stress=False))
        stress_results.append(_simulate(series, binding, policy, stress=True))

    base_eval = [x for x in base_results if x["evaluable"]]
    stress_eval = [x for x in stress_results if x["evaluable"]]
    if [x["symbol"] for x in base_eval] != [x["symbol"] for x in stress_eval]:
        raise MCFError("base/stress evaluable universe mismatch")

    evaluable_symbols = len(base_eval)
    total_trades = sum(int(x["completed_trades"]) for x in base_eval)
    symbols_5_trades = sum(int(x["completed_trades"]) >= 5 for x in base_eval)
    base_returns = [Decimal(x["net_return"]) for x in base_eval]
    stress_returns = [Decimal(x["net_return"]) for x in stress_eval]
    initial = Decimal(policy.initial_equity)

    fold_base = []
    fold_stress = []
    for start, end in FOLDS:
        br = [_fold_return(x, start, end, initial) for x in base_eval]
        sr = [_fold_return(x, start, end, initial) for x in stress_eval]
        br = [x for x in br if x is not None]
        sr = [x for x in sr if x is not None]
        fold_base.append(None if not br else str(sum(br, Decimal(0)) / Decimal(len(br))))
        fold_stress.append(None if not sr else str(sum(sr, Decimal(0)) / Decimal(len(sr))))

    failures = []
    if evaluable_symbols < 15:
        failures.append("F1_EVALUABLE_SYMBOLS_LT_15")
    if total_trades < 250:
        failures.append("F1_COMPLETED_TRADES_LT_250")
    if symbols_5_trades < 10:
        failures.append("F1_SYMBOLS_WITH_5_TRADES_LT_10")

    base_aggregate = sum(base_returns, Decimal(0)) / Decimal(len(base_returns)) if base_returns else Decimal(0)
    stress_aggregate = sum(stress_returns, Decimal(0)) / Decimal(len(stress_returns)) if stress_returns else Decimal(0)
    base_median = median(base_returns) if base_returns else Decimal(0)
    stress_median = median(stress_returns) if stress_returns else Decimal(0)
    stress_positive_fraction = (
        Decimal(sum(x > 0 for x in stress_returns)) / Decimal(len(stress_returns))
        if stress_returns else Decimal(0)
    )
    if base_aggregate <= 0:
        failures.append("F2_AGGREGATE_BASE_NOT_POSITIVE")
    if stress_aggregate <= 0:
        failures.append("F2_AGGREGATE_STRESS_NOT_POSITIVE")
    if base_median <= 0:
        failures.append("F2_MEDIAN_SYMBOL_BASE_NOT_POSITIVE")
    if stress_median <= 0:
        failures.append("F2_MEDIAN_SYMBOL_STRESS_NOT_POSITIVE")
    if stress_positive_fraction < Decimal("0.60"):
        failures.append("F2_STRESS_POSITIVE_SYMBOL_FRACTION_LT_0_60")

    base_positive_folds = sum(x is not None and Decimal(x) > 0 for x in fold_base)
    stress_positive_folds = sum(x is not None and Decimal(x) > 0 for x in fold_stress)
    if base_positive_folds < 5:
        failures.append("F3_BASE_POSITIVE_FOLDS_LT_5")
    if stress_positive_folds < 4:
        failures.append("F3_STRESS_POSITIVE_FOLDS_LT_4")
    if any(x is None for x in fold_base + fold_stress):
        failures.append("F3_MISSING_FOLD")

    exposure = [Decimal(x["exposure_coverage"]) for x in base_eval]
    turnover = [Decimal(x["turnover"]) for x in base_eval]
    max_dd = [Decimal(x["maximum_drawdown_fraction"]) for x in base_eval]
    daily = _daily_candidate_returns(base_eval, binding, initial)

    result = {
        "schema": VERSION,
        "candidate_id": candidate.candidate_id,
        "candidate_spec_sha256": candidate.candidate_spec_sha256,
        "family_id": candidate.family_id,
        "economic_mechanism_id": candidate.economic_mechanism_id,
        "family_spec_sha256": candidate.family_spec_sha256,
        "parameter_neighbor_ids": candidate.parameter_neighbor_ids,
        "neighbor_graph_sha256": candidate.neighbor_graph_sha256,
        "free_parameter_dimensions": candidate.free_parameter_dimensions,
        "batch_id": freeze.batch_id,
        "evidence_partition": "DEVELOPMENT",
        "accounting_engine": "MCF_PRODUCTION_DECIMAL/1.0.0",
        "exact_accounting": True,
        "development_start_ms": DEVELOPMENT_START_MS,
        "development_end_ms": DEVELOPMENT_END_MS,
        "evaluable_symbol_count": evaluable_symbols,
        "missing_symbol_series": tuple(missing_symbols),
        "completed_trades": total_trades,
        "symbols_with_5_completed_trades": symbols_5_trades,
        "aggregate_base_net_return": str(base_aggregate),
        "aggregate_stress_net_return": str(stress_aggregate),
        "median_symbol_base_net_return": str(base_median),
        "median_symbol_stress_net_return": str(stress_median),
        "stress_positive_symbol_fraction": str(stress_positive_fraction),
        "mean_exposure_coverage": str(sum(exposure, Decimal(0)) / Decimal(len(exposure)) if exposure else Decimal(0)),
        "mean_turnover": str(sum(turnover, Decimal(0)) / Decimal(len(turnover)) if turnover else Decimal(0)),
        "maximum_normalized_drawdown": str(max(max_dd) if max_dd else Decimal(0)),
        "fold_base_returns": tuple(fold_base),
        "fold_stress_returns": tuple(fold_stress),
        "base_positive_fold_count": base_positive_folds,
        "stress_positive_fold_count": stress_positive_folds,
        "per_symbol_base": tuple(base_eval),
        "per_symbol_stress": tuple(stress_eval),
        "daily_return_series": daily,
        "per_symbol_daily_return_series": _daily_per_symbol_returns(base_eval, initial),
        "f0_f3_state": "F0_F3_PASS" if not failures else "DEVELOPMENT_FAIL",
        "failure_reasons": tuple(sorted(set(failures))),
        "safety": {
            "paper_research_only": True,
            "p10_read": False,
            "p10_write": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "futures": False,
            "leverage": False,
            "short": False,
            "live": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
            "p11_locked": True,
        },
    }
    return {**result, "result_sha256": digest(result)}
