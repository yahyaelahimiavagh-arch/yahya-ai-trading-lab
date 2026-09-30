# RIE-006 — Current-Main Readiness + Deduplication Check 001

Work Unit ID: `RIE-006-IEI-CURRENT-MAIN-READINESS-DEDUPE-001`  
Status: **READINESS CHECK COMPLETE / NO MECHANISM PREREGISTRATION AUTHORIZED / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting authoritative state:
- current `main`: `8faaa84038aa1614a0964b35788390f949d18626`
- Research branch: `research-institutional-edge-intelligence`
- starting Research HEAD: `d2e7286666ef29f8b0a250985b37b39ff57f5d89`
- PR #152: OPEN / DRAFT / UNMERGED
- relation to current main: DIVERGED / Research 20 commits ahead / 108 commits behind
- merge base: `ce8e7b747f712779ed5e16144d74bda013226948`

No merge, rebase, force-push, history rewrite or lineage reconciliation is authorized or performed.

Boundary:
- PAPER / RESEARCH ONLY
- `LIVE_MASTER_LOCK=OFF`
- NO Futures execution / leverage / short / Live / order endpoint / AI execution
- no candidate returns, PnL, Sharpe, drawdown, outcome ranking or performance read
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED

## 1. Exact blocker this unit closes

The previous MECH-024 closeout required a bounded check of current `main` before
selecting any further RIE-006 mechanism because the Research branch is materially
behind main.

This unit asks only:

1. Has current-main AF-01C / MCF-PROD-001 work made the previously blocked
   `IEI-MECH-002` cross-sectional same-weekday mechanism data-admissible?
2. Does current main create a deduplication conflict that would make another
   RIE-006 test redundant?
3. Is any already-committed bounded RIE-006 mechanism ready for exact
   preregistration without spending more source/audit work?

It does not select by performance.

## 2. Current-main evidence inspected

Current main contains a newer production-readiness checkpoint than the Research
branch base.

Accepted state recorded on main includes:

- AF-01C P-C population state:
  `POPULATION_COMPLETE_WITH_SOURCE_GAPS`;
- 9,306 final archive identities;
- 6,443 successful archive identities;
- source gaps/anomalies retained as negative evidence;
- MCF-PROD-001 candidate/spec/neighbor freeze accepted before performance;
- 6,852 executable MCF-PROD-001 candidate identities frozen;
- production binding preflight added on current main.

The current MCF-PROD-001 binding preflight is explicitly pre-performance and
requires:
- >=60 days admitted history;
- >=99.5% trailing-30d 15m continuity at each UTC month start;
- independent historical product classification;
- lagged trailing-30d quote-volume ranking;
- fail-closed treatment of unresolved products.

Current `exchangeInfo` is explicitly rejected as historical classification
evidence.

The first documented real-P-C diagnostic recorded:
- 413 AF-01C symbols scanned;
- 34 month grid;
- 384 unresolved data-eligible symbols;
- state `CLASSIFICATION_INCOMPLETE`;
- no candidate performance read.

A classification-neutral top-50 liquidity frontier now exists only as diagnostic
evidence. It does not authorize membership.

## 3. IEI-MECH-002 readiness

AF-03D described MECH-002 as cross-sectional same-weekday seasonality requiring:
- PIT Spot listing/delisting universe;
- historical eligibility/liquidity;
- completed lagged observations;
- minimum-history rule;
- no future survival/delisting knowledge.

### What current main improves

The data-foundation blocker has materially narrowed.

Unlike the AF-03D checkpoint, current main now has:
- a reconciled historical archive population;
- explicit continuity/history rules;
- lagged liquidity machinery;
- a classification-neutral monthly ranking frontier;
- fail-closed historical product-classification semantics.

Therefore MECH-002 is no longer blocked merely because AF-01C acquisition is
unfinished.

### What remains unresolved

The exact historical ordinary-Spot membership is **not yet admitted**.

MCF-PROD-001 itself currently fails closed on historical product classification.
A classification-neutral ranking cannot be projected into an ordinary-Spot
cross-sectional universe.

Therefore RIE-006 must not:
- use current exchange membership backward;
- use unresolved products as ordinary Spot;
- independently invent a competing universe definition while main is already
  resolving the same PIT membership problem;
- preregister MECH-002 on an unfrozen cross-sectional universe.

Disposition:

`IEI-MECH-002 = DISTINCT_MECHANISM_CONFIRMED / ECONOMIC_RELEVANCE_PRE_OUTCOME_COMPLETED / BLOCKED_DATA_ON_CURRENT_MAIN_PIT_MEMBERSHIP / NOT_PREREGISTRATION_READY`.

## 4. Deduplication against current MCF

Current MCF has thousands of frozen executable candidate identities, but candidate
count is not independent-mechanism count.

The current Alpha Factory family map already contains:
- `AF-TIME` for session/weekday/month-boundary recurring time effects;
- `AF-RELATIVE` for cross-sectional/relative-strength/lead-lag mechanisms.

Therefore MECH-002 must not be represented as a new alpha family.

Its only potentially distinct economic specification is the **cross-sectional
same-weekday rank conditioned on a point-in-time eligible Spot universe**, not a
generic weekday effect and not a per-symbol calendar clone.

Before any future AF-04A preregistration, the exact frozen MCF candidate ledger on
then-current main must be checked for an equivalent cross-sectional weekday rule.
That check is deferred until the PIT membership blocker closes; doing a large
6,852-candidate comparison now would not change the current blocked-data decision.

