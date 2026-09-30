# RIE-006-IEI-SWEEP-007 — Protocol Cash Flow, Staking & Value-Capture Economics

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch: **research-institutional-edge-intelligence**
- starting branch HEAD: **bc770c1073e6db062c676a309a65eaf51730c8a7**
- PR #152: **OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS / recent reserve: **NOT READ**
- Live authority: **NONE**

## 1. Scope

This bounded manual sweep tests whether protocol-native economic activity can create
mechanisms materially distinct from price trend, volume confirmation, COT positioning,
ETF flows, exchange flows, derivatives basis and flow toxicity.

Focus:
1. demand-side network fees;
2. staking / voluntarily locked supply;
3. protocol revenue versus actual tokenholder capture;
4. buyback / burn economics;
5. inflation and dilution interactions.

The purpose is mechanism extraction and adversarial falsification, not candidate
inflation. No Development run, parameter sweep, Fresh OOS, recent reserve, P10 or
Live evidence is read.

## 2. Deep-reviewed sources

### IEI-SRC-065 — Dünnes & Felsenstein-Eckberg (2026)
**Demand-Side Fee Flows and Return Predictability on Ethereum**
- public SSRN working paper, posted July 2026;
- constructs an ETH-native demand signal from network fees divided by token supply;
- the signal is the log deviation of current fee intensity from a trailing median;
- reports predictive information at 10-60 day horizons after momentum, macro and
  standard crypto controls;
- reports that predictability emerges only after the March 2024 Dencun hard fork.

Source:
- https://doi.org/10.2139/ssrn.7003998

Disposition: **SOURCE_BOUND / HIGH-PRIORITY PROTOCOL-DEMAND MECHANISM**

### IEI-SRC-066 — Affiliated public methodology for IEI-SRC-065
The published methodology specifies:
- Flow Intensity = total ETH-denominated fees / circulating ETH supply;
- 30-day smoothing of Flow Intensity;
- reference rate = 90-day trailing median;
- Flow Deviation = ln(smoothed Flow Intensity / reference rate).

This page is affiliated with a commercial product built around the paper, so it is
usable for method extraction but **not independent performance confirmation**.

Source:
- https://www.majorkeycapital.com/ethereum/valuation-terminal/methodology

Disposition: **METHOD DETAIL / NOT INDEPENDENT EVIDENCE**

### IEI-SRC-067 — Ethereum EIP-1559 and official gas documentation
- the protocol computes a base fee from preceding-block conditions;
- the base fee is burned rather than paid to the block producer;
- base fee therefore captures a protocol-native demand / congestion payment while
  also changing ETH supply.

Sources:
- https://eips.ethereum.org/EIPS/eip-1559
- https://ethereum.org/developers/docs/gas/

Disposition: **A-PRIMARY MECHANISM / DATA SEMANTICS**

### IEI-SRC-068 — DefiLlama Data Definitions
DefiLlama explicitly separates:
- **Fees:** total user payments;
- **Revenue:** the subset retained by protocol / treasury / team / tokenholders after
  amounts distributed to LPs and similar actors;
- **Holders Revenue:** the subset reaching tokenholders through buybacks, burns,
  direct distributions or staking-linked mechanisms.

Source:
- https://investors.defillama.com/data-definitions

Disposition: **DATA-SEMANTICS / VALUE-CAPTURE WARNING**

### IEI-SRC-069 — Ghasemlu (2026)
**Does Revenue Back Valuation? Protocol Revenue Multiples and the Cross-Section of Token Returns in Decentralized Finance**
- studies fee/revenue-reporting protocols tracked by DefiLlama;
- 2,259 protocols in the broader tracked set and 345 with traded market cap in the
  return study;
- reports no useful formation-date price-to-revenue ranking of subsequent 12-month
  winners in the studied period;
- explicitly notes the evidence is from a single, predominantly bearish regime and
  a revenue-generating conditioned universe.

Source:
- https://doi.org/10.2139/ssrn.6901559

Disposition: **NEGATIVE SOURCE EVIDENCE AGAINST NAIVE REVENUE-VALUE FACTOR**

### IEI-SRC-070 — Cong, He & Tang (2025)
**The Tokenomics of Staking**
- NBER Working Paper 33640;
- theoretical model links aggregate staking ratio, platform activity, reward rates
  and token price dynamics;
