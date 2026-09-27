# YATL Alpha Factory — Mass Canonical Candidate Factory v1.0

Status: DESIGN / AUTHORIZED DIRECTION
Established: 2026-09-27
Mode: CHAT_DIRECTOR for design; implementation may require WORK_REQUIRED once
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

Purpose: convert YATL from a candidate-by-candidate research workflow into a
high-throughput deterministic strategy discovery laboratory capable of
canonicalizing, evaluating, classifying, and filtering very large candidate
populations without weakening evidence discipline.

The software architecture should be capable of handling at least 100,000
candidate specifications over time. Research expansion remains staged and
budgeted; scale does not relax scientific controls.

## 1. Strategic shift

Old operating pattern:
- select one candidate;
- source/reproduce;
- implement;
- run;
- close;
- repeat.

New operating pattern:
- maintain source-driven and internally generated mechanism families;
- generate many bounded deterministic candidates from preregistered family
  manifests;
- canonicalize every candidate before outcome;
- execute Development evaluation in batches;
- retain every result, including negative evidence;
- classify failures;
- deduplicate correlated/near-identical variants;
- promote only survivors through stronger gates.

The six frozen HSSE survivors remain useful historical evidence, but YATL is no
longer architecturally centered on those six variants.

## 2. Scale target

Engineering target:
- support 100,000+ canonical candidate specifications without one branch, PR, or
  artifact file per candidate.

Research execution scale is progressive:
- calibration batch: approximately 1,000 candidates;
- expansion batch: approximately 10,000 candidates;
- large-scale batch: up to 100,000 candidates when throughput, storage,
  deterministic reproducibility, and multiple-testing accounting are proven.

These are capacity targets, not quotas for accepted survivors.

Zero survivors is always a valid outcome.

## 3. Candidate identity

Each generated candidate receives a stable canonical ID:

MCF-YYYY-GG-XXXXXX

where:
- MCF = Mass Candidate Factory;
- YYYY = research year;
- GG = generation/batch family;
- XXXXXX = deterministic ordinal.

Every candidate specification binds:
- family;
- economic mechanism;
- signal definition;
- entry rule;
- exit rule;
- sizing rule;
- timeframe;
- market scope;
- venue scope;
- parameter vector;
- cost model;
- evidence partition;
- parent/source lineage;
- trial-family identity;
- canonical spec SHA-256.

Candidate identity must not depend on outcome.

## 4. Candidate sources

Mass candidates may originate from:

### A. Source-derived canonical families
Exact or bounded adaptations of external methods.

### B. Mechanism-derived internal families
Simple economic mechanisms expressed as bounded deterministic strategy templates.

### C. Negative-evidence salvage children
New candidates motivated by prior failure, only when they receive:
- new candidate identity;
- new preregistration;
- new trial budget;
- fresh allowed evidence.

### D. Control/baseline families
Simple benchmark strategies used for causal comparison.

Mass generation must not become random formula mining detached from an economic
or market-structure mechanism.

## 5. Required family diversity

The factory must support materially distinct families, including at minimum:

- TREND
- BREAKOUT
- MEAN_REVERSION
- CRASH_REBOUND
- VOLUME_CONDITIONED
- VOLATILITY
- SESSION_TIME
- LIQUIDITY
- RELATIVE_STRENGTH
- LEAD_LAG
- REGIME_CONDITIONAL
- MULTI_VENUE
- PRICE_VOLUME_INTERACTION
- STATISTICAL_SIMPLE
- SIZING_OVERLAY
- EXIT_OVERLAY

Candidate count alone is not diversity.

Registry v2 must report:
- raw candidate count;
- effective parameter-neighbor count;
- economic mechanism count;
- common-factor cluster count;
- independent-family count.

## 6. No one-PR-per-candidate architecture

The factory must use:

- one family manifest/specification;
- deterministic candidate expansion;
- sharded batch execution;
- append-only result ledgers;
- content-addressed artifacts;
- batch-level PRs/checkpoints.

Do NOT create:
- 100,000 branches;
- 100,000 PRs;
- 100,000 hand-written strategy files.

A small number of reusable engines should execute large candidate matrices.

## 7. Deterministic candidate generator

A Mass Candidate Generator must:

1. read a frozen family manifest;
2. deterministically enumerate candidate parameter combinations;
3. reject invalid combinations before performance;
4. assign canonical IDs;
5. emit canonical candidate specs;
6. record generation manifest SHA;
7. never inspect performance while generating later candidates in the same
   frozen batch.

