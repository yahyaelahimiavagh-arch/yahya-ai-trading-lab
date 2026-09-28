# RIE-006-IEI-SWEEP-002 — Flow Toxicity, Liquidity Premium & Edge-Decay Sweep

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch: **research-institutional-edge-intelligence**
- starting branch HEAD: **8882e2c43cdca6253c70c6460b34e0171765b18b**
- PR: **#152 — OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS: **NOT READ**
- recent reserve: **NOT READ**

## 1. Scope

This bounded follow-up sweep focuses on:
- public on-chain exchange-flow information;
- order-flow toxicity / jump-risk microstructure;
- liquidity as both an edge amplifier and a capacity constraint;
- informed-trading evidence;
- crowding / alpha-decay methodology;
- whether existing MCF mean-reversion and liquidity families are being misattributed.

No canonical Development run, parameter search, OOS, crisis, Forward or Live work
is allowed in this work unit.

## 2. Deep-reviewed public sources

### IEI-SRC-022 — Chi, Chu, Hao (2025)
**Return and Volatility Forecasting Using On-Chain Flows in Cryptocurrency Markets**
- public arXiv source;
- studies BTC, ETH and USDT exchange net inflows over 2017–2023;
- intraday horizons: 1, 2, 3, 4 and 6 hours;
- net inflow is defined as wallet-to-exchange inflows minus exchange-to-wallet outflows;
- reports ETH net inflow as negatively associated with subsequent ETH return and
  volatility, and USDT net inflow into exchanges as positively associated with BTC/ETH
  returns at some intraday horizons;
- BTC net inflow return forecasting is comparatively weak.

Disposition: **SOURCE_BOUND / DISTINCT ALTERNATIVE-DATA MECHANISM**

### IEI-SRC-023 — Kitvanitphasu, Kyaw, Likitapiwat, Treepongkaruna (2026)
**Bitcoin wild moves: Evidence from order flow toxicity and price jumps**
- peer-reviewed, open-access article;
- uses high-frequency Bitcoin data;
- order-flow toxicity is measured with VPIN;
- reports VPIN predicting subsequent Bitcoin price jumps;
- documents serial persistence in VPIN and jump size;
- also reports time-zone and day-of-week structure.

Disposition: **SOURCE_BOUND / DISTINCT AF-MICRO MECHANISM**

### IEI-SRC-024 — Dong, Jiang, Liu, Zhu (2022)
**Liquidity in the cryptocurrency market and commonalities across anomalies**
- models funding liquidity -> crypto asset liquidity;
- empirically reports stronger anomaly returns in lower-liquidity states;
- uses market-based characteristics rather than accounting fundamentals;
- interprets illiquidity as a force that limits arbitrage and allows mispricing to persist.

Disposition: **MECHANISM SUPPORT / NOT A NEW DIRECTIONAL FAMILY**

### IEI-SRC-025 — Farag, Luo, Yarovaya, Zieba (2025)
**Returns from liquidity provision in cryptocurrency markets**
- studies a cryptocurrency liquidity-provision premium using short-reversal returns;
- reports the premium varying with volatility, crash/tail risk and Tether-liquidity
  innovations;
- higher premium is associated with lower liquidity, lower trading activity and
  greater frictions;
- the source therefore links attractive gross reversal economics to precisely the
  states in which capacity/implementation may be worst.

Disposition: **DEDUPE / CAPACITY-FALSIFICATION SOURCE**

### IEI-SRC-026 — Wang et al. (2022)
**Can investors’ informed trading predict cryptocurrency returns?**
- investigates informed-trading variables with machine-learning models;
- reports useful predictability for some individual cryptocurrencies;
- explicitly reports no significant average improvement in prediction accuracy over
  the full market.

Disposition: **NEGATIVE SOURCE EVIDENCE AGAINST GENERIC INFORMED-TRADING ML**

### IEI-SRC-027 — Volpati et al. (2020)
**Zooming In on Equity Factor Crowding**
- equity/institutional source, not crypto evidence;
- identifies crowding through correlated same-direction institutional order flow;
- reports crowding especially in mechanical factor strategies such as momentum.

Disposition: **IEI-09 META / EXTERNAL-ASSET METHODOLOGY ONLY**

### IEI-SRC-028 — Lee (2025)
**Not All Factors Crowd Equally: Modeling, Measuring, and Trading on Alpha Decay**
- external-asset preprint;
- studies explicit alpha-decay functional forms;
- argues mechanical factors may exhibit more measurable crowding/decay than
  judgment-based factors;
- reported crowding model does not itself produce reliable incremental alpha.

Disposition: **IEI-09 META / DECAY-MODEL INSPIRATION, NOT CRYPTO EVIDENCE**

### IEI-SRC-029 — Binance Public Data
**Official public Spot archive documentation**
- Spot historical data includes klines, trades and aggregate trades;
- aggregate trades contain trade price, quantity, timestamp, first/last trade IDs,
  buyer-maker flag and best-price-match flag;
