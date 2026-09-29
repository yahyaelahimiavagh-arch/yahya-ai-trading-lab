# MCF-03 / MCF-04 — Implementation Closeout v1.0

Status: **IMPLEMENTATION ACCEPTED / MERGED / PERFORMANCE STILL LOCKED**

Date: 2026-09-29

## Accepted repository state

- implementation PR: #159
- implementation Final HEAD:
  `cbb282ca008d90a8c610c426e32350b6d7fc9e7b`
- accepted main merge commit:
  `7ccefe3386947b5e6ef13c649629d9fdec55ec04`
- GitHub Actions:
  - P5 deterministic gates run #372 — **SUCCESS**
  - `accepted-public-data` — **SUCCESS**
  - `unit-and-safety` — **SUCCESS**

## Accepted implementation scope

MCF-03:
- point-in-time dynamic-universe binding;
- normalized per-symbol long/cash Development accounting;
- next-bar fill and source-gap cancellation semantics;
- membership-transition exits;
- exact F1-F3 gates;
- daily candidate/per-symbol return artifacts;
- pre-outcome candidate/universe/cost binding;
- deterministic production candidate generator and executable freeze.

MCF-04:
- pre-outcome one-step parameter-neighbor graph;
- F4 local-neighbor stability;
- raw/effective trial accounting for generation, family and mechanism;
- Deflated Sharpe confidence gate;
- deterministic 8-slice CSCV/PBO;
- deterministic 2,000-rep circular 14-calendar-day block-bootstrap diagnostic;
- |rho| >= 0.80 common-factor clustering;
- deterministic cluster representative selection;
- F7 survivor-freeze primitive.

Director hardening before acceptance additionally closed:
- all-valid-neighbor median semantics for F4;
- failed trials retained in multiple-testing denominators;
- calendar-day rather than compressed-observation bootstrap blocks;
- member -> nonmember -> reentry transitions hidden inside source gaps;
- daily-return source-gap bridge contamination;
- exact-accounting and identity re-verification at MCF-04 entry.

## Evidence boundary

This closeout accepts implementation only.

It does **not** expose or certify:
- MCF-PROD-001 Development performance;
- any Development survivor;
- Fresh OOS;
- recent reserve;
- P10 evidence;
- P11;
- Live readiness.

Hard safety state remains:
- PAPER / RESEARCH ONLY;
- LIVE_MASTER_LOCK=OFF;
- NO FUTURES;
- NO LEVERAGE;
- NO SHORT;
- NO LIVE EXECUTION;
- NO ORDER ENDPOINT;
- NO AI DIRECT EXECUTION;
- Fresh OOS sealed;
- recent reserve sealed;
- P10 untouched;
- P11 locked.

## Next checkpoint

Before any MCF-PROD-001 Development outcome is read:

1. deterministically regenerate the exact candidate set;
2. record exact raw/valid/executable counts;
3. freeze candidate/spec ledger SHA;
4. freeze parameter-neighbor graph SHA;
5. preserve implementation-blocked families as negative/pre-performance evidence;
6. reproduce the freeze in CI;
7. materialize the runtime freeze on the VPS;
8. only then authorize the manual Development run.

Checkpoint artifact:
`MCF-PROD-001-PREOUTCOME-FREEZE-CHECKPOINT-v1.0.json`

No Development performance run is authorized by this closeout.
