# RIE-006 — IEI COT Data Audit 001

Work Unit ID: `RIE-006-IEI-COT-DATA-AUDIT-001`  
Status: **AUDIT COMPLETE / PUBLICATION CLOCK PARTIALLY RESOLVED / PIT ORIGINAL-VERSION BLOCKED / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state verified directly before execution:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `33294e7165c9eb3731928b6f79ee0dbd46d5d102`
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

Parent checkpoint:
- `AF-03D-CORPUS-SYNTHESIS-CHECKPOINT-v1.0.md`
- queue item: **AF-03D-FU-01 COT publication audit**

Mechanism under audit:
- `IEI-MECH-011 — Regulated trader-positioning pressure`
- no candidate is created or promoted by this audit.

## 1. Audit question

Can CME Bitcoin CFTC Commitments of Traders data be reconstructed with an explicit
point-in-time publication clock, contract lineage and revision policy such that a
future preregistered Spot long/cash method cannot accidentally use Tuesday
positions before they were public?

This unit does **not** ask whether COT predicts returns.

## 2. Official-source findings

### 2.1 Observation date is not publication date

CFTC states that COT reports provide a breakdown of Tuesday open interest and are
generally released later in the week. Current CFTC documentation states:

- COT reports are released at **3:30 p.m. Eastern time**.
- Futures Only and Futures-and-Options Combined reports are usually released on
  Friday.
- the release usually includes data from the previous Tuesday.
- federal holidays may delay publication by one or two days.
- CFTC receives reporting-firm data on Wednesday morning, then corrects and
  verifies it for Friday-afternoon release.
- the CFTC Historical Viewable index explicitly warns that displayed dates are
  **report dates, not release dates**.

Therefore:
`report_date == observation/as-of date` MUST NOT be used as
`public_availability_time`.

Official sources:
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm

### 2.2 Historical archive structure

CFTC maintains several historical report families.

Relevant structures include:
- Legacy Futures Only by year, with history back to 1986.
- Legacy Futures-and-Options Combined by year, from March 1995.
- Disaggregated Futures Only / Combined by year.
- Traders in Financial Futures (TFF) Futures Only / Combined by year.
- historical viewable weekly reports.
- the CFTC Public Reporting Environment (PRE).

For TFF, the Historical Compressed index lists annual files and historical files
back to 2006, while the TFF report itself was introduced in 2010.

Important:
annual historical files and PRE are convenient query surfaces, but their existence
today does **not** establish what was publicly available on a historical decision
date.

Official source:
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm

## 3. Required six-clock model

Every COT row used by YATL must carry six distinct time concepts.

### 3.1 `observation_time`

The market-position observation represented by the COT report.

For ordinary reports this is the Tuesday open-interest snapshot. Do not invent an
intraday timestamp if the source only proves the report date.

### 3.2 `as_of_time`

The CFTC report-date label.

Usually Tuesday, but holiday exceptions exist. Examples in CFTC special
announcements show weeks where Monday data were used instead.

### 3.3 `public_availability_time`

The earliest time YATL can prove the row was public.

Normal case:
- release date from the official CFTC Release Schedule;
- 15:30 `America/New_York`, DST-aware.

Special case:
- a CFTC Historical Special Announcement or specific CFTC release overrides the
  normal schedule.

If an abnormal catch-up announcement proves only the publication **date** and not
the exact intraday time, the timestamp is **not reconstructed by assumption**.

### 3.4 `retrieval_time`

UTC time at which YATL fetched the artifact.

This is not a substitute for historical public availability.

### 3.5 `revision_version_time`

Timestamp/date at which a correction, reclassification, revised artifact or other
version change became known.

If no immutable original is available, record `UNKNOWN_ORIGINAL_VERSION`.

### 3.6 `decision_eligibility_time`

Earliest strategy decision time after:
1. proven public availability;
2. ingestion/processing latency;
3. any required completed Spot decision bar.

Normal scheduled COT rows can be eligible only after 15:30 Eastern on the actual
release day, never from Tuesday merely because the row is dated Tuesday.

