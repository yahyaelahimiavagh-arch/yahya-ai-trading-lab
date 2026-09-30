"""Canonical MCF-03 runtime wiring frozen candidates to production accounting."""
from __future__ import annotations

from typing import Mapping
from types import MappingProxyType

from .models import MCFError
from .production import (
    FrozenCandidateBinding,
    PreOutcomeFreeze,
    ProductionCostPolicy,
    ProductionUniverseBinding,
    freeze_digest,
    run_candidate,
)
from .production_features import ProductionBars, ProductionFeatureCache, liquidity_percentiles
from .production_rules import compile_candidate


def make_preoutcome_freeze(executable_freeze: Mapping[str, object],
                           binding: ProductionUniverseBinding,
                           cost_policy: ProductionCostPolicy | None = None) -> PreOutcomeFreeze:
    policy = cost_policy or ProductionCostPolicy()
    binding_sha, cost_sha = freeze_digest(binding, policy)
    summary = executable_freeze.get("summary")
    if not isinstance(summary, Mapping) or summary.get("state") != "PRE_OUTCOME_EXECUTABLE_SET_FROZEN":
        raise MCFError("executable generation is not frozen")
    registered = tuple(executable_freeze.get("registered_candidates", ()))
    if not registered or summary.get("candidate_ledger_sha256") is None:
        raise MCFError("missing frozen executable candidate ledger")
    neighbor = executable_freeze.get("neighbor_graph")
    if not isinstance(neighbor, Mapping):
        raise MCFError("missing frozen production neighbor graph")
    if neighbor.get("neighbor_graph_sha256") != summary.get("neighbor_graph_sha256"):
        raise MCFError("neighbor graph/freeze identity mismatch")

    freeze = PreOutcomeFreeze(
        batch_id="MCF-PROD-001",
        registered_candidates=registered,
        candidate_ledger_sha256=str(summary["candidate_ledger_sha256"]),
        family_manifest_sha256s=tuple(summary["family_spec_sha256s"]),
        neighbor_graph_sha256=str(summary["neighbor_graph_sha256"]),
        evidence_binding_sha256=binding_sha,
        cost_policy_sha256=cost_sha,
    )
    freeze.validate()
    return freeze


