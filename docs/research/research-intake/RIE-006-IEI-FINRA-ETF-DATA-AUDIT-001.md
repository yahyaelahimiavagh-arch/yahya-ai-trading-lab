# RIE-006 — IEI FINRA / Spot Bitcoin ETF Clock Audit 001

Work Unit ID: `RIE-006-IEI-FINRA-ETF-DATA-AUDIT-001`  
Status: **BOUNDED AUDIT COMPLETE / PUBLICATION CLOCK PARTLY RESOLVED / PIT INVENTORY PROVENANCE BLOCKED / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting authoritative GitHub state:
- `main`: `ce8e7b747f712779ed5e16144d74bda013226948`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `f12ee7623a0664321c67d9d71122ae2f329f25be`
- PR #152: OPEN / DRAFT / UNMERGED

Parent checkpoint: `AF-03D-CORPUS-SYNTHESIS-CHECKPOINT-v1.0.md`  
Queue item: **AF-03D-FU-02 FINRA/ETF clock audit**

Boundary:
- PAPER / RESEARCH ONLY
- no price/return/backtest/performance evidence
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED
- `LIVE_MASTER_LOCK=OFF`
- no candidate creation or promotion

## 1. Audit question

Can the institutional-flow mechanisms associated with AF-03D mechanisms 022/023
be observed with a defensible historical publication clock before a proposed BTC
Spot decision, while keeping FINRA short-sale volume distinct from ETF inventory
creation/redemption state?

This unit tests data semantics and PIT feasibility only.

## 2. FINRA Daily Short Sale Volume

Official FINRA documentation establishes:

- Daily Short Sale Volume aggregates short-sale volume by security for qualifying
  publicly disseminated trades executed off-exchange and reported to FINRA TRFs,
  the ADF, or ORF.
- FINRA posts Daily Short Sale Volume files **no later than 6:00:00 p.m. ET on
  the same relevant trade date**.
- in rare cases FINRA can update a file on a later day; the original and updated
  files are shown and the latter identified as `Updated`.
- the files are **not consolidated with exchange short-sale data**.
- they exclude trading activity that is not publicly disseminated.
- FINRA explicitly states Daily Short Sale Volume is **not short interest**.

Official sources:
- https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files
- https://www.finra.org/finra-data/browse-catalog/short-sale-volume
- https://www.finra.org/rules-guidance/notices/information-notice-051019

### Consequence

A trade-date row is not eligible merely because the underlying trades occurred
during that session. A same-day BTC decision that occurs before the relevant
FINRA file is actually public cannot consume the complete daily value.

For a fail-closed historical protocol, absent a stronger dated publication log,
the conservative public clock for a normal daily file is no earlier than
18:00:00 America/New_York on the trade date.

If an `Updated` file exists, original and updated versions must remain separate.
A modern query must not silently replace the original historically known value.

## 3. FINRA semantic guardrail

The following interpretation is rejected:

`FINRA Daily Short Sale Volume == short interest`

It is also rejected as:

`FINRA Daily Short Sale Volume == total-market short-sale activity`

The numerator covers a bounded reporting universe. A ratio using FINRA short
volume against an incompatible total-volume denominator can create a false
economic interpretation.

Any future denominator must be preregistered and source-compatible.

## 4. Required FINRA clocks

Every admissible daily record must distinguish:

1. `observation_time` — trade date/session represented;
2. `as_of_time` — date label in the FINRA artifact;
3. `public_availability_time` — actual posting time when provable, otherwise
   conservative 18:00 ET bound for the normal file;
4. `retrieval_time`;
5. `revision_version_time` — including `Updated` files;
6. `decision_eligibility_time`.

Historical queryability is not PIT availability.

## 5. Spot Bitcoin ETP universe is time varying

SEC materials establish that proposed rule changes allowing spot Bitcoin ETP
listings were approved on 2024-01-10. Approval is not sufficient to assign every
approved product to a spot-holding universe from that date.

A concrete PIT counterexample is Hashdex DEFI:

- on 2024-01-10 Hashdex/Tidal described approval of the listing-rule conversion
  of the then Hashdex Bitcoin Futures ETF;
- an SEC-filed March 26, 2024 Free Writing Prospectus states that the conversion
  of the investment strategy to allow spot bitcoin holdings became effective
  **2024-03-27**;
- Hashdex's own current fund disclosure likewise states that performance through
  2024-03-26 reflected the previous futures strategy and the spot strategy is
  reflected from 2024-03-27 onward.

Sources:
- https://www.sec.gov/newsroom/speeches-statements/uyeda-statement-spot-bitcoin-011023
- https://www.sec.gov/Archives/edgar/data/1985840/000199937124000549/defi_fwp-011024.htm
- https://www.sec.gov/Archives/edgar/data/1985840/000199937124003989/defi_fwp-032624.htm
- https://hashdex-etfs.com/defi

Therefore a static modern list of "11 spot Bitcoin ETFs" backfilled to
2024-01-11 is not an admissible PIT universe rule.