If the release date is known but intraday release time is not provable, a
same-day decision is disallowed. The conservative fallback is no earlier than
00:00 `America/New_York` on the following calendar day, subject to the later
strategy bar rule.

## 4. Holiday and abnormal-release evidence

The normal Friday clock is not universal.

### 4.1 Ordinary federal-holiday delays

The CFTC Release Schedule explicitly marks delayed dates caused by federal
holidays and states that holidays may delay release by one or two days.

CFTC historical announcements also show that the **as-of date itself can change**.
Examples:
- 2020 holiday handling used Monday December 21 data and published on Monday
  December 28.
- 2018 year-end notices specified Monday observations when Christmas and New
  Year's Day fell on Tuesday.
- June 2021 Juneteenth observance moved a report containing Tuesday June 15 data
  from Friday June 18 to Monday June 21.

Therefore a generic `Tuesday + 3 days` rule is invalid.

### 4.2 2018–2019 lapse in appropriations

CFTC suspended weekly COT publication during the federal shutdown.

Official CFTC release 7864-19 states:
- last COT publication before the backlog was December 21, 2018;
- the report originally scheduled for December 28, 2018, based on Monday
  December 24 data, was expected to be published February 1, 2019;
- CFTC then used accelerated Tuesday/Friday catch-up publications.

A modern historical query returning those old rows cannot move their public
availability backward into December/January.

Official source:
- https://www.cftc.gov/PressRoom/PressReleases/7864-19

### 4.3 2023 ION cyber-related reporting failure

CFTC postponed COT releases because reporting firms could not submit timely and
accurate data after the ION incident.

CFTC subsequently issued missed reports sequentially:
- February 24: report originally due February 3;
- March 3: report originally due February 10;
- March 8: report originally due February 17;
- March 10: report originally due February 24;
- March 14: report originally due March 3;
- March 16: report originally due March 10;
- March 21: report originally due March 17.

CFTC also documented adjustments to some affected markets to provide best
estimates of positions.

This establishes both publication-delay risk and contemporaneous data-quality /
revision risk.

Official sources:
- https://www.cftc.gov/PressRoom/PressReleases/8662-23
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm

### 4.4 2025 lapse in federal appropriations

CFTC states that COT processing/publication was interrupted from October 1 through
November 12, 2025.

The official catch-up table maps report dates and original publication dates to
new publication dates, beginning with:
- report date 2025-09-30;
- original publish date 2025-10-03;
- actual catch-up publication date 2025-11-19.

Further backlogged reports were released in chronological order.

This is direct evidence that historical report date and originally intended
publication date are insufficient for PIT eligibility.

Official source:
- https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm

## 5. Revision and classification provenance

### 5.1 Historical CFTC files are not guaranteed immutable originals

CFTC Historical Special Announcements document multiple forms of revision:
- reporting-firm corrections;
- revised reports after incomplete positions;
- concentration-ratio corrections;
- reclassification of traders;
- revised historical compressed data;
- formatting corrections that required revised COT files.

A particularly important historical example is July 2008, where CFTC stated that
historical compressed reports were revised after trader reclassification and
that individual historical HTML reports were also being replaced.

Therefore:

> Current historical query result != proven original-at-release value.

No YATL pipeline may silently treat a current PRE/annual archive result as the
exact value known to a historical trader unless original-version provenance is
established.

### 5.2 TFF trader categories have historical-classification limitations

TFF separates large financial-futures traders into:
- Dealer/Intermediary
- Asset Manager/Institutional
- Leveraged Funds
- Other Reportables

CFTC explanatory material states that it does not maintain a historical series
of large-trader classifications for the backcast history; recent classifications
were used to classify older historical positions, and accuracy diminishes further
back in time.

For CME Bitcoin, which begins after the 2010 TFF launch, this old pre-launch
backcast problem does not by itself invalidate every Bitcoin week. However:
- trader classifications can change;
- current bulk historical data must not be assumed to reproduce the exact
  classification that was public on the original release date;
- date-specific artifacts and revision notices remain required.