No mechanism-count inflation is authorized.

## 5. ECONOMIC_RELEVANCE_PRE_OUTCOME — IEI-MECH-002

Status:

`PLAUSIBLY_MONETIZABLE_IF_EDGE_EXISTS`

Pre-outcome profile:
- monetization path: long/cash allocation among PIT-eligible liquid Spot assets,
  or cash when no preregistered eligible long exists;
- holding horizon: daily / multi-day calendar horizon, exact rule still requires
  preregistration;
- opportunity frequency: potentially recurring weekly across a cross-section,
  before any filter;
- likely turnover: moderate to potentially high if ranks rotate frequently;
- execution sensitivity: not latency-critical, but close/open convention and
  decision eligibility must be frozen;
- fee/slippage sensitivity: material because cross-sectional rotation can create
  more turnover than single-asset state signals;
- liquidity/capacity: must inherit PIT lagged-liquidity membership and later
  participation/cost constraints; illiquid historical winners cannot be used to
  manufacture deployable edge;
- YATL transferability: structurally compatible with Spot / long-cash / no
  leverage / no short if the universe and ranking are PIT-admissible;
- $10k / $100k: not obviously capacity-limited if restricted to the admitted
  liquid universe, but this is not established until membership and later cost
  evidence exist.

No ROI, expectancy or dollar-profit forecast is authorized.

## 6. IEI-MECH-021 status

No current-main evidence inspected in this bounded readiness check closes the
existing MECH-021 blocker around contemporaneous vesting schedules, historical
circulating-supply labels and versioned supply/holder classification.

Disposition remains:

`IEI-MECH-021 = BLOCKED_PIT_LABEL_AND_SNAPSHOT_PROVENANCE / NOT_PREREGISTRATION_READY`.

Do not start another unlock-data sweep merely because MECH-002 is waiting.

## 7. Cheapest falsification and stop condition

For MECH-002 the cheapest next falsification is **not** another RIE data audit.

Wait for current-main MCF-PROD-001 production binding to freeze exact historical
ordinary-Spot monthly membership.

Then, in one bounded CHAT_DIRECTOR check:
1. verify the frozen membership artifact is accepted on main;
2. compare MECH-002's exact economic fingerprint against the then-current frozen
   MCF candidate/family registry;
3. if duplicate, close `REJECTED_DUPLICATE`;
4. if distinct and the required lagged daily inputs are derivable from admitted
   data, move to exact AF-04A preregistration;
5. otherwise close/remain `BLOCKED_DATA`.

Stop condition now:

Until production binding reaches an accepted frozen PIT membership state,
**do not create another MECH-002 audit and do not preregister/test it**.

This prevents RIE-006 from duplicating the data-foundation work already active on
main.

## 8. Information-gain decision

This work unit materially advances the funnel by converting an outdated blocker:

`AF-01C acquisition not admitted`

into the narrower current blocker:

`historical ordinary-Spot product classification / frozen monthly membership not yet accepted`.

It also establishes that RIE-006 should not build a parallel universe pipeline.

No already-committed mechanism is ready for preregistration at this checkpoint:
- MECH-024: terminal `BLOCKED_DATA / ECONOMIC_TEST_NOT_AUTHORIZED`;
- MECH-021: blocked PIT label/snapshot provenance;
- MECH-002: materially closer, but blocked on current-main PIT membership;
- COT path: PIT original-version provenance not validated;
- FINRA/ETF path: original-version/inventory provenance remains unresolved;
- Spot-flow path: method specified but historical feed integrity/live
  observability remain unresolved.

Zero preregistration-ready mechanisms is accepted.

## 9. Next allowed action

Do **not** launch another source sweep.

The next RIE-006 action is conditional:

When current-main MCF-PROD-001 production binding freezes and accepts exact
historical ordinary-Spot monthly membership, run one bounded
`MECH-002 CURRENT-MAIN DEDUPE + PREREG READINESS` check.

Expected route: `CHAT_DIRECTOR` if it is a bounded comparison against a small
number of registry/family artifacts.

If resolving membership itself requires bulk acquisition/transformation, that
belongs to the current-main MCF/AF data track, not a parallel RIE work unit, and
its existing execution routing governs it.

No next work unit is executed automatically here.

## 10. Closeout

- Work Unit ID: `RIE-006-IEI-CURRENT-MAIN-READINESS-DEDUPE-001`
- execution mode: `CHAT_DIRECTOR`
- current main: `8faaa84038aa1614a0964b35788390f949d18626`
- starting Research HEAD: `d2e7286666ef29f8b0a250985b37b39ff57f5d89`
- PR #152: OPEN / DRAFT / UNMERGED
- Research divergence at start: 20 ahead / 108 behind
- exact blocker closed: stale assumption that AF-01C acquisition itself is still
  the MECH-002 blocker
- blocker remaining: accepted historical product classification + frozen PIT
  monthly membership on current main
- ECONOMIC_RELEVANCE_PRE_OUTCOME:
  `PLAUSIBLY_MONETIZABLE_IF_EDGE_EXISTS`
- mechanism moved materially toward test: YES, but remains blocked before
  preregistration
- Research bounded scope: YES
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next allowed action: conditional bounded MECH-002 dedupe/prereg-readiness check
  only after current-main PIT membership acceptance
- merge status: NO

**MERGED=NO**
