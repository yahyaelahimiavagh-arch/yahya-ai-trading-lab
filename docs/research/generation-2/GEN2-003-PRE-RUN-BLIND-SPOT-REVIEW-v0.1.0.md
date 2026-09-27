# GEN2-003 Pre-Run Blind-Spot Review v0.1.0

Status: CLOSED_BEFORE_DEVELOPMENT_OUTCOME
Established: 2026-09-27
Protocol: GEN2-003-DOWNSIDE-VOL-SCALING-001
Protocol SHA-256: 2821e5dbcbdbb503ba7e68627ef3eeee1454f9ee268d5af2a5cc564954d5c3bc
Implementation: GEN2-003-DOWNSIDE-VOL-SCALING/0.1.0

This review is interpretation/governance only. It does not mutate the frozen
protocol, trial matrix, gates, data windows, parameters, or implementation.

## 1. Research claim under test

GEN2-003 tests whether a lagged downside-volatility sizing overlay improves
after-cost economics and drawdown behavior across the frozen correlated
Generation-1 trend family, while outperforming a source-style total-volatility
comparator and preserving directional opportunity.

It does NOT test:
- whether the six survivors are six independent edges;
- whether the trend family is ALL_REGIME certified;
- whether a conditional regime detector works;
- whether the strategy is capacity-scalable;
- whether the edge generalizes across venues or quote assets;
- whether the strategy is Live ready.

## 2. Blind-spot conclusions before outcome

### A. Correlated-family interpretation

The six frozen survivors are highly correlated members of one trend family.
Passing across them is family-level robustness evidence for the sizing overlay,
not six independent confirmations.

No blocker to Development run.

### B. Conditional-edge interpretation

The new Blind-Spot / Conditional-Edge governance does not retroactively change
GEN2-003.

If GEN2-003 fails:
- do not classify the underlying trend family as NO_EDGE solely from this result;
- classify what actually failed: the registered downside-volatility sizing
  adaptation and its claim;
- a future REGIME_CONDITIONAL_EDGE hypothesis is allowed only under a new
  candidate ID, new preregistered operating envelope/detector, and fresh
  evidence budget.

If GEN2-003 passes:
- do not infer ALL_REGIME certification;
- do not infer that crisis/regime weakness of the underlying family is solved;
- the result remains sizing/risk-layer Development evidence.

No blocker to Development run.

### C. Opportunity-starvation risk

The frozen protocol explicitly prevents qualification by simply not trading:
- directional entry signals must equal control;
- completed directional trades must equal control;
- active exposure hours fraction must be at least 1.0 of control;
- notional exposure ratio must be at least 0.25 of control;
- valid new scale decision fraction must be at least 0.50.

This materially addresses the principal starvation blind spot.

No blocker.

### D. Comparator fairness

The total-volatility comparator and downside-volatility candidate use:
- the same frozen reference strategies;
- the same Development corpus;
- the same monthly update semantics;
- the same expanding normalization convention;
- the same no-leverage cap;
- the same fee/slippage execution model.

The comparator is fit for the registered incremental question.

CASH / Buy-and-Hold are not required to answer the narrow sizing-overlay
question because CONTROL_UNSCALED is the relevant causal baseline. Broader
benchmarking remains required downstream for strategy-level claims.

No blocker.

### E. Gross estimator vs after-cost adjudication

The volatility estimator intentionally uses gross control mark-to-market returns
without fees/slippage, while economics are adjudicated after costs.

This is source-motivated and frozen. It means a positive result should be
attributed to the sizing rule under the registered estimator, not to a
cost-aware risk estimator.

No blocker; interpretation limitation recorded.

### F. Missing-data / stale-scale risk

Exposed gaps invalidate estimator months; missing estimators/constants carry the
previous valid scale, and carries are not counted as new observations.

The protocol reports:
- valid new scale decisions;
- carried decisions;
- unavailable estimator months;
- unavailable training-constant months;
- exposed gap days.

