# CRL-003 — Data quality and canonical manifests

Status: **ACTIVE — 2026-09-23**

Entry evidence: CRL-002 accepted after real VPS pilot `CRL-E003` with six complete
source-provenance manifests, exact row counts, zero acquisition gaps/duplicates,
REST boundary matches and an external P10 no-write proof.

Goal: admit only datasets safe for replay.

Required checks:
- closed candles only;
- exact timeframe alignment;
- no duplicates;
- no gaps unless explicitly classified and quarantined;
- monotonic timestamps;
- valid decimal OHLCV;
- symbol/interval identity;
- bounded event window;
- immutable canonical manifest;
- deterministic SHA-256.

Data-quality failure is evidence; it is not silently repaired. Any repair requires a
new manifest/version and explicit reason.

Exit gate: every admitted event dataset has a canonical quality PASS manifest;
failed datasets remain indexed as failed evidence.


## Active execution order

1. define/version the canonical CRL-003 quality-manifest schema and deterministic
   validation rules before inspecting Development outcomes;
2. validate the already acquired CRL-E003 six-dataset pilot using structural and
   semantic quality checks only;
3. only after the validator is accepted, acquire/validate the remaining registered
   Development datasets in bounded batches;
4. Blind Holdout acquisition/quality remains automated structural-only and must
   not expose price/return/drawdown/strategy summaries before final evaluation;
5. replay stays closed until an event's required datasets have CRL-003 quality
   PASS manifests.

CRL-003 may reject or quarantine a dataset. It must never silently edit source
history to manufacture a PASS.
