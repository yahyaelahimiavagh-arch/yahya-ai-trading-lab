# RIE-006 — IEI COT PIT Version Audit 002

Work Unit ID: `RIE-006-IEI-COT-PIT-VERSION-AUDIT-002`  
Status: **AUDIT COMPLETE / ORIGINAL-AT-RELEASE PROVENANCE NOT ESTABLISHED / FAIL CLOSED / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state verified directly before execution:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `2b2315b02ba16f5e50fedac454bc7d4cdd0e4d08`
- PR #152: OPEN / DRAFT / UNMERGED

Boundary:
- PAPER / RESEARCH ONLY
- `LIVE_MASTER_LOCK=OFF`
- P10 untouched and not read
- P11 locked
- Fresh OOS sealed
- recent reserve sealed
- no Development / crisis / Forward performance evidence read
- no returns, backtests, parameter sweeps or outcome optimization

Parent audit:
- `RIE-006-IEI-COT-DATA-AUDIT-001.md`

Parent AF-03D queue:
- `AF-03D-FU-01 COT publication audit`

## 1. Audit question

Can YATL establish, from legal/public evidence, that the CFTC Bitcoin COT value
used for a historical decision is the same version that was publicly available at
that historical decision time rather than a later corrected/reclassified value?

This audit is about version provenance only. It does not test predictive or
economic performance.

## 2. Direct official evidence inspected

### 2.1 CFTC Historical Viewable weekly artifacts

CFTC exposes dated weekly HTML reports in the historical archive.

Examples inspected:
- Legacy Futures Only, CME, report date 2018-05-01:
  `deacmesf050118.htm`
- Legacy Futures Only, CME, report date 2018-08-28:
  `deacmesf082818.htm`
- Legacy Futures Only, CME, report date 2018-11-06:
  `deacmesf110618.htm`
- Legacy Futures Only, CME, report date 2018-12-31:
  `deacmesf123118.htm`

These pages contain:
- `BITCOIN - CHICAGO MERCANTILE EXCHANGE`
- CFTC code `133741`
- report-date/as-of label
- contract unit `5 Bitcoins`
- category positions and open interest.

CFTC's Historical Viewable index explicitly states:

> Dates indicate the report date and not the release date.

Therefore the dated weekly file is a useful report artifact, but its filename/date
does not establish publication time.

Official sources:
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2018/futures/deacmesf050118.htm
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2018/futures/deacmesf082818.htm
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2018/futures/deacmesf110618.htm
- https://www.cftc.gov/sites/default/files/files/dea/cotarchives/2018/futures/deacmesf123118.htm

## 3. What official weekly pages prove — and do not prove

### Proven

For a currently retrievable dated weekly artifact, YATL can verify:
- report family;
- report/as-of date;
- contract code;
- contract unit;
- currently served category values;
- current artifact bytes after retrieval;
- current artifact hash after retrieval.

### Not proven

The current CFTC page does **not** by itself prove:
- the exact bytes served at the original release time;
- that category values were never corrected later;
- that trader classification was never changed;
- that the same URL was never overwritten;
- an immutable original publication hash;
- an original CFTC version identifier;
- a complete revision lineage for that specific row.

Therefore:

`CURRENT_CFTC_DATED_ARTIFACT != PROVEN_ORIGINAL_AT_RELEASE_ARTIFACT`

unless independent provenance establishes equivalence.

## 4. Official revision evidence

CFTC's Historical Special Announcements establish that COT artifacts and
underlying report content can change after initial publication.

Examples include:
- incomplete or incorrect COT data followed by corrections;
- revised reports after reporting-firm problems;
- trader reclassifications;
- revised concentration ratios;
- formatting corrections that caused revised COT files;
- historical compressed reports revised after classification changes.

2018 examples:
- 2018-09-25: CFTC stated concentration ratios published on 2018-09-21 for
  report date 2018-09-18 were incorrect.
- 2018-09-26: corrections were made.
- 2018-07-25: CFTC documented trader reclassification in the Supplemental
  Commodity Index report and stated that classifications can change with new
  information.

