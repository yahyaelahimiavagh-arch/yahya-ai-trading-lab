# YATL Alpha Factory — Execution Board

Status date: **2026-09-27**
Mode: **PAPER / RESEARCH ONLY**
Authority: **LIVE_MASTER_LOCK=OFF / P11 LOCKED**

This board is the operational view of
`ALPHA-FACTORY-MASTER-PLAN-v1.0.md`. It should stay short and should always
answer four questions:

1. What is open now?
2. What is next?
3. What is locked?
4. What evidence closes the current checkpoint?

## Current position

### CLOSED — AF-00 Governance Closeout

Objective:
- establish Alpha Factory as the authoritative program layer;
- preserve all frozen Generation protocols;
- commit the machine-readable stage contract;
- obtain a green Final HEAD.

Artifacts:
- `docs/research/alpha-factory/ALPHA-FACTORY-MASTER-PLAN-v1.0.md`
- `docs/research/alpha-factory/ALPHA-FACTORY-STAGE-GATES-v1.0.json`
- authoritative summary in `docs/MASTER-PLAN.md`

Closeout gate:
- documents present and internally consistent;
- no mutation of frozen GEN2-MASTER-001;
- GitHub Actions green on Final HEAD.

### CANONICAL CLOSED — GEN2-001

State:
- stop overlay;
- 0 proposals;
- retained negative evidence;
- no same-evidence rescue.

### CANONICAL CLOSED — GEN2-002

State:
- volatility scaling;
- `INVALIDATED_BEFORE_ECONOMIC_EVALUATION`;
- 40 structurally incomplete estimator windows;
- 0 proposals;
- no same-evidence target/window/EWMA rescue.

## CLOSED — AF-03A Source Unblock Sprint

Closeout:
- `RIE-CAND-0011` → `BLOCKED_REPRODUCIBILITY`
- `RIE-CAND-0022` → `BLOCKED_SOURCE`
- `RIE-CAND-0027` → `METHOD_SPECIFIED`

AF-03A performed zero performance runs.

Because 0027's original source-method blocker is now resolved, the preregistered
availability-skip rule returns priority to 0027.

### CANONICAL CLOSED — GEN2-003 / RIE-CAND-0027

State:
- downside-volatility scaler vs total-volatility comparator;
- single canonical Development run complete;
- `FAIL / 0 proposals`;
- all six opportunity failures were `VALID_SCALE_DECISION_FRACTION_LOW`;
- directional entries/trades were preserved;
- downside scaling improved control economics and median drawdown;
- total-volatility comparator outperformed downside scaling in base and stress;
- primary Blind-Spot classification: `REDUNDANT_EDGE`;
- secondary mechanism: `ESTIMATOR_AVAILABILITY_LIMITATION`;
- no same-evidence rescue, threshold relaxation, estimator retune, or post-hoc
  total-vol promotion.

Canonical closeout:
- `GEN2-003-CANONICAL-RESULT-v0.1.0.json`;
- `GEN2-003-CANONICAL-CLOSEOUT-v0.1.0.md`;
- artifact SHA-256 `c9e864aa24e4b722671001af42f2165e608078fe7865bebdc02f8d26d4fa2255`.

Fresh OOS / recent reserve / P10 remained untouched.

## PARALLEL DESIGN LANE — AF-01 / AF-02

These tasks may be designed without spending sealed evidence:

### AF-01 Opportunity Data Design
- point-in-time liquid Spot universe;
- symbol eligibility/listing history;
- gap-aware policies;
- capacity/liquidity metadata;
- no Futures execution capability.

### AF-02 Registry v2
Add:
- `alpha_family_id`;
- `economic_mechanism_id`;
- opportunity frequency;
- turnover expectation;
- capacity sensitivity;
- regime dependence;
- duplication/common-factor fingerprint.

No mass data expansion or migration happens before these designs are accepted.

## AFTER THAT — AF-03B Independent Alpha Sweep #2

Priority families deliberately outside the current trend-overlay cluster:

1. mean reversion;
2. crash/rebound/dislocation;
3. volume-conditioned signals;
4. liquidity regimes;
5. recurring session/time effects;
6. relative strength / lead-lag on a point-in-time liquid Spot universe.

Trend/regime research may continue, but it cannot dominate candidate count while
these families remain unexplored.

## Locked gates

### AF-07 Portfolio / Ensemble
LOCKED until standalone component evidence exists.

### AF-08 Fresh OOS
SEALED until a survivor or portfolio is frozen.

### AF-09 Crisis Certification
LOCKED until OOS survival.

### AF-10 Independent Audit
LOCKED until crisis certification.

### AF-11 Forward Opportunity Validation
LOCKED for new Alpha Factory candidates until independent audit.

