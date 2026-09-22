# CRL-003 — Data quality and canonical manifests

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
