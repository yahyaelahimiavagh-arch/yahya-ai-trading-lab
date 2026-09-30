"""Pre-registered statistical multiplicity and overfit guards for YATL.

This module is deliberately independent of the production runner. It contains
pure statistical utilities plus a metadata-only pre-outcome manifest builder.
It does not read performance, Fresh OOS, recent reserve, P10, or any live state.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import e, isfinite, log, sqrt
from statistics import NormalDist, mean, pstdev, stdev
from typing import Mapping, Sequence

from .models import MCFError, digest

SCHEMA = "YATL_STATISTICAL_GUARD/1.0.0"
MANIFEST_SCHEMA = "YATL_MULTIPLICITY_PREOUTCOME/1.0.0"
EULER_MASCHERONI = 0.5772156649015329


def _probability(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MCFError(f"{name} must be numeric")
    value = float(value)
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise MCFError(f"{name} outside [0,1]")
    return value


def _returns(values: Sequence[float], *, minimum: int = 5) -> tuple[float, ...]:
    out = tuple(float(v) for v in values)
    if len(out) < minimum or any(not isfinite(v) for v in out):
        raise MCFError("invalid statistical return series")
    if stdev(out) == 0:
        raise MCFError("zero-variance return series")
    return out


@dataclass(frozen=True)
class FDRDecision:
    candidate_id: str
    p_value: float
    adjusted_p_value: float
    rejected: bool


def fdr_adjust(
    p_values: Mapping[str, float],
    *,
    alpha: float = 0.05,
    method: str = "BY",
) -> tuple[FDRDecision, ...]:
    """Control false discoveries with BH or the dependence-robust BY correction.

    BY is the YATL default until a later dependency audit justifies BH.
    """
    alpha = _probability(alpha, name="alpha")
    if alpha <= 0:
        raise MCFError("alpha must be positive")
    if method not in {"BH", "BY"}:
        raise MCFError("unsupported FDR method")
    if not p_values:
        raise MCFError("empty FDR family")

    rows = []
    for candidate_id, p_value in p_values.items():
        if not isinstance(candidate_id, str) or not candidate_id:
            raise MCFError("invalid candidate id in FDR family")
        rows.append((candidate_id, _probability(p_value, name="p_value")))
    rows.sort(key=lambda item: (item[1], item[0]))

    m = len(rows)
    dependence_factor = 1.0 if method == "BH" else sum(1.0 / i for i in range(1, m + 1))

    raw_adjusted = [
        min(1.0, p * m * dependence_factor / rank)
        for rank, (_, p) in enumerate(rows, 1)
    ]
    adjusted = list(raw_adjusted)
    for index in range(m - 2, -1, -1):
        adjusted[index] = min(adjusted[index], adjusted[index + 1])

    return tuple(
        FDRDecision(
            candidate_id=candidate_id,
            p_value=p_value,
            adjusted_p_value=adjusted[index],
            rejected=adjusted[index] <= alpha,
        )
        for index, (candidate_id, p_value) in enumerate(rows)
    )


def _moments(values: Sequence[float]) -> tuple[float, float, float, float]:
    """Return mean, sample std, moment skewness and Pearson kurtosis."""
    x = _returns(values)
    mu = mean(x)
    sigma = stdev(x)
    n = len(x)
    m2 = sum((v - mu) ** 2 for v in x) / n
    if m2 <= 0:
        raise MCFError("invalid second moment")
    m3 = sum((v - mu) ** 3 for v in x) / n
    m4 = sum((v - mu) ** 4 for v in x) / n
    skewness = m3 / (m2 ** 1.5)
    kurtosis = m4 / (m2 ** 2)
    if any(not isfinite(v) for v in (mu, sigma, skewness, kurtosis)):
        raise MCFError("non-finite return moments")
    return mu, sigma, skewness, kurtosis


def periodic_sharpe(values: Sequence[float]) -> float:
    """Unannualized per-observation Sharpe used by the statistical guards."""
    mu, sigma, _, _ = _moments(values)
    return mu / sigma


def probabilistic_sharpe_ratio(
    values: Sequence[float],
    *,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Probability that the true periodic Sharpe exceeds benchmark_sharpe."""
    x = _returns(values)
    sr = periodic_sharpe(x)
    _, _, skewness, kurtosis = _moments(x)
    benchmark = float(benchmark_sharpe)
    if not isfinite(benchmark):
        raise MCFError("non-finite Sharpe benchmark")
    variance_term = 1.0 - skewness * sr + ((kurtosis - 1.0) / 4.0) * (sr ** 2)
    if not isfinite(variance_term) or variance_term <= 0:
        raise MCFError("invalid probabilistic Sharpe variance term")
    z = (sr - benchmark) * sqrt(len(x) - 1) / sqrt(variance_term)
    return NormalDist().cdf(z)