### AF-12 Capacity / Capital Scaling
LOCKED until a Forward-capable edge exists.

### Live
NOT AUTHORIZED.

## Parallel P10 lane

Existing P10 real-forward evidence collection continues independently.

Alpha Factory:
- does not read P10 for Development selection;
- does not write P10;
- does not modify P10 candidates/gates/windows;
- does not convert historical success into P10 acceptance.

## Work-unit discipline

Every research work unit must close with:

1. work-unit ID;
2. exact repository HEAD;
3. protocol/specification identity;
4. tests/CI state;
5. evidence boundary used;
6. canonical artifact/result when applicable;
7. closeout state;
8. explicit next allowed action.

No work unit remains in an ambiguous “almost done” state.

## Director command semantics

- “ادامه / بریم” = continue the current authorized research/work unit.
- “مرج” = explicit merge authorization for the current accepted branch/PR.
- “مرج و ادامه” = merge current accepted work, then start the next authorized
  checkpoint.
- no merge is inferred from successful tests or CI.

## Current immediate queue

1. GEN2-001 / GEN2-002 / GEN2-003 canonical outcomes remain immutable.
2. RIE-CAND-0028 exact source/method assessment.
3. AF-01 Opportunity Data Design.
4. AF-02 Registry v2 design.
5. AF-03B independent Alpha Sweep #2.
6. AF-04 standalone Development for the next preregistered candidate.
7. AF-06 independence/cluster gate when survivors exist.
8. AF-07+ only when unlocked.

## Execution mode checkpoint

Authoritative matrix:
`EXECUTION-MODE-MATRIX-v1.0.md`

Current package:
- **RIE-CAND-0028 exact source/method assessment**
- Mode: `CHAT_DIRECTOR`
- Goal: determine whether the pre-existing 3-state HMM regime candidate is
  reproducible enough for a bounded preregistration.
- No performance run is authorized during source/method assessment.
- Work is not required unless later implementation becomes substantial.

Upcoming required-mode gates:
1. **AF-01B Opportunity data implementation** → `⚠️ WORK GATE`
2. **AF-02B Registry migration/classification** → `⚠️ WORK GATE`
3. **AF-03C Deep Alpha Sweep** → `⚠️ WORK GATE`
4. **AF-03D Corpus Synthesis Checkpoint** → `⚠️ WORK + ASTRA GATE` when threshold fires
5. **AF-10B Corpus-scale independent audit** → `⚠️ WORK + ASTRA GATE`

The Director must show the relevant warning before execution begins. A generic
continue command does not cross these gates.

Astra threshold counters to track:
- deep-reviewed sources since prior Astra synthesis;
- reproducible methods since prior Astra synthesis;
- total registered candidates;
- survivor variants;
- independent mechanism clusters;
- completed generations;
- negative-evidence records.

## Cross-cutting governance — Blind spots / conditional edges

Authoritative document:
BLIND-SPOT-AND-CONDITIONAL-EDGE-GOVERNANCE-v1.0.md

Rules now active for future research closeouts:
- gate failure is not automatically NO_EDGE;
- every meaningful rejection receives a failure classification;
- rejection closeout includes a salvage review;
- new conditional logic requires a new candidate/protocol and cannot rescue the
  failed candidate on spent evidence;
- candidates may ultimately be ALL_REGIME_EDGE or REGIME_CONDITIONAL_EDGE;
- conditional edges require explicit operating-envelope and detector metrics;
- crisis failure remains negative evidence even when a conditional-edge
  hypothesis is opened.

The six HSSE-004A survivors remain NOT all-regime certified. Their possible
normal-regime/conditional use is an untested future hypothesis, not approval.

### Work conservation

Default mode for governance/review/design remains CHAT_DIRECTOR.

Do not invoke Work merely because a task touches multiple documentation files.
Use Work for substantial implementation, bulk data, large numerical analysis,
repository-wide migration, or heavy test/build execution.

Before each Work gate, first ask whether Chat can complete the task safely.



## Mass Candidate Factory status — 2026-09-27

### MCF-00 — CLOSED
Governance and mass-factory architecture accepted.

### MCF-01 — CLOSED
Family manifest/candidate identity schema and initial mechanism catalog accepted.

### MCF-02 — IMPLEMENTATION ACCEPTED / MERGED

- PR #144 merged.
- implementation Final HEAD:
  `637b865c097246a901c937bb1de8fc4b90c8f8c3`
- merged main:
  `2adb89eb2eae1c3160e0adb66aabbb2c2dd85f66`
- Actions run `36332442478`: green.
- engineering calibration only; no production selection batch.

