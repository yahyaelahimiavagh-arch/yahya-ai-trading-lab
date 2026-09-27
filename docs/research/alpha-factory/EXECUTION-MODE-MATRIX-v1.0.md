# YATL Alpha Factory — Execution Mode Matrix v1.0

Status: **AUTHORITATIVE EXECUTION ROUTING**
Established: **2026-09-27**

Purpose: split the Alpha Factory Master Plan into executable work packages and
state explicitly when ordinary Director chat is sufficient, when ChatGPT Work
should be used, and when an Astra-class deep-synthesis pass is required.

This routing document does **not** change any frozen research protocol, evidence
boundary, safety rule, merge rule, or canonical outcome.

## 1. Execution modes

### CHAT_DIRECTOR
Use the normal reasoning chat for:
- scope and protocol decisions;
- preregistration;
- narrow GitHub review/editing;
- exact VPS commands and canonical-run supervision;
- go/no-go decisions;
- blocker classification;
- small source/method extraction tasks.

### WORK_REQUIRED
Use ChatGPT Work when a stage requires substantial multi-step execution across
many repository files, datasets, browser sources, or artifacts and the task is
better treated as a bounded work package rather than a conversational edit.

Typical reasons:
- multi-file implementation/refactor;
- dataset acquisition/organization;
- registry migration;
- large deterministic analysis jobs;
- producing coordinated artifacts/reports from many files.

Work mode never receives extra trading authority. All YATL safety and evidence
locks remain binding.

### ASTRA_REQUIRED
Use Astra only when the task is dominated by very large-context synthesis or
cross-source reasoning where ordinary hourly research would fragment the
evidence.

Typical triggers:
- deep synthesis of >50 materially distinct research sources in one checkpoint;
- cross-language synthesis across many long papers/books/transcripts;
- comparing >100 registered candidates/mechanisms at once;
- reconstructing a very large evidence chain for an independent scientific
  audit;
- resolving conflicts across many research generations/artifacts where the
  whole corpus must be considered together.

Astra is **not** used merely because a task is difficult. It is reserved for
corpus-scale synthesis.

### WORK_AND_ASTRA_REQUIRED
Use both when a task simultaneously requires:
1. large-context/corpus-scale synthesis, and
2. substantial multi-file/browser/artifact execution.

## 2. Mandatory warning gate

Before entering any stage marked `WORK_REQUIRED`,
`ASTRA_REQUIRED`, or `WORK_AND_ASTRA_REQUIRED`, the YATL Director must stop
and explicitly warn Yahya **before execution begins**.

Required warning forms:

**WORK gate**
> ⚠️ WORK GATE — مرحله بعد برای اجرای چندمرحله‌ای فایل/داده/ریپو به Work نیاز دارد. هنوز وارد اجرای مرحله نشده‌ایم.

**ASTRA gate**
> ⚠️ ASTRA GATE — مرحله بعد corpus-scale است و طبق Master Plan باید با Astra انجام شود. هنوز وارد اجرای مرحله نشده‌ایم.

**WORK + ASTRA gate**
> ⚠️ WORK + ASTRA GATE — مرحله بعد هم اجرای چندمرحله‌ای Work و هم synthesis عمیق Astra می‌خواهد. هنوز وارد اجرای مرحله نشده‌ایم.

The Director must not silently cross a required-mode gate after a generic
`ادامه` or `بریم`. The warning must be shown first. After Yahya switches to
the required mode and explicitly continues, execution may start.

This warning requirement is a workflow rule, not a merge authorization.

## 3. Master Plan split into work packages

