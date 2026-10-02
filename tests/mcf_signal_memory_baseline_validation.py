"""Test-only accepted-main ProductionSeries validator; synthetic input only."""
from decimal import Decimal
from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production import CADENCE_MS

def legacy_series_validate(self) -> None:
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