def one_sided_sharpe_p_value(values: Sequence[float]) -> float:
    """One-sided p-value for H0: periodic Sharpe <= 0."""
    return 1.0 - probabilistic_sharpe_ratio(values, benchmark_sharpe=0.0)


def expected_maximum_sharpe(
    trial_sharpes: Sequence[float],
    *,
    conservative_trial_count: int,
) -> float:
    """Expected maximum null Sharpe after multiple trials.

    The cross-sectional dispersion is measured from all trial Sharpes supplied.
    YATL keeps conservative_trial_count at the full frozen trial count until an
    audited dependency model exists.
    """
    sharpes = tuple(float(v) for v in trial_sharpes)
    if len(sharpes) < 2 or any(not isfinite(v) for v in sharpes):
        raise MCFError("insufficient trial Sharpes for deflation")
    if (
        type(conservative_trial_count) is not int
        or conservative_trial_count < len(sharpes)
        or conservative_trial_count < 2
    ):
        raise MCFError("invalid conservative trial count")
    sigma = pstdev(sharpes)
    if not isfinite(sigma):
        raise MCFError("invalid cross-trial Sharpe dispersion")
    if sigma == 0:
        return 0.0
    normal = NormalDist()
    n = float(conservative_trial_count)
    extreme = (
        (1.0 - EULER_MASCHERONI) * normal.inv_cdf(1.0 - 1.0 / n)
        + EULER_MASCHERONI * normal.inv_cdf(1.0 - 1.0 / (n * e))
    )
    return sigma * extreme


def deflated_sharpe_probability(
    values: Sequence[float],
    *,
    trial_sharpes: Sequence[float],
    conservative_trial_count: int,
) -> dict:
    """Bailey/Lopez de Prado-style DSR probability using periodic Sharpes."""
    x = _returns(values)
    sr = periodic_sharpe(x)
    threshold = expected_maximum_sharpe(
        trial_sharpes,
        conservative_trial_count=conservative_trial_count,
    )
    probability = probabilistic_sharpe_ratio(x, benchmark_sharpe=threshold)
    return {
        "schema": SCHEMA,
        "observed_periodic_sharpe": sr,
        "deflated_null_sharpe": threshold,
        "dsr_probability": probability,
        "observation_count": len(x),
        "conservative_trial_count": conservative_trial_count,
    }


def _score(values: Sequence[float]) -> float:
    return periodic_sharpe(values)


def _average_rank(scores: Mapping[str, float], selected: str) -> float:
    target = scores[selected]
    less = sum(value < target for value in scores.values())
    equal = sum(value == target for value in scores.values())
    # Ranks are 1..N, ascending. Average tie rank.
    return less + (equal + 1.0) / 2.0


