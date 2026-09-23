# Crisis Lab Research Log

Append-only decision/evidence log.

## 2026-09-22

- Crisis & Regime Stress Lab approved as a parallel RESEARCH_ONLY track.
- Active P10 must remain untouched.
- Formal data-acquisition work is scheduled from 2026-09-23; desk research and
  planning may begin immediately.
- Ordered checkpoints CRL-000 through CRL-010 established.
- First execution target: CRL-001 Event Catalog research, followed by CRL-002 data
  acquisition planning.

- Repository entry audit verified `main` at
  `8f47fefb0dc05a1cd3f3c9d5a65a4377d54c2b60` before Crisis Lab work.
- CRL-000 audit found no blocking boundary defect. The charter was strengthened
  with explicit P10-owned runtime paths, fail-closed no-write rules, holdout
  visibility rules, timestamp-conflict quarantine and v0.1 exclusion of
  News/Macro/AI from the decision path.
- CRL-001 Event Catalog v0.1.0 registered with **16** source-backed events:
  **9 Development / 7 Blind Holdout**. Fixed window templates were registered
  before replay; no endpoint is selected from later BTC/ETH extrema.
- CRL-E010 (7 October 2023) and CRL-E015 (Hormuz 2026 shipping disruption) remain
  replay-ineligible because first-public-timestamp evidence is not clean enough.
  Quarantine is retained rather than inventing precision.
- CRL-E016 adds an explicit sudden crypto price-dislocation case as
  **Development-only** because its selection is outcome/price-defined; it cannot
  serve as a blind holdout or evidence of ex-ante prediction.
- No BTCUSDT/ETHUSDT holdout return summary, plot, YATL replay or strategy metric
  was inspected or produced during CRL-001 registration.
- CRL-002 acquisition specification v0.1.0 registered: official Binance Public
  Data daily Spot klines are the primary bulk source; credential-free Binance
  market-data REST is verification/fallback; source disagreements quarantine
  instead of silently overwriting data.
- Binance Spot archive timestamps from 2025-01-01 onward are treated as
  microseconds per the official public-data documentation. Timestamp units and
  raw/canonical hashes are mandatory provenance.
- Crisis Lab bulk runtime data remains under `data/research/crisis-lab/` and
  outside Git. The active P10 runtime tree `/var/lib/yatl/p10/` is a forbidden
  acquisition input/output target.
- CRL-002 remains **IN PROGRESS** until real VPS acquisition, provenance manifests
  and an explicit before/after no-P10-write proof exist.
- No historical profitability, robustness PASS, economic acceptance or Live
  readiness conclusion has been produced. P10 and P11 status are unchanged.
- Pre-PR structural validation PASS: catalog JSON parses; 16 event IDs are unique;
  split is 9 Development / 7 Blind Holdout; every event has source metadata;
  CRL-E010 and CRL-E015 are the only replay-quarantined records; all registered
  events retain BTCUSDT/ETHUSDT × 15m/1h/4h primary scope.
- Acquisition register IDs match the catalog exactly and retain
  `/var/lib/yatl/p10/` as a protected runtime prefix with P11 locked.
- Git compare against entry checkpoint `8f47fef...` shows every changed path is
  under `docs/research/crisis-lab/`. `docs/P10-OPERATIONS.md` retained blob
  SHA `cf3868cc8f3fc9178e8511d7a567fb090c50a61f` on both `main` and the research branch.

- CRL-002 implementation branch opened from accepted research checkpoint
  `80bb590a8fdac29ee2e12f6f42f6951c697966b5`.
- Added research-only package `research/crisis_lab/`; production `yatl` imports
  were not changed.
- Implemented event/dataset planning, official Binance Public Data archive
  acquisition, sibling CHECKSUM verification, immutable content-addressed runtime
  storage, millisecond/microsecond normalization, exact UTC-grid checks and
  credential-free REST boundary verification.
- Network transport is HTTPS-only with exact host allowlists, redirects and
  ambient proxies disabled, bounded response sizes and at most three attempts.
- Runtime path resolution rejects `/var/lib/yatl/p10/` and descendants before
  opening an output target. Crisis Lab does not read P10 runtime evidence.
- Blind Holdout CLI/manifests expose structural provenance only; no return, PnL,
  direction, drawdown, volatility rank, trade result or price summary is emitted.
- Added focused CRL-002 tests covering register consistency, P10 path rejection,
  monthly/daily archive planning, 2025 timestamp-unit transition, checksum
  identity, microsecond boundary failure, immutable replay, source-conflict
  quarantine, exact six-dataset event scope, Holdout redaction and capability
  source scan.
- Local isolated execution of the focused CRL-002 test module before GitHub write:
  **18/18 PASS**. This is development evidence only; matching Final-HEAD GitHub
  Actions remains required before merge.
- Added `CRL-002-VPS-RUNBOOK.md`. Real VPS acquisition and external before/after
  P10 no-write proof remain pending, so CRL-002 is still **IN PROGRESS** and
  CRL-003 is not open.
- Pre-merge boundary review found and closed one gap: custom `--register` input
  paths now pass the same protected-path guard as runtime outputs, so Crisis Lab
  cannot be pointed at a registration file under `/var/lib/yatl/p10/`.

- CRL-002 transport provenance was tightened before merge: real HTTPS fetches now
  retain sanitized attempt/failure summaries, and repeated acquisition reuses a
  locally cached ZIP only after its full SHA-256 matches the freshly fetched
  official CHECKSUM. A conflicting cache fails closed rather than redownloading
  over it.
- Focused tests were extended for bounded retry provenance and verified archive
  cache reuse. Final acceptance remains tied to the latest GitHub Actions HEAD,
  not the earlier superseded runs.


## 2026-09-23

- CRL-002 implementation PR #86 Final candidate HEAD
  `e3b3e12cd54ef4b612d211473680c40421f0ddf5` completed matching GitHub Actions
  run `35783881556` successfully and was squash-merged to `main` at
  `2b58280af5afb5ef895487565bbe951d78feb3fd`.
- Real VPS pilot acquisition executed for Development event `CRL-E003`.
  Event-level status was `COMPLETE`: 6/6 BTCUSDT/ETHUSDT × 15m/1h/4h datasets,
  zero failures, exact expected row counts, zero gaps, zero duplicates and REST
  boundary verification `MATCH` for every dataset.
- Event acquisition manifest file SHA-256:
  `bb2986d87cb672eb91e2dccfbc7e593ea05c12b6f9a49d0d1ffd762b01b995cb`;
  retrieval timestamp `2026-09-23T12:12:57Z`.
- External P10 no-write evidence PASS. Before/after SHA-256 values were identical:
  P10 SQLite `577fc15d3a8966c3f947166376b11945f93de0a32a57cdc4ec2958f7c2fad2f2`;
  snapshot `4fd18e0d3de9dca0978c9766867364313960db9c11f13583b49a793f03340687`.
  Hash-file diff was empty; repository working tree remained clean.
- CRL-002 is ACCEPTED as the reproducible acquisition/provenance mechanism.
  This does not pre-admit the remaining corpus; CRL-003 now owns dataset quality
  admission and replay remains closed pending CRL-003 PASS manifests.
- P10 candidate/config/gates/window/evidence remain unchanged. P11 remains locked.
