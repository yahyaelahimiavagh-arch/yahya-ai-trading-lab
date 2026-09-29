# AF-01C P-C — Final Population and Reconciliation Evidence

Status: **PASS / COMPLETE WITH SOURCE GAPS / CLOSEOUT EVIDENCE**

Date: 2026-09-29

## Executable code

Optimized reconciliation code HEAD:

`f6098c0b823cc98e33fcd9ca014512dd51026140`

Merged to `main` through PR #157.

Main merge commit:

`ccb8eda76c63da9a164de59432bbe09d926b9d1f`

GitHub Actions validation:

- workflow: P5 deterministic gates
- run: #336
- result: **SUCCESS**

Focused VPS tests before final reconciliation:

- 20 tests
- result: **PASS**

## Frozen population result

Runtime root:

`/var/lib/yatl/research/opportunity-data-pc`

Final population:

- completed identities: **9,306 / 9,306**
- remaining identities: **0**
- MONTHLY_SUCCESS: **6,443**
- SOURCE_GAP: **1,299**
- TIMESTAMP_ANOMALY: **1,562**
- INVALID_SCHEMA: **2**
- source-gap-or-failure total: **2,863**
- artifact bytes: **5,967,772,132**
- final status SHA-256:
  `59ef745317bb6e11c9bfad0e99643333d3611449332ec2da975fde9b1bd86703`

No failed or anomalous evidence was repaired, interpolated, deleted, or reacquired.

## Final reconciliation

- state: **POPULATION_COMPLETE_WITH_SOURCE_GAPS**
- final count: **9,306**
- source gap count: **2,863**
- adapter reconciliation SHA-256:
  `f7ea2af3f0c31df2ff561d9648e65e6fad1b608eea9d4ccefb93770ab46918e7`
- population reconciliation SHA-256:
  `1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17`
- status SHA-256:
  `59ef745317bb6e11c9bfad0e99643333d3611449332ec2da975fde9b1bd86703`
- reconciliation verdict: **PASS**
- elapsed: **154.04 seconds**
- max RSS: **813,496 KB**

## Reconciliation performance defect and correction

The original reconciliation path indirectly repeated full `verify_plan()` work
inside the per-record loop. The accepted correction verifies the frozen plan once
and derives each binding from that already-verified plan while retaining record
digest, identity, selected-object binding, artifact-hash, canonical-hash and final
state checks.

A regression test requires reconciliation to invoke `verify_plan()` exactly once.

The slow reconciliation process was stopped only after the immutable population
had already reached 9,306/9,306. A post-stop status verification confirmed the
same status SHA before optimized reconciliation.

## Governance

- DATA_REACQUIRED=NO
- DATA_DELETED=NO
- SOURCE_GAPS_PRESERVED=YES
- P10_TOUCHED=NO
- FRESH_OOS_READ=NO
- RECENT_RESERVE_READ=NO
- P11=LOCKED
- LIVE_MASTER_LOCK=OFF
- NO FUTURES EXECUTION
- NO LEVERAGE
- NO SHORT
- NO LIVE EXECUTION
- NO ORDER ENDPOINT
- NO AI DIRECT EXECUTION

## VPS report package

Local report path:

`/home/ubuntu/af01c-fast-full9306-report.tar.gz`

Report SHA-256:

`da21ef02a195aadac0b6b151ff0175f2de345a595fb7cbb72628247d7cd6200f`

The bulk report remains runtime evidence on the VPS; this document records its
cryptographic identity.
