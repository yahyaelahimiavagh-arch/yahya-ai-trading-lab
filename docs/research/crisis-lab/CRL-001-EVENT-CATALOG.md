# CRL-001 — Versioned Crisis Event Catalog

Status: **CATALOG v0.1.0 REGISTERED — 2026-09-22**

Canonical machine-readable catalog:
`EVENT-CATALOG-v0.1.0.json`.

Goal: build a source-backed catalog of crisis/regime windows without using future
market outcomes to choose the event boundaries.

## Catalog semantics

Every event records:

- stable `event_id` and catalog version;
- neutral event name and category;
- the earliest retained source-verifiable public timestamp for the specific
  milestone, its original timezone and normalized UTC value;
- timestamp precision/confidence and any source conflict;
- pre-event, core and aftermath windows;
- a predeclared window template and reason;
- required BTCUSDT/ETHUSDT market-data profile plus optional contextual data;
- shock type(s);
- `DEVELOPMENT` or `BLIND_HOLDOUT`;
- source registry;
- overlap/cluster identity so correlated events are not counted as independent
  samples;
- replay eligibility and anti-lookahead notes.

"First publicly knowable" does **not** mean the first moment the broader crisis
existed. It means the first retained timestamp for the exact milestone named in
the record. For example, the Terra record is anchored to Binance's exact LUNA/UST
withdrawal-suspension timestamp while preserving the earlier May 7 public Curve
liquidity signal as a precursor instead of inventing an intraday timestamp for it.

## Frozen v0.1 window templates

These durations were registered before any YATL crisis replay.

| Template | Pre-event | Core | Aftermath | Intended class |
|---|---:|---:|---:|---|
| `POINT_SHOCK_V1` | 7 days | 72 hours | 14 days | geopolitical, energy, banking, discrete public shocks |
| `OUTAGE_V1` | 24 hours | 24 hours | 72 hours | exchange/data availability incidents |
| `SOLVENCY_V1` | 7 days | 10 days | 30 days | stablecoin/exchange solvency cascades |
| `REGIME_180D_V1` | 30 days | 180 days | 30 days | slow regime transition/context episode |

Windows are half-open UTC intervals. The core starts at the registered anchor.
The aftermath starts when the fixed core duration ends. Operational resolution
timestamps may be retained as context, but do not shorten/extend a template.

These templates may be superseded only by a new catalog version **before** the
affected replay is inspected. v0.1 windows may never be moved to match subsequent
BTC/ETH extrema.

## Required market-data profile

`CRYPTO_CORE_V1`:
- BTCUSDT Spot: 15m, 1h, 4h;
- ETHUSDT Spot: 15m, 1h, 4h;
- acquisition includes a 14-day pre-window warm-up buffer, but warm-up observations
  are not scored as part of the pre-event window.

Optional contextual series (oil, stablecoins, exchange-status records, etc.) are
research metadata only in v0.1. They are not Strategy inputs.

## Initial Crisis Museum — v0.1.0

| ID | Neutral milestone | Category | Public anchor UTC | Template | Split | Replay |
|---|---|---|---|---|---|---|
| CRL-E001 | U.S. COVID-19 travel-restriction escalation address | global-risk shock | 2020-03-12 01:02 | POINT | Development | eligible |
| CRL-E002 | WTI May-2020 contract first trades below zero | energy/market dislocation | 2020-04-20 18:08 | POINT | Development | eligible |
| CRL-E003 | Coinbase connectivity outage during May-19 crypto selloff | crypto/outage dislocation | 2021-05-19 12:50 | OUTAGE | Development | eligible |
| CRL-E004 | Russian televised announcement preceding invasion of Ukraine | geopolitical shock | 2022-02-24 02:30 | POINT | Development | eligible with timestamp note |
| CRL-E005 | Federal Reserve first rate increase of 2022 tightening cycle | regime transition | 2022-03-16 18:00 | REGIME | Development | eligible; overlapping context |
| CRL-E006 | Terra stress — Binance LUNA/UST withdrawal suspension | crypto/stablecoin stress | 2022-05-10 02:20 | SOLVENCY | Development | eligible; May-7 precursor retained |
| CRL-E007 | Alameda balance-sheet disclosure preceding FTX crisis | crypto/solvency stress | 2022-11-02 14:44 | SOLVENCY | Development | eligible |
| CRL-E008 | Silicon Valley Bank closure | banking/liquidity stress | 2023-03-10 16:15 | POINT | Development | eligible |
| CRL-E016 | 17 Aug 2023 sudden BTC/ETH price dislocation | crypto flash/deleveraging shock | 2023-08-17 21:30 | POINT | Development | eligible; price-defined |
| CRL-E009 | Binance Spot trading halt | exchange outage | 2023-03-24 11:27 | OUTAGE | Blind holdout | eligible |
| CRL-E010 | 7 October Israel-Gaza regional shock | geopolitical shock | 2023-10-07 03:29 derived from 06:29 local | POINT | Blind holdout | timestamp conflict quarantine |
| CRL-E011 | Iran direct UAV launch toward Israel publicly confirmed | geopolitical shock | 2024-04-13 20:12 | POINT | Blind holdout | eligible |
| CRL-E012 | Israel begins strikes on Iran — first retained Reuters report | geopolitical/energy risk | 2025-06-13 00:26 | POINT | Blind holdout | eligible |
| CRL-E013 | U.S. strike on Iranian nuclear sites — first retained public announcement | geopolitical/US-Iran shock | 2025-06-21 23:46 | POINT | Blind holdout | eligible; overlaps E012 |
| CRL-E014 | 2026 U.S.-Israel/Iran conflict onset — first retained official public alert | geopolitical/energy risk | 2026-02-28 06:15 | POINT | Blind holdout | eligible |
| CRL-E015 | Hormuz shipping suspensions after Iranian closure claim | energy/shipping dislocation | 2026-02-28 14:39 conservative confirmation | POINT | Blind holdout | **not replay-eligible yet** |