class ProductionRuntime:
    """Reusable cache layer for one frozen universe/evidence binding."""

    def __init__(self, *, executable_freeze: Mapping[str, object],
                 binding: ProductionUniverseBinding,
                 bars_by_timeframe: Mapping[str, Mapping[str, ProductionBars]],
                 cost_policy: ProductionCostPolicy | None = None,
                 frozen_input=None, synthetic_fixture: bool = False):
        from .production_runner_input import FrozenRunnerInput
        self._frozen_input = frozen_input
        if frozen_input is None:
            if (not synthetic_fixture or not bars_by_timeframe
                    or any(not b.dataset_id.startswith("SYNTHETIC-")
                           for items in bars_by_timeframe.values() for b in items.values())
                    or len(executable_freeze.get("registered_candidates", ())) != 1
                    or executable_freeze.get("summary", {}).get("freeze_sha256") is not None):
                raise MCFError("production runtime requires frozen runner input; raw data is forbidden")
        elif not isinstance(frozen_input, FrozenRunnerInput) or bars_by_timeframe or synthetic_fixture:
            raise MCFError("frozen runtime cannot accept replacement bars or synthetic mode")
        self.binding = binding
        self.binding.validate()
        self.cost_policy = cost_policy or ProductionCostPolicy()
        self.cost_policy.validate()
        if frozen_input is not None:
            frozen_input.require_runtime(executable_freeze, binding, self.cost_policy)
        self.executable_freeze = executable_freeze
        self.freeze = make_preoutcome_freeze(executable_freeze, binding, self.cost_policy)
        self._candidates = {
            str(row["candidate_id"]): row
            for row in executable_freeze.get("executable", ())
        }
        if len(self._candidates) != len(self.freeze.registered_candidates):
            raise MCFError("runtime executable candidate inventory mismatch")
        self._neighbor_graph = executable_freeze["neighbor_graph"]["graph"]
        self._bars = {
            timeframe: dict(symbols)
            for timeframe, symbols in bars_by_timeframe.items()
        }
        universe = {s for snapshot in binding.membership_snapshots for s in snapshot.symbols}
        for timeframe, items in self._bars.items():
            if timeframe not in ("15m", "1h", "4h") or set(items) - universe:
                raise MCFError("runtime raw matrix contains unregistered symbol/timeframe")
        self._caches: dict[str, dict[str, ProductionFeatureCache]] = {}
        self._liquidity: dict[tuple[str, int], dict[str, tuple[float | None, ...]]] = {}

    @classmethod
    def from_frozen_input(cls, frozen_input):
        from .production_generator import freeze_executable_generation
        from .production_rules import BLOCKED_FAMILIES
        return cls(executable_freeze=freeze_executable_generation(BLOCKED_FAMILIES),
                   binding=frozen_input.binding, bars_by_timeframe={},
                   cost_policy=frozen_input.cost_policy, frozen_input=frozen_input)

    def _timeframe_caches(self, timeframe: str) -> dict[str, ProductionFeatureCache]:
        if timeframe in self._caches:
            return self._caches[timeframe]
        if self._frozen_input is not None:
            if self._bars:
                raise MCFError("external bars cannot replace frozen runtime data")
            bars = self._frozen_input.load_timeframe(timeframe)
        else:
            bars = self._bars.get(timeframe, {})
        universe_symbols = {
            symbol
            for snapshot in self.binding.membership_snapshots
            for symbol in snapshot.symbols
        }
        admitted = {
            symbol: item
            for symbol, item in bars.items()
            if symbol in universe_symbols
        }
        for symbol, item in admitted.items():
            item.validate()
            if item.symbol != symbol or item.timeframe != timeframe:
                raise MCFError("runtime bars map identity mismatch")
        caches = {
            symbol: ProductionFeatureCache(
                item,
                {
                    peer_symbol: peer
                    for peer_symbol, peer in admitted.items()
                    if peer_symbol in {"BTCUSDT", "ETHUSDT"} and peer_symbol != symbol
                },
            )
            for symbol, item in admitted.items()
        }
        self._caches[timeframe] = MappingProxyType(caches)
        return self._caches[timeframe]

    def _liquidity_percentiles(self, timeframe: str, window: int):
        key = (timeframe, window)
        if key not in self._liquidity:
            caches = self._timeframe_caches(timeframe)
            self._liquidity[key] = liquidity_percentiles(caches, window, self.binding)
        return self._liquidity[key]

    def release_transient_features(self) -> None:
        """Bound long-run RSS by discarding candidate-derived feature matrices."""
        for caches in self._caches.values():
            for cache in caches.values():
                cache.clear_transient()
        self._liquidity.clear()

    def candidate_binding(self, candidate: Mapping[str, object]) -> FrozenCandidateBinding:
        cid = str(candidate["candidate_id"])
        neighbors = tuple(self._neighbor_graph[cid])
        return FrozenCandidateBinding(
            candidate_id=cid,
            candidate_spec_sha256=str(candidate["candidate_spec_sha256"]),
            family_id=str(candidate["family_id"]),
            economic_mechanism_id=str(candidate["economic_mechanism_id"]),
            family_spec_sha256=str(candidate["family_spec_sha256"]),
            parameter_neighbor_ids=neighbors,
            neighbor_graph_sha256=str(self.executable_freeze["summary"]["neighbor_graph_sha256"]),
            free_parameter_dimensions=int(candidate["free_parameter_dimensions"]),
        )

    def run(self, candidate_id: str, *, director_authorized: bool = False) -> dict:
        if self._frozen_input is not None:
            if director_authorized is not True:
                raise MCFError("Director performance authorization required after input freeze")
            self._frozen_input.require_runtime(self.executable_freeze, self.binding, self.cost_policy)
            if self._bars:
                raise MCFError("runtime data outside frozen input")
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise MCFError("candidate not in frozen executable generation")
        timeframe = str(candidate["timeframe"])
        caches = self._timeframe_caches(timeframe)
        percentile = None
        if candidate["family"] == "LIQUIDITY_CONDITIONED_ENTRY":
            window = int(candidate["parameter_vector"]["liquidity_window"])
            percentile = self._liquidity_percentiles(timeframe, window)

        series = {}
        for symbol, cache in caches.items():
            series[symbol] = compile_candidate(
                candidate,
                cache,
                liquidity_percentile=None if percentile is None else percentile[symbol],
                universe_binding=self.binding,
            )

        return run_candidate(
            candidate=self.candidate_binding(candidate),
            freeze=self.freeze,
            binding=self.binding,
            series_by_symbol=series,
            cost_policy=self.cost_policy,
        )
