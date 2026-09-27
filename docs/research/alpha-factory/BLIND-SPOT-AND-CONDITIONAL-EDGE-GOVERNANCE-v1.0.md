# YATL Alpha Factory — Blind-Spot & Conditional-Edge Governance v1.0

Status: AUTHORITATIVE CROSS-CUTTING GOVERNANCE
Established: 2026-09-27

Purpose: prevent YATL from confusing “failed one gate” with “no economic edge,”
and create a systematic mechanism for discovering assumptions, missing tests,
over-restrictive gates, and conditional opportunities before they are silently
discarded.

This document does not authorize Live trading, retuning, hidden trials, or
reuse of sealed evidence. All existing safety and evidence locks remain binding.

## 1. Failure classification

Every economically meaningful rejection or structural invalidation must be
classified as one of:

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

A rejection on one evidence dimension is not automatically equivalent to
NO_EDGE. The classification is evidence bookkeeping, not permission to rescue
the same candidate on the same evidence.

## 2. Two economic deployment profiles

Every serious candidate must eventually declare one of:

### ALL_REGIME_EDGE

The candidate claims economic validity across its preregistered operating
regime set and must pass the ordinary Fresh OOS, crisis/regime, audit, Forward,
and capacity gates for that claim.

### REGIME_CONDITIONAL_EDGE

The candidate claims edge only inside a preregistered operating envelope.
Outside that envelope the objective is not necessarily profitability; it is
correct eligibility detection, bounded damage, capital preservation, and safe
re-entry behavior.

A conditional edge is not a weaker label assigned after seeing failure. Its
operating envelope, detector/gating logic, lag semantics, and safety behavior
must be preregistered in a new candidate/protocol before new evidence is used.

### UNKNOWN_EDGE_SCOPE

Default until sufficient evidence exists.

## 3. Conditional-edge certification

A REGIME_CONDITIONAL_EDGE may progress only if all of the following are tested:

1. In-envelope economics
   - positive after-cost economics on preregistered eligible regimes;
   - sufficient opportunity count;
   - no opportunity starvation.

2. Regime detector / eligibility gate
   - false activation rate;
   - false deactivation rate;
   - recognition lag;
   - missed-opportunity cost;
   - loss incurred before shutdown;
   - re-entry lag;
   - false re-entry count.

3. Out-of-envelope safety
   - capital survival;
   - bounded drawdown and exposure;
   - de-risk/kill response where applicable;
   - no hidden fallback, leverage, or short path.

4. Fresh evidence
   - envelope rules frozen before Fresh OOS;
   - Fresh OOS cannot be reused to invent or tune the detector.

5. Forward evidence
   - report eligible time;
   - ineligible time;
   - detector-unknown time;
   - missed eligible opportunities;
   - false eligible activations.

Crisis evidence therefore asks two different questions:
- ALL_REGIME_EDGE: does the edge itself survive required adverse regimes?
- REGIME_CONDITIONAL_EDGE: does the complete gated system recognize and contain
  adverse regimes safely while preserving its claimed in-envelope edge?

Failure of all-regime profitability alone does not prove absence of a
conditional edge.

## 4. Mandatory rejection review

Every meaningful rejection must close with:

- failure_classification;
- what_failed;
- what_did_not_fail;
- claim_that_was_disproved;
- claims_not_tested;
- possible_conditional_edge;
- possible_data_or_execution_artifact;
- salvage_review_result;
- new_candidate_required true/false.

Salvage review may create a new research question, but it may not alter the
failed candidate, retune against the same evidence, reopen sealed evidence, or
reuse a spent trial budget. New detector/envelope/threshold/sizing/combination
logic receives a new candidate ID and a new preregistered budget.

## 5. Blind-Spot / Assumption Audit

YATL maintains an explicit assumption ledger with this structure:

ASSUMPTION -> WHY WE BELIEVE IT -> WHAT IF FALSE? -> TEST -> EVIDENCE -> STATUS

Minimum audit domains:

- strategy edge assumptions;
- regime assumptions;
- data completeness and survivorship;
- venue/exchange dependence;
- stablecoin/quote-asset dependence;
- execution/slippage assumptions;
- turnover and capacity;
- market impact;
- signal-vs-sizing-vs-execution attribution;
- benchmark choice;
- multiple-testing and selection bias;
- opportunity starvation;
- opportunity cost of risk filters;
- detector delay;
- strategy decay;
- cross-strategy correlation/common-factor exposure;
- portfolio concentration;
- operational failure;
- model/feature leakage;
- timezone/session effects;
- liquidity-state dependence;
- capital scaling.

