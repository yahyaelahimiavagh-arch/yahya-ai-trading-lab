# YATL MCF-01 — Family Manifest & Canonical Candidate Specification v1.0

Status: DESIGN FROZEN BEFORE GENERATOR IMPLEMENTATION
Established: 2026-09-27
Mode: CHAT_DIRECTOR
Safety: PAPER / RESEARCH ONLY | LIVE_MASTER_LOCK=OFF | P11 LOCKED

## 1. Purpose

MCF-01 defines the machine-readable contracts used by the Mass Canonical
Candidate Factory.

The generator must be able to create thousands to hundreds of thousands of
candidate specifications without creating handwritten strategy files.

Every generated candidate must be:
- deterministic;
- attributable to one economic mechanism/family;
- identifiable before outcome;
- bound to a frozen parameter domain;
- bound to a trial budget;
- bound to an evidence partition;
- reproducible from the same family manifest and generator version.

## 2. Family manifest identity

Each family manifest contains:

- manifest_schema;
- manifest_schema_version;
- family_manifest_id;
- family_manifest_version;
- alpha_family_id;
- economic_mechanism_id;
- common_factor_cluster_hint;
- origin_type;
- source_refs;
- tested_object_type;
- market_scope;
- data_dependencies;
- signal_template;
- entry_template;
- exit_template;
- sizing_template;
- parameter_domains;
- structural_constraints;
- cost_policy_ref;
- evidence_policy_ref;
- generation_budget;
- screening_policy;
- exact_recompute_policy;
- prohibited_adaptations;
- research_only;
- safety flags.

Manifest content is SHA-256 bound before generation.

## 3. Canonical candidate identity

Candidate ID format:

MCF-YYYY-GG-XXXXXX

The ID is assigned from deterministic manifest expansion order, not from
performance.

Candidate canonical identity binds:
- generator version;
- family manifest SHA-256;
- parameter vector;
- market/timeframe assignment;
- source/adaptation lineage;
- cost policy;
- evidence partition.

The candidate spec receives its own canonical SHA-256.

## 4. Parameter-domain types

Supported deterministic domains:

- ENUM
- INTEGER_RANGE
- DECIMAL_RANGE
- LOG_RANGE
- BOOLEAN
- FIXED
- DERIVED_DETERMINISTIC

A domain must define:
- field name;
- type;
- values or bounds/step;
- ordering;
- semantic role;
- whether it creates a distinct economic mechanism or only a parameter neighbor.

Randomized search is not the default.

If deterministic sampling is later used, the manifest must freeze:
- population;
- sample size;
- seed;
- sampling algorithm/version;
- ordering.

## 5. Structural constraints

Constraints execute before performance.

Examples:
- fast_window < slow_window;
- exit_window <= entry_window when required;
- lookback >= minimum history;
- scale <= 1.0;
- no negative quantity;
- no leverage;
- no short;
- no Futures;
- no forward-looking extrema;
- required data dependency admitted;
- parameter combination not duplicated.

Structurally invalid combinations receive an immutable pre-performance record
and do not consume an economic trial.

## 6. Signal / entry / exit / sizing separation

Every candidate spec must separately identify:

- signal_rule;
- entry_rule;
- exit_rule;
- sizing_rule;
- eligibility/regime_rule.

This prevents a sizing improvement from being mislabeled as signal alpha.

Attribution default:
- signal changed -> SIGNAL_ALPHA candidate;
- signal unchanged, exposure changed -> SIZING_ALPHA candidate;
- fill/execution logic changed -> EXECUTION_ALPHA candidate;
- only eligibility timing changed -> TIMING_ALPHA / conditional candidate.

## 7. Market scope

Candidate market scope must state:

- assets;
- quote assets;
- venue(s);
- timeframe(s);
- spot_only;
- directionality;
- universe policy ref.

A broad-universe candidate must reference the point-in-time universe policy.

No candidate may silently use current listings as historical constituents.

## 8. Data dependency binding

Allowed dependency labels include:

- PRICE_OHLC
- VOLUME
- TRADE_COUNT
- MULTI_ASSET
- MULTI_VENUE
- EXTERNAL_CONTEXT
- ORDER_BOOK
- ON_CHAIN
- NEWS_SENTIMENT
- MACRO_RELEASE

Every required dependency must be admitted before performance.

Unavailable required data causes:
BLOCKED_DATA / structural invalidation,
not silent substitution.

## 9. Generation budgets

Every family manifest defines:

- batch_generation_id;
- maximum_raw_candidates;
- maximum_valid_economic_trials;
- parameter_neighbor_accounting;
- hidden_trials_forbidden = true;
- post_outcome_expansion_forbidden = true;
- child_generation_requires_new_batch = true.

A later generation may explore a new neighborhood only with:
- a new generation ID;
- a new frozen manifest;
- a new trial budget;
- an allowed evidence partition.

## 10. Broad-discovery diversity gate