Official sources:
- CFTC TFF Explanatory Notes
- https://www.cftc.gov/PressRoom/PressReleases/5857-10
- https://www.cftc.gov/PressRoom/PressReleases/5943-10

## 6. CME Bitcoin contract lineage

### 6.1 Standard CME Bitcoin futures

CME listed the standard Bitcoin futures contract for trade date
**2017-12-18**.

Key identity:
- CME product: Bitcoin Futures
- product code: `BTC`
- CFTC market code observed in COT: `133741`
- contract size: **5 bitcoin**
- cash settled using the CME CF Bitcoin Reference Rate framework

The CFTC archive continues to identify:
`BITCOIN - CHICAGO MERCANTILE EXCHANGE — Code-133741`
with `(5 Bitcoins)`.

Official CME/CFTC sources:
- https://www.cmegroup.com/notices/ser/2017/12/SER-8051R.html
- CFTC dated CME COT reports

### 6.2 Micro Bitcoin futures

CME launched Micro Bitcoin futures for trade date **2021-05-03**.

Key identity:
- CME product: Micro Bitcoin Futures
- product code: `MBT`
- CFTC market code observed in COT: `133742`
- contract size: **0.10 bitcoin**

Official CME/CFTC sources:
- https://www.cmegroup.com/notices/ser/2021/03/SER-8746.html
- CFTC dated CME COT reports

### 6.3 No silent aggregation

Standard `133741` and Micro `133742` are separate reported contracts.

A future method must not:
- add contract counts directly;
- splice the two series as though one replaced the other;
- treat Micro launch as a contract-size change in `133741`;
- combine futures-only with futures-and-options-combined without preregistration.

If future research aggregates standard and Micro exposure, the aggregation rule
must be frozen before outcomes and normalized to a common BTC-equivalent notional
with separate contract identifiers preserved.

## 7. Series-selection rule for the next preregistration

This audit does **not** freeze a predictive formula.

The next preregistration must select exactly one primary CFTC report family for
the first candidate.

Two conceptually valid but non-equivalent source families exist:

1. **Legacy Futures Only / CME Bitcoin / 133741**
   - commercial / non-commercial categories.

2. **TFF Futures Only / CME Bitcoin / 133741**
   - Dealer/Intermediary
   - Asset Manager/Institutional
   - Leveraged Funds
   - Other Reportables

They MUST NOT be mixed after outcome inspection.

Futures-and-options-combined, Micro Bitcoin, or any cross-series composite requires
a separately frozen adaptation.

## 8. Reproducibility artifact requirements

Before any canonical historical performance run, the COT data package must
preserve at minimum:

- source URL;
- CFTC report family;
- CFTC contract code;
- market/exchange name;
- contract unit;
- report/as-of date;
- official scheduled release date;
- actual release date if a special announcement overrides schedule;
- exact public release timestamp when provable;
- timezone and UTC conversion;
- retrieval timestamp;
- raw artifact bytes where legally/publicly retrievable;
- SHA-256 of raw artifact;
- parser/schema version;
- transformation hash;
- revision flag;
- revision announcement URL/date;
- whether original-at-release version is proven;
- missing-data rule;
- decision-eligibility timestamp.

Do not silently forward-fill a missing COT week.

## 9. Fail-closed decision rules

A COT row is **INELIGIBLE** if any of the following applies:

1. the strategy would act from the Tuesday report date before public release;
2. the release date is inferred only from a generic Friday rule while an official
   holiday/delay exception exists;
3. a delayed/backlogged report is timestamped to its originally intended release
   rather than actual release;
4. the exact same-day release time is unknown and the strategy acts on that same
   day;
5. the row was corrected/revised and the historical version used by YATL cannot
   establish which version was available at the decision time;
6. contract identity or unit is ambiguous;
7. standard and Micro contracts are mixed without a frozen normalization rule;
8. trader-category mapping is reconstructed from a modern classification without
   contemporaneous provenance;
9. a missing report is silently filled from the next/previous week;
10. PRE/current annual files are treated as proof of historical public
    availability by themselves.

## 10. Adversarial findings

