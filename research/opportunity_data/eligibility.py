"""Frozen policy input and historical eligibility, without selection/ranking."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .lifecycle import Lifecycle
from .liquidity import Liquidity
from .models import AdmittedDataset, BLOCKED, CADENCE_MS, OpportunityError, SUPPORTED, digest


@dataclass(frozen=True)
class UniversePolicy:
    ref: str
    quote_asset: str
    required_intervals: tuple[str, ...]
    required_dependencies: tuple[str, ...]
    warmup_bars: int
    maximum_gap_rate: str | None = None
    minimum_trailing_quote_volume: str | None = None
    liquidity_window_bars: int | None = None
    policy_sha256: str = ""

    def payload(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "policy_sha256"}

    def frozen(self) -> UniversePolicy:
        from dataclasses import replace
        self.validate(check_digest=False)
        return replace(self, policy_sha256=digest(self.payload()))

    def validate(self, *, check_digest: bool = True) -> None:
        if not self.ref.endswith("/v1") or not self.quote_asset or not self.required_intervals:
            raise OpportunityError("unversioned/empty policy")
        if any(i not in CADENCE_MS for i in self.required_intervals) or self.warmup_bars < 0:
            raise OpportunityError("invalid policy interval/warmup")
        if any(dep not in SUPPORTED | BLOCKED for dep in self.required_dependencies):
            raise OpportunityError("unknown data dependency")
        if self.liquidity_window_bars is not None and self.liquidity_window_bars <= 0:
            raise OpportunityError("invalid liquidity window")
        for value in (self.maximum_gap_rate, self.minimum_trailing_quote_volume):
            if value is not None:
                try:
                    x = Decimal(value)
                except (InvalidOperation, TypeError):
                    raise OpportunityError("invalid threshold") from None
                if not x.is_finite() or x < 0:
                    raise OpportunityError("invalid threshold")
        if self.maximum_gap_rate is not None and Decimal(self.maximum_gap_rate) > 1:
            raise OpportunityError("gap rate > 1")
        if self.minimum_trailing_quote_volume is not None and self.liquidity_window_bars is None:
            raise OpportunityError("unbound liquidity window")
        if check_digest and self.policy_sha256 != digest(self.payload()):
            raise OpportunityError("policy digest mismatch")


@dataclass(frozen=True)
class Eligibility:
    symbol: str
    timestamp_ms: int
    policy_sha256: str
    data_admitted: bool
    production_research_eligible: bool
    reasons: tuple[str, ...]
    identity_sha256: str


def check(lifecycle: Lifecycle, datasets: tuple[AdmittedDataset, ...], policy: UniversePolicy,
          t_ms: int, *, liquidity: Liquidity | None = None,
          companion: tuple[AdmittedDataset, ...] = ()) -> Eligibility:
    lifecycle.validate(); policy.validate()
    if t_ms < 0:
        raise OpportunityError("negative timestamp")
    reasons: list[str] = []
    if not lifecycle.existed_at(t_ms):
        reasons.append("NOT_HISTORICALLY_KNOWN")
    if lifecycle.quote_asset != policy.quote_asset:
        reasons.append("QUOTE_MISMATCH")
    valid = {}
    for dataset in datasets:
        dataset.validate_binding()
        if dataset.symbol != lifecycle.symbol:
            raise OpportunityError("foreign dataset in symbol query")
        if dataset.quality_verdict not in {"PASS_CONTIGUOUS", "PASS_WITH_GAPS"}:
            continue
        valid[dataset.interval] = dataset
    admitted = any(r.close_time_ms < t_ms for d in valid.values() for r in d.rows)
    for interval in policy.required_intervals:
        data = valid.get(interval)
        if data is None:
            reasons.append("MISSING_INTERVAL:" + interval)
            continue
        cadence = CADENCE_MS[interval]
        window_start = (t_ms // cadence - policy.warmup_bars) * cadence
        history = [r for r in data.rows if r.close_time_ms < t_ms
                   and r.open_time_ms >= window_start]
        latest_expected_open = (t_ms // cadence) * cadence - cadence
        if latest_expected_open < 0 or not any(r.open_time_ms == latest_expected_open for r in data.rows):
            reasons.append("STALE_INTERVAL:" + interval)
        if len(history) < policy.warmup_bars:
            reasons.append("INSUFFICIENT_HISTORY:" + interval)
        if policy.maximum_gap_rate is not None and policy.warmup_bars:
            rate = Decimal(policy.warmup_bars - min(len(history), policy.warmup_bars)) / policy.warmup_bars
            if rate > Decimal(policy.maximum_gap_rate):
                reasons.append("GAP_RATE:" + interval)
    for dep in policy.required_dependencies:
        if dep in BLOCKED:
            reasons.append("BLOCKED_DEPENDENCY:" + dep)
        elif dep == "MULTI_ASSET":
            if not companion:
                reasons.append("MISSING_MULTI_ASSET")
            else:
                by_symbol: dict[str, dict[str, AdmittedDataset]] = {}
                for c in companion:
                    c.validate_binding()
                    if c.venue != lifecycle.venue:
                        reasons.append("MISSING_MULTI_ASSET")
                        by_symbol = {}
                        break
                    by_symbol.setdefault(c.symbol, {})[c.interval] = c
                for symbol_data in by_symbol.values():
                    for interval in policy.required_intervals:
                        c = symbol_data.get(interval)
                        if c is None:
                            reasons.append("MISSING_MULTI_ASSET")
                            break
                        cadence = CADENCE_MS[interval]
                        latest_expected_open = (t_ms // cadence) * cadence - cadence
                        window_start = (t_ms // cadence - policy.warmup_bars) * cadence
                        history = [r for r in c.rows if r.close_time_ms < t_ms
                                   and r.open_time_ms >= window_start]
                        if (latest_expected_open < 0
                                or not any(r.open_time_ms == latest_expected_open for r in c.rows)
                                or len(history) < policy.warmup_bars):
                            reasons.append("MISSING_MULTI_ASSET")
                            break
                if not by_symbol:
                    reasons.append("MISSING_MULTI_ASSET")
        elif not valid:
            reasons.append("MISSING_DEPENDENCY:" + dep)
    if policy.minimum_trailing_quote_volume is not None:
        if (liquidity is None or liquidity.symbol != lifecycle.symbol
                or liquidity.dataset_id not in {d.dataset_id for d in valid.values()}
                or liquidity.ending_ms != t_ms or liquidity.window_bars != policy.liquidity_window_bars
                or liquidity.metric_sha256 != digest(liquidity.payload())):
            reasons.append("UNBOUND_LIQUIDITY")
        elif Decimal(liquidity.trailing_quote_volume) < Decimal(policy.minimum_trailing_quote_volume):
            reasons.append("INSUFFICIENT_LIQUIDITY")
    payload = dict(symbol=lifecycle.symbol, timestamp_ms=t_ms, policy_sha256=policy.policy_sha256,
                   data_admitted=admitted, production_research_eligible=admitted and not reasons,
                   reasons=tuple(sorted(set(reasons))))
    return Eligibility(**payload, identity_sha256=digest(payload))