- empirical results report staking ratios positively predicting excess returns;
- the underlying empirical work uses historical staking data assembled from
  StakingRewards plus protocol documentation.

Source:
- https://www.nber.org/papers/w33640

Disposition: **SOURCE_BOUND / DISTINCT LOCKED-SUPPLY ECONOMIC MECHANISM**

### IEI-SRC-071 — Khoja (2026)
**Skin in the Chain: Locked Supply and the Cross-section of Cryptocurrency Returns**
- public August 2026 working paper;
- defines a broader locked-supply / "conviction" concept using voluntarily locked
  supply through staking, governance commitment or dormancy;
- reports conditional pricing interactions between locked supply and valuation;
- exact historical construction / point-in-time source lineage is not available
  from the indexed abstract and must be reproduced before YATL candidate creation.

Source:
- https://doi.org/10.2139/ssrn.7314420

Disposition: **BLOCKED_REPRODUCIBILITY / SUPPORTING STAKING-LOCK MECHANISM**

### IEI-SRC-072 — Gupta et al. (2024)
**Forecasting Cryptocurrency Staking Rewards**
- studies ETH, SOL, XTZ, ATOM and MATIC reward-rate forecasting;
- simple historical models can forecast staking rewards for several assets;
- forecasting the staking reward itself is **not evidence that token returns are
  forecastable after price risk, inflation, lockup and opportunity cost**.

Source:
- https://arxiv.org/abs/2401.10931

Disposition: **REWARD-FORECAST SUPPORT / NOT A RETURN-ALPHA CANDIDATE**

### IEI-SRC-073 — Dong, Weber & Xiao (2026)
**Valuation of proof-of-stake and smart contract cryptocurrencies**
- Finance Research Letters;
- equilibrium model jointly treats fee revenue, fee burning, staking rewards,
  issuance and token supply;
- supports the view that fee demand and token supply mechanics cannot be treated as
  economically independent channels by default.

Source:
- https://doi.org/10.1016/j.frl.2026.110003

Disposition: **THEORETICAL MECHANISM / COMPOSITE-ECONOMICS WARNING**

### IEI-SRC-074 — CoinGecko token-buyback study (2026)
- 2025 buyback spending is extremely concentrated;
- Hyperliquid alone represented roughly 46% of buyback spending in the study;
- the top ten programs represented about 92% of total measured spending;
- buyback structures differ materially: buy-and-burn, buy-and-hold, distribute,
  treasury accumulation, etc.

Source:
- https://www.coingecko.com/research/publications/token-buybacks

Disposition: **OUTLIER / HETEROGENEITY WARNING**

### IEI-SRC-075 — Garratt & van Oordt / BIS
**Crypto exchange tokens / Buyback Programs for Platform Tokens**
- formal model links platform demand and token buyback pledges;
- buyback pledges can affect valuation but may be costly and strategically gamed;
- existence of a buyback policy is not itself proof of durable tokenholder value.

Sources:
- https://www.bis.org/publications/working-paper-1201-crypto-exchange-tokens
- https://doi.org/10.2139/ssrn.4773455

Disposition: **MECHANISM SUPPORT / BUYBACK-NARRATIVE FALSIFICATION**

## 3. Mechanism extraction

### IEI-MECH-024 — Ethereum demand-side fee intensity

Lanes:
- IEI-01 Predictive Alpha
- IEI-07 Time / Regime Structure
- IEI-08 Public Alternative / Protocol-Native Data

Economic mechanism:
- network usage creates ETH-denominated demand for blockspace;
- comparing fee demand per unit of ETH supply with its own recent baseline may
  identify a demand state that is not reducible to price momentum alone.

Source-specified transformation:
1. FI_t = Fees_t / Supply_t
2. smooth FI with a 30-day average
3. Reference_t = trailing 90-day median of FI
4. FD_t = ln(smoothed_FI_t / Reference_t)

YATL adaptation boundary:
- research **FD itself**, not the source's commercial fair-value output;
- any action remains Spot ETH long/cash;
- the source's reported 45-day performance is external metadata only.

Required PIT data:
- completed Ethereum block / daily fee data;
- execution and blob/data-availability fee semantics;
- ETH supply series with explicit derivation/versioning;
- Spot ETH completed bars;
- exact UTC day cut.

Structural-break rule:
- Dencun (March 2024) materially changed fee composition.
- Pre- and post-Dencun observations must not be silently pooled as one stationary
  process.
