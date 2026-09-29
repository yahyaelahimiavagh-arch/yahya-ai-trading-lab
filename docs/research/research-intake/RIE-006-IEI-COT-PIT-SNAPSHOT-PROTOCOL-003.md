# RIE-006 — IEI COT PIT Snapshot Protocol 003

Work Unit ID: `RIE-006-IEI-COT-PIT-SNAPSHOT-PROTOCOL-003`  
Status: **PREREGISTERED PROVENANCE PROTOCOL / NO BULK ACQUISITION / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `4070213f00ef0f3d727a9438337a76e8daf677c2`
- PR #152: OPEN / DRAFT / UNMERGED

Parent:
- `RIE-006-IEI-COT-PIT-VERSION-AUDIT-002.md`

Boundary:
- PAPER / RESEARCH ONLY
- no returns/backtests/outcome reads
- Fresh OOS SEALED
- recent reserve SEALED
- P10 UNTOUCHED
- P11 LOCKED
- no merge authorization

## 1. Purpose

Freeze the exact evidence standard and sampling protocol for determining whether a
historical CFTC Bitcoin COT artifact can be treated as the version that was
publicly available at a historical strategy decision time.

This protocol is frozen before any bulk archive acquisition.

## 2. Primary source family for provenance testing

Provenance testing begins with:

- report family: **Legacy Futures Only**
- exchange: **Chicago Mercantile Exchange**
- product: **Bitcoin Futures**
- CFTC code: **133741**
- contract unit: **5 Bitcoins**

This selection is for provenance mechanics only and is not a predictive-method
selection.

TFF, Futures-and-Options Combined and Micro Bitcoin are excluded from the first
snapshot-provenance pass to avoid multiplying version ambiguity before the
pipeline itself is validated.

## 3. Frozen representative sample

Five release regimes must be tested.

### S1 — Normal release

- report date: **2018-05-01**
- expected ordinary public release: **2018-05-04 at 15:30 America/New_York**
- CFTC artifact:
  `deacmesf050118.htm`

Purpose:
- establish the normal-case snapshot workflow.

### S2 — Federal-holiday delay

- report date: **2021-06-15**
- originally due: **2021-06-18**
- actual CFTC publication date: **2021-06-21**
- reason: federal Juneteenth observance.

Purpose:
- verify that archive provenance preserves actual delayed publication rather than
  a generic Friday rule.

### S3 — 2018–2019 appropriations lapse

- report/as-of date: **2018-12-24**
- originally scheduled publication: **2018-12-28**
- CFTC catch-up publication: **2019-02-01**

Purpose:
- verify long publication-gap handling.

### S4 — 2023 ION incident

- report/as-of date: **2023-01-31**
- originally scheduled publication: **2023-02-03**
- CFTC announced first catch-up release: **2023-02-24**

Purpose:
- verify an incident where underlying reporting firms had timeliness/accuracy
  problems and CFTC documented best-estimate / revised-report risk.

### S5 — 2025 appropriations lapse

- report date: **2025-09-30**
- original intended publish date: **2025-10-03**
- actual catch-up publication: **2025-11-19**

Purpose:
- verify a modern delayed-release case with an explicit official old/new schedule.

No sample date may be replaced because archive recovery is inconvenient or because
a recovered value later appears economically unattractive.

## 4. Acceptable external snapshot evidence

A snapshot is acceptable only when all required fields can be recorded:

- archive provider;
- original CFTC URL;
- archive capture timestamp;
- reproducible snapshot identifier or immutable capture URL;
- HTTP status if available;
- archived response bytes retrievable;
- SHA-256 computed by YATL over the archived bytes;
- MIME/content type;
- report family/date parsed from the bytes;
- Bitcoin code `133741` located in the artifact;
- position values parsed deterministically;
- capture timestamp >= official public release time;
- capture timestamp < known correction/revision time, when testing the original
  version;
- retrieval timestamp;
- parser/schema version;
- transformation hash.

Search-engine snippets, current CFTC timestamps, or undigested screenshots are
not acceptable substitutes.

## 5. Snapshot timing windows

### 5.1 Strong original window

A capture qualifies as `ORIGINAL_WINDOW_STRONG` when:

`official_public_availability_time <= capture_time < first_known_revision_time`

If no revision is known, the protocol still requires a capture reasonably close
to release and does not infer immutability from silence.

### 5.2 Delayed release

For S2–S5, a capture before the actual public release is not evidence of the
final COT report.

### 5.3 Same-day ambiguity

If only a date is known and the exact release time is not independently proven,
the snapshot cannot support a same-day decision eligibility claim.

## 6. Comparison with current official CFTC artifact

For each sample:

