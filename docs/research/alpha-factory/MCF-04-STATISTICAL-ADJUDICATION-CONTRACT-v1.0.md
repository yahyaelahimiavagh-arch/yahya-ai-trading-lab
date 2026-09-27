# MCF-04 — Neighbor Stability, Multiple Testing & Cluster Adjudication v1.0

Status: **FROZEN BEFORE IMPLEMENTATION / BEFORE MCF-PROD-001 OUTCOME**
Date: 2026-09-27
Safety: RESEARCH ONLY

## 1. Purpose

Apply severe post-Development controls to the F0-F3 pass set before any
candidate may be frozen for Fresh OOS.

MCF-04 operates only on Development artifacts.

## 2. F4 parameter-neighbor stability

Neighbor graph is generated before performance from family-manifest topology.

A candidate is F4-eligible only if:
- it has at least 3 valid one-step parameter neighbors after structural
  constraints;
- at least 50% of its valid one-step neighbors pass F0-F3;
- median neighbor stress return is positive;
- the candidate is not the sole isolated profitable point in its local grid.

If fewer than 3 valid neighbors exist because the candidate lies on a bounded
domain edge, it may remain diagnostic but cannot pass F4 in MCF-PROD-001.

## 3. Daily return matrix

MCF-04 consumes exact-recomputed Development daily normalized return series for
F0-F3 passers.

Requirements:
- same Development calendar;
- missing candidate days explicitly represented as zero only when the candidate
  is legitimately flat, never when source data is missing;
- invalid/missing source days retain an availability mask;
- no later evidence.

## 4. Effective trial count

Report both raw and effective trial counts.

For a family return-correlation matrix with eigenvalues λ:
`N_eff = (sum λ)^2 / sum(λ^2)`

Bound:
`1 <= N_eff <= N_raw`

Compute:
- per family;
- entire generation;
- per economic mechanism where multiple manifests share a mechanism.

This is accounting, not a standalone pass condition.

## 5. Deflated Sharpe Ratio

For candidates remaining after F4:
- calculate Development daily Sharpe from exact normalized return series;
- use the generation/family effective trial count and non-normal return moments
  in a versioned Deflated Sharpe implementation;
- hard requirement: DSR confidence >= 0.95 that the candidate exceeds the
  multiple-testing-adjusted null threshold.

If DSR assumptions/input series are invalid, candidate is
`STATISTICAL_EVIDENCE_INVALID`, not silently passed.

## 6. Probability of Backtest Overfitting

Use deterministic CSCV on 8 chronological Development slices.

- slice boundaries fixed before outcome;
- all valid symmetric train/test combinations evaluated;
- family-level PBO recorded;
- candidate-family hard gate: PBO <= 0.20.

A family with PBO > 0.20 may retain negative/diagnostic evidence but produces no
MCF-PROD-001 survivors.

## 7. Reality-check diagnostic

Implement a block-bootstrap family-level reality-check/SPA-style diagnostic
with:
- deterministic seed frozen in implementation contract;
- block length selected by a fixed pre-outcome rule;
- at least 2,000 bootstrap replications for canonical run.

For MCF-PROD-001 this is a required diagnostic, not an independent rescue gate.

If it materially contradicts DSR/PBO, the family is held for Director review
rather than automatically promoted.

## 8. F6 duplication / common-factor clustering

For F4/F5 pass candidates:
- calculate pairwise Pearson correlation of exact daily normalized returns on
  common valid Development days;
- create an undirected duplicate/common-factor edge when absolute correlation
  >= 0.80;
- connected components form the v1 common-factor clusters.

Also report:
- signal/exposure overlap where available;
- same-family/neighbor relationship;
- mechanism identity.

Correlation clustering does not claim causal independence.

## 9. Representative selection inside cluster

Only candidates already passing all hard F0-F5 gates are eligible.

One representative per cluster is selected lexicographically by:

1. higher stress median per-symbol normalized return;
2. higher minimum fold stress return;
3. lower maximum normalized drawdown;
4. lower turnover;
5. fewer free parameter dimensions;
6. lexicographically smaller canonical candidate ID.

No weighted score.

No failed hard gate can be rescued by cluster ranking.

## 10. Cross-family independence

Representatives from different family labels are not automatically independent.

The same correlation clustering applies across the entire pass set.

Report:
- raw candidates;
- F0-F3 passers;
- F4 passers;
- F5 passers;
- common-factor clusters;
- cluster representatives;
- independent mechanism hints.

## 11. F7 exact survivor freeze

Before Development survivor state:
- representative exact result recomputed from canonical data;
- candidate spec SHA reverified;
- universe/evidence/cost SHAs reverified;
- MCF-04 statistical artifact SHAs frozen;
- no parameter mutation;
- no replacement by a nearby candidate after seeing later evidence.

State becomes:
`DEVELOPMENT_SURVIVOR_FROZEN`

Only these frozen representatives may approach AF-08 Fresh OOS.

## 12. Zero survivor is valid

No quota, top-k, or minimum accepted count.

If all candidates fail:
`MCF_PROD_001_NO_DEVELOPMENT_SURVIVORS`

This is a valid canonical outcome.

## 13. Negative evidence

Retain:
- every F0-F3 result;
- neighbor failures;
- statistical failures;
- family PBO;
- DSR;
- cluster assignments;
- source/data blockers.

No failed candidate is removed from trial-count denominators.

## 14. Implementation gate

MCF-04 code and tests must be accepted before MCF-PROD-001 performance is
exposed.

The canonical MCF-PROD-001 run must not be used to debug statistical thresholds.
