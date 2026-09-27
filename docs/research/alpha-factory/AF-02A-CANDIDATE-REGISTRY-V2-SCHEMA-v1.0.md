# YATL Alpha Factory — AF-02A Candidate Registry v2 Schema v1.0

Status: DESIGN FROZEN BEFORE AF-02B MIGRATION
Established: 2026-09-27
Mode: CHAT_DIRECTOR

Purpose: define a candidate registry that measures economic diversity, preserves
negative evidence, separates source reproduction from YATL adaptation, and
prevents status labels from silently granting performance or Live authority.

This document is schema policy only. It does not migrate the legacy registry and
does not authorize any performance run.

## 1. Design principles

Registry v2 must make these questions answerable without opening outcome files:

- What economic mechanism is being tested?
- What source, if any, motivated it?
- Is the source method actually reproduced?
- Is the YATL adaptation fully specified?
- What data dependencies are required?
- What evidence has been spent?
- What evidence remains sealed?
- Is the candidate all-regime, conditional, or scope-unknown?
- Is it independent from existing mechanisms or merely a correlated variant?
- What exactly failed if it was rejected?
- Can it progress without guessing a missing rule?

No status alone grants:
- performance authorization;
- Fresh OOS access;
- Forward promotion;
- P11/Tiny-Live/Live authority.

Those are separate explicit fields/gates.

## 2. Identity

Required fields:

- candidate_id
- schema_version
- created_at_utc
- origin_type
- title
- short_hypothesis

Allowed origin_type:
- EXTERNAL_SOURCE
- INTERNAL_HYPOTHESIS
- NEGATIVE_EVIDENCE_SALVAGE
- PORTFOLIO_COMBINATION
- CONTROL_BASELINE

A salvage-origin candidate must reference the closed parent candidate but may not
rewrite it.

## 3. Source layer

Required structure:

source:
- source_id
- source_type
- title
- authors
- publication_date
- doi_or_uri
- source_tier
- source_bytes_frozen
- implementation_found
- performance_claims_are_yatl_evidence = false

source_method_state:
- UNASSESSED
- SOURCE_BOUND
- SOURCE_METHOD_SPECIFIED
- BLOCKED_SOURCE
- BLOCKED_REPRODUCIBILITY

The source method state must not imply that a YATL adaptation is ready.

## 4. Source-to-YATL adaptation layer

Separate required structure:

adaptation:
- adaptation_required
- adaptation_state
- tested_object_id
- protocol_ref
- source_replication_claim
- source_to_yatl_gaps
- frozen_choices
- unresolved_choices

Allowed adaptation_state:
- NOT_REQUIRED
- NOT_STARTED
- DESIGN_IN_PROGRESS
- SPECIFIED
- PREREGISTERED
- IMPLEMENTED
- BLOCKED_ADAPTATION_SPECIFICATION

Rule:
a candidate cannot enter Development unless source method and adaptation state
together support a fully preregistered tested object.

RIE-CAND-0028 is the motivating example:
the published HMM method can be source-method-specified while the BTC/ETH
intraday YATL adaptation remains blocked.

## 5. Lifecycle state

Authoritative lifecycle states:

- DISCOVERED
- SOURCE_BOUND
- METHOD_SPECIFIED
- PREREGISTERED
- IMPLEMENTED
- DEVELOPMENT_EVALUATED
- REJECTED_NEGATIVE_EVIDENCE
- DEVELOPMENT_SURVIVOR
- FROZEN_FOR_OOS
- OOS_REJECTED
- OOS_SURVIVOR
- CRISIS_CERTIFIED
- INDEPENDENT_AUDIT_PASS
- FORWARD_CANDIDATE
- BLOCKED_SOURCE
- BLOCKED_DATA
- BLOCKED_REPRODUCIBILITY
- INVALIDATED_BEFORE_ECONOMICS

A separate progression_blocker field handles finer distinctions without
exploding lifecycle states.

Examples:
- ADAPTATION_NOT_FROZEN
- REQUIRED_DATA_NOT_ADMITTED
- SOURCE_RULE_MISSING
- IMPLEMENTATION_GATE_PENDING
- CI_NOT_GREEN
- SEALED_EVIDENCE_LOCKED
- NONE

