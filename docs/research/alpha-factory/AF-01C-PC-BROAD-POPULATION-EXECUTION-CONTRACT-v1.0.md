# AF-01C P-C — Broad Population Execution Contract v1.0

Status: **FROZEN BEFORE P-C IMPLEMENTATION**
Date: 2026-09-28
Parent implementation: PR #149 / `af-01c-historical-archive-adapter`
Required parent HEAD: `d7c3b1e68024ca6aa7c3b1c1c399bb2bb5ffa0c8`

Safety:
- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- NO FUTURES
- NO LEVERAGE
- NO SHORT
- NO LIVE EXECUTION
- NO ORDER ENDPOINT
- NO AI DIRECT EXECUTION
- P10 UNTOUCHED
- Fresh OOS read=false
- recent reserve read=false
- P11 LOCKED
- no strategy outcome / PnL / Sharpe / drawdown / win-rate inspection

## 1. Objective

Execute AF-01C phase P-C Broad Population for the frozen Development window
2020-01-01 through 2022-12-31 using the independently-audited historical
Binance Spot USDT 15m archive inventory.

This work unit is a data population execution lane, not strategy research.

## 2. Frozen upstream evidence

P-A inventory:
- snapshot SHA-256:
  `3c27c203e188095cc6a0f1ab7bafbd9bd534ed786bccf8cfe3c240644ccedeb6`
- raw inventory SHA-256:
  `bc9f77cae4c07541fc7538dac982302728f44766e1238eb94408522595220df4`
- normalized inventory SHA-256:
  `83aba891ce5163d372ade6021950277ae335c0455e16eb9d5dd88fd050f671cf`
- independent replay audit SHA-256:
  `cc5221fc79c0a35bace700603f7b8332eef842d5dd0e4b918017d7af9785cf5d`

P-A cardinality:
- 1,846 immutable raw listing pages
- 286,877 registered archive objects
- 413 object-bearing symbols
- range 2020-01 through 2022-12-31

P-B:
- plan SHA-256:
  `7e99e7affba2b4c2956c17458fd13bf7f722d3df585f08c5be1915611977e25e`
- 13/13 reconciled
- 8 MONTHLY_SUCCESS
- 5 preserved SOURCE_GAP
- reconciliation SHA-256:
  `f93eff255856f5835209c03c8bbcc8bbe4b65936fc7461d9a1afcad92798d782`
- ACAUSDT quality/lifecycle/index closeout PASS

No negative P-B evidence may be rewritten, deleted, or silently upgraded.

## 3. P-C frozen cardinality

Verified preflight:
- object-bearing symbols: 413
- planned symbol/month identities: 9,306
- monthly identities: 9,306
- daily-only identities: 0
- non-ASCII acquire blocker: 0

The final P-C plan must reproduce these cardinalities from the same inventory
unless the implementation fails closed before acquisition.

## 4. Planner scalability gate

The original broad planner exhibited O(objects × requested-periods) behavior.

Parent HEAD `d7c3b1e...` replaces it with a one-pass indexed lookup.

Accepted VPS benchmark target:
- broad plan state = REGISTERED_DEVELOPMENT
- period count = 9,306
- elapsed time must be bounded and operationally reasonable
- observed reference benchmark: 13.69 seconds, 99% CPU, max RSS 282,592 KB

Regression back to repeated full-inventory scans blocks P-C.

## 5. Runtime isolation

P-C MUST NOT reuse the P-B ledger namespace.

P-B runtime remains:
`/var/lib/yatl/research/opportunity-data`

P-C runtime root:
`/var/lib/yatl/research/opportunity-data-pc`

Rules:
- P-B root is read-only input/evidence for P-C bootstrap.
- P-C writes only under the P-C root.
- no P-C artifact may overwrite a P-B artifact.
- no path may touch `/var/lib/yatl/p10`.
- P-C plan and ledgers are bound to the P-C broad-plan SHA.

The P-C root may contain a byte-identical copy of the frozen P-A snapshot and
audit references after SHA verification.

## 6. Storage preflight