def pbo_cscv(
    return_panel: Mapping[str, Sequence[float]],
    *,
    block_count: int,
    max_splits: int = 20_000,
) -> dict:
    """Estimate Probability of Backtest Overfitting using symmetric CSCV.

    Input must be a complete rectangular panel on common timestamps. Missing
    observations must be resolved upstream by intersection, never imputation.
    block_count is pre-registered and must evenly divide the observation count.
    """
    if len(return_panel) < 2:
        raise MCFError("PBO requires at least two candidate variants")
    if type(block_count) is not int or block_count < 4 or block_count % 2:
        raise MCFError("PBO block count must be even and >=4")
    if type(max_splits) is not int or max_splits <= 0:
        raise MCFError("invalid PBO split ceiling")

    ids = tuple(sorted(return_panel))
    rows = {candidate_id: _returns(return_panel[candidate_id], minimum=block_count)
            for candidate_id in ids}
    lengths = {len(values) for values in rows.values()}
    if len(lengths) != 1:
        raise MCFError("PBO requires a rectangular return panel")
    observation_count = lengths.pop()
    if observation_count % block_count:
        raise MCFError("PBO observations must divide evenly into frozen blocks")

    block_size = observation_count // block_count
    if block_size < 2:
        raise MCFError("PBO blocks too small")
    split_count = 0
    failed = 0
    logits: list[float] = []
    selected_counts: Counter[str] = Counter()

    all_blocks = tuple(range(block_count))
    combinations_count = 1
    # math.comb without another import; fail before expensive materialization.
    for i in range(1, block_count // 2 + 1):
        combinations_count = combinations_count * (block_count - i + 1) // i
    if combinations_count > max_splits:
        raise MCFError("PBO split count exceeds frozen computational ceiling")

    for in_blocks in combinations(all_blocks, block_count // 2):
        in_set = set(in_blocks)
        out_blocks = tuple(block for block in all_blocks if block not in in_set)

        def indices(blocks: Sequence[int]) -> tuple[int, ...]:
            return tuple(
                index
                for block in blocks
                for index in range(block * block_size, (block + 1) * block_size)
            )

        in_idx = indices(in_blocks)
        out_idx = indices(out_blocks)

        in_scores = {
            candidate_id: _score(tuple(rows[candidate_id][i] for i in in_idx))
            for candidate_id in ids
        }
        winner = min(ids, key=lambda candidate_id: (-in_scores[candidate_id], candidate_id))
        selected_counts[winner] += 1

        out_scores = {
            candidate_id: _score(tuple(rows[candidate_id][i] for i in out_idx))
            for candidate_id in ids
        }
        rank = _average_rank(out_scores, winner)
        omega = rank / (len(ids) + 1.0)
        if not 0.0 < omega < 1.0:
            raise MCFError("invalid PBO relative rank")
        value = log(omega / (1.0 - omega))
        logits.append(value)
        split_count += 1
        if value <= 0.0:
            failed += 1

    return {
        "schema": SCHEMA,
        "method": "CSCV_PBO",
        "candidate_count": len(ids),
        "observation_count": observation_count,
        "block_count": block_count,
        "split_count": split_count,
        "pbo": failed / split_count,
        "logit_min": min(logits),
        "logit_max": max(logits),
        "selected_candidate_counts": tuple(sorted(selected_counts.items())),
    }


def build_preoutcome_multiplicity_manifest(
    executable: Sequence[Mapping[str, object]],
    *,
    expected_candidate_count: int | None = None,
) -> dict:
    """Freeze metadata needed by later statistical adjudication without outcomes."""
    if not executable:
        raise MCFError("empty executable set")
    seen: set[str] = set()
    family_counts: Counter[str] = Counter()
    mechanism_counts: Counter[str] = Counter()
    timeframe_counts: Counter[str] = Counter()
    dimension_counts: Counter[int] = Counter()
    neighbor_edges = 0

    for row in executable:
        candidate_id = str(row.get("candidate_id", ""))
        family = str(row.get("family", row.get("family_id", "")))
        mechanism = str(row.get("economic_mechanism_id", ""))
        timeframe = str(row.get("timeframe", ""))
        dimensions = row.get("free_parameter_dimensions")
        neighbors = row.get("parameter_neighbor_ids", ())
        if not candidate_id or candidate_id in seen:
            raise MCFError("invalid/duplicate candidate in multiplicity manifest")
        if not family or not mechanism or timeframe not in {"15m", "1h", "4h"}:
            raise MCFError("incomplete candidate metadata in multiplicity manifest")
        if type(dimensions) is not int or dimensions < 0:
            raise MCFError("invalid parameter dimension metadata")
        if not isinstance(neighbors, (tuple, list)) or any(not isinstance(x, str) or not x for x in neighbors):
            raise MCFError("invalid neighbor metadata")
        seen.add(candidate_id)
        family_counts[family] += 1
        mechanism_counts[mechanism] += 1
        timeframe_counts[timeframe] += 1
        dimension_counts[dimensions] += 1
        neighbor_edges += len(set(neighbors))

    candidate_count = len(seen)
    if expected_candidate_count is not None and candidate_count != expected_candidate_count:
        raise MCFError("multiplicity manifest candidate count mismatch")

    payload = {
        "schema": MANIFEST_SCHEMA,
        "state": "PRE_OUTCOME_MULTIPLICITY_FROZEN",
        "candidate_count": candidate_count,
        "conservative_trial_count": candidate_count,
        "family_counts": tuple(sorted(family_counts.items())),
        "economic_mechanism_counts": tuple(sorted(mechanism_counts.items())),
        "timeframe_counts": tuple(sorted(timeframe_counts.items())),
        "free_parameter_dimension_counts": tuple(sorted(dimension_counts.items())),
        "directed_parameter_neighbor_edge_count": neighbor_edges,
        "default_fdr_method": "BY",
        "bh_requires_dependency_justification": True,
        "dsr_uses_full_trial_count_until_dependency_audit": True,
        "pbo_requires_common_complete_return_panel": True,
        "performance_read": False,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "live_authorized": False,
    }
    return {**payload, "manifest_sha256": digest(payload)}