- official archive also publishes checksums and an update ledger for replaced files.

Disposition: **PUBLIC DATA PREREQUISITE / POSSIBLE MICROSTRUCTURE DATA UNBLOCK**

## 3. Mechanism extraction

### IEI-MECH-008 — Exchange net-flow pressure

Lanes:
- IEI-01 Predictive Alpha
- IEI-08 Public Alternative Data

Mechanism:
- transfers into exchanges can represent an immediate change in potential sell-side
  inventory for native assets;
- stablecoin inflows can represent immediate exchange-side purchasing liquidity;
- the sign and interpretation are asset-specific rather than a single generic
  "on-chain activity bullish/bearish" rule.

Why economically distinct:
- not price momentum;
- not volume confirmation;
- not stablecoin issuance;
- not generic exchange trading volume;
- the state variable is **wallet-to-exchange / exchange-to-wallet transfer flow**.

Required data:
- historically reconstructable wallet/exchange transfer flow;
- immutable chain timestamps / block ordering;
- point-in-time exchange-address registry;
- Spot OHLCV;
- optional aggregate-trade data for execution attribution.

Critical leakage risk:
- modern exchange-address labels projected backward can create severe future-label
  leakage;
- source-provider revisions can rewrite historical net-flow series;
- internal exchange wallet reshuffles can masquerade as economic inflow/outflow.

Falsification:
- require a point-in-time label protocol;
- separate native-asset and stablecoin flows;
- compare against simple return/volume/liquidity baselines;
- audit sign stability across eras;
- reject if results are dominated by a few exchange reclassification events.

Status: **BLOCKED_DATA**
Reason: exact historical point-in-time exchange-address provenance is not yet
admitted by YATL.

### IEI-MECH-009 — Order-flow toxicity / jump-risk state

Lanes:
- IEI-05 Market Microstructure
- IEI-02 Execution Alpha
- IEI-07 Time Structure

Mechanism:
- persistent imbalance in aggressive order flow may reveal asymmetric information
  / toxicity before discontinuous price moves;
- this is primarily a **jump-risk and adverse-selection state**, not automatically
  a directional alpha.

Required data:
- Spot trades or aggregate trades;
- aggressor-side classification;
- exact event timestamps and quantities;
- point-in-time bucket construction;
- jump estimator and conservative transaction-cost model.

Important data finding:
- unlike order-book OFI/resilience research, this mechanism may be testable from
  official historical Spot aggregate-trade archives without requiring full L2 book
  reconstruction;
- Binance public Spot aggregate-trade records expose quantity, timestamp and
  buyer-maker state, making a research-grade volume-bucket toxicity series
  plausible in principle.

Leakage risks:
- VPIN bucket construction using future volume;
- wrong maker/aggressor sign interpretation;
- mixed millisecond/microsecond archive eras;
- changed exchange microstructure;
- selecting jump threshold after seeing outcomes.

Opportunity profile:
- high-frequency state variable;
- could be used to delay/avoid entries during toxic flow;
- opportunity-starvation must be explicitly measured.

Capacity:
- useful as an adverse-selection control;
- if it merely avoids all volatile periods, it is not execution alpha.

Duplicate fingerprint:
- not MCF TRADE_COUNT_CONFIRMED_DIRECTION;
- not PRICE_VOLUME_INTERACTION;
- not OFI/depth;
- not session-time effect;
- belongs inside existing **AF-MICRO**, so no new Alpha Factory family ID is needed.

Falsification:
- test whether toxicity predicts future jump incidence/severity beyond volatility,
  volume, taker imbalance and recent returns;
- freeze bucket size and jump estimator before economics;
- test delayed-entry opportunity cost;
- reject if a simple taker-buy ratio explains the same information;
- reject if cost savings arise only from eliminating nearly all trades.

Status: **SOURCE_BOUND**
Next requirement: exact method extraction / preregistration before any data run.

### IEI-MECH-010 — Liquidity-amplified mispricing with capacity inversion

Lanes:
- IEI-03 Liquidity & Capacity
- IEI-09 Edge Decay / Crowding
- IEI-10 Meta Research

Mechanism:
- some anomalies may look stronger precisely when liquidity is poor because
  arbitrage capital cannot efficiently remove them;
- the same illiquidity that increases gross anomaly returns may sharply reduce
  realizable dollar capacity.

This creates a required distinction:

**percentage edge can rise while deployable-dollar edge falls.**

YATL implication:
- candidate ranking by raw expectancy is insufficient;
- liquidity-conditioned alpha must be paired with a capacity/impact curve;
- low-liquidity "strong alpha" cannot outrank a weaker but scalable edge without
  net-dollar-capacity evidence.