Required output:
- batch_id;
- family_id;
- candidate_count;
- invalid_preperformance_count;
- candidate ID range;
- generation manifest SHA;
- parameter-domain digest;
- source/parent lineage;
- trial-budget identity.

## 8. Candidate-generation rules

Allowed:
- bounded parameter grids;
- bounded categorical rule variants;
- preregistered combinations of independent mechanism components;
- deterministic sampled designs if seed/domain are frozen before outcome.

Forbidden:
- generating new parameter neighborhoods after seeing winners from the same
  evidence unless a new research generation/evidence budget is created;
- hidden retry;
- silent removal of failed candidates;
- outcome-conditioned candidate IDs;
- post-hoc rule mutation;
- generating thousands of mathematically different but economically identical
  aliases to inflate candidate count.

## 9. High-throughput execution engine

The evaluation engine should minimize repeated computation.

Preferred architecture:
- load canonical data once per shard;
- cache shared indicators/features;
- vectorize or batch common calculations where numerically safe;
- parallelize independent candidate shards;
- separate signal generation from cost/equity adjudication;
- deterministic Decimal/exact recomputation only for survivors when a faster
  screening representation is explicitly allowed and validated.

Two-stage numerical pattern may be used:

### SCREENING
High-throughput deterministic screening with validated numerical tolerances.

### EXACT_RECOMPUTE
Exact canonical recomputation for every candidate that crosses the screening
boundary.

No candidate may reach Fresh OOS based only on approximate screening output.

## 10. Throughput calibration before 100k

Before large-scale execution, benchmark:

- candidates/second;
- bars processed/second;
- peak RAM;
- artifact bytes/candidate;
- cache hit rate;
- CPU utilization;
- deterministic repeatability;
- exact-recompute cost;
- shard failure/recovery behavior.

Run scale expands only after the engine demonstrates that results are
deterministic and operationally tractable.

This is engineering calibration, not strategy selection.

## 11. Filter cascade

The Mass Factory uses a staged cascade so expensive tests are reserved for
survivors.

### F0 — Structural validity
Reject:
- lookahead;
- missing required data;
- impossible fills;
- invalid parameter ordering;
- zero/NaN/unsafe arithmetic;
- prohibited leverage/short/Futures;
- duplicate candidate spec.

### F1 — Minimum opportunity
Measure:
- signal count;
- trade count;
- exposure;
- turnover;
- eligible-time coverage.

Sparse strategies are allowed only when sparsity is part of the preregistered
mechanism, not as a way to avoid risk.

### F2 — After-cost Development economics
Base and stress costs.

### F3 — Temporal robustness
Per-fold/rolling/era decomposition.

### F4 — Neighbor stability
A candidate that wins only at one isolated parameter point is downgraded or
rejected.

### F5 — Multiple-testing correction
Account for:
- raw trials;
- effective correlated trials;
- family breadth;
- selection process.

Use appropriate tools such as DSR/PBO/Reality-Check-style diagnostics where
their assumptions fit.

### F6 — Duplication / correlation
Cluster highly similar candidates and common-factor clones.

### F7 — Mechanism survivor freeze
Freeze a small set of representatives per independent mechanism cluster.

### F8 — Fresh OOS
Only frozen survivors.

### F9 — Conditional/all-regime certification
Apply the appropriate claim:
- ALL_REGIME_EDGE;
- REGIME_CONDITIONAL_EDGE.

### F10 — Independent audit / Forward
Only after prior gates.

## 12. No fixed survivor quota

Never require:
- top 10;
- top 1%;
- best 100;
- any minimum accepted count.

Thresholds are evidence gates, not ranking quotas.

If all 100,000 candidates fail, result is:
NO QUALIFYING EDGE IN THIS SEARCH SPACE.

## 13. Family-aware multiple testing

100,000 raw candidates do not necessarily equal 100,000 independent trials.

The system must estimate/report:
- raw trial count;
- effective trial count;
- within-family dependence;
- cross-family dependence;
- number of parameter-neighbor clusters;
- number of economic mechanism clusters.

A candidate cannot receive stronger confidence merely because thousands of
near-duplicate variants were searched.

## 14. Ranking is secondary to gates

Ranking may be used only after minimum gates are met.

Preferred ordering among already-qualified candidates may consider:
- after-cost economics;
- drawdown;
- fold consistency;
- opportunity frequency;
- capacity;
- independence;
- simplicity;
- execution burden.

A high score cannot rescue a failed hard gate.

## 15. Conditional-edge preservation

A candidate failing all-regime robustness may be classified for a separate
conditional-edge research path when justified.

This does not rescue the same candidate.