| Work package | Parent stage | Main output | Mode | Astra/Work trigger |
|---|---|---|---|---|
| AF-00A Governance closeout | AF-00 | architecture docs + CI | CHAT_DIRECTOR | none |
| AF-01A Universe policy design | AF-01 | point-in-time universe/gap/capacity spec | CHAT_DIRECTOR | none |
| AF-01B Opportunity data implementation | AF-01 | loaders/manifests/universe history | WORK_REQUIRED | multi-file + dataset work |
| AF-01C Historical universe acquisition | AF-01 | admitted liquid Spot research corpus | WORK_REQUIRED | bulk data acquisition/verification |
| AF-02A Registry-v2 schema | AF-02 | schema + lifecycle fields | CHAT_DIRECTOR | none |
| AF-02B Registry migration/classification | AF-02 | all active candidates migrated | WORK_REQUIRED | many candidate files/records |
| AF-02C Global candidate-cluster synthesis | AF-02 | dedupe/common-mechanism map | ASTRA_REQUIRED_CONDITIONAL | trigger at >=100 candidates or >=50 materially distinct method records |
| AF-03A Source unblock sprint | AF-03 | 0011/0022/0027 exact blocker resolution | CHAT_DIRECTOR | bounded source work |
| AF-03B Hourly Research Sentinel | AF-03 | stateful intake queue | CHAT_DIRECTOR_AUTOMATION | max 3–10 deep reviews/cycle |
| AF-03C Deep Alpha Sweep | AF-03 | broad independent-family candidate intake | WORK_REQUIRED | large source collection + structured registry updates |
| AF-03D Corpus Synthesis Checkpoint | AF-03 | cross-source gap map + research priorities | WORK_AND_ASTRA_REQUIRED | >=50 distinct deep-reviewed sources since prior synthesis OR >=25 new reproducible methods |
| AF-03E Long-media Research Batch | AF-03 | paper/book/transcript method packets | ASTRA_REQUIRED_CONDITIONAL | multiple long documents/transcripts whose combined context is too large for reliable fragmented review |
| AF-04A Candidate protocol/preregistration | AF-04 | frozen candidate protocol | CHAT_DIRECTOR | none |
| AF-04B Standalone implementation | AF-04 | deterministic runner + tests | WORK_REQUIRED | multi-file coding/testing |
| AF-04C Canonical Development run | AF-04 | one canonical Development outcome | CHAT_DIRECTOR + MANUAL_VPS | scarce-evidence run; no autonomous bulk runner |
| AF-05A Search/statistics implementation | AF-05 | trial ledger + false-discovery diagnostics | WORK_REQUIRED | analysis code + many artifacts |
| AF-05B Survivor freeze decision | AF-05 | immutable survivor digest | CHAT_DIRECTOR | explicit go/no-go |
| AF-06A Independence analytics | AF-06 | correlation/overlap/failure clusters | WORK_REQUIRED | many survivor artifacts |
| AF-06B Global edge-cluster synthesis | AF-06 | independent edge count + opportunity map | ASTRA_REQUIRED_CONDITIONAL | >=20 survivor variants or >=8 economic mechanism clusters |
| AF-07A Portfolio protocol | AF-07 | bounded combination rules | CHAT_DIRECTOR | none |
| AF-07B Portfolio/ensemble implementation | AF-07 | combined simulation + marginal contribution | WORK_REQUIRED | multi-edge analysis |
| AF-07C Large portfolio architecture synthesis | AF-07 | allocation/capacity architecture | ASTRA_REQUIRED_CONDITIONAL | >=10 independent edge clusters or major cross-market expansion |
| AF-08A Fresh-OOS freeze check | AF-08 | sealed-evidence authorization checklist | CHAT_DIRECTOR | none |
| AF-08B Canonical Fresh OOS | AF-08 | one frozen OOS adjudication | CHAT_DIRECTOR + MANUAL_VPS | **no autonomous Work/Astra execution over sealed OOS** |
| AF-09A Crisis/adversarial test implementation | AF-09 | regime/cost/liquidity stress harness | WORK_REQUIRED | batch stress analysis |
| AF-09B Crisis certification decision | AF-09 | certified/rejected failure profile | CHAT_DIRECTOR | explicit adjudication |
| AF-10A Independent evidence-pack assembly | AF-10 | complete audit bundle | WORK_REQUIRED | many repo/artifact sources |
| AF-10B Corpus-scale independent audit | AF-10 | independent scientific audit verdict | WORK_AND_ASTRA_REQUIRED | full-generation evidence-chain synthesis |
| AF-11A Forward protocol | AF-11 | elapsed-time/opportunity/execution gates | CHAT_DIRECTOR | none |
| AF-11B Forward monitoring tooling | AF-11 | Paper/shadow telemetry + reports | WORK_REQUIRED | multi-file operational tooling |
| AF-11C Forward adjudication | AF-11 | forward candidate/reject/continue | CHAT_DIRECTOR | live-time evidence decision |
| AF-12A Capacity model implementation | AF-12 | slippage/participation/capacity curves | WORK_REQUIRED | market/liquidity simulations |
| AF-12B Cross-edge capacity synthesis | AF-12 | portfolio capital bottleneck map | ASTRA_REQUIRED_CONDITIONAL | large universe + many independent edges |
| AF-13 Adaptive research review | AF-13 | next-generation hypothesis map | CHAT_DIRECTOR | normal cycle |
| AF-13B Multi-generation failure synthesis | AF-13 | structural lessons across generations | ASTRA_REQUIRED_CONDITIONAL | >=3 completed generations or very large negative-evidence corpus |