Duplicate fingerprint:
- this is not a new entry signal;
- it is a cross-cutting adjudication mechanism for AF-MEANREV, AF-LIQUIDITY and
  future cross-sectional families.

Falsification:
- measure expectancy and capacity jointly across liquidity states;
- reject the interpretation if net-dollar opportunity does not fall with
  deteriorating liquidity;
- compare against simple market-activity controls.

Status: **METHOD_SPECIFIED AS GOVERNANCE / NOT A TRADING CANDIDATE**

## 4. Dedupe and negative evidence

### Short-horizon reversal / liquidity-provision premium
Not promoted as a new candidate.

Reason:
- MCF already contains SHORT_HORIZON_MEAN_REVERSION and SIMPLE_STATISTICAL_DEVIATION;
- Registry v2 already contains mean-reversion candidates.

New learning:
- future evaluation must ask whether apparent reversal alpha is really compensation
  for liquidity provision / adverse-selection risk;
- if yes, capacity may be materially smaller than raw historical return suggests.

### Generic informed-trading ML
Not promoted.

Reason:
- the reviewed source reports only selective asset-level predictability and no
  significant market-wide average improvement;
- without a simple, source-specified informed-trading statistic and clear
  incremental baseline, a flexible ML candidate would introduce large
  multiple-testing and complexity risk.

Status: **NEGATIVE SOURCE EVIDENCE RETAINED**

### Crowding as a direct signal
Not promoted.

Reason:
- strongest reviewed crowding papers rely on institutional holdings/metaorders not
  publicly available for crypto Spot;
- proxying such data with price momentum would simply rename the existing trend
  cluster.

Allowed YATL adaptation:
- measure **observable edge decay**, turnover/capacity interaction and common
  failure clustering;
- do not claim direct crowding identification without a real crowding proxy.

## 5. Adversarial findings

### Blind spot 1 — kline-only research hides aggressor information
Klines preserve total volume and taker-buy aggregates but lose much of the
event-level sequence. Official aggregate-trade history provides a legal public path
to a richer microstructure layer without immediately requiring L2.

### Blind spot 2 — stronger historical alpha may mean worse scalability
Liquidity-anomaly literature creates a direct warning against sorting candidates
only by percentage return.

### Blind spot 3 — alternative data label provenance can be more dangerous than
ordinary price lookahead
A correct blockchain timestamp is not enough when the semantic label ("exchange
wallet") was learned years later.

### Blind spot 4 — toxicity is more defensible as risk/execution state than as a
directional predictor
A jump-risk predictor can improve net economics by reducing adverse selection even
if it has no buy/sell direction.

## 6. Prioritization after Sweep 002

| Priority | Mechanism | Decision |
|---|---|---|
| A1 | IEI-MECH-009 Order-flow toxicity / jump-risk state | **SOURCE_BOUND — exact spec next** |
| A2 | IEI-MECH-008 Exchange net-flow pressure | **BLOCKED_DATA — PIT label provenance needed** |
| A3 | IEI-MECH-010 Liquidity-amplified mispricing / capacity inversion | **ADJUDICATION RULE — integrate into future capacity screens** |
| HOLD | generic liquidity-provision reversal | **DUPLICATE — use as mechanism attribution/falsification** |
| REJECT | generic informed-trading ML | **NEGATIVE / insufficient incremental evidence** |
| HOLD | direct crowding signal | **BLOCKED_PROXY — no public institutional-position proxy admitted** |

## 7. Recommended next allowed work

### RIE-006-IEI-MICRO-SPEC-001 — CHAT_DIRECTOR
Extract and freeze an exact Spot trade-flow toxicity protocol:
- data schema;
- maker/aggressor sign;
- volume-bucket construction;
- timestamp precision transition rules;
- jump estimator;
- comparison baselines;
- opportunity-preservation metrics;
- cost/adverse-selection attribution.

No performance read.

### RIE-006-IEI-ONCHAIN-PIT-001 — CHAT_DIRECTOR
Define admissibility rules for on-chain exchange-flow labels:
- how exchange addresses become known;
- label versioning;
- reclassification history;
- wallet migration handling;
- chain finality;
- provider revision policy.

No acquisition/run yet.

### AF-12 / capacity integration — FUTURE
Add the principle that edge percentage and deployable net-dollar capacity are
joint outputs. Do not modify existing frozen candidate outcomes.

## 8. Closeout

- New deep-reviewed sources: **8**
- New distinct mechanisms: **3**
- New formal Registry candidates: **0**
- Duplicate mechanisms rejected: **3 classes**
- Negative source evidence added: **generic informed-trading ML**
- Potential data unblock: **public Spot aggTrades for toxicity research**
- Backtests: **0**
- Fresh OOS read: **false**
- recent reserve read: **false**
- P10 read/write: **false / false**
- P11: **LOCKED**
- Live authority: **none**
- Merge: **not authorized**

**MERGED=NO**