## 6. Economic taxonomy

Required fields:

- alpha_family_id
- economic_mechanism_id
- edge_scope
- edge_attribution
- common_factor_cluster_id
- duplicate_of_candidate_id

edge_scope:
- UNKNOWN_EDGE_SCOPE
- ALL_REGIME_EDGE
- REGIME_CONDITIONAL_EDGE

edge_attribution:
- SIGNAL_ALPHA
- TIMING_ALPHA
- SIZING_ALPHA
- EXECUTION_ALPHA
- DIVERSIFICATION_ALPHA
- MIXED_OR_UNRESOLVED

The registry must be able to count independent mechanisms, not parameter
variants.

## 7. Market and data scope

Required fields:

market_scope:
- assets
- quote_assets
- venues
- venue_scope_type
- timeframes
- directionality
- spot_only

venue_scope_type:
- SINGLE_VENUE
- MULTI_VENUE
- VENUE_SPECIFIC
- MARKET_WIDE_UNTESTED

data_dependencies is a list drawn from:
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

Each dependency must also record:
- availability_state
- point_in_time_admitted
- provenance_ref

## 8. Opportunity and trading-profile metadata

Required pre-Development estimates:

- holding_horizon_class
- expected_opportunity_frequency
- expected_turnover_class
- expected_active_exposure_class
- capacity_sensitivity
- liquidity_sensitivity
- implementation_complexity

These are hypothesis metadata, not evidence.

After Development, observed fields may be added separately:
- observed_opportunity_count
- observed_turnover
- observed_active_exposure
- observed_capacity_warning

Expected and observed values must never overwrite each other.

## 9. Regime and conditional-edge fields

Required:

regime_hypothesis:
- NONE
- ROBUST_ACROSS_REGISTERED_REGIMES
- CONDITIONAL_ON_REGISTERED_ENVELOPE
- UNKNOWN

For conditional candidates:

conditional_edge:
- operating_envelope_ref
- detector_ref
- detector_state
- unknown_state_semantics
- false_activation_metric_required
- false_deactivation_metric_required
- recognition_lag_metric_required
- missed_opportunity_metric_required
- loss_before_shutdown_metric_required
- reentry_lag_metric_required
- false_reentry_metric_required

A conditional label without a preregistered envelope/detector cannot unlock
OOS.

## 10. Trial and multiple-testing accounting

Required:

trial_budget:
- research_generation_id
- hypothesis_family_id
- candidate_ordinal
- maximum_registered_trials
- trials_spent
- hidden_trials_forbidden
- post_outcome_expansion_forbidden

selection_bias:
- effective_family_id
- related_candidates
- multiple_testing_accounting_required
- accounting_ref

A candidate created after observing another candidate's outcome must record that
lineage explicitly.

## 11. Evidence ledger

Evidence entries are append-only.

Each entry contains:
- evidence_id
- stage
- artifact_ref
- artifact_sha256
- code_head_sha
- protocol_id
- protocol_sha256
- executed_at_utc
- outcome_state
- canonical
- evidence_partition
- read_boundaries
- p10_read
- p10_write
- fresh_oos_read
- recent_reserve_read

evidence_partition:
- DEVELOPMENT
- KNOWN_HISTORICAL
- FRESH_OOS
- CRISIS
- FORWARD_PAPER
- OTHER_REGISTERED

Negative evidence is never deleted when a candidate progresses or a child
candidate is created.

## 12. Failure and salvage ledger

If rejected or invalidated:

failure_closeout:
- failure_classification
- secondary_failure_mechanisms
- what_failed
- what_did_not_fail
- claim_disproved
- claims_not_tested
- possible_conditional_edge
- possible_data_or_execution_artifact
- salvage_review_result
- new_candidate_required
- child_candidate_ids