A child conditional candidate requires:
- new ID;
- frozen operating envelope;
- frozen detector;
- false activation/deactivation metrics;
- recognition lag;
- missed opportunity;
- loss-before-shutdown;
- re-entry metrics;
- new evidence budget.

Thus the Mass Factory avoids discarding useful conditional mechanisms while
preserving scientific separation.

## 16. Negative evidence as an asset

Every canonical candidate result is retained.

The factory should be able to answer:
- which mechanisms repeatedly fail;
- which parameter regions are consistently weak;
- which families are redundant;
- which filters destroy opportunity;
- where data availability causes structural invalidation;
- which mechanisms only work conditionally.

This negative-evidence corpus becomes input to future research design.

## 17. Strategy breadth versus six-survivor fixation

The historical six HSSE survivors are one correlated trend cluster.

Mass Factory policy:
- they remain as reference/control evidence;
- they do not dominate candidate generation;
- no more than a bounded share of a broad discovery generation should come from
  one common-factor family unless that generation is explicitly family-specific;
- independent mechanisms take priority in broad discovery runs.

The objective is not to perfect six variants indefinitely.
The objective is to discover independent, scalable, after-cost opportunity.

## 18. Evidence partition acceleration

The following can be accelerated through compute:
- candidate generation;
- Development backtests;
- robustness decomposition;
- clustering;
- false-discovery diagnostics;
- historical crisis replay;
- exact recomputation;
- documentation/artifact generation.

The following cannot be compressed by compute:
- real future Forward observation time;
- future market regimes that have not happened yet;
- real execution experience;
- time-dependent operational reliability.

Therefore:
historical research that once took months manually may be compressed into a much
shorter engineering/research cycle, but Forward evidence remains calendar-time
evidence.

## 19. Research-calendar objective

YATL should optimize for:
- maximum high-quality hypotheses evaluated per unit time;
- minimum manual orchestration;
- deterministic reproducibility;
- strict evidence isolation;
- rich negative-evidence retention.

It should not optimize for:
- maximum raw backtest count alone;
- fastest path to a positive-looking chart;
- survivor quotas;
- repeated use of the same evidence until something passes.

## 20. Execution modes

### CHAT_DIRECTOR
Use for:
- family design;
- trial budgets;
- filter definitions;
- blind-spot audits;
- result classification;
- batch closeout;
- queue decisions.

### WORK_REQUIRED
Use only when materially useful for:
- building the reusable Mass Candidate Engine;
- major multi-file implementation;
- bulk data ingestion;
- heavy test/build integration.

Do not use Work per candidate.

### MANUAL_VPS / BATCH_RUNTIME
Use for:
- large canonical historical batch runs;
- benchmark/throughput runs;
- exact-recompute jobs.

### ASTRA
Use only when corpus-scale synthesis thresholds fire, e.g. large source,
candidate, failure, or survivor corpora.

## 21. Initial implementation sequence

MCF-00 — Governance and architecture
- this document;
- Master Plan integration;
- stage-gate integration.

MCF-01 — Family manifest schema
- candidate spec schema;
- family parameter domains;
- canonical ID rules;
- trial-budget identity.

MCF-02 — Generator
- deterministic expansion;
- dedupe;
- structural validation.

MCF-03 — Batch screening engine
- shared feature cache;
- sharding;
- F0-F3.

MCF-04 — Multiple-testing / neighbor / cluster analytics
- F4-F6.

MCF-05 — Survivor freeze
- representative mechanism survivors;
- exact recompute.

MCF-06 — Fresh OOS handoff
- only frozen survivors.

## 22. Initial research scale

The first broad generation should be diverse rather than enormous.

Recommended engineering progression:
- validate engine on approximately 1,000 candidates;
- expand to approximately 10,000 after deterministic/throughput acceptance;
- allow up to 100,000 only after family diversity, effective-trial accounting,
  storage, and exact-recompute paths are proven.

This is not a requirement to stop at 100,000; architecture should avoid a hard
candidate-count ceiling.

## 23. Safety boundary

Unchanged:
- PAPER / RESEARCH ONLY;
- LIVE_MASTER_LOCK=OFF;
- NO FUTURES;
- NO LEVERAGE;
- NO SHORT in the current path;
- NO LIVE EXECUTION;
- NO ORDER ENDPOINT;
- NO AI DIRECT EXECUTION;
- P10 independent and untouched by Development;
- P11 LOCKED;
- Fresh OOS sealed until survivor freeze;
- recent reserve sealed.

Mass scale never relaxes safety or evidence locks.