A broad discovery batch must declare:
- represented alpha families;
- represented economic mechanisms;
- expected common-factor clusters.

Broad batches are not allowed to consist almost entirely of a single trend
parameter family while being described as broad alpha discovery.

The batch manifest must report concentration by family and mechanism before any
performance outcome is read.

No survivor quota is imposed.

## 11. Screening vs exact recompute

A candidate may pass through two numerical layers:

### SCREENING
Fast deterministic evaluation.

### EXACT_RECOMPUTE
Canonical high-precision recomputation.

The screening layer must have:
- fixed numerical implementation/version;
- validated tolerance against exact results;
- no outcome-dependent tolerance changes.

Every candidate considered for survivor freeze must pass exact recomputation.

## 12. Canonical result states

At batch level, every candidate resolves to one of:

- STRUCTURALLY_INVALID
- DEVELOPMENT_FAIL
- DEVELOPMENT_INTERESTING_NOT_QUALIFIED
- DEVELOPMENT_GATE_PASS
- DUPLICATE_OR_REDUNDANT
- EXACT_RECOMPUTE_FAIL
- DEVELOPMENT_SURVIVOR

Later states live in Registry v2 and are not assigned by MCF-01.

## 13. Negative-evidence retention

All candidate results remain addressable.

The result ledger must retain:
- candidate_id;
- candidate_spec_sha256;
- result_state;
- failure reasons;
- trial-family identity;
- batch identity;
- result digest.

Failed candidates are never silently removed from denominators used for
multiple-testing accounting.

## 14. Family-level failure learning

Batch closeout must aggregate:
- failure count by reason;
- failure count by parameter region;
- opportunity starvation count;
- data-blocked count;
- duplicate/redundant count;
- positive-but-not-qualified count;
- survivor count.

This allows YATL to learn where search space is unproductive without retuning
the same evidence.

## 15. Initial family catalog

The initial broad catalog contains materially different starting families:

1. TREND_CROSSOVER
2. BREAKOUT_CHANNEL
3. SHORT_HORIZON_MEAN_REVERSION
4. CRASH_REBOUND
5. VOLUME_CONFIRMED_DIRECTION
6. VOLATILITY_CONDITIONED_EXPOSURE
7. SESSION_TIME_EFFECT
8. LIQUIDITY_CONDITIONED_ENTRY
9. RELATIVE_STRENGTH
10. LEAD_LAG
11. REGIME_CONDITIONAL_DIRECTION
12. MULTI_VENUE_DISLOCATION
13. PRICE_VOLUME_INTERACTION
14. SIMPLE_STATISTICAL_DEVIATION
15. SIZING_OVERLAY
16. EXIT_OVERLAY

Not every family is immediately executable.

Families whose required data is not admitted remain BLOCKED_DATA rather than
being approximated with unrelated inputs.

## 16. Initial calibration generation

The first calibration run should test the engine, not exhaust the search space.

Target:
approximately 1,000 valid canonical candidates distributed across multiple
executable families.

Goals:
- validate ID determinism;
- validate generator repeatability;
- benchmark throughput;
- validate feature caching;
- validate result-ledger completeness;
- compare screening versus exact recompute on a bounded sample;
- validate multiple-testing counters.

The batch does not need to produce any survivor.

## 17. 10k expansion gate

Expansion to approximately 10,000 candidates requires:
- exact same input manifest -> exact same candidate IDs/spec SHAs;
- no missing result rows;
- deterministic repeat run on calibration sample;
- bounded runtime/storage;
- exact-recompute agreement;
- valid family/effective-trial accounting;
- no sealed evidence read.

## 18. 100k expansion gate

Expansion to up to approximately 100,000 candidates requires:
- 10k gate accepted;
- sharded restart/recovery proven;
- result ledger can reconcile all shards;
- memory/storage within operational limits;
- effective-trial accounting implemented;
- duplicate/neighbor clustering implemented;
- exact recompute pipeline implemented;
- broad family diversity preserved.

## 19. No same-evidence adaptive search

After a batch outcome is exposed:
- do not add parameter neighbors to that same batch;
- do not change hard filters to rescue winners;
- do not regenerate IDs;
- do not hide failed trials.

A new adaptive generation is allowed only under a new generation ID and an
explicit evidence policy.

## 20. Execution routing

MCF-01 design: CHAT_DIRECTOR.

MCF-02 reusable generator implementation:
WORK_REQUIRED only once the implementation scope is substantial enough to
justify it.

Candidate generation and batch execution:
deterministic runtime / VPS, not interactive Work per candidate.

## 21. Safety boundary

All candidates inherit:
- PAPER / RESEARCH ONLY;
- Spot only;
- no leverage;
- no short in the current path;
- no Futures;
- no Live;
- no order endpoint;
- no AI direct execution;
- P10 independent;
- P11 locked.

A family manifest cannot weaken these defaults.