Allowed primary failure_classification:
- NO_EDGE
- CONDITIONAL_EDGE
- OVERFIT
- DATA_BLOCKED
- EXECUTION_LIMITED
- CAPACITY_LIMITED
- REGIME_MISMATCH
- REDUNDANT_EDGE
- IMPLEMENTATION_INVALIDATED
- INSUFFICIENT_EVIDENCE
- UNKNOWN_FAILURE_MECHANISM

GEN2-003 is the motivating example:
the exact downside-over-total claim can be REDUNDANT_EDGE while the broader
volatility-sizing observation remains preserved without post-hoc promotion.

## 13. Benchmark and attribution metadata

Before promotion, record:
- causal_control_candidate_id or control condition;
- CASH benchmark status where applicable;
- Buy-and-Hold benchmark status where applicable;
- simple family baseline status;
- incremental comparator identities.

A result must not be described as SIGNAL_ALPHA if the directional signal is
unchanged and improvement came from sizing/execution.

## 14. Capacity and venue dependence

Required fields:
- early_capacity_screen_state
- venue_dependency_state
- quote_asset_dependency_state
- market_impact_model_state

States may be:
- UNASSESSED
- LOW_RISK
- MATERIAL_DEPENDENCY
- BLOCKED
- DEFERRED_TO_AF12

This prevents a single-venue or tiny-capacity edge from being described as
generally scalable.

## 15. Strategy-decay lifecycle

For Forward-capable candidates:

decay_monitoring:
- baseline_window_ref
- monitored_metrics
- warning_state
- retirement_state
- last_review_utc

Possible warning_state:
- NOT_STARTED
- STABLE
- DECAY_WARNING
- STRUCTURAL_BREAK_SUSPECTED

Decay monitoring never retroactively changes historical evidence.

## 16. Authorization fields

Explicit booleans/locks:

- performance_run_allowed
- fresh_oos_read_allowed
- crisis_run_allowed
- forward_run_allowed
- p10_read_allowed
- p10_write_allowed
- tiny_live_candidate
- live_authorized
- ai_direct_execution_allowed
- order_endpoint_allowed
- leverage_allowed
- short_allowed

Current YATL defaults remain false unless an authoritative later gate explicitly
changes them.

A lifecycle status can never infer these booleans.

## 17. Immutability and mutation rules

Allowed:
- append evidence;
- append failure/salvage records;
- progress lifecycle state when gate evidence exists;
- add child-candidate references;
- correct clerical metadata with an auditable migration record.

Forbidden:
- overwrite canonical negative evidence;
- delete failed trials;
- change a frozen protocol identity after outcome;
- convert a comparator into a selected winner after seeing results;
- change source facts to match an adaptation;
- silently broaden asset/venue/timeframe claims.

## 18. Migration policy

AF-02B migrates the legacy registry without inventing missing facts.

For each legacy candidate:
- map known fields;
- mark unknown v2 fields UNKNOWN/UNASSESSED;
- preserve original source text;
- preserve existing candidate ID;
- preserve blockers;
- link canonical Generation outcomes where available;
- do not infer regime/capacity/independence from absent evidence.

The legacy registry remains a historical input snapshot.

AF-02B migration may stay in CHAT_DIRECTOR if the bounded migration can be
performed safely and validated deterministically. Escalate to Work only if the
migration becomes repository-wide/heavy enough that manual orchestration
materially increases error risk.

This explicitly supersedes any assumption that AF-02B automatically requires
Work.

## 19. Required registry queries

Registry v2 must support at minimum:
- candidates by lifecycle state;
- candidates by independent alpha family;
- candidates by economic mechanism;
- candidates by edge scope;
- candidates blocked by data/source/adaptation;
- negative-evidence count by failure classification;
- survivors by common-factor cluster;
- candidates requiring multi-venue data;
- candidates with capacity warnings;
- candidates whose source method is specified but adaptation is not;
- trial budget spent by generation/family;
- sealed evidence status;
- candidates eligible for the next gate.

## 20. AF-02A exit gate

AF-02A closes when:
- this schema policy is committed;
- no legacy evidence is rewritten;
- Execution Board points to AF-02B migration as next registry action;
- CI is green.

No performance evidence is spent by AF-02A.