The minimum 0.50 valid-new-scale-decision fraction prevents a mostly stale
overlay from qualifying.

No blocker.

### G. Small expanding-window normalization

The first scored decision can be based on the preregistered minimum of six valid
historical managed-return pairs.

This is a potentially noisy early-sample assumption, but it was frozen before
outcome and was selected from the available warmup constraint, not from observed
GEN2-003 economics.

Per-fold reporting is mandatory. A protocol PASS must not be interpreted as
proof that the normalization is stable in every fold.

No blocker and no alternate warmup is authorized on the same evidence.

### H. Fold concentration

The proposal gate is aggregate/family-oriented and does not require every
Development fold to be individually profitable.

Per-fold metrics are nevertheless mandatory.

Therefore:
- a PASS means the preregistered GEN2-003 Development proposal gate passed;
- it does not mean every temporal regime is robust;
- downstream AF-05 / survivor-freeze adjudication must not erase severe fold
  concentration if observed;
- no new post-outcome fold threshold may be invented to rescue or reject this
  exact candidate using the same evidence.

No blocker.

### I. Multiple-testing context

GEN2-003 is registered as primary hypothesis ordinal 3 under a bounded
Generation-2 primary-hypothesis budget of 8, with hidden trials and post-outcome
budget expansion forbidden.

This limits but does not eliminate selection bias. Generation-level
multiple-testing accounting remains an AF-05 responsibility before broader
promotion.

No blocker to this single canonical Development run.

### J. Signal / sizing attribution

GEN2-003 cannot create or alter directional signals. Any improvement is
primarily attributable to SIZING_ALPHA / risk-layer behavior, subject to
execution costs.

A positive result must not be reported as discovery of a new directional alpha
signal.

No blocker.

### K. Capacity and market impact

The registered quantity is small and the cost model is linear. GEN2-003 does not
establish market-impact capacity or large-capital scalability.

Any PASS remains capacity-unproven until the appropriate capacity stage.

No blocker.

### L. Venue / quote-asset dependence

Development evidence is tied to the registered control corpus and its market
provenance. The run does not establish cross-venue or cross-quote robustness.

No blocker; claim scope remains bounded.

### M. Strategy decay

The Development window cannot establish persistence indefinitely into the
future. Decay monitoring remains a Forward/later-stage responsibility.

No blocker.

## 3. Pre-outcome interpretation lock

Before running GEN2-003, the following interpretation is frozen:

### If proposal gate PASS

Classification:
DEVELOPMENT_PROPOSAL_PASS

Evidence attribution:
SIZING_ALPHA / RISK_LAYER_EVIDENCE

It may proceed only to the next already-authorized adjudication stage. It does
not automatically unlock Fresh OOS, crisis certification, P10, P11, Tiny Live,
or Live.

### If proposal gate FAIL

Do not automatically label:
- the six underlying strategies NO_EDGE;
- the trend family unusable;
- conditional deployment impossible.

Required closeout:
- exact proposal-gate failure reasons;
- failure classification under the Blind-Spot governance;
- what failed / what did not fail;
- salvage review;
- any new conditional detector/envelope must become a new candidate/protocol.

### If structurally invalidated before economics

Classification:
IMPLEMENTATION_INVALIDATED, DATA_BLOCKED, or another exact structural class as
supported by evidence.

No economic conclusion may be inferred.

## 4. Authorization conclusion

PRE_RUN_BLIND_SPOT_REVIEW: PASS

No governance blocker was found that justifies mutating or cancelling the
already-frozen GEN2-003 protocol.

Next allowed evidence-spending action:
ONE canonical GEN2-003 Development run on the registered Development corpus,
Director-supervised / manual runtime only.

Fresh OOS remains sealed.
Recent reserve remains sealed.
P10 remains untouched.
P11 remains locked.
Live remains unauthorized.
