"""Deterministic historical universe index and narrow MCF data-query bridge."""
from __future__ import annotations

from dataclasses import dataclass

from .eligibility import Eligibility, UniversePolicy, check
from .lifecycle import Lifecycle
from .liquidity import Liquidity
from .models import AdmittedDataset, BLOCKED, CADENCE_MS, OpportunityError, SUPPORTED, digest
from .quality import GapMap, verify_quality


@dataclass(frozen=True)
class UniverseIndex:
    records: tuple[Lifecycle, ...]
    datasets: tuple[AdmittedDataset, ...]
    quality_refs: tuple[tuple[str, str], ...]
    index_sha256: str

    def payload(self) -> dict:
        return dict(version="AF-01B-INDEX/1.0.0",
                    records=tuple(r.payload() | {"record_sha256": r.record_sha256} for r in self.records),
                    datasets=tuple(dict(dataset_id=d.dataset_id, symbol=d.symbol, interval=d.interval,
                                        first_ms=d.rows[0].open_time_ms, last_ms=d.rows[-1].open_time_ms,
                                        row_count=len(d.rows), content_sha256=d.content_sha256,
                                        quality_sha256=d.quality_sha256, gap_sha256=d.gap_sha256,
                                        quality_verdict=d.quality_verdict) for d in self.datasets),
                    quality_refs=self.quality_refs)

    def symbol(self, symbol: str, t_ms: int) -> dict | None:
        return next((r.snapshot_at(t_ms) for r in self.records if r.symbol == symbol
                     and any(d.symbol == symbol and any(bar.close_time_ms < t_ms for bar in d.rows)
                             for d in self.datasets)), None)

    def symbols_at(self, t_ms: int) -> tuple[str, ...]:
        return tuple(r.symbol for r in self.records if self.symbol(r.symbol, t_ms) is not None)

    def intervals_at(self, symbol: str, t_ms: int) -> tuple[str, ...]:
        if self.symbol(symbol, t_ms) is None:
            return ()
        return tuple(sorted({d.interval for d in self.datasets if d.symbol == symbol
                             and any(r.close_time_ms < t_ms for r in d.rows)}))

    def dependency_available(self, symbol: str, t_ms: int, dependency: str,
                             *, companions: tuple[str, ...] = ()) -> bool:
        if dependency not in SUPPORTED | BLOCKED:
            raise OpportunityError("unknown dependency")
        if dependency in BLOCKED or not self.intervals_at(symbol, t_ms):
            return False
        if dependency == "MULTI_ASSET":
            return bool(companions) and all(s != symbol and self.intervals_at(s, t_ms) for s in companions)
        return True

    def mcf_data_binding(self, symbol: str, t_ms: int, policy: UniversePolicy,
                         *, companions: tuple[str, ...] = ()) -> dict:
        """Read-only versioned bridge; does not authorize an MCF manifest or selection."""
        eligibility = self.eligibility(symbol, t_ms, policy, companions=companions)
        data = tuple(d for d in self.datasets if d.symbol == symbol and d.interval in policy.required_intervals)
        payload = dict(version="AF-01B-MCF-BINDING/1.0.0", universe_policy_ref=policy.ref,
                       universe_policy_sha256=policy.policy_sha256, symbol=symbol,
                       timestamp_ms=t_ms, evidence_partition="DEVELOPMENT",
                       dataset_identities=tuple(sorted(d.dataset_id for d in data)),
                       quality_identities=tuple(sorted(d.quality_sha256 for d in data)),
                       symbol_eligible=eligibility.production_research_eligible,
                       dependency_availability={dep: self.dependency_available(
                           symbol, t_ms, dep, companions=companions)
                           for dep in policy.required_dependencies},
                       eligibility_sha256=eligibility.identity_sha256)
        return payload | {"binding_sha256": digest(payload)}

    def liquidity_available(self, metric: Liquidity, t_ms: int) -> bool:
        return (metric.ending_ms == t_ms and metric.metric_sha256 == digest(metric.payload())
                and any(d.dataset_id == metric.dataset_id and d.symbol == metric.symbol for d in self.datasets)
                and metric.symbol in self.symbols_at(t_ms))

    def eligibility(self, symbol: str, t_ms: int, policy: UniversePolicy,
                    *, liquidity: Liquidity | None = None,
                    companions: tuple[str, ...] = ()) -> Eligibility:
        record = next((r for r in self.records if r.symbol == symbol), None)
        if record is None:
            raise OpportunityError("unregistered symbol")
        data = tuple(d for d in self.datasets if d.symbol == symbol)
        companion_data = tuple(d for d in self.datasets if d.symbol in companions and d.symbol != symbol)
        if ("MULTI_ASSET" in policy.required_dependencies
                and not self.dependency_available(symbol, t_ms, "MULTI_ASSET", companions=companions)):
            companion_data = ()
        return check(record, data, policy, t_ms, liquidity=liquidity, companion=companion_data)


def build_index(records: tuple[Lifecycle, ...], bindings: tuple[tuple[AdmittedDataset, GapMap, dict], ...]) -> UniverseIndex:
    if len({r.symbol for r in records}) != len(records):
        raise OpportunityError("duplicate lifecycle symbol")
    for r in records:
        r.validate()
    data = []
    for dataset, gaps, manifest in bindings:
        verify_quality(dataset, manifest, gaps)
        record = next((r for r in records if r.symbol == dataset.symbol), None)
        if record is None or dataset.venue != record.venue:
            raise OpportunityError("dataset not in lifecycle")
        if dataset.rows[0].open_time_ms < record.first_admitted_data_ms or dataset.rows[-1].open_time_ms > record.last_admitted_data_ms:
            raise OpportunityError("dataset outside lifecycle range")
        data.append(dataset)
    if len({d.dataset_id for d in data}) != len(data) or len({(d.symbol, d.interval) for d in data}) != len(data):
        raise OpportunityError("duplicate dataset identity/interval")
    ordered = UniverseIndex(tuple(sorted(records, key=lambda r: r.symbol)),
                            tuple(sorted(data, key=lambda d: (d.symbol, CADENCE_MS[d.interval]))),
                            tuple(sorted((d.dataset_id, d.quality_sha256) for d in data)), "")
    return UniverseIndex(ordered.records, ordered.datasets, ordered.quality_refs, digest(ordered.payload()))