- Source claims predictability appears only after Dencun; therefore a YATL protocol
  must freeze whether it is a post-Dencun structural hypothesis before outcomes.

Duplicate fingerprint:
- distinct from active-address/hashrate MECH-020: this measures paid demand intensity,
  not user count or security resources;
- distinct from MCF volume/price families;
- **burn is not a second independent edge** because EIP-1559 base-fee burn is
  mechanically generated by the same fee-demand process.

Adversarial tests:
- compare against ETH momentum, volatility, volume and active-use proxies;
- compare raw fees, FI and FD to test whether normalization adds information;
- require no same-evidence tuning of the 30d/90d windows;
- test post-Dencun only under a preregistered structural-break protocol;
- reject if predictive content is a small number of congestion episodes;
- reject if supply denominator adds no incremental information.

Status: **METHOD_SPECIFIED / DATA-ADMISSIBILITY AUDIT REQUIRED**

### IEI-MECH-025 — Staking / voluntarily locked-supply state

Lanes:
- IEI-01 Predictive Alpha
- IEI-03 Liquidity & Capacity
- IEI-06 Cross-sectional
- IEI-09 Crowding / Float State

Economic mechanism:
- voluntary staking locks part of supply and may simultaneously encode network
  participation, tokenholder commitment and reduced tradable float;
- changes in staking participation can therefore reflect both a fundamental demand
  state and a market-liquidity state.

Important mechanism split:
- **staking ratio** and **staking reward rate** are not equivalent;
- reward rate can be mechanically high because of issuance/incentives;
- a high nominal staking yield can be offset by dilution or price decline.

Current evidence:
- IEI-SRC-070 reports predictive information in staking ratio;
- IEI-SRC-071 independently motivates locked supply as a pricing state;
- IEI-SRC-072 shows staking rewards themselves can be forecastable, but that does
  not establish token-return alpha.

Data problem:
- the major cross-sectional academic dataset relies on StakingRewards / protocol
  sources and is not yet a YATL-controlled point-in-time archive;
- staking definitions vary across native staking, delegated staking, governance
  locks, liquid staking and DeFi incentive programs;
- historical token universes and staking mechanics change over time.

Falsification:
- separate staking ratio from reward/APY;
- control for token inflation, dilution, momentum, size and liquidity;
- test whether locked supply adds information beyond MECH-020 fundamentals;
- require historically valid staking definitions per asset;
- reject if results are dominated by illiquid high-staking tokens;
- reject if modern staking ratios are projected backward.

Status: **BLOCKED_DATA / PIT CROSS-ASSET STAKING HISTORY NOT YET ADMITTED**

## 4. Governance / adjudication mechanism

### IEI-MECH-026 — Net tokenholder value-capture quality

This is **not a directional candidate**.

Purpose:
prevent YATL from treating "fees", "protocol revenue", "holder revenue", "buybacks",
"burns" and "staking APY" as interchangeable fundamentals.

Required decomposition:

User Fees
-> protocol-retained Revenue
-> tokenholder-directed Revenue
-> actual reduction/distribution to holder economics
-> minus issuance / unlock dilution / incentive emissions
-> minus execution leakage / governance discretion where relevant.

Implication:
- a protocol can have high fees and zero tokenholder capture;
- a token can have high staking APY and negative real holder economics after
  dilution;
- a buyback can be funded by genuine revenue, treasury depletion, token issuance or
  other sources with very different economics;
- buyback tokens may be burned, distributed, vested or retained, so "buyback USD"
  is not a homogeneous factor.

Status: **METHOD_SPECIFIED AS GOVERNANCE / NOT A TRADING CANDIDATE**

## 5. Negative evidence and candidate-inflation prevention

### A. Naive price-to-revenue "value"
**NOT PROMOTED.**

IEI-SRC-069 is direct negative source evidence against assuming low
price-to-revenue tokens outperform. The source has a short/single-regime limitation,
so it does **not** prove revenue valuation can never matter. It does prove that
"cheap on revenue" cannot be accepted as an obvious crypto value factor.

### B. Burn as separate alpha
**REJECTED_DUPLICATE.**

For Ethereum, EIP-1559 burn is mechanically linked to base-fee demand. Counting
"high fee demand" and "high burn" as two independent edges would double-count the
same mechanism.