## 4. Hard rules for sealed/scarce evidence

Work/Astra capability is **not** a reason to automate scarce-evidence
adjudication.

The following remain Director-supervised even when Work/Astra are available:
- canonical Development outcome execution;
- survivor freeze;
- Fresh OOS opening;
- Fresh OOS canonical run;
- crisis certification verdict;
- Forward promotion/rejection;
- any future Tiny Live authorization.

Large-context tools may prepare an audit or analysis packet, but cannot silently
spend a sealed evidence set or promote a candidate.

## 5. Astra trigger accounting

The Research Sentinel and Alpha Factory must maintain counters sufficient to
know when an Astra checkpoint is due:

- `deep_reviewed_sources_since_astra`;
- `reproducible_methods_since_astra`;
- `registered_candidate_count`;
- `survivor_variant_count`;
- `independent_mechanism_cluster_count`;
- `completed_generation_count`;
- `negative_evidence_record_count`.

When a threshold in the matrix is reached, the next relevant work package is
marked `ASTRA_GATE_PENDING` and the Director warning is mandatory.

## 6. Current routing from 2026-09-27

Current active work:
- AF-00A Governance closeout — `CHAT_DIRECTOR`.

Immediately after AF-00 acceptance:
- AF-03A Source unblock sprint — `CHAT_DIRECTOR`;
- AF-01A Universe policy design — `CHAT_DIRECTOR`;
- AF-02A Registry-v2 schema — `CHAT_DIRECTOR`.

First expected Work gates:
- AF-01B Opportunity data implementation;
- AF-02B Registry migration;
- AF-03C Deep Alpha Sweep.

First expected Astra gate:
- AF-03D Corpus Synthesis Checkpoint when its source/method threshold is met.

The Director must warn Yahya before any of these required-mode transitions.

## 7. Work-token conservation override — 2026-09-27

Work is a scarce execution resource. The routing table must be interpreted with
a Chat-first bias.

Before any WORK_REQUIRED transition, the Director must first test whether the
task can be completed safely and deterministically in CHAT_DIRECTOR. If yes,
the task stays in chat even if it touches several documentation or policy files.

The following are explicitly CHAT-first:
- governance and Master Plan edits;
- protocol/preregistration design;
- candidate/failure classification;
- blind-spot and assumption audits;
- rejection/salvage reviews;
- bounded source extraction;
- queue and registry-policy decisions;
- small registry updates;
- bounded comparison/review of a small number of artifacts.

Work remains mandatory for:
- substantial code implementation;
- bulk dataset acquisition/transformation;
- repository-wide migrations;
- large deterministic numerical jobs;
- coordinated testing/build execution;
- large artifact packs whose manual orchestration creates material error risk.

Updated routing clarifications:
- AF-02B Registry migration/classification: CHAT_DIRECTOR while bounded; escalate
  to Work only for bulk/repository-wide migration.
- AF-03C Deep Alpha Sweep: CHAT_DIRECTOR for bounded research batches; escalate
  to Work only when a bulk sweep materially exceeds the Sentinel-sized batch or
  requires coordinated artifact writes.
- AF-06A Independence analytics: CHAT_DIRECTOR for a small survivor set; Work
  only when artifact count/analysis volume becomes materially large.
- documentation-only cross-cutting governance never requires Work by itself.

Astra thresholds are unchanged.

## 8. Mass Candidate Factory execution routing

MCF-00 Governance / architecture -> CHAT_DIRECTOR  
MCF-01 Family manifest / candidate spec design -> CHAT_DIRECTOR  
MCF-02 Generator implementation -> WORK_REQUIRED only for the reusable engine implementation  
MCF-03 Batch historical screening -> MANUAL_VPS / BATCH_RUNTIME  
MCF-04 Statistical/cluster analytics -> CHAT_DIRECTOR for bounded result sets; WORK_REQUIRED only when materially large  
MCF-05 Exact recompute / freeze -> CHAT_DIRECTOR + MANUAL_VPS  
MCF-06 Fresh OOS handoff -> CHAT_DIRECTOR + MANUAL_VPS under sealed-evidence supervision

Rules:
- never invoke Work once per candidate;
- never invoke Work merely because a batch contains thousands of candidates;
- candidate enumeration and historical execution belong in deterministic runtime
  engines, not interactive orchestration;
- Astra is considered only when corpus-scale synthesis thresholds fire;
- real Forward calendar time is never replaced by historical compute.