These particular 2018 notices do not prove that CME Bitcoin Legacy position
counts were revised. They prove the broader version-risk mechanism and therefore
prevent an assumption of global archive immutability.

Official source:
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm

## 5. Bitcoin classification-specific risk

CFTC's 2017 Bitcoin COT announcement for the CBOE Bitcoin contract is directly
relevant to the classification process.

CFTC stated that:
- Bitcoin was placed in the financial report classification;
- Legacy default classification could be Non-Commercial;
- TFF classification reused a trader's classification from other published
  financial contracts when available;
- otherwise a trader could default to Other Reportable;
- Form 40 information had not yet been fully updated for Bitcoin;
- classifications could change after receipt/processing of new Form 40 or other
  information.

This is not evidence that CME code `133741` had a specific revision on a
specific week. It is official evidence that early Bitcoin trader-category labels
were not guaranteed immutable.

Official source:
- CFTC Historical Special Announcements, 2017-12-22 entry.

## 6. Abnormal release/version episodes remain mandatory

### 6.1 2018–2019 lapse in appropriations

CFTC stated:
- last normal COT publication was 2018-12-21;
- the report originally scheduled for 2018-12-28, based on 2018-12-24 data,
  was expected to be published on 2019-02-01;
- catch-up reports followed in chronological order on accelerated Tuesday/Friday
  releases.

Thus a current historical page for a shutdown-era report cannot inherit the
originally scheduled December/January release date.

Official source:
- https://www.cftc.gov/PressRoom/PressReleases/7864-19

### 6.2 2023 ION incident

CFTC stated that some reporting firms could not submit timely and accurate data
after the ION cyber incident.

CFTC also instructed affected reporting firms to:
- use best estimates when necessary;
- file revised reports after systems became operational.

Later CFTC statements postponed and then sequentially released missed COT
reports.

This is direct evidence that:
- release-time availability can diverge materially from report date;
- later revisions may exist because contemporaneous submissions were incomplete
  or estimated.

Official sources:
- https://www.cftc.gov/PressRoom/SpeechesTestimony/cftcstatement020223
- https://www.cftc.gov/PressRoom/PressReleases/8655-23
- https://www.cftc.gov/PressRoom/PressReleases/8662-23

### 6.3 2025 lapse in appropriations

CFTC's Historical Special Announcements include an explicit mapping of:
- COT report date;
- original intended publish date;
- actual new publish date.

Example:
- report date: 2025-09-30
- original publish date: 2025-10-03
- actual catch-up publish date: 2025-11-19.

This reinforces that PIT logic must use actual publication, not intended
publication.

## 7. External web-archive provenance attempt

The bounded audit attempted to establish whether a public web archive could
supply snapshot-level provenance for representative 2018 CFTC weekly Bitcoin
pages.

Within the available research tooling, a reproducible snapshot record containing:
- archive capture timestamp;
- original CFTC URL;
- archived response bytes or digest;
- capture identity suitable for a YATL provenance ledger

was **not established**.

Search-engine metadata that labels a CFTC page as having been published/crawled
near the historical date is not accepted as immutable archive provenance.

Fail-closed rule:

> Search-engine publication/crawl metadata is not a substitute for an archived
> artifact hash or reproducible snapshot identifier.

No claim is made that a legal public web archive cannot supply such evidence.
This audit establishes only that sufficient reproducible snapshot provenance was
not obtained in this bounded pass.

## 8. PIT version-admissibility levels

Future ingestion must label every COT row/artifact with one of these states.

### `PIT_VERSION_A` — Strong

Required:
- contemporaneous archived artifact captured at/after public release and before
  any known revision;
- reproducible snapshot timestamp/identifier;
- raw bytes preserved by YATL;
- SHA-256;
- release clock established;
- revision ledger checked.

Eligible for future canonical use subject to the rest of the preregistered
protocol.

### `PIT_VERSION_B` — Current official artifact + no proven original snapshot

