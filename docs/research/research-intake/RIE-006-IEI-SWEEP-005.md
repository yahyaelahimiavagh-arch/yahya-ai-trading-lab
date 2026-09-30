# RIE-006-IEI-SWEEP-005 — Clock-Phase Algorithmic Flow & Cross-Chain Capital Substitution

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch starting HEAD: **158dbe54985f335e47987c0de0cd81bc04a7c17f**
- PR #152: **OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS / recent reserve: **NOT READ**

## Scope
Bounded public/legal source sweep targeting mechanisms not already represented by
Registry v2, Generation 1/2, HSSE or MCF-PROD-001. No Development test or performance
read is permitted.

## Deep-reviewed sources

### IEI-SRC-048 — Kim & Hansen (2026), The Quarter-Hour Effect
Public arXiv/RePEc working paper using trades for six Binance perpetual contracts.
Documents periodic volatility/volume bursts at one-, five- and fifteen-minute marks,
lower trade-size roundness consistent with algorithmic participation, clock-phase
serial dependence, out-of-sample predictability of quarter-hour opening returns, and
opening order imbalance associated with returns over four-to-twelve-hour horizons.
Disposition: **SOURCE_BOUND / NOVEL CLOCK-PHASE MICROSTRUCTURE**

### IEI-SRC-049 — Ma, Bao & Wen (2026), One Rising Ship Sinks Other Ships
Public arXiv/RePEc working paper. Uses on-chain data for Ethereum, Solana, BSC,
Arbitrum and Avalanche (2022–2025). Reports negative cross-chain return spillovers
that intensify during attention shocks and attributes them to attention-driven
capital reallocation after controls for Bitcoin, equities and rates.
Disposition: **SOURCE_BOUND / NOVEL CROSS-CHAIN SUBSTITUTION**

### IEI-SRC-050 — Colak, Della Vedova, Foley & Mai (2026)
Journal of Banking & Finance. Studies 618 cryptocurrencies (2014–2021) and reports
a cross-sectional relation between financial-uncertainty beta and returns, while
macro/policy/volatility uncertainty measures do not show the same association.
Disposition: **SOURCE_BOUND / DATA-TAXONOMY RISK**

### IEI-SRC-051 — Grobys & Shahzad (2026), Cryptocurrency Momentum: Is It an Illusion?
Peer-reviewed negative evidence. Six momentum strategies show power-law behavior in
realized variance; block-bootstrap tests imply conventional variance-based
performance metrics may be unreliable and tail risks are cross-sectionally dependent.
Disposition: **NEGATIVE EVIDENCE / EXISTING TREND CLUSTER**

### IEI-SRC-052 — Pyo & Jang (2026), Revisiting the low-volatility anomaly
Finance Research Letters. Reports a post-2017 low-volatility premium across multiple
formation/holding horizons and interprets the reversal from earlier evidence as
consistent with market maturation.
Disposition: **REGIME-INSTABILITY EVIDENCE / POSSIBLE AF-RELATIVE INPUT**

### IEI-SRC-053 — Maghyereh & Awartani (2026), Common risk drivers
Open-access Finance Research Open study of ten major cryptocurrencies (2018–2025).
Finds a latent common-volatility component associated primarily with global
financial stress and investor sentiment.
Disposition: **RISK-STATE SUPPORT / NOT NEW DIRECTIONAL ALPHA**

## Mechanisms

### IEI-MECH-017 — Clock-phase algorithmic-flow state
Economic mechanism: synchronized algorithmic execution can create periodic,
clock-phase-specific order-flow dependence that is invisible to generic session
gates.

YATL adaptation:
- research as Spot execution/risk context first, not Futures trading;
- exact quarter-hour phase must be frozen ex ante;
- Spot aggTrades are the preferred eventual data path if comparable structure can
  be established without importing Futures outcomes.

Required PIT data:
- event-level Spot aggTrades/trades with timestamps, quantity and aggressor proxy;
- UTC clock phase;
- no future-volume bucket construction.

Holding/opportunity:
- recurring every quarter hour; potentially high opportunity count;
- source reports order-imbalance association over 4–12h, but YATL must not import
  that horizon as performance evidence.

Duplicate fingerprint:
- distinct from MCF SESSION_TIME_EFFECT: this is periodic algorithmic microstructure
  at minute/quarter-hour phase plus order flow, not broad session membership;
