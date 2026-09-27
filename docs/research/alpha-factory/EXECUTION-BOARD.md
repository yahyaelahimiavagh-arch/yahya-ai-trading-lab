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

## OPEN NEXT — GEN2-003 candidate specification

Next eligible candidate:
- `RIE-CAND-0027`;
- downside-volatility exposure scaling;
- exact source estimator and real-time lag semantics are now method-specified;
- YATL must create a fresh long-only/no-leverage adaptation protocol before any
  Development run;
- no performance is authorized until the adaptation, missing-data semantics,
  opportunity-preservation gates and bounded comparison set are frozen.

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

1. AF-00 closeout + Final-HEAD CI.
2. GEN2-002 closeout remains immutable.
3. AF-03A source unblock sprint (0011 / 0022 / 0027).
4. GEN2 next eligible protocol if blockers remain.
5. AF-01 data design.
6. AF-02 Registry v2.
7. AF-03B independent Alpha Sweep #2.
8. AF-04 standalone Development.
9. AF-06 independence/cluster gate.
10. AF-07+ only when unlocked.

## Execution mode checkpoint

Authoritative matrix:
`EXECUTION-MODE-MATRIX-v1.0.md`

Current package:
- **GEN2-003 / RIE-CAND-0027 adaptation specification**
- Mode: `CHAT_DIRECTOR`
- Required-mode warning: none

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

