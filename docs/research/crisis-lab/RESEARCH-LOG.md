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