Evidence:
- current CFTC dated weekly artifact;
- release calendar/special announcements;
- no known specific revision affecting that row;
- but no immutable original-at-release copy/digest.

**Not canonical-admitted.**
May be used only for source/method engineering where no economic outcome is read.

### `PIT_VERSION_C` — Known revision/uncertain classification/version

Examples:
- affected by a correction/reclassification notice;
- ION best-estimate/revision environment without original/revised separation;
- source version cannot be associated with the proposed decision time.

**Ineligible** until original/revision lineage is recovered.

### `PIT_VERSION_D` — Publication time itself unresolved

**Ineligible.**

## 9. Conservative admissibility decision

Current disposition for historical CME Bitcoin COT:

**`BLOCKED_PIT_ORIGINAL_VERSIONING` remains.**

The existence of dated CFTC weekly pages reduces the problem from
"no historical artifact exists" to:

> "historical artifact exists, but original-at-release version equivalence is not
> sufficiently proven for canonical outcome testing."

This is a meaningful narrowing of the blocker, but not a scientific admission.

## 10. What may proceed without spending outcome evidence

Allowed:
- freeze the exact CFTC source family candidates under consideration;
- define archive acquisition/provenance schema;
- attempt bounded snapshot recovery;
- build a revision ledger;
- hash retrieved source artifacts;
- specify rejection rules.

Not allowed:
- Development backtest;
- return comparison;
- threshold selection;
- candidate promotion;
- opening Fresh OOS/recent reserve;
- using current archive values as though they were automatically PIT-correct.

## 11. Cheapest next falsification

Next bounded action:

`RIE-006-IEI-COT-PIT-SNAPSHOT-PROTOCOL-003`

Goal:
- freeze an exact legal/public provenance-recovery protocol before any bulk
  acquisition;
- define representative sample dates covering:
  1. normal release;
  2. federal-holiday release;
  3. 2018–2019 shutdown catch-up;
  4. 2023 ION disruption;
  5. 2025 shutdown catch-up;
- define acceptable archive snapshot evidence;
- define byte/hash comparison with current CFTC artifact;
- define revision-ledger mapping;
- define fail-closed criteria when a snapshot is missing.

This protocol design remains `CHAT_DIRECTOR`.

If the subsequent stage requires bulk archive acquisition, transformation or
many-file comparison, re-apply the Execution Mode Matrix. That later stage is
expected to be `WORK_REQUIRED`.

## 12. Work-unit closeout

- Work Unit ID: `RIE-006-IEI-COT-PIT-VERSION-AUDIT-002`
- GitHub authoritative starting HEAD:
  `2b2315b02ba16f5e50fedac454bc7d4cdd0e4d08`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item addressed: `AF-03D-FU-01 COT publication audit`
- files changed: this audit artifact only
- sources/endpoints inspected:
  CFTC Historical Viewable index; dated CFTC CME Legacy weekly reports;
  CFTC Historical Special Announcements; CFTC delayed-report press release;
  CFTC 2023 ION statements/releases
- PIT/publication-time findings:
  dated weekly artifacts exist, but current availability does not prove
  original-at-release byte/value identity
- blocker resolved:
  existence/location/identity of dated official weekly Bitcoin artifacts
- blockers remaining:
  immutable original-at-release snapshot/digest and row-level revision lineage
- negative evidence:
  official correction/reclassification/revision history; ION best-estimate and
  later-revision environment; shutdown publication gaps
- duplicate/mechanism-cluster findings:
  none newly created; COT remains within leverage/crowding cluster
- tests:
  source/provenance audit only; no code/performance test
- CI:
  documentation-only work unit; verify Final HEAD status after commit
- Fresh OOS:
  SEALED / NOT READ
- recent reserve:
  SEALED / NOT READ
- P10:
  UNTOUCHED / NOT READ / NOT WRITTEN
- P11:
  LOCKED
- next allowed action:
  `RIE-006-IEI-COT-PIT-SNAPSHOT-PROTOCOL-003`
- merge status:
  NO

**MERGED=NO**
