"""Historical instruments, separate from current exchange listing state."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .models import OpportunityError, digest


@dataclass(frozen=True)
class Lifecycle:
    symbol: str
    base_asset: str
    quote_asset: str
    venue: str
    instrument_type: str
    spot_allowed: bool
    leveraged_token_flag: bool
    first_admitted_data_ms: int
    last_admitted_data_ms: int
    listing_time_ms: int | None
    delisting_time_ms: int | None
    lifecycle_status: str
    lifecycle_source_refs: tuple[str, ...]
    record_sha256: str = ""
    predecessor_symbol: str | None = None
    successor_symbol: str | None = None
    migration_ref: str | None = None

    def payload(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "record_sha256"}

    def frozen(self) -> Lifecycle:
        self.validate(check_digest=False)
        return replace(self, record_sha256=digest(self.payload()))

    def validate(self, *, check_digest: bool = True) -> None:
        if not self.symbol or not self.base_asset or not self.quote_asset or self.venue != "BINANCE_SPOT":
            raise OpportunityError("invalid instrument identity")
        if self.instrument_type != "SPOT" or not self.spot_allowed or self.leveraged_token_flag:
            raise OpportunityError("nonordinary Spot instrument")
        if self.first_admitted_data_ms < 0 or self.last_admitted_data_ms < self.first_admitted_data_ms:
            raise OpportunityError("invalid admitted history")
        if self.listing_time_ms is not None and self.listing_time_ms > self.first_admitted_data_ms:
            raise OpportunityError("listing after first admitted data")
        if self.delisting_time_ms is not None and self.delisting_time_ms <= self.last_admitted_data_ms:
            raise OpportunityError("data at/after delisting")
        if self.lifecycle_status not in {"ACTIVE", "INACTIVE", "DELISTED", "UNKNOWN"} or not self.lifecycle_source_refs:
            raise OpportunityError("unbound lifecycle provenance")
        if check_digest and self.record_sha256 != digest(self.payload()):
            raise OpportunityError("lifecycle digest mismatch")

    def snapshot_at(self, t_ms: int) -> dict | None:
        """Only reveal future status/delisting once its timestamp has arrived."""
        if not self.existed_at(t_ms):
            return None
        return dict(symbol=self.symbol, base_asset=self.base_asset, quote_asset=self.quote_asset,
                    venue=self.venue, instrument_type=self.instrument_type,
                    first_admitted_data_ms=self.first_admitted_data_ms,
                    listing_time_ms=self.listing_time_ms,
                    delisting_time_ms=None, lifecycle_status="HISTORICALLY_ADMITTED",
                    predecessor_symbol=None, successor_symbol=None, migration_ref=None)

    def existed_at(self, t_ms: int) -> bool:
        self.validate()
        # Unknown listing is never inferred from the first bar as an official listing.
        return (t_ms >= self.first_admitted_data_ms
                and (self.listing_time_ms is None or t_ms >= self.listing_time_ms)
                and (self.delisting_time_ms is None or t_ms < self.delisting_time_ms))