### A. Tuesday lookahead is decisively rejected

A Tuesday-dated row is not Tuesday-eligible.

This blocker is resolved at the protocol level.

### B. Generic Friday lag is insufficient

Holiday schedules, shutdowns, cyber incidents and catch-up publication create
real release-date variation.

The actual CFTC calendar/special-announcement mapping is mandatory.

### C. Current historical archive is revision-capable

The official archive is not an immutable tape of original releases.

This remains the central PIT data-admissibility blocker for a canonical historical
test.

### D. TFF/Legacy are not interchangeable

TFF is not merely a finer decomposition of Legacy categories. CFTC states that
TFF traders may be drawn from either Legacy commercial or non-commercial groups.

A future candidate must select one series before outcomes.

### E. Standard/Micro are not one continuous contract-count series

CFTC codes and contract units differ. Micro launch creates a new instrument, not
a historical rescaling of standard BTC futures.

### F. No economic conclusion follows

This audit establishes data/time semantics only. It does not establish
predictability, profitability, capacity, independence, persistence or
monetizable edge.

## 11. Audit disposition

### Resolved

- normal COT release clock identified;
- Tuesday as-of versus public-release distinction formalized;
- holiday-delay requirement formalized;
- major abnormal release episodes documented;
- six-clock schema specified;
- standard CME Bitcoin / Micro Bitcoin lineage identified;
- CFTC contract codes and units separated;
- no-silent-aggregation rule specified;
- revision provenance requirement specified.

### Remaining blocker

**`BLOCKED_PIT_ORIGINAL_VERSIONING`**

The current official historical query surfaces are revision-capable and do not,
by themselves, prove the exact original-at-release values for every historical
Bitcoin COT week.

Before canonical Development:
- reconstruct/verify original-version provenance for the intended historical
  sample, or
- freeze a conservative admissible subset with verifiable original artifacts,
  or
- reject historical COT as canonical PIT data if that provenance cannot be
  established.

Do not weaken this requirement after seeing outcomes.

## 12. Next allowed action

Bounded next action:

`RIE-006-IEI-COT-PIT-VERSION-AUDIT-002`

Purpose:
- test whether original weekly Bitcoin COT artifacts and revision lineage can be
  reconstructed sufficiently for canonical PIT use;
- inspect official dated weekly artifacts first;
- inspect official revision announcements;
- if official sources cannot establish original versions, evaluate a legal public
  web-archive snapshot strategy as provenance support;
- no returns;
- no backtest;
- no candidate promotion.

Only if PIT original-version admissibility is resolved should
`RIE-006-IEI-COT-PREREG-001` freeze the exact report family, category equation,
lag and Spot long/cash action.

## 13. Work-unit closeout

- Work Unit ID: `RIE-006-IEI-COT-DATA-AUDIT-001`
- GitHub authoritative starting HEAD:
  `33294e7165c9eb3731928b6f79ee0dbd46d5d102`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item addressed: `AF-03D-FU-01 COT publication audit`
- files changed: this audit artifact only
- sources/endpoints inspected: official CFTC COT release schedule, historical
  compressed archive, historical viewable archive, COT explanatory material,
  Historical Special Announcements, 2019 delayed-data release, 2023 ION release,
  CME standard Bitcoin and Micro Bitcoin listing notices, dated CFTC Bitcoin COT
  reports
- PIT/publication-time finding: normal and exception clocks can be modeled, but
  original-version immutability is not yet proven
- blocker resolved: Tuesday/publication-time leakage model
- blockers remaining: original-at-release version/revision provenance
- negative evidence: historical CFTC archives can be revised; TFF historical
  classification has backcast limitations; abnormal releases invalidate generic
  lag assumptions
- duplicate/mechanism-cluster finding: none newly created; COT remains within the
  broader leverage/crowding cluster and is not counted as an independent edge
- tests: documentation/source audit only; no code test required
- CI: not required for documentation-only bounded audit
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next allowed action: `RIE-006-IEI-COT-PIT-VERSION-AUDIT-002`
- merge status: NO

**MERGED=NO**
