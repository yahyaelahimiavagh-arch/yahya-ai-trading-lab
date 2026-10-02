# IB-002 — Statistical Multiplicity & Overfit Guard Contract v1.0

Date: 2026-09-30  
Status: **IMPLEMENTATION CANDIDATE / PRE-OUTCOME ONLY**  
Generation: `MCF-PROD-001`  
Baseline main at start: `21aa64e774f54b0399c561dab3f33e47d17630ff`

## Purpose

MCF-PROD-001 contains thousands of frozen candidate variants. A large search
space guarantees that some candidates will look strong by chance even when no
true edge exists. Data integrity alone does not solve this selection problem.

IB-002 adds a statistical guard layer that is frozen **before** the full
Development performance batch is exposed.

This work unit does not authorize:
- the complete 6,852-candidate performance batch;
- survivor selection;
- Fresh OOS;
- recent reserve;
- P10 read/write;
- P11;
- live or order execution.

## Primary references

The contract is based on:

1. Benjamini & Hochberg (1995), *Controlling the False Discovery Rate: A
   Practical and Powerful Approach to Multiple Testing*.
   DOI: https://doi.org/10.1111/j.2517-6161.1995.tb02031.x

2. Bailey & López de Prado (2014), *The Deflated Sharpe Ratio: Correcting for
   Selection Bias, Backtest Overfitting, and Non-Normality*.
   DOI: https://doi.org/10.3905/jpm.2014.40.5.094

3. Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest
   Overfitting*.
   DOI: https://doi.org/10.21314/JCF.2016.322

The implementations are standard-library only and deterministic.

---

## Scientific position

The batch must not ask:

> Which candidate has the highest return?

before it asks:

> How much apparent performance should we expect from chance after trying
> thousands of variants?

The multiplicity layer therefore treats the **entire frozen candidate search**
as part of the experiment.

For MCF-PROD-001 the conservative trial count is the full executable count:

`N = 6,852`

No effective-trial discount is allowed for this generation.

Even if IB-003 later demonstrates strong correlation among candidates, that
finding must not be used retroactively to reduce the MCF-PROD-001 DSR trial
count after outcomes have been observed. A dependency-based effective trial
count may only be used in a future pre-registered generation.

---

## Pre-outcome multiplicity manifest

Before any full-batch economic output is revealed, YATL freezes a metadata-only
manifest from:

- exact executable candidate IDs;
- family;
- economic mechanism;
- timeframe;
- free-parameter dimension count;
- frozen one-step parameter-neighbor graph.

The manifest contains no return, PnL, trade count, Sharpe, rank, pass/fail or
survivor information.

Required state:

`PRE_OUTCOME_MULTIPLICITY_FROZEN`

Required fields include:

- candidate count;
- conservative trial count;
- family counts;
- economic-mechanism counts;
- timeframe counts;
- free-parameter-dimension distribution;
- directed neighbor-edge count;
- FDR method;
- DSR trial-count policy;
- PBO completeness policy;
- safety flags;
- content hash.

Any candidate/neighbor identity mismatch blocks later statistical adjudication.

---

## Guard 1 — False Discovery Rate

### Primary procedure for MCF-PROD-001

The primary correction is:

**Benjamini–Yekutieli (BY), global across all 6,852 candidate hypotheses.**

Reason:

Candidates are intentionally correlated through:
- shared market data;
- shared economic mechanisms;
- common timeframes;
- adjacent parameter vectors;
- common universe membership.

Classical BH is more powerful, but its guarantees depend on a suitable
dependence structure. That structure has not yet been audited.

Therefore:

- MCF-PROD-001 uses BY as the production FDR correction;
- BH may be calculated only as a diagnostic;
- BH cannot replace BY for this generation;
- a future generation may use BH only if dependency assumptions are frozen
  before performance.

### Candidate p-value

For each candidate, the one-sided null is:

`H0: periodic Sharpe <= 0`

The p-value is derived from the Probabilistic Sharpe Ratio using the candidate's
Development daily-return series.

The statistical guard deliberately uses **periodic daily Sharpe**, not a
presentation-only annualized Sharpe, so the sampling formula is applied in the
same observation units used for skewness, kurtosis and sample size.

### Admission threshold

Primary global FDR threshold:

`BY adjusted p <= 0.05`

Passing BY is necessary but not sufficient for survival.

Family/timeframe BY tables may be emitted as diagnostics but cannot override a
global BY failure.

---

## Guard 2 — Deflated Sharpe Ratio

DSR asks whether the candidate Sharpe exceeds the level expected from the best
result of a large search under a null of no skill.

The null Sharpe threshold uses:

- the observed cross-trial dispersion of periodic Sharpes;
- the frozen trial count of **6,852**;
- the candidate return skewness;
- Pearson kurtosis;
- candidate observation count.

Required probability threshold:

`DSR probability >= 0.95`

The candidate must pass both:
- global BY FDR;
- DSR.

Neither can rescue failure of the other.

### No trial-count shrinkage

For MCF-PROD-001:

`conservative_trial_count = 6,852`

is immutable.

It is illegal to:
- count only survivors;
- count only the candidate's local neighbors;
- count only one family;
- estimate a smaller independent-trial count after seeing performance;
- remove losing/failed trials from the DSR population.

The Sharpe population used to estimate cross-trial dispersion must contain
**exactly 6,852 entries**, one for every frozen executable candidate, under the
same Development accounting contract. A partial Sharpe population is invalid
even if `conservative_trial_count` is still written as 6,852.

For batch orchestration, a candidate with a flat/undefined return series is not
deleted from the experiment. The frozen convention is:

- candidate statistical admission: **FAIL / NO EVIDENCE**;
- global FDR p-value contribution: `1.0`;
- cross-trial DSR dispersion value: periodic Sharpe `0.0` **for population
  accounting only**.

This convention prevents inactive/undefined trials from being dropped after
outcomes are known. It does not permit that candidate itself to pass DSR or any
economic gate.

---

## Guard 3 — Probability of Backtest Overfitting

PBO/CSCV tests whether the variant selected as best in one subset of time tends
to fall below the median out of sample.

### Scope

PBO is applied within the frozen:

`family × timeframe`

variant panel after the already-preregistered F1 activity/evaluability gate.
F1 may remove candidates that cannot form a meaningful return comparison, but
it may not filter on return sign, Sharpe, rank or any later profitability
measure before the PBO panel is constructed.

This scope tests hyperparameter/variant selection among economically comparable
candidates rather than mixing unrelated mechanisms and different bar cadences.

### Panel construction

PBO input must be a complete rectangular matrix:

- rows = common Development daily observations;
- columns = all candidates in the frozen family/timeframe scope;
- no missing values;
- no imputation;
- no forward fill;
- no interpolation;
- no source-gap bridging.

The common observation set is the strict timestamp intersection.

A panel that cannot meet the completeness requirement returns
`PBO_NOT_APPLICABLE`; it must never silently repair data.

### Block rule

The CSCV block count must be frozen from data availability only, never outcome.

Later orchestration must use a deterministic rule such as:
- candidate even block counts from a pre-registered set;
- choose using common observation count only;
- require equal-size contiguous blocks;
- require a minimum block length;
- reject if the split count exceeds the frozen compute ceiling.

The statistical utility itself requires an explicit pre-registered even
`block_count` and rejects non-divisible panels.

### Interpretation

Hard stop:

`PBO > 0.50`

A value above 0.50 means the in-sample winner lands at or below the OOS median
more often than not.

For this generation:
- PBO <= 0.50 is necessary for any candidate selected from that scope;
- PBO is not by itself proof of alpha;
- lower PBO does not waive BY, DSR, cost, fold or later Fresh OOS gates.

---

## Existing MCF gates remain authoritative

IB-002 does not replace F0-F3 or later planned gates.

A candidate can be statistically significant and still fail because:
- too few trades;
- too few evaluable symbols;
- weak stress economics;
- poor fold consistency;
- excessive turnover;
- unacceptable drawdown;
- execution/capacity failure;
- later Fresh OOS failure.

Likewise, a candidate with positive Development economics cannot survive if it
fails the multiplicity guards.

---

## Required adjudication order after future full-batch authorization

No step below is authorized by this PR; this is the frozen future order.

1. Verify exact runner-input identity.
2. Verify exact 6,852-candidate result inventory.
3. Reject missing, duplicated or foreign result identities.
4. Verify every result belongs to Development and the frozen accounting engine.
5. Build the complete candidate daily-return inventory.
6. Compute one-sided Sharpe p-values for all candidates; undefined/flat
   candidates contribute p=1.0 and remain in the family size.
7. Apply **global BY at 0.05** across all 6,852 hypotheses.
8. Compute the complete 6,852-entry Sharpe population; undefined/flat
   candidates contribute the frozen population-accounting value 0.0 and cannot
   themselves pass statistical admission.
9. Compute DSR with `N=6,852`.
10. Build frozen family×timeframe common-return panels.
11. Run PBO/CSCV where applicable.
12. Combine IB-002 outcomes with existing MCF economic/stress/fold gates.
13. Preserve all failures and negative results.
14. Do not open Fresh OOS until a separate Director authorization.

No candidate parameter, threshold, family membership or search domain may be
changed after steps 6–12 and rerun on the same Development evidence.

---

## Fail-closed conditions

Statistical adjudication blocks on any of:

- missing candidate;
- extra candidate;
- duplicate candidate;
- candidate-spec mismatch;
- non-finite p-value or return;
- zero-variance return series where Sharpe is undefined;
- incomplete DSR trial population;
- trial count smaller than frozen count;
- malformed neighbor graph;
- PBO non-rectangular panel;
- PBO block-count mismatch;
- PBO computational split ceiling exceeded;
- post-outcome attempt to change the FDR method;
- post-outcome attempt to reduce the DSR trial count.

---

## Implementation in this work unit

Module:

`research/mass_candidate_factory/statistical_guard.py`

Implemented pure functions:

- `fdr_adjust(..., method="BY"|"BH")`
- `periodic_sharpe(...)`
- `probabilistic_sharpe_ratio(...)`
- `one_sided_sharpe_p_value(...)`
- `expected_maximum_sharpe(...)`
- `deflated_sharpe_probability(...)`
- `pbo_cscv(...)`
- `build_preoutcome_multiplicity_manifest(...)`

The module imports no external numerical package and performs no I/O.

Tests use synthetic data only.

---

## Relationship to IB-003

IB-003 will study:
- return correlation;
- mechanism similarity;
- parameter-neighbor redundancy;
- cluster structure;
- independent-edge count.

That work can improve **future** search design and portfolio construction.

For MCF-PROD-001 it must not weaken the already-frozen multiplicity penalty.

---

## Safety

Unchanged:

- PAPER / RESEARCH ONLY;
- LIVE_MASTER_LOCK=OFF;
- NO FUTURES;
- NO LEVERAGE;
- NO SHORT;
- NO LIVE EXECUTION;
- NO ORDER ENDPOINT;
- NO AI DIRECT EXECUTION;
- Fresh OOS unread;
- recent reserve unread;
- P10 read/write=false;
- P11 locked.

IB-002 adds statistical defenses. It grants no performance or capital authority.