### C. Staking APY as alpha
**REJECTED AS UNSPECIFIED RETURN ALPHA.**

A predictable reward rate is not equivalent to predictable total return. Any future
staking research must include price movement, issuance, dilution, lockup/liquidity
and implementation.

### D. Buyback program existence
**NOT PROMOTED.**

Buyback spending is highly concentrated and mechanism-specific. A binary
"has buyback" feature would combine economically incompatible policies and is
vulnerable to outlier dependence.

## 6. Data-integrity findings

### A. Protocol economic metrics need semantic versioning
"Fees", "revenue" and "holders revenue" depend on protocol-specific routing rules.
Governance can change take rates, fee switches, burns and distributions without a
change in user activity.

Future adapters must preserve:
- metric definition/version;
- effective governance date;
- raw source;
- retrieval timestamp;
- chain block/date boundary;
- transformation hash.

### B. Hard forks are economic schema migrations
Dencun changed where Ethereum demand pays fees. A chain upgrade is not just a date
dummy; it can change the meaning of the measured variable.

### C. Cross-chain comparability is not automatic
ETH base-fee burn, Solana base-fee burn, validator rewards and DeFi token buybacks
have different economic incidence. A generic "fee yield" cross-section should not
be built until a common economic schema exists.

## 7. Priority update

| Priority | Mechanism | State |
|---|---|---|
| A1 | IEI-MECH-011 CFTC regulated trader positioning | SOURCE_BOUND / prereg-ready |
| A2 | IEI-MECH-022 FINRA ETF short-pressure | METHOD_SPECIFIED / data audit next |
| A3 | IEI-MECH-024 ETH demand-side fee intensity | **METHOD_SPECIFIED / data audit next** |
| A4 | IEI-MECH-009 order-flow toxicity / jump-risk | SOURCE_BOUND / exact spec next |
| A5 | IEI-MECH-002 cross-sectional same-weekday | BLOCKED on PIT universe |
| A6 | IEI-MECH-020 protocol fundamental state | SOURCE_BOUND / versioning needed |
| A7 | IEI-MECH-025 staking / locked-supply state | BLOCKED_DATA |
| A8 | IEI-MECH-013 derivatives basis -> Spot | SOURCE_BOUND |
| A9 | IEI-MECH-021 token dilution / unlock pressure | BLOCKED_DATA |
| A10 | IEI-MECH-023 ETF institutional-flow persistence | SOURCE_BOUND / revision risk |

This is a **research queue**, not a profitability ranking.

## 8. Recommended next allowed work

### RIE-006-IEI-ETH-FLOW-SPEC-001 — CHAT_DIRECTOR
Freeze:
- exact Ethereum fee components;
- UTC aggregation clock;
- 30-day smoothing;
- 90-day reference median;
- post-Dencun eligibility;
- ETH supply derivation;
- Spot action clock;
- benchmark ladder;
- cost/opportunity metrics;
- falsification rules.

No performance read.

### RIE-006-IEI-STAKING-PIT-001 — CHAT_DIRECTOR
Determine whether a reproducible PIT staking dataset can be created without
retrospective provider values:
- native vs delegated staking;
- liquid staking;
- governance locks;
- inflation / reward semantics;
- protocol migrations;
- historical universe.

### RIE-006-IEI-VALUE-CAPTURE-SCHEMA-001 — CHAT_DIRECTOR
Create a source-neutral schema for:
fees -> revenue -> holder revenue -> burn/buyback/distribution -> net dilution.

This is infrastructure/specification, not a trading test.

No Work/Astra gate is reached by these bounded specification work units.

## 9. Closeout

- new deep-reviewed sources / source groups: **11**
- materially distinct predictive mechanisms: **2**
- governance/adjudication mechanism: **1**
- formal Registry candidates created: **0**
- negative/duplicate candidate paths rejected: **4**
- highest-priority new finding: **ETH demand-side fee intensity**
- strongest negative finding: **raw protocol revenue multiple is not established as a crypto value factor**
- candidate inflation prevented: **fee+burn split, staking APY, binary buyback factor**
- backtests: **0**
- performance data read: **0**
- Fresh OOS / recent reserve: **SEALED / NOT READ**
- P10 read/write: **false / false**
- P11: **LOCKED**
- Futures execution: **NONE**
- Live authority: **NONE**

**MERGED=NO**