- partially adjacent to IEI-MECH-009 toxicity; future independence analysis must
  test whether simple signed flow/toxicity fully explains it.

Falsification:
- Spot-only reproduction must exist before economic testing;
- compare quarter-hour phase against 1m/5m phase and random clock phases;
- compare against simple taker imbalance, volatility and volume;
- reject if the effect exists only in perpetuals;
- reject if execution benefit comes only from suppressing nearly all entries.

Status: **SOURCE_BOUND / SPOT TRANSFER NOT ESTABLISHED**

### IEI-MECH-018 — Cross-chain attention-driven capital substitution
Economic mechanism: capital/attention may rotate between blockchain ecosystems,
producing negative spillovers rather than generic positive market beta.

YATL adaptation:
- point-in-time chain-level activity shock -> rank eligible Spot assets belonging to
  competing ecosystems -> long/cash or relative long-only selection;
- no short leg.

Required PIT data:
- immutable chain activity;
- historically valid token-to-chain membership;
- point-in-time Spot eligibility/liquidity;
- BTC/global market controls.

Leakage risks:
- current token taxonomy projected backward;
- bridge/multichain assets;
- chain activity metrics whose definitions/providers were revised;
- selecting "competing chains" after seeing spillovers.

Duplicate fingerprint:
- distinct from BTC/ETH price LEAD_LAG because the proposed driver is chain activity
  and capital substitution;
- distinct from news-defined peer reversal (MECH-016);
- adjacent to on-chain flow MECH-008 but uses ecosystem activity/substitution rather
  than exchange-wallet flows.

Falsification:
- freeze chain universe and membership rule;
- require incremental information beyond BTC return, market return, token momentum
  and liquidity;
- test whether negative spillover is merely stablecoin/bridge flow or common beta;
- reject if long-only adaptation has no actionable opportunity after costs.

Status: **BLOCKED_DATA / PIT CHAIN-MEMBERSHIP PROTOCOL REQUIRED**

### IEI-MECH-019 — Financial-uncertainty exposure sorting
Economic mechanism: heterogeneous sensitivity to financial uncertainty may price
different crypto use-cases differently.

Adversarial decision:
- **DO NOT PREREGISTER YET**.
- source sample ends 2021 and requires a design-feature taxonomy;
- reported spread is unusually large and concentrated in a taxonomy-defined subset;
- current-universe and retrospective classification risks are substantial.

Status: **BLOCKED_REPRODUCIBILITY / TAXONOMY-PIT RISK**

## Negative evidence and dedupe

1. **Momentum cluster:** IEI-SRC-051 strengthens existing negative evidence. Heavy
tails/power-law realized variance make variance-based Sharpe-like summaries fragile;
no new momentum candidate is created.

2. **Low-volatility anomaly:** IEI-SRC-052 conflicts with older high-volatility
cross-sectional narratives. Treat volatility sorting as regime-instability evidence,
not a timeless alpha. No candidate is created until point-in-time universe and
maturation/regime hypothesis are preregistered.

3. **Common volatility:** IEI-SRC-053 is useful for risk attribution but does not
justify a directional signal. It maps to AF-REGIME/risk-state work and is not a new
family.

## Priority change

A new high-priority source-intelligence item is admitted:
- **IEI-MECH-017 clock-phase algorithmic-flow state** — high data plausibility but
  requires Spot transfer proof.

Cross-chain substitution is economically distinct but lower priority because
historical token-chain membership and activity semantics are harder to make PIT-safe.

## Next allowed actions

1. **RIE-006-IEI-CLOCK-SPEC-001 — CHAT_DIRECTOR**
   Freeze a Spot-only clock-phase protocol: UTC phase, aggTrade schema, baseline
   phases, signed-flow definition, opportunity-preservation metrics and falsification.
   No performance read.

2. **RIE-006-IEI-CHAIN-PIT-001 — CHAT_DIRECTOR**
   Define point-in-time token-chain membership, chain activity semantics and bridge
   handling before any acquisition/test.

No Work/Astra gate is reached by these source/specification actions.

## Closeout
- sources deep-reviewed: **6**
- materially distinct mechanisms: **2**
- blocked high-risk mechanism: **1**
- formal Registry candidates: **0**
- backtests/performance reads: **0**
- negative evidence preserved: **momentum tail-risk / low-volatility regime reversal**
- Fresh OOS / recent reserve: **SEALED / NOT READ**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Futures execution: **NONE**
- Live authority: **NONE**

**MERGED=NO**