Authoritative closeout:
`MCF-02-IMPLEMENTATION-CLOSEOUT-v1.0.md`

### AF-02B — BOUNDED MIGRATION COMPLETE

31/31 legacy candidates migrated conservatively to Registry v2.

- no candidate ID lost;
- no performance authorization granted;
- GEN2-001/002/003 canonical evidence linked;
- RIE-CAND-0028 source/adaptation split preserved.

Artifacts:
- `CANDIDATE-REGISTRY-V2-v1.0.json`
- `AF-02B-REGISTRY-V2-MIGRATION-CLOSEOUT-v1.0.md`

### Current production blocker

The Mass Candidate Engine is ready, but the first true mass Development
selection batch remains locked until AF-01B point-in-time opportunity data
foundation is implemented/accepted and production family/trial/evidence
manifests are frozen.

### Current next package

AF-01B Opportunity Data Foundation implementation.

Mode:
`WORK_REQUIRED`

Reason:
multi-file point-in-time universe/data loader, manifests, eligibility history,
gap-aware research API and bulk data plumbing.

No Work is required for per-candidate execution after the shared foundation is
built.


## Production Readiness checkpoint — 2026-09-27

### AF-01B — IMPLEMENTATION ACCEPTED / MERGED

Merged main:
`d6b0c2662d7c92123a099fd1e9cf79d16c0f3b5e`

Final reviewed implementation HEAD:
`7a34dc9a2d30d95b8d6461dc07f60bf2d32f9437`

Final Actions:
`36341399844` — green.

Director hardening before merge:
- stale interval eligibility blocked;
- MULTI_ASSET requires all policy-required intervals.

Authoritative closeout:
`AF-01B-IMPLEMENTATION-CLOSEOUT-v1.0.md`

### MCF-PROD-001 — PRE-OUTCOME GOVERNANCE FROZEN

Development boundary:
- population: 2020-01-01 through 2023-01-01 exclusive;
- scored search: 2020-03-01 through 2023-01-01 exclusive;
- Fresh OOS/recent reserve/P10 remain unread.

Production universe:
- Binance Spot / USDT;
- dynamic monthly top-50 by lagged trailing-30d quote volume;
- 60d minimum admitted history;
- 99.5% trailing continuity;
- ordinary Spot only;
- unresolved product classification blocked.

Search budget:
- target raw candidates: 8,000–12,000;
- hard cap: 12,000;
- 12 initial mechanism families;
- no survivor quota;
- zero survivors valid;
- no family may dominate the generation.

Frozen domain-plan upper bound:
- 8,176 raw Cartesian combinations before structural filtering.

### AF-01C — NEXT DATA PACKAGE

Bulk population plan frozen:
`AF-01C-BULK-POPULATION-PLAN-v1.0.md`

Archive adapter implementation contract frozen:
`AF-01C-ARCHIVE-ADAPTER-IMPLEMENTATION-CONTRACT-v1.0.md`

Important historical-universe rule:
current `exchangeInfo` may not serve as the sole historical symbol inventory.
The adapter must freeze an auditable historical archive-object inventory or stop
with `HISTORICAL_SYMBOL_INVENTORY_UNPROVEN`.

### MCF-03 — LOCKED UNTIL IMPLEMENTED

Contract:
`MCF-03-PRODUCTION-INTEGRATION-CONTRACT-v1.0.md`

Adds:
- dynamic point-in-time universe binding;
- normalized per-symbol accounting;
- exact F0-F3 production runner;
- daily return artifacts for statistical adjudication.

### MCF-04 — LOCKED UNTIL IMPLEMENTED

Contract:
`MCF-04-STATISTICAL-ADJUDICATION-CONTRACT-v1.0.md`

Adds severe filters:
- 50%+ local neighbor stability;
- Deflated Sharpe confidence >= 0.95;
- family PBO <= 0.20;
- required bootstrap reality-check diagnostic;
- |rho| >= 0.80 common-factor clustering;
- one deterministic representative per qualifying cluster.

No MCF-PROD-001 performance may be exposed before MCF-03 and MCF-04 are
implementation-accepted.

### Parallel execution route

1. Implement AF-01C historical archive adapter — WORK_REQUIRED.
2. Implement MCF-03 + MCF-04 production runner/statistical layer — WORK_REQUIRED.
3. Pilot AF-01C adapter.
4. Director-supervised VPS bulk population — MANUAL_VPS / BATCH_RUNTIME.
5. Freeze exact generated candidate count/spec SHAs before performance.
6. Run MCF-PROD-001 Development.
7. Apply F0-F7 and freeze only qualifying independent representatives.
8. Fresh OOS remains sealed until step 7 completes.

No production performance run is authorized by this checkpoint alone.