1. retrieve archived snapshot bytes;
2. hash archived bytes;
3. retrieve current CFTC dated artifact;
4. hash current bytes;
5. parse only the selected Bitcoin row/section;
6. compare:
   - contract code;
   - unit;
   - report date;
   - open interest;
   - Non-Commercial Long/Short/Spreading;
   - Commercial Long/Short;
   - Nonreportable Long/Short;
7. record whether full-byte hash matches;
8. record whether parsed Bitcoin semantic fields match;
9. check CFTC Historical Special Announcements for revision notices;
10. classify provenance state.

A byte mismatch does not automatically mean economic fields changed; it triggers
field-level comparison and revision investigation.

A semantic-field mismatch is fail-closed until lineage is explained.

## 7. Frozen provenance classifications

### `SNAPSHOT_A_ORIGINAL_MATCH`

- valid contemporaneous archive capture;
- release clock valid;
- archived semantic fields match current CFTC artifact;
- no known intervening revision affecting selected fields.

Eligible to support future `PIT_VERSION_A`.

### `SNAPSHOT_B_ORIGINAL_DIFF_EXPLAINED`

- valid contemporaneous capture;
- current artifact differs;
- official revision/correction lineage explains the difference.

Original archived value remains the only value eligible for a decision before
the revision.

### `SNAPSHOT_C_DIFF_UNEXPLAINED`

- archived and current semantic fields differ;
- no sufficient official lineage explains why.

Fail closed.

### `SNAPSHOT_D_NO_CONTEMPORANEOUS_CAPTURE`

- no acceptable snapshot after release and before revision can be established.

Fail closed for canonical PIT use.

### `SNAPSHOT_E_RELEASE_CLOCK_UNRESOLVED`

Fail closed.

## 8. Revision ledger requirements

Each sample must carry:

- report date;
- intended release date;
- actual release time/date;
- disruption type;
- CFTC announcement URL;
- correction/revision announcement URL(s);
- affected report family;
- affected contract/market if specified;
- revision publication timestamp/date;
- original snapshot identity;
- revised snapshot identity when available;
- original semantic-field hash;
- revised semantic-field hash;
- disposition.

Unknown scope is recorded as unknown, never assumed Bitcoin-unaffected.

## 9. Fail-closed rules

Reject PIT admission for a sample if:

1. archive capture is before actual public release;
2. archive capture timestamp is missing or non-reproducible;
3. archived bytes cannot be retrieved and hashed;
4. Bitcoin section cannot be parsed deterministically;
5. current and archived semantic values differ without explainable lineage;
6. a known correction exists but original and revised versions cannot be
   separated;
7. release time is guessed from report date;
8. report family changes between archived/current comparisons;
9. TFF/Legacy or Futures Only/Combined are mixed;
10. standard/Micro Bitcoin are aggregated in this provenance test.

## 10. Admission decision rule

The snapshot-provenance mechanism itself is considered validated only if:

- S1 normal release is recoverable at `SNAPSHOT_A` or `B`;
- at least one delayed-release sample among S2/S3/S5 is recoverable with correct
  actual-publication semantics;
- S4 ION is either recoverable with explicit revision lineage or is explicitly
  rejected without contaminating other periods;
- no sample uses current-only data to impersonate historical original data.

This protocol does not require all historical weeks to become admissible.

After protocol validation, canonical-history construction must include only weeks
that independently meet the frozen provenance standard.

## 11. No-outcome rule

During snapshot acquisition/comparison:

- do not join Spot prices;
- do not compute returns;
- do not inspect subsequent Bitcoin moves;
- do not compare profitable/unprofitable weeks;
- do not reorder dates based on market outcomes.

Archive availability alone determines admissibility.

## 12. Execution-mode boundary

This protocol design is `CHAT_DIRECTOR`.

The next stage:

`RIE-006-IEI-COT-PIT-SNAPSHOT-ACQUISITION-004`

would retrieve, preserve, hash and compare multiple archived artifacts and produce
a provenance pack.

If that stage is executed as coordinated acquisition/transformation across the
five regimes or expanded historical coverage, it is `WORK_REQUIRED` under the
Execution Mode Matrix.

No acquisition execution begins from this protocol automatically.

## 13. Closeout

- Work Unit ID: `RIE-006-IEI-COT-PIT-SNAPSHOT-PROTOCOL-003`
- starting HEAD: `4070213f00ef0f3d727a9438337a76e8daf677c2`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item: `AF-03D-FU-01`
- files changed: this protocol only
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next stage: `RIE-006-IEI-COT-PIT-SNAPSHOT-ACQUISITION-004`
- next-stage expected mode: `WORK_REQUIRED`
- merge status: NO

**MERGED=NO**
