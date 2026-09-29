"""Deterministic MCF-04 orchestration from F0-F3 Development passers."""
from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from .adjudication import (
    BOOTSTRAP_BLOCK_DAYS,
    BOOTSTRAP_REPLICATIONS,
    BOOTSTRAP_SEED,
    DailySeries,
    TrialAccounting,
    common_factor_clusters,
    cscv_pbo,
    effective_trial_count,
    neighbor_stability,
    reality_check,
    select_representative,
    statistical_gate,
)
from .models import MCFError, digest

VERSION = "MCF_ADJUDICATION_RUNNER/1.0.0"
SAFETY = {
    "paper_research_only": True,
    "fresh_oos_read": False,
    "recent_reserve_read": False,
    "p10_read": False,
    "p10_write": False,
    "live": False,
    "p11_locked": True,
}


def _valid_result(result: Mapping[str, object]) -> bool:
    if "result_sha256" not in result:
        return False
    body = {k: v for k, v in result.items() if k != "result_sha256"}
    return result["result_sha256"] == digest(body)


def daily_series_from_result(result: Mapping[str, object]) -> DailySeries:
    if not _valid_result(result):
        raise MCFError("invalid MCF-03 result digest")
    daily = result.get("daily_return_series")
    if not isinstance(daily, Mapping):
        raise MCFError("missing MCF-03 daily return series")
    series = DailySeries(
        candidate_id=str(result["candidate_id"]),
        family_id=str(result["family_id"]),
        mechanism_id=str(result["economic_mechanism_id"]),
        calendar_days=tuple(int(x) for x in daily["calendar_days"]),
        returns=tuple(None if x is None else float(x) for x in daily["returns"]),
        valid_mask=tuple(daily["valid_mask"]),
    )
    series.validate()
    return series


def _validate_neighbor_graph(artifact: Mapping[str, object], expected_ids: set[str]) -> Mapping[str, Sequence[str]]:
    if artifact.get("schema") != "MCF_PRODUCTION_NEIGHBOR_GRAPH/1.0.0":
        raise MCFError("wrong production neighbor graph schema")
    graph = artifact.get("graph")
    if not isinstance(graph, Mapping) or set(graph) != expected_ids:
        raise MCFError("production neighbor graph candidate set mismatch")
    body = {"schema": artifact["schema"], "graph": graph}
    if artifact.get("neighbor_graph_sha256") != digest(body):
        raise MCFError("production neighbor graph digest mismatch")
    for cid, neighbors in graph.items():
        if tuple(sorted(set(neighbors))) != tuple(neighbors):
            raise MCFError("noncanonical production neighbor list")
        if cid in neighbors or any(n not in expected_ids for n in neighbors):
            raise MCFError("invalid production neighbor identity")
    return graph


