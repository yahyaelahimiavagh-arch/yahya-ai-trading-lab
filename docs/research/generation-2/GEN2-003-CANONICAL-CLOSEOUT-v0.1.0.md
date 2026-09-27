# GEN2-003 Canonical Closeout — Downside Volatility Scaling

Status: **CANONICAL COMPLETE / ZERO PROPOSALS**

Protocol: `GEN2-003-DOWNSIDE-VOL-SCALING-001`  
Protocol SHA-256: `2821e5dbcbdbb503ba7e68627ef3eeee1454f9ee268d5af2a5cc564954d5c3bc`  
Implementation: `GEN2-003-DOWNSIDE-VOL-SCALING/0.1.0`  
Canonical artifact SHA-256: `c9e864aa24e4b722671001af42f2165e608078fe7865bebdc02f8d26d4fa2255`

## Outcome

The single canonical Development run returned **FAIL / 0 proposals**.

Registered failures:
- opportunity-preservation gate failed on all six reference strategies;
- downside base economics did not exceed the total-volatility comparator;
- downside stress economics did not exceed the total-volatility comparator.

The opportunity diagnostic shows that all six opportunity failures had the same
exact subreason:

`VALID_SCALE_DECISION_FRACTION_LOW`

No directional starvation was observed:
- entry-signal counts remained identical to control;
- completed directional trade counts remained identical to control;
- no active-hours starvation reason fired;
- no notional-exposure starvation reason fired.

Valid-new-scale-decision fractions were approximately **34.5% to 44.8%**, below
the frozen 50% minimum. Each reference therefore relied on carried scales more
often than the protocol allowed for promotion.

## Economics

Aggregate net PnL after registered costs:

| Condition | Base | Stress |
|---|---:|---:|
| Control | 114.389535 | 75.652663 |
| Downside-vol scaler | 139.780885 | 103.740974 |
| Total-vol comparator | 149.160683 | 114.987609 |

Relative to control:
- downside-vol: about **+22.20% base / +37.13% stress**;
- total-vol: about **+30.40% base / +51.99% stress**.

Relative to total-vol, downside-vol was about:
- **-6.29% base**;
- **-9.78% stress**.

The downside condition nevertheless had:
- positive median base delta vs control;
- positive median stress delta vs control;
- negative median drawdown delta vs control;
- all 6/6 references with non-worse drawdown;
- activation on 6/6 references;
- 274 scaled entry/rebalance events.

## Blind-Spot classification

Primary failure classification: **REDUNDANT_EDGE**

Why:
the registered incremental claim was not merely “volatility sizing can help.”
It specifically required downside-volatility sizing to outperform both control
and the source-style total-volatility comparator. That incremental advantage was
not observed; the simpler comparator was stronger in both base and stress
economics.

Secondary mechanism:
**ESTIMATOR_AVAILABILITY_LIMITATION**

The downside estimator frequently could not produce a new valid scale under the
frozen rules, so the strategy relied on carried scales too often to satisfy the
registered reliability gate.

## What failed

- downside-specific superiority over total volatility;
- the 50% minimum valid-new-scale-decision fraction.

## What did not fail

- directional signal preservation;
- completed directional trade preservation;
- aggregate economics versus unscaled control;
- median base/stress improvement versus control;
- median drawdown improvement versus control;
- 6/6 non-worse drawdown references.

Therefore this result must **not** be summarized as “volatility sizing does not
work” or “the six underlying trend strategies have no edge.”

## Salvage review

Result:
**OBSERVATION RETAINED / NO POST-HOC PROMOTION**

The total-volatility comparator is economically interesting, but it was a
registered comparator rather than the selection-eligible GEN2-003 candidate.
It cannot be promoted after seeing this outcome.

Forbidden on the same evidence:
- lowering the 0.50 valid-scale threshold;
- changing estimator availability rules;
- trying an alternate downside estimator;
- promoting the total-vol comparator post hoc;
- rerunning GEN2-003 for selection;
- any hidden target/window/EWMA/fixed-weight variant.

A future volatility-sizing hypothesis may exist only as a new candidate/protocol
with a fresh evidence budget.

The separate hypothesis that the six underlying trend survivors may be
`REGIME_CONDITIONAL_EDGE` remains **untested** by GEN2-003.

## Evidence boundary

- Fresh OOS: not read
- recent reserve: not read
- P10: not read/written
- P11: locked
- Live: unauthorized

## Queue consequence

GEN2-003 is closed as negative evidence.

The research queue may advance to the next previously registered eligible
candidate/source work. RIE-CAND-0028 remains the next pre-existing regime-aware
candidate to assess; its existence predates this outcome, so advancing to it is
not a post-outcome invention.

Before any performance run for 0028:
- exact source method must be reproduced;
- state canonicalization, training/update window, feature set, and exposure map
  must be frozen;
- conditional-edge detector metrics from the Blind-Spot governance must be
  incorporated where applicable.