## 6. Required red-team questions

At designated checkpoints the Director must ask:

- What assumption are we treating as fact without direct evidence?
- Which gate could be rejecting a useful conditional edge?
- Which gate can be gamed by not trading?
- Are we rewarding robustness by eliminating opportunity?
- Is a positive result merely the best survivor of too many trials?
- Is the result signal alpha, sizing alpha, execution alpha, or market beta?
- Would CASH, Buy-and-Hold, or a simple frozen baseline explain most of it?
- Does the edge exist beyond one venue/quote asset/liquidity state?
- Could the strategy be decaying?
- Does it survive realistic costs at the capital size we care about?
- What would a skeptical external quant challenge first?
- What evidence would falsify our current interpretation?

## 7. Multiple-testing accounting

AF-05 must explicitly account for research breadth. Candidate count itself is a
selection-bias source.

Where technically appropriate and preregistered, the toolkit may include:
- Deflated Sharpe Ratio;
- Probability of Backtest Overfitting / CSCV-style diagnostics;
- Reality-Check or superior-predictive-ability style benchmark correction;
- trial-count and effective-family accounting;
- neighbor robustness;
- exact recomputation.

No statistic is mandatory when its assumptions do not fit. The mandatory rule
is explicit multiple-testing accounting.

## 8. Benchmark ladder

Where applicable, candidate economics should be interpreted against:

- CASH;
- Buy-and-Hold;
- a simple frozen family-relevant baseline;
- unmanaged/control version;
- only then more complex alternatives.

Complexity must demonstrate incremental value.

## 9. Signal / sizing / execution attribution

Promoted candidates should identify whether improvement is mainly:

- SIGNAL_ALPHA
- TIMING_ALPHA
- SIZING_ALPHA
- EXECUTION_ALPHA
- DIVERSIFICATION_ALPHA
- MIXED_OR_UNRESOLVED

## 10. Strategy decay lifecycle

Historical acceptance is not permanent validity.

Future lifecycle:
DISCOVER -> VALIDATE -> FORWARD -> DEPLOY_CANDIDATE -> MONITOR ->
DECAY_WARNING -> RETIRE_OR_NEW_RESEARCH

This does not grant Live authority now.

## 11. Early capacity sanity check

Full capacity modelling remains AF-12. Development survivors should receive an
early coarse screen for obvious non-scalability so clearly unusable ideas do
not consume excessive downstream research budget.

## 12. Venue / quote-asset dependence

A future candidate must state whether its claim is venue-specific,
quote-asset-specific, cross-venue, or market-wide.

An exchange-specific microstructure edge can be valid, but its dependency,
capacity, and operational risk must be explicit.

## 13. Work-token conservation rule

Work mode is a scarce execution resource and must not be used by default.

Default CHAT_DIRECTOR tasks:
- governance;
- protocol design;
- candidate classification;
- assumption audits;
- rejection reviews;
- narrow source extraction;
- queue decisions;
- registry-policy design;
- Director reviews;
- small, localized documentation edits.

Escalate to WORK_REQUIRED only when at least one is materially true:
- substantial multi-file implementation;
- bulk dataset acquisition/transformation;
- large deterministic analysis;
- coordinated artifact generation across many files;
- repository-wide migration;
- testing/build workflows that materially benefit from Work execution.

A task being intellectually difficult is not enough to justify Work.

Before every Work gate the Director must first ask:
Can this be completed safely in CHAT_DIRECTOR without materially increasing
error risk or operational burden?

If yes, stay in chat.

Astra remains reserved for corpus-scale synthesis under the existing thresholds.

## 14. Current six-survivor interpretation

The six HSSE-004A survivors are not reclassified as approved conditional edges
merely because this governance exists.

Known evidence:
- high correlation and common-family behavior;
- earlier historical/OOS success;
- failure of the all-regime crisis/regime gate.

Correct current interpretation:
- not ALL_REGIME certified;
- REGIME_CONDITIONAL_EDGE remains an untested hypothesis;
- any operating envelope/detector must be a new preregistered candidate;
- prior crisis outcomes remain negative evidence;
- no Live or Tiny-Live authority is created.

## 15. Safety boundary

Nothing here changes:
PAPER / RESEARCH ONLY; LIVE_MASTER_LOCK=OFF; NO FUTURES; NO LEVERAGE; NO SHORT;
NO LIVE EXECUTION; NO ORDER ENDPOINT; NO AI DIRECT EXECUTION; P10 independent;
P11 LOCKED; Fresh OOS and recent reserve sealed; explicit merge authorization.