def adjudicate(*, production_results: Sequence[Mapping[str, object]],
               executable_candidates: Sequence[Mapping[str, object]],
               neighbor_graph_artifact: Mapping[str, object]) -> dict:
    """Run F4-F6 and stop before F7 until the reality diagnostic is reviewed.

    MCF-03 may emit daily series for every executable candidate, but MCF-04
    correlation/statistical work is intentionally limited to F0-F3 passers.
    Raw trial counts still cover the full frozen executable generation.
    """
    candidates = {str(c["candidate_id"]): c for c in executable_candidates}
    if len(candidates) != len(executable_candidates) or not candidates:
        raise MCFError("invalid executable candidate set")
    graph = _validate_neighbor_graph(neighbor_graph_artifact, set(candidates))

    results = {str(r.get("candidate_id", "")): r for r in production_results}
    if len(results) != len(production_results):
        raise MCFError("duplicate MCF-03 production result")
    if set(results) != set(candidates):
        raise MCFError("MCF-04 requires complete executable MCF-03 result coverage")

    for cid, result in results.items():
        if not _valid_result(result):
            raise MCFError("invalid MCF-03 result digest")
        candidate = candidates[cid]
        if result.get("candidate_spec_sha256") != candidate.get("candidate_spec_sha256"):
            raise MCFError("MCF-03 result/candidate spec mismatch")
        if result.get("family_id") != candidate.get("family_id"):
            raise MCFError("MCF-03 result/candidate family mismatch")
        if result.get("evidence_partition") != "DEVELOPMENT":
            raise MCFError("MCF-04 received non-Development result")

    passers = {
        cid for cid, result in results.items()
        if result.get("f0_f3_state") == "F0_F3_PASS"
    }
    raw_family = Counter(str(c["family_id"]) for c in executable_candidates)

    base = {
        "schema": VERSION,
        "executable_candidate_count": len(candidates),
        "f0_f3_passer_count": len(passers),
        "raw_family_trials": tuple(sorted(raw_family.items())),
        "neighbor_graph_sha256": neighbor_graph_artifact["neighbor_graph_sha256"],
        "safety": dict(SAFETY),
    }
    if not passers:
        result = {
            **base,
            "state": "ZERO_SURVIVOR_VALID",
            "f4": (),
            "trial_accounting": None,
            "family_pbo": (),
            "family_reality_check": (),
            "f5": (),
            "clusters": (),
            "representatives_pending_reality_review": (),
            "development_survivor_count": 0,
        }
        return {**result, "adjudication_sha256": digest(result)}

    passer_series = {
        cid: daily_series_from_result(results[cid])
        for cid in sorted(passers)
    }
    stress = {
        cid: float(results[cid]["aggregate_stress_net_return"])
        for cid in passers
    }
    f4 = {
        cid: neighbor_stability(cid, graph, passers, stress)
        for cid in sorted(passers)
    }
    f4_passers = {cid for cid, row in f4.items() if row["f4_pass"]}

    generation_eff = effective_trial_count(tuple(passer_series.values()))["effective_trials"]
    family_series: dict[str, list[DailySeries]] = {}
    for series in passer_series.values():
        family_series.setdefault(series.family_id, []).append(series)
    effective_family = {}
    for family in raw_family:
        rows = family_series.get(family, [])
        effective_family[family] = (
            effective_trial_count(rows)["effective_trials"] if rows else 1.0
        )
    accounting = TrialAccounting(
        raw_generation_trials=len(candidates),
        effective_generation_trials=generation_eff,
        raw_family_trials=dict(raw_family),
        effective_family_trials=effective_family,
    )
    accounting.validate()

    family_pbo = {
        family: cscv_pbo(rows)
        for family, rows in sorted(family_series.items())
    }
    family_reality = {}
    for family, rows in sorted(family_series.items()):
        f4_rows = [s for s in rows if s.candidate_id in f4_passers]
        if not f4_rows:
            family_reality[family] = {
                "schema": "MCF_REALITY_CHECK/1.0.0",
                "state": "NOT_APPLICABLE_NO_F4_PASSER",
                "p_value": None,
                "replications": BOOTSTRAP_REPLICATIONS,
                "block_days": BOOTSTRAP_BLOCK_DAYS,
                "seed": BOOTSTRAP_SEED,
            }
        else:
            diagnostic = reality_check(
                f4_rows,
                replications=BOOTSTRAP_REPLICATIONS,
                block_days=BOOTSTRAP_BLOCK_DAYS,
                seed=BOOTSTRAP_SEED,
            )
            if diagnostic.get("replications") != 2000 or diagnostic.get("block_days") != 14 or diagnostic.get("seed") != 20260927:
                raise MCFError("canonical reality-check protocol changed")
            family_reality[family] = diagnostic

    f5 = {}
    for cid in sorted(f4_passers):
        series = passer_series[cid]
        f5[cid] = statistical_gate(series, accounting, family_pbo[series.family_id])
    f5_passers = {cid for cid, row in f5.items() if row["f5_pass"]}

    cluster_series = [passer_series[cid] for cid in sorted(f5_passers)]
    cluster_artifact = common_factor_clusters(cluster_series)
    metrics = {}
    for cid in f5_passers:
        row = dict(results[cid])
        row["free_parameter_dimensions"] = int(candidates[cid]["free_parameter_dimensions"])
        metrics[cid] = row

    representatives = []
    for cluster in cluster_artifact.get("clusters", ()):
        representative = select_representative(cluster, metrics)
        family_id = passer_series[representative].family_id
        representatives.append({
            "candidate_id": representative,
            "cluster": tuple(cluster),
            "family_id": family_id,
            "state": "PENDING_DIRECTOR_REALITY_REVIEW",
            "reality_check": family_reality[family_id],
            "exact_accounting": results[representative].get("exact_accounting") is True,
            "candidate_spec_sha256": results[representative]["candidate_spec_sha256"],
        })

    state = "ZERO_SURVIVOR_VALID" if not representatives else "PENDING_DIRECTOR_REALITY_REVIEW"
    result = {
        **base,
        "state": state,
        "f4": tuple(f4[cid] for cid in sorted(f4)),
        "trial_accounting": {
            "raw_generation_trials": accounting.raw_generation_trials,
            "effective_generation_trials": accounting.effective_generation_trials,
            "raw_family_trials": tuple(sorted(accounting.raw_family_trials.items())),
            "effective_family_trials": tuple(sorted(accounting.effective_family_trials.items())),
        },
        "family_pbo": tuple((family, family_pbo[family]) for family in sorted(family_pbo)),
        "family_reality_check": tuple((family, family_reality[family]) for family in sorted(family_reality)),
        "f5": tuple(f5[cid] for cid in sorted(f5)),
        "clusters": tuple(cluster_artifact.get("clusters", ())),
        "cluster_artifact": cluster_artifact,
        "representatives_pending_reality_review": tuple(representatives),
        "development_survivor_count": 0,
    }
    return {**result, "adjudication_sha256": digest(result)}