The machine-readable catalog contains exact windows, timezone provenance, sources,
uncertainty and leakage notes for every row.

## Development vs blind holdout

Initial split: **9 Development / 7 Blind Holdout**.

Development events are intentionally diverse: health/global risk, energy
dislocation, crypto selloff/outage, geopolitical shock, monetary-policy regime
transition, stablecoin failure, exchange solvency and banking stress.

Blind Holdout contains both operational and geopolitical cases, including the
more recent Iran-related shocks. From registration onward no BTC/ETH price
summary, plot, YATL replay result or threshold optimization may be produced from
these holdouts before final evaluation.

Named holdouts are outcome-blind rather than identity-secret. CRL-007 will add
random windows and a stronger sealed random holdout to reduce narrative/event
selection bias.

## Source/timestamp findings that matter

- COVID: the White House archive gives the address start at 9:02 p.m. EDT on
  March 11, 2020; this is normalized to 01:02 UTC on March 12. WHO's pandemic
  characterization is retained as same-day context, not used to move the window.
- WTI: CFTC materials identify approximately 2:08 p.m. ET as the first
  below-zero trade. The later 2:29 p.m. intraday low is explicitly forbidden as
  an anchor because that would be outcome selection.
- Russia/Ukraine: the official Russian address is preserved as the primary event
  record; independent timestamp research places the televised address at 05:30
  Moscow time (02:30 UTC). Contemporaneous reporting rounds the announcement to
  shortly before 03:00 GMT, so the source difference remains explicit.
- Terra: Richmond Fed documents publicly visible Curve liquidity withdrawal on
  May 7, but without an exact intraday timestamp in the retained source. v0.1
  therefore does not invent one; the exact Binance suspension at 02:20 UTC on
  May 10 is the replay anchor.
- 17 August 2023 sudden price dislocation: the onset is deliberately price-defined
  from a contemporaneous minute-level market report and is therefore Development
  only. It may stress reaction latency, but may never be used as a Blind Holdout
  or as evidence that an ex-ante event detector predicted the move.
- 7 October 2023: retained Reuters material conflicts internally: later Reuters
  anniversary coverage identifies 06:29 local as the attack time, while an older
  Reuters graphic prints 06:30 local with 04:30 GMT. Because the UTC mapping is
  inconsistent, E010 remains quarantined for timestamp confirmation before replay.
- Hormuz 2026: Reuters publication at 14:39 UTC is an exact retained confirmation,
  but the article states that VHF closure warnings existed earlier. E015 therefore
  remains catalogued but replay-ineligible until an earlier timestamp is resolved
  or a conservative-anchor protocol is separately approved.

## Leakage rules

- Event labels/source text never enter Strategy/Risk inputs.
- No window endpoint may be selected using BTC/ETH high, low, maximum drawdown,
  liquidation cluster, eventual recovery or later narrative importance.
- Publication/update time is distinct from event time; later post-mortems can
  verify history but cannot simulate information availability.
- Overlapping events (notably 2022 macro/crypto and 2025/2026 Iran clusters) are
  tagged and may not be pooled as statistically independent observations.
- Holdout OHLCV is inaccessible to design work; structural quality metadata only.
- No catalog result upgrades P10 evidence or unlocks P11.

## CRL-001 exit gate

- schema frozen for v0.1.0 — **PASS**;
- source/timestamp rules documented — **PASS**;
- first source-backed catalog batch registered — **PASS**;
- Development/Holdout split frozen — **PASS**;
- unresolved timestamp conflicts explicitly quarantined — **PASS**.

CRL-002 may acquire the replay-eligible records and structurally acquire
quarantined records without interpreting their BTC/ETH outcomes.