## 6. ETF inventory / flow semantics

ETF secondary-market volume, FINRA short-sale volume, shares outstanding,
creation/redemption activity, net assets and bitcoin holdings are distinct
objects.

A future ETF inventory mechanism must not infer daily primary-market creations or
redemptions from secondary-market short-sale volume.

SEC periodic filings can prove shares outstanding and aggregate
creation/redemption activity at filing/reporting dates, but a later quarterly or
annual filing does not prove that the same daily inventory value was publicly
known on each historical day.

Issuer webpages may expose current/daily holdings, but current queryability does
not establish immutable historical daily snapshots or original publication
timestamps.

Therefore exact daily ETF inventory/flow history remains fail-closed until
original dated issuer/filing artifacts and publication clocks are established.

## 7. Denominator audit

For mechanism 022, no denominator is frozen in this audit.

Potential constructions such as:

- FINRA short volume / FINRA total volume;
- FINRA short volume / consolidated total market volume;
- FINRA short volume / shares outstanding;
- FINRA short volume / ETF net assets;

represent different measurements and cannot be substituted after seeing outcomes.

If shares outstanding is used, YATL must prove:
- the date-specific share count;
- its public availability time;
- whether it reflects creations/redemptions effective that day;
- revision/version lineage.

A modern shares-outstanding field is not acceptable as historical PIT evidence by
itself.

## 8. Missing days / holidays

A missing FINRA daily file is not zero.

Do not forward-fill, backward-fill or synthesize a short-volume value across:
- market holidays;
- non-trading days;
- absent facility data;
- publication failures.

Calendar alignment must use the relevant U.S. securities trading date and preserve
the BTC decision clock separately.

## 9. Mechanism clustering / dedupe

No new mechanism is created.

- FINRA ETF short-sale volume remains part of the institutional
  demand/risk-transfer cluster.
- ETF creation/redemption/inventory remains a related but non-identical
  institutional demand channel.
- neither is an independent edge merely because the observable differs.
- generic ETF price lead remains duplicate/rejected under AF-03D governance.

Incremental independence, if ever tested, requires a later frozen comparator and
cannot be inferred here.

## 10. Opportunity-starvation accounting

Any future use of after-18:00 ET FINRA availability as a gate must preserve:
- opportunities available before publication;
- opportunities delayed until publication;
- opportunities skipped;
- completed trades;
- missed moves;
- exposure;
- costs saved;
- opportunity cost;
- net economic effect.

A publication rule that eliminates nearly all opportunities is not automatically
successful.

No such economic measurement occurs in this audit.

## 11. Adversarial findings

### Resolved

- FINRA normal same-day latest posting bound: 18:00 ET.
- short-sale volume versus short-interest semantic distinction.
- off-exchange/publicly-disseminated scope limitation.
- later `Updated` file risk.
- static modern ETF-universe backfill is invalid.
- Hashdex DEFI supplies a concrete effective-date counterexample.

### Remaining blockers

**`BLOCKED_FINRA_ORIGINAL_DAILY_VERSION_PROVENANCE`**
- normal posting bound is documented, but a canonical historical dataset still
  needs original daily files/version lineage, especially when updates occurred.

**`BLOCKED_PIT_ETF_DAILY_INVENTORY_PROVENANCE`**
- exact historical daily shares/holdings/creation-redemption states and their
  public clocks are not established by current pages or later periodic filings.

**`DENOMINATOR_UNFROZEN`**
- no economically coherent denominator is selected at this audit stage.

These blockers must not be replaced with convenient modern vendor backfills after
outcome inspection.

## 12. Disposition

AF-03D-FU-02 is complete as a bounded clock/admissibility audit.

Mechanism 022:
`PUBLICATION_CLOCK_RESOLVED / ORIGINAL_VERSION_PROVENANCE_REQUIRED / DENOMINATOR_UNFROZEN`

Mechanism 023:
`BLOCKED_PIT_DAILY_INVENTORY_PROVENANCE`

No preregistration or performance test is authorized by this result.

The next bounded AF-03D queue item is:

`AF-03D-FU-03 Spot flow measurement protocol`

Expected route for the bounded specification: `CHAT_DIRECTOR`.

Substantial historical archive acquisition, if later authorized, is separately
`WORK_REQUIRED`.

## 13. Closeout

- Work Unit ID: `RIE-006-IEI-FINRA-ETF-DATA-AUDIT-001`
- execution mode: `CHAT_DIRECTOR`
- starting main: `ce8e7b747f712779ed5e16144d74bda013226948`
- starting branch HEAD: `f12ee7623a0664321c67d9d71122ae2f329f25be`
- branch: `research-institutional-edge-intelligence`
- AF-03D queue item addressed: `AF-03D-FU-02`
- files changed: this audit only
- tests: documentation/source audit only; no code tests
- performance evidence: NOT READ
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- next allowed action: `AF-03D-FU-03 Spot flow measurement protocol`
- merge status: NO

**MERGED=NO**
