"""MCF-04 Development-only statistical adjudication.

The module implements neighbor stability, effective trial accounting, Deflated
Sharpe confidence, deterministic CSCV/PBO, the required family bootstrap
reality-check diagnostic, common-factor clustering and deterministic cluster
representative selection.  It has no access path to Fresh OOS, P10 or Live.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import e, isfinite, sqrt
from random import Random
from statistics import NormalDist, mean, median
from typing import Mapping, Sequence
import json

from .manifest import domain_values, validate as validate_manifest
from .models import MCFError, digest

VERSION = "MCF_ADJUDICATION/1.0.0"
NEIGHBOR_VERSION = "MCF_NEIGHBOR_GRAPH/1.0.0"
DSR_VERSION = "MCF_DSR/1.0.0"
PBO_VERSION = "MCF_CSCV_PBO/1.0.0"
REALITY_VERSION = "MCF_REALITY_CHECK/1.0.0"
CLUSTER_VERSION = "MCF_COMMON_FACTOR_CLUSTER/1.0.0"
SURVIVOR_VERSION = "MCF_DEVELOPMENT_SURVIVOR_FREEZE/1.0.0"

DSR_MIN_CONFIDENCE = 0.95
PBO_MAX = 0.20
CORRELATION_EDGE = 0.80
BOOTSTRAP_SEED = 20260927
BOOTSTRAP_BLOCK_DAYS = 14
BOOTSTRAP_REPLICATIONS = 2000
EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True)
class DailySeries:
    candidate_id: str
    family_id: str
    mechanism_id: str
    calendar_days: tuple[int, ...]
    returns: tuple[float | None, ...]
    valid_mask: tuple[bool, ...]

    def validate(self) -> None:
        n = len(self.calendar_days)
        if not self.candidate_id or not self.family_id or not self.mechanism_id or n < 2:
            raise MCFError("invalid daily-series identity")
        if len(self.returns) != n or len(self.valid_mask) != n:
            raise MCFError("daily-series length mismatch")
        if any(a >= b for a, b in zip(self.calendar_days, self.calendar_days[1:])):
            raise MCFError("nonmonotonic daily calendar")
        for value, valid in zip(self.returns, self.valid_mask):
            if type(valid) is not bool:
                raise MCFError("nonboolean daily validity")
            if valid:
                if value is None or not isfinite(float(value)):
                    raise MCFError("valid daily return is missing/nonfinite")
            elif value is not None:
                raise MCFError("invalid source day cannot carry a synthetic return")

    def values(self, indexes: Sequence[int] | None = None) -> list[float]:
        self.validate()
        use = range(len(self.returns)) if indexes is None else indexes
        return [float(self.returns[i]) for i in use if self.valid_mask[i]]


@dataclass(frozen=True)
class TrialAccounting:
    raw_generation_trials: int
    effective_generation_trials: float
    raw_family_trials: Mapping[str, int]
    effective_family_trials: Mapping[str, float]
    raw_mechanism_trials: Mapping[str, int]
    effective_mechanism_trials: Mapping[str, float]

    def validate(self) -> None:
        if self.raw_generation_trials < 1:
            raise MCFError("invalid raw generation trial count")
        if not (1.0 <= float(self.effective_generation_trials) <= self.raw_generation_trials):
            raise MCFError("invalid effective generation trial count")
        if not self.raw_family_trials or set(self.raw_family_trials) != set(self.effective_family_trials):
            raise MCFError("incomplete family trial accounting")
        for family, raw in self.raw_family_trials.items():
            eff = float(self.effective_family_trials[family])
            if raw < 1 or not 1.0 <= eff <= raw:
                raise MCFError("invalid family trial accounting")
        if not self.raw_mechanism_trials or set(self.raw_mechanism_trials) != set(self.effective_mechanism_trials):
            raise MCFError("incomplete mechanism trial accounting")
        for mechanism, raw in self.raw_mechanism_trials.items():
            eff = float(self.effective_mechanism_trials[mechanism])
            if raw < 1 or not 1.0 <= eff <= raw:
                raise MCFError("invalid mechanism trial accounting")


def _vector_key(vector: Mapping[str, object], names: Sequence[str]) -> tuple[str, ...]:
    return tuple(json.dumps(vector[name], sort_keys=True, separators=(",", ":")) for name in names)


def build_neighbor_graph(candidates: Sequence[Mapping[str, object]],
                         manifests_by_sha: Mapping[str, Mapping[str, object]]) -> dict:
    """Build the one-step graph from frozen family topology before performance."""
    by_family: dict[str, list[Mapping[str, object]]] = {}
    for candidate in candidates:
        required = {"candidate_id", "candidate_spec_sha256", "family_manifest_sha256", "parameter_vector"}
        if not required <= set(candidate):
            raise MCFError("incomplete candidate for neighbor graph")
        sha = str(candidate["family_manifest_sha256"])
        if sha not in manifests_by_sha:
            raise MCFError("candidate family manifest missing")
        by_family.setdefault(sha, []).append(candidate)

    graph: dict[str, set[str]] = {str(c["candidate_id"]): set() for c in candidates}
    for sha, rows in by_family.items():
        manifest = manifests_by_sha[sha]
        if validate_manifest(dict(manifest)) != sha:
            raise MCFError("family manifest SHA mismatch")
        domains = manifest["parameter_domains"]
        names = [d["name"] for d in domains]
        values_by_name = {d["name"]: domain_values(d) for d in domains}
        index = {_vector_key(c["parameter_vector"], names): str(c["candidate_id"]) for c in rows}
        if len(index) != len(rows):
            raise MCFError("duplicate parameter vector in family")

        for candidate in rows:
            cid = str(candidate["candidate_id"])
            vector = dict(candidate["parameter_vector"])
            for name in names:
                values = values_by_name[name]
                try:
                    pos = values.index(vector[name])
                except ValueError as exc:
                    raise MCFError("parameter outside frozen domain") from exc
                for step in (-1, 1):
                    q = pos + step
                    if not 0 <= q < len(values):
                        continue
                    other = dict(vector)
                    other[name] = values[q]
                    neighbor = index.get(_vector_key(other, names))
                    if neighbor is not None:
                        graph[cid].add(neighbor)

    canonical = {cid: tuple(sorted(neighbors)) for cid, neighbors in sorted(graph.items())}
    return {
        "schema": NEIGHBOR_VERSION,
        "graph": canonical,
        "neighbor_graph_sha256": digest({"schema": NEIGHBOR_VERSION, "graph": canonical}),
    }


def neighbor_stability(candidate_id: str, graph: Mapping[str, Sequence[str]],
                       f0_f3_passers: set[str],
                       stress_return_by_candidate: Mapping[str, float]) -> dict:
    if candidate_id not in graph:
        raise MCFError("candidate absent from neighbor graph")
    neighbors = tuple(graph[candidate_id])
    passing = tuple(n for n in neighbors if n in f0_f3_passers)
    missing_stress = tuple(n for n in neighbors if n not in stress_return_by_candidate)
    if missing_stress:
        raise MCFError("incomplete neighbor stress-return coverage")
    values = [float(stress_return_by_candidate[n]) for n in neighbors]
    fraction = len(passing) / len(neighbors) if neighbors else 0.0
    med = median(values) if values else float("-inf")
    passed = len(neighbors) >= 3 and fraction >= 0.50 and bool(values) and med > 0.0
    reasons = []
    if len(neighbors) < 3:
        reasons.append("F4_VALID_NEIGHBORS_LT_3")
    if fraction < 0.50:
        reasons.append("F4_NEIGHBOR_PASS_FRACTION_LT_0_50")
    if not values or med <= 0.0:
        reasons.append("F4_MEDIAN_NEIGHBOR_STRESS_NOT_POSITIVE")
    return {
        "candidate_id": candidate_id,
        "valid_neighbor_count": len(neighbors),
        "passing_neighbor_count": len(passing),
        "passing_neighbor_fraction": fraction,
        "median_neighbor_stress_return": None if not values else med,
        "f4_pass": passed,
        "failure_reasons": tuple(reasons),
    }


def _pearson_pairs(a: DailySeries, b: DailySeries, indexes: Sequence[int] | None = None) -> tuple[float, int]:
    a.validate()
    b.validate()
    if a.calendar_days != b.calendar_days:
        raise MCFError("daily calendars differ")
    use = range(len(a.returns)) if indexes is None else indexes
    pairs = [
        (float(a.returns[i]), float(b.returns[i]))
        for i in use if a.valid_mask[i] and b.valid_mask[i]
    ]
    if len(pairs) < 2:
        return 0.0, len(pairs)
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx, my = mean(xs), mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return 0.0, len(pairs)
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    return max(-1.0, min(1.0, cov / sqrt(vx * vy))), len(pairs)


def effective_trial_count(series: Sequence[DailySeries]) -> dict:
    if not series:
        raise MCFError("empty return matrix")
    calendar = series[0].calendar_days
    for s in series:
        s.validate()
        if s.calendar_days != calendar:
            raise MCFError("daily calendars differ")
    n = len(series)
    sum_squares = float(n)  # diagonal correlations are one
    correlations = {}
    for i in range(n):
        for j in range(i + 1, n):
            rho, common = _pearson_pairs(series[i], series[j])
            correlations[(series[i].candidate_id, series[j].candidate_id)] = {
                "rho": rho, "common_valid_days": common
            }
            sum_squares += 2.0 * rho * rho
    neff = n * n / sum_squares if sum_squares > 0.0 else float(n)
    neff = max(1.0, min(float(n), neff))
    return {
        "raw_trials": n,
        "effective_trials": neff,
        "pairwise": correlations,
    }


def _moments(values: Sequence[float]) -> tuple[float, float, float, float]:
    n = len(values)
    if n < 3:
        raise MCFError("insufficient returns")
    mu = mean(values)
    variance = sum((x - mu) ** 2 for x in values) / (n - 1)
    if variance <= 0.0:
        raise MCFError("zero return variance")
    sd = sqrt(variance)
    m3 = sum((x - mu) ** 3 for x in values) / n
    m4 = sum((x - mu) ** 4 for x in values) / n
    return mu, sd, m3 / (sd ** 3), m4 / (sd ** 4)


def deflated_sharpe(series: DailySeries, effective_trials: float) -> dict:
    values = series.values()
    if len(values) < 30 or not isfinite(float(effective_trials)) or effective_trials < 1.0:
        return {
            "schema": DSR_VERSION, "candidate_id": series.candidate_id,
            "state": "STATISTICAL_EVIDENCE_INVALID", "confidence": None,
            "annualized_sharpe": None, "effective_trials": effective_trials,
        }
    try:
        mu, sd, skew, kurtosis = _moments(values)
    except MCFError:
        return {
            "schema": DSR_VERSION, "candidate_id": series.candidate_id,
            "state": "STATISTICAL_EVIDENCE_INVALID", "confidence": None,
            "annualized_sharpe": None, "effective_trials": effective_trials,
        }

    sr = mu / sd
    if effective_trials <= 1.0:
        null_sr = 0.0
    else:
        sigma_sr = 1.0 / sqrt(len(values) - 1)
        normal = NormalDist()
        p1 = min(1.0 - 1e-12, max(1e-12, 1.0 - 1.0 / effective_trials))
        p2 = min(1.0 - 1e-12, max(1e-12, 1.0 - 1.0 / (effective_trials * e)))
        null_sr = sigma_sr * (
            (1.0 - EULER_GAMMA) * normal.inv_cdf(p1)
            + EULER_GAMMA * normal.inv_cdf(p2)
        )

    denom_sq = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denom_sq <= 0.0 or not isfinite(denom_sq):
        return {
            "schema": DSR_VERSION, "candidate_id": series.candidate_id,
            "state": "STATISTICAL_EVIDENCE_INVALID", "confidence": None,
            "annualized_sharpe": sr * sqrt(365.0), "effective_trials": effective_trials,
        }
    z = (sr - null_sr) * sqrt(len(values) - 1) / sqrt(denom_sq)
    confidence = NormalDist().cdf(z)
    return {
        "schema": DSR_VERSION,
        "candidate_id": series.candidate_id,
        "state": "PASS" if confidence >= DSR_MIN_CONFIDENCE else "FAIL",
        "confidence": confidence,
        "daily_sharpe": sr,
        "annualized_sharpe": sr * sqrt(365.0),
        "multiple_testing_null_daily_sharpe": null_sr,
        "skewness": skew,
        "kurtosis": kurtosis,
        "effective_trials": effective_trials,
        "valid_days": len(values),
    }


def _sharpe(values: Sequence[float]) -> float:
    if len(values) < 2:
        return float("-inf")
    mu = mean(values)
    variance = sum((x - mu) ** 2 for x in values) / (len(values) - 1)
    if variance <= 0.0:
        return float("-inf")
    return mu / sqrt(variance)


def cscv_pbo(series: Sequence[DailySeries]) -> dict:
    if len(series) < 2:
        return {"schema": PBO_VERSION, "state": "STATISTICAL_EVIDENCE_INVALID", "pbo": None, "split_count": 0}
    calendar = series[0].calendar_days
    for s in series:
        s.validate()
        if s.calendar_days != calendar:
            raise MCFError("daily calendars differ")
    n = len(calendar)
    if n < 16:
        return {"schema": PBO_VERSION, "state": "STATISTICAL_EVIDENCE_INVALID", "pbo": None, "split_count": 0}

    slices = []
    for i in range(8):
        a = (i * n) // 8
        b = ((i + 1) * n) // 8
        slices.append(tuple(range(a, b)))

    overfit = 0
    valid_splits = 0
    logits = []
    all_slice_ids = set(range(8))
    for train_slices in combinations(range(8), 4):
        train_idx = tuple(i for s in train_slices for i in slices[s])
        test_slices = sorted(all_slice_ids - set(train_slices))
        test_idx = tuple(i for s in test_slices for i in slices[s])

        train_scores = []
        for s in series:
            train_scores.append((_sharpe(s.values(train_idx)), s.candidate_id, s))
        train_scores.sort(key=lambda x: (-x[0], x[1]))
        selected_score, _, selected = train_scores[0]
        if selected_score == float("-inf"):
            continue

        test_scores = [(s.candidate_id, _sharpe(s.values(test_idx))) for s in series]
        selected_test = dict(test_scores)[selected.candidate_id]
        finite = [(cid, score) for cid, score in test_scores if score != float("-inf")]
        if selected_test == float("-inf") or len(finite) < 2:
            overfit += 1
            valid_splits += 1
            logits.append(float("-inf"))
            continue
        lower = sum(score < selected_test for _, score in finite)
        equal = sum(score == selected_test for _, score in finite)
        rank = (lower + 0.5 * equal) / len(finite)
        rank = max(1e-12, min(1.0 - 1e-12, rank))
        logit = __import__("math").log(rank / (1.0 - rank))
        logits.append(logit)
        overfit += int(logit <= 0.0)
        valid_splits += 1

    if not valid_splits:
        return {"schema": PBO_VERSION, "state": "STATISTICAL_EVIDENCE_INVALID", "pbo": None, "split_count": 0}
    pbo = overfit / valid_splits
    return {
        "schema": PBO_VERSION,
        "state": "PASS" if pbo <= PBO_MAX else "FAIL",
        "pbo": pbo,
        "split_count": valid_splits,
        "overfit_split_count": overfit,
        "logits": tuple(logits),
    }


def reality_check(series: Sequence[DailySeries], *, replications: int = BOOTSTRAP_REPLICATIONS,
                  block_days: int = BOOTSTRAP_BLOCK_DAYS, seed: int = BOOTSTRAP_SEED) -> dict:
    if not series or replications <= 0 or block_days <= 0:
        raise MCFError("invalid reality-check inputs")
    calendar = series[0].calendar_days
    for s in series:
        s.validate()
        if s.calendar_days != calendar:
            raise MCFError("daily calendars differ")
    common = [
        i for i in range(len(calendar))
        if all(s.valid_mask[i] for s in series)
    ]
    if len(common) < 30:
        return {
            "schema": REALITY_VERSION, "state": "STATISTICAL_EVIDENCE_INVALID",
            "p_value": None, "replications": replications, "block_days": block_days,
            "seed": seed, "common_valid_days": len(common),
        }

    matrix = [[float(s.returns[i]) for i in common] for s in series]
    means = [mean(row) for row in matrix]
    centered = [[x - m for x in row] for row, m in zip(matrix, means)]
    observed = max(means) * sqrt(len(common))
    rng = Random(seed)
    exceed = 0
    n = len(common)
    compact_index = {calendar_index: i for i, calendar_index in enumerate(common)}
    calendar_n = len(calendar)
    for _ in range(replications):
        indexes = []
        while len(indexes) < n:
            # Blocks are 14 calendar days, not 14 compressed valid observations.
            start = rng.randrange(calendar_n)
            for offset in range(block_days):
                calendar_index = (start + offset) % calendar_n
                compact = compact_index.get(calendar_index)
                if compact is not None:
                    indexes.append(compact)
                    if len(indexes) == n:
                        break
        boot = max(
            sum(row[i] for i in indexes) / n * sqrt(n)
            for row in centered
        )
        exceed += int(boot >= observed)
    p_value = (exceed + 1) / (replications + 1)
    return {
        "schema": REALITY_VERSION,
        "state": "DIAGNOSTIC_COMPLETE",
        "p_value": p_value,
        "observed_max_mean_statistic": observed,
        "replications": replications,
        "block_days": block_days,
        "seed": seed,
        "common_valid_days": n,
    }


def common_factor_clusters(series: Sequence[DailySeries]) -> dict:
    if not series:
        return {"schema": CLUSTER_VERSION, "clusters": (), "edges": ()}
    for s in series:
        s.validate()
    parent = {s.candidate_id: s.candidate_id for s in series}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    edges = []
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            rho, common = _pearson_pairs(series[i], series[j])
            if abs(rho) >= CORRELATION_EDGE:
                a, b = sorted((series[i].candidate_id, series[j].candidate_id))
                edges.append((a, b, rho, common))
                union(a, b)

    groups: dict[str, list[str]] = {}
    for cid in sorted(parent):
        groups.setdefault(find(cid), []).append(cid)
    clusters = tuple(tuple(v) for _, v in sorted(groups.items()))
    return {
        "schema": CLUSTER_VERSION,
        "clusters": clusters,
        "edges": tuple(sorted(edges)),
        "cluster_sha256": digest({"schema": CLUSTER_VERSION, "clusters": clusters, "edges": tuple(sorted(edges))}),
    }


def select_representative(cluster: Sequence[str], metrics: Mapping[str, Mapping[str, object]]) -> str:
    if not cluster:
        raise MCFError("empty common-factor cluster")
    missing = set(cluster) - set(metrics)
    if missing:
        raise MCFError("cluster metrics missing")
    def key(cid: str):
        m = metrics[cid]
        required = {
            "median_symbol_stress_net_return", "fold_stress_returns",
            "maximum_normalized_drawdown", "mean_turnover", "free_parameter_dimensions"
        }
        if not required <= set(m):
            raise MCFError("incomplete representative metrics")
        folds = [float(x) for x in m["fold_stress_returns"] if x is not None]
        if not folds:
            raise MCFError("missing stress folds")
        return (
            -float(m["median_symbol_stress_net_return"]),
            -min(folds),
            float(m["maximum_normalized_drawdown"]),
            float(m["mean_turnover"]),
            int(m["free_parameter_dimensions"]),
            cid,
        )
    return min(cluster, key=key)


def statistical_gate(series: DailySeries, accounting: TrialAccounting,
                     family_pbo: Mapping[str, object]) -> dict:
    accounting.validate()
    if series.family_id not in accounting.raw_family_trials:
        raise MCFError("family absent from trial accounting")
    if series.mechanism_id not in accounting.raw_mechanism_trials:
        raise MCFError("mechanism absent from trial accounting")
    effective = max(
        float(accounting.effective_generation_trials),
        float(accounting.effective_family_trials[series.family_id]),
    )
    dsr = deflated_sharpe(series, effective)
    pbo = family_pbo.get("pbo")
    passed = dsr.get("state") == "PASS" and pbo is not None and float(pbo) <= PBO_MAX
    reasons = []
    if dsr.get("state") != "PASS":
        reasons.append("F5_DSR_CONFIDENCE_LT_0_95_OR_INVALID")
    if pbo is None:
        reasons.append("F5_FAMILY_PBO_INVALID")
    elif float(pbo) > PBO_MAX:
        reasons.append("F5_FAMILY_PBO_GT_0_20")
    return {
        "candidate_id": series.candidate_id,
        "f5_pass": passed,
        "dsr": dsr,
        "family_pbo": dict(family_pbo),
        "failure_reasons": tuple(reasons),
        "raw_family_trials": accounting.raw_family_trials[series.family_id],
        "effective_family_trials": accounting.effective_family_trials[series.family_id],
        "raw_mechanism_trials": accounting.raw_mechanism_trials[series.mechanism_id],
        "effective_mechanism_trials": accounting.effective_mechanism_trials[series.mechanism_id],
        "effective_trials_used": effective,
    }


def freeze_survivor(*, candidate_id: str, candidate_spec_sha256: str,
                    universe_sha256: str, evidence_sha256: str, cost_sha256: str,
                    statistical_artifact_sha256: str, exact_recomputed: bool,
                    reality_review_clear: bool) -> dict:
    values = (
        candidate_spec_sha256, universe_sha256, evidence_sha256,
        cost_sha256, statistical_artifact_sha256
    )
    if not candidate_id or any(len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in values):
        raise MCFError("invalid survivor freeze identity")
    if exact_recomputed is not True:
        raise MCFError("F7 requires canonical exact recompute")
    if reality_review_clear is not True:
        return {
            "schema": SURVIVOR_VERSION,
            "candidate_id": candidate_id,
            "state": "HELD_FOR_DIRECTOR_REVIEW",
        }
    row = {
        "schema": SURVIVOR_VERSION,
        "candidate_id": candidate_id,
        "candidate_spec_sha256": candidate_spec_sha256,
        "universe_sha256": universe_sha256,
        "evidence_sha256": evidence_sha256,
        "cost_sha256": cost_sha256,
        "statistical_artifact_sha256": statistical_artifact_sha256,
        "state": "DEVELOPMENT_SURVIVOR_FROZEN",
        "safety": {
            "fresh_oos_opened": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
            "p11_locked": True,
        },
    }
    return {**row, "freeze_sha256": digest(row)}
