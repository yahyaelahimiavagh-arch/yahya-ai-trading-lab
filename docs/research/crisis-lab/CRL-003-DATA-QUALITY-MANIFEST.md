# CRL-003 — Data quality and canonical manifests

Status: **ACTIVE — CRL-E003 REAL VPS QUALITY PASS ACCEPTED / REMAINING REGISTERED DATASETS PENDING**

Entry evidence: CRL-002 accepted after real VPS pilot `CRL-E003` with six complete
source-provenance manifests, exact row counts, zero acquisition gaps/duplicates,
REST boundary matches and an external P10 no-write proof.

Canonical machine-readable contract: `QUALITY-MANIFEST-SPEC-v0.1.0.json`.

Goal: admit only datasets safe for replay.

Required checks:
- closed candles only;
- exact timeframe alignment;
- no duplicates;
- no gaps unless explicitly classified and quarantined;
- monotonic timestamps;
- any CRL-002 historical close-boundary normalization has a one-for-one exact
  REST verification count; incomplete fallback evidence is a quality failure;
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


## v0.1.0 implementation

Research-only validator: `research/crisis_lab/quality.py`.

Invocation:

```bash
uv run --locked python -m research.crisis_lab.quality validate-event \
  --runtime-root data/research/crisis-lab \
  --event-manifest <event-acquisition-relative-path> \
  --event-manifest-sha256 <full-sha256>
```

The validator does not call Binance and does not read P10. It validates only the
immutable CRL-002 runtime corpus supplied by explicit content-addressed identity.

Dataset admission requires:
- acquisition/event/dataset schema and identity consistency;
- content-address filename + full SHA-256 integrity;
- official archive checksum identity retained from CRL-002;
- REST boundary verification already equal to `MATCH`;
- exact semantic/transport bounds and UTC timeframe grid;
- exact expected row count;
- monotonic, unique and contiguous timestamps;
- exact close-time semantics and closed candles only;
- finite decimal OHLCV fields;
- positive prices and valid OHLC relations;
- nonnegative volume/trade counts and taker volume not exceeding totals;
- all Paper-only/P10-no-write/P11-lock safety invariants retained.

Quality output contains only structural evidence, identities, counts, bounds,
digests and failure codes. It never emits candle prices, returns, direction,
PnL, drawdown, volatility rank, plots or YATL trade metrics.

A catalog-replay-ineligible event may receive structural quality PASS but remains
`replay_admitted=false`. Quality PASS never overrides the event catalog.

## CRL-E003 real VPS quality evidence — 2026-09-24

Validation ran on VPS `vps-2e03c7d1` after updating the repository to accepted
CRL-003 implementation checkpoint
`90ff04eaaa7d15ff282ab06f48759db201d2debb`.

Input event acquisition manifest:
- relative path:
  `manifests/event-catalog-v0.1.0/CRL-E003/event-acquisition-bb2986d87cb672eb91e2dccf.json`;
- full SHA-256:
  `bb2986d87cb672eb91e2dccfbc7e593ea05c12b6f9a49d0d1ffd762b01b995cb`.

Real validator result:
- event: `CRL-E003`;
- designation: `DEVELOPMENT`;
- datasets: **6/6 PASS**;
- failures: **0**;
- overall status: **PASS**;
- admission reason: `QUALITY_PASS`;
- replay eligible: `true`;
- replay admitted: `true`;
- market outcomes exposed: `false`;
- P10 write allowed: `false`;
- P11 locked: `true`;
- research only: `true`.

Canonical runtime quality manifest:
- relative path:
  `quality/event-catalog-v0.1.0/CRL-E003/event-quality-9db76653f252ac16e44fdd70.json`;
- full SHA-256:
  `9db76653f252ac16e44fdd701f606bcd1e177609cb4e342e4564dc8d9bd77451`.

This accepts CRL-E003 for CRL-004 replay work. It does **not** close CRL-003 for
the remaining registered corpus; those datasets still require bounded acquisition
and the same deterministic quality admission.

## CRL-003 implementation / pilot gate

- machine-readable quality contract frozen — **PASS**;
- deterministic research-only validator implemented — **PASS**;
- focused adversarial/unit test matrix — **PASS**;
- matching Final-HEAD GitHub Actions for PR #88 — **PASS**;
- production dependency changes — **NONE**;
- P10 access/write capability — **NONE**;
- real CRL-E003 quality manifest — **PASS / ACCEPTED 2026-09-24**;
- remaining registered Development datasets — **PENDING BOUNDED ACQUISITION + QUALITY**.

CRL-004 is open for replay implementation and validation against CRL-E003 only.
No unadmitted event dataset may enter replay.
