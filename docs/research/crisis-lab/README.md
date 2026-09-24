# YATL Crisis & Regime Stress Lab

Status: **RESEARCH ONLY — P10 UNTOUCHED — P11 LOCKED**

Current checkpoint status (2026-09-24):

| ID | Status | Evidence |
|---|---|---|
| CRL-000 | **ACCEPTED** | research/P10 isolation audit closed |
| CRL-001 | **REGISTERED v0.1.0** | 16-event source-backed catalog; 9 Development / 7 Blind Holdout |
| CRL-002 | **ACCEPTED 2026-09-23** | real VPS pilot complete; provenance + REST verification + external P10 no-write proof accepted |
| CRL-003 | **ACTIVE — E003 REAL QUALITY PASS ACCEPTED** | CRL-E003 6/6 datasets PASS; canonical quality manifest SHA-256 `9db76653f252ac16e44fdd701f606bcd1e177609cb4e342e4564dc8d9bd77451`; remaining registered datasets pending bounded admission |
| CRL-004 | **ACTIVE — E003 PILOT OPEN** | historical point-in-time replay may be implemented/tested against admitted CRL-E003 only |
| CRL-005..010 | NOT STARTED / SPEC ONLY | ordered downstream gates remain closed |

Purpose: stress the accepted YATL strategy/risk architecture against historical
crises, control windows, random windows and synthetic shocks while preserving the
integrity of the active P10 real-forward experiment.

## Ordered checkpoints

| ID | Scope |
|---|---|
| CRL-000 | Charter, isolation and evidence rules |
| CRL-001 | Event Catalog research |
| CRL-002 | Data acquisition and provenance |
| CRL-003 | Data quality and canonical manifests |
| CRL-004 | Historical point-in-time replay |
| CRL-005 | Control windows and baselines |
| CRL-006 | Synthetic adversarial stress matrix |
| CRL-007 | Severity model and random windows |
| CRL-008 | Shadow challenger and ablation track |
| CRL-009 | Survival Certificate specification |
| CRL-010 | Independent final research audit |

Supporting files:
- `EVENT-CATALOG-v0.1.0.json` — canonical CRL-001 machine-readable event registry.
- `DATA-ACQUISITION-REGISTER-v0.1.0.json` — canonical CRL-002 range/source registration.
- `CRL-002-VPS-RUNBOOK.md` — operator procedure for real acquisition without stopping or mutating P10.
- `QUALITY-MANIFEST-SPEC-v0.1.0.json` — frozen CRL-003 structural quality/admission contract.
- `DIRECTORY-LAYOUT.md` — canonical repository/runtime layout.
- `RESEARCH-LOG.md` — append-only research decisions and evidence notes.
- `RESULTS-INDEX.md` — accepted research output index.

No checkpoint may modify the active P10 candidate, configuration, gate registry,
sealed window, fee/slippage, risk thresholds or evidence. No Crisis Lab result
can unlock P11 or claim Live readiness.