Before any bulk archive acquisition:
- record filesystem free bytes;
- record current P-B evidence size;
- estimate pilot bytes-per-successful-period from actual artifacts where
  possible;
- refuse bulk start when a conservative capacity check is not satisfied.

No automatic deletion of evidence to free space.

## 7. Broad plan

Create and persist a content-addressed P-C plan:
- state = REGISTERED_DEVELOPMENT
- inventory binding = frozen normalized inventory SHA
- 413 symbols
- 9,306 periods
- interval = 15m
- Development start = 2020-01-01T00:00:00Z
- end exclusive = 2023-01-01T00:00:00Z

Plan creation performs no remote candle download.

## 8. Acquisition policy

For each planned period:
1. prefer monthly archive;
2. fetch official CHECKSUM;
3. fetch bounded ZIP;
4. verify checksum;
5. verify expected member;
6. normalize/validate canonical rows;
7. preserve timestamp anomalies explicitly;
8. if monthly fails for a recoverable source reason, allow explicit registered
   daily fallback for that same month only;
9. never interpolate missing bars;
10. write immutable artifacts and one final ledger state.

All existing AF-01C recovery states remain valid.

## 9. Restart / resume

P-C bulk execution must be restartable and idempotent.

Required:
- existing valid completed ledgers are verified and skipped;
- incomplete identities may be retried only through the registered source
  policy, not by changing acceptance rules;
- conflicting plan/inventory/artifact binding fails closed;
- no duplicate accepted identity;
- progress is derived from immutable ledgers, never an untrusted counter.

## 10. Batching

The implementation must support bounded execution:
- deterministic ordered identity list;
- `--limit` or equivalent bounded batch size;
- resume from immutable ledger state;
- no requirement to complete all 9,306 periods in one process.

Initial canary:
- <=25 identities
- no strategy outputs
- reconcile canary state before broad continuation

A canary failure must not be hidden by selecting a different favorable batch.

## 11. Population status

Provide read-only status without requiring completion:
- plan SHA
- total identities
- completed identities
- remaining identities
- counts by final state
- success count
- source-gap/failure count
- artifact bytes if practical

Status must not read market outcomes beyond registered data-quality metadata.

## 12. Reconciliation

Final P-C reconciliation requires:
- all 9,306 planned identities in one valid final state;
- every referenced artifact hash verified;
- plan/inventory binding intact;
- no mutable/colliding ledger;
- deterministic summary SHA.

Allowed final data-population states follow the frozen bulk plan:
- POPULATION_COMPLETE
- POPULATION_COMPLETE_WITH_SOURCE_GAPS
- POPULATION_BLOCKED_INVENTORY
- POPULATION_BLOCKED_SOURCE
- POPULATION_INVALID

## 13. Product classification

P-C archive presence alone does not prove ordinary Spot eligibility.

- preserve known nonordinary classifications;
- unresolved remains unresolved;
- do not use current exchangeInfo to rewrite historical product identity;
- do not block raw data preservation solely because classification is unresolved.

Classification/index policy closeout remains a later population/index gate.

## 14. Implementation scope

Implement only what is needed to safely execute and monitor P-C:
- broad plan persistence;
- isolated runtime bootstrap;
- restartable bounded bulk acquisition;
- read-only population status;
- final reconciliation/manifest support as needed.

Do not add trading functionality.

## 15. Acceptance before broad continuation

Before >25 identities are acquired:
- parent AF-01C focused tests green;
- new P-C tests green;
- CI green for Final HEAD;
- disk/storage preflight PASS;
- P-C root isolation PASS;
- broad plan hash/cardinality PASS;
- <=25 identity canary completes and reconciles;
- P10 path untouched.

## 16. Git / merge policy

Branch:
`af-01c-pc-broad-population`

This branch is based on the unmerged PR #149 Final HEAD and therefore depends
on PR #149.

DO NOT MERGE this work unit without the Director's explicit command
`مرج` or `مرج و ادامه`.

Negative results are retained.
No retune/retry/hidden trial after observing outcomes on the same evidence.
