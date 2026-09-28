# RIE-006-IEI-SWEEP-006 — Fundamental Adoption, Token Dilution & Regulated ETF Flow

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch: **research-institutional-edge-intelligence**
- starting branch HEAD: **1230c8ce9a08b069f6b66720f347439f08216c9d**
- PR #152: **OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS / recent reserve: **NOT READ**
- Live authority: **NONE**

## 1. Scope

This bounded manual sweep tests three under-covered mechanism classes:
1. protocol-native adoption/security fundamentals;
2. scheduled token dilution / vesting supply pressure;
3. regulated U.S. spot-Bitcoin-ETF flow and short-sale information.

The goal is not to maximize candidate count. Closely correlated observables are
collapsed into one economic mechanism unless independent causal content can later be
shown.

No Development run, parameter sweep, Fresh OOS, recent reserve, P10 or Live evidence
is read.

## 2. Deep-reviewed sources

### IEI-SRC-054 — Guidolin & Ionta (2026)
**Predictive sorting of cryptocurrencies based on fundamentals and sentiment**
- Journal of International Financial Markets, Institutions & Money, open access.
- August 2015-April 2025 sample; weekly factor-mimicking portfolios based on active
  users, hashrate and Google-search sentiment.
- One-step-ahead expanding-window forecasting.
- The paper explicitly reports very high correlations among several fundamental
  factor-mimicking portfolios; therefore User and Hashrate factors must not be
  treated as automatically independent YATL edges.
- Source URL: https://doi.org/10.1016/j.intfin.2026.102285

Disposition: **METHOD-SPECIFIED SUPPORT / INDEPENDENCE WARNING**

### IEI-SRC-055 — Bhambhwani, Delikouras & Korniotis (2023)
**Blockchain characteristics and cryptocurrency returns**
- Journal of International Financial Markets, Institutions & Money.
- Network size and computing power are treated as economic fundamentals related to
  adoption and network security.
- Aggregate blockchain characteristics explain expected cryptocurrency returns at
  least as well as return-based market/size/momentum models in the source.
- Source URL: https://doi.org/10.1016/j.intfin.2023.101788

Disposition: **MECHANISM SUPPORT**

### IEI-SRC-056 — Liebi (2022)
**Is there a value premium in cryptoasset markets?**
- Economics Letters / Elsevier.
- Uses active-addresses-to-network-value as a crypto-native value ratio.
- Large cross-section, but source data are proprietary and the author reports an
  NDA for the underlying dataset.
- Source URL: https://doi.org/10.1016/j.econlet.2022.110373

Disposition: **BLOCKED_REPRODUCIBILITY / SUPPORTING MECHANISM ONLY**

### IEI-SRC-057 — Guo (2026)
**Token Dilution and the Cross-Section of Cryptocurrency Returns**
- Public SSRN working paper.
- Weekly panel of 404 coins, 2020-2026.
- Defines dilution using float ratio, FDV premium and a 12-week circulating-supply
  growth measure.
- Reports dilution predictability concentrated in younger / less-mature coins and
  absent in top-five blue chips.
- External returns/statistics remain untrusted metadata.
- Source URL: https://doi.org/10.2139/ssrn.6636258

Disposition: **SOURCE_BOUND / DISTINCT SUPPLY MECHANISM**

### IEI-SRC-058 — 6th Man Ventures (2023)
**We Analyzed 5,000 Token Unlocks**
- Public empirical study of more than 5,000 unlocks across 20 protocols.
- Dataset was checked against on-chain data and/or protocol teams.
- Reports little relationship for unlocks below 1% of circulating supply and a
  stronger negative relationship for larger unlocks.
- Explicitly warns that the study establishes correlation, not rigorous causation.
- Source URL: https://6thman.ventures/writing/token-unlocks

Disposition: **SOURCE SUPPORT / CAUSALITY WARNING**

### IEI-SRC-059 — CoinGecko supply methodology and 2026 historical-data notices
- Circulating supply may depend on team-provided locked/unvested wallet information.
- CoinGecko states date-specific historical market cap can be provisional for two
  days because circulating supply can arrive late or be corrected.
- A 2026 API pipeline change also changed historical values for some historical
  timestamp queries, including circulating supply.
- Sources:
  - https://www.coingecko.com/en/methodology
  - https://support.coingecko.com/hc/en-us/articles/61976309053337-Why-do-historical-market-cap-values-change-shortly-after-a-date-then-settle
  - https://status.coingecko.com/info_notices/387371

Disposition: **PRIMARY DATA-PROVENANCE WARNING**

### IEI-SRC-060 — FINRA Daily Short Sale Volume
- Primary U.S. regulatory data.
- Aggregated short-sale volume by security for publicly disseminated off-exchange
  trades reported to FINRA facilities.
- Daily files are posted no later than 18:00 ET on the trade date.
- FINRA explicitly states the files are not consolidated with exchange short-sale
  data and are not equivalent to short-interest positions.
- Source URL:
  https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files

Disposition: **A-PRIMARY / CLEAN PUBLIC-AVAILABILITY CLOCK**

### IEI-SRC-061 — Onishchenko (2026)
**Betting against Bitcoin: Evidence from spot Bitcoin ETFs**
- Journal of Behavioral and Experimental Finance, open access.
- January 2024-October 2025 sample.
- Uses FINRA Bitcoin-ETF short-sale data and reports shorting flow predictive of
  negative ETF returns for up to five trading days.
- The paper defines a daily short ratio relative to ETF shares outstanding.
- The source interpretation is informed short selling, but YATL must independently
  test whether any information transfers to Spot BTC after controlling for BTC
  momentum/sentiment/ETF flow.
- Source URL: https://doi.org/10.1016/j.jbef.2026.101191

Disposition: **METHOD-SPECIFIED / DISTINCT REGULATED-FLOW MECHANISM**

### IEI-SRC-062 — Mohamad (2025)
**Do Bitcoin ETFs Lead Price Discovery Following their Introduction in the Bitcoin Market?**
- Computational Economics, open access.
- Uses 5-minute data from January-October 2024.
- Reports time-varying price discovery; the most active U.S. spot Bitcoin ETFs lead
  Spot under the paper's information-leadership measure much of the sample.
- Source URL: https://doi.org/10.1007/s10614-025-10998-x

Disposition: **PRICE-DISCOVERY SUPPORT / SHORT SAMPLE**

### IEI-SRC-063 — Lim (2026)
**The Price Impact of Spot Bitcoin ETF Flows**
- Public SSRN working paper.
- Daily U.S. spot-Bitcoin-ETF flow study, January 2024-April 2025.
- Reports bidirectional flow/return feedback and next-day predictive content.
- Critically distinguishes persistent sequences of flows from permanent impact of a
  single flow shock.
- Source URL: https://doi.org/10.2139/ssrn.6592830

Disposition: **SOURCE_BOUND / INSTITUTIONAL DEMAND PRESSURE**

### IEI-SRC-064 — Coin Metrics Community Data / revision evidence
- Community Network Data exposes public on-chain metrics such as active addresses
  and some mining/network metrics.
- Coin Metrics documents metric definitions and revision/status semantics.
- On 2026-09-22 Coin Metrics reported a historical recalculation affecting BTC ETF
  flow-related metrics over a long prior period, demonstrating that "historical"
  provider series can change after initial publication.
- Sources:
  - https://docs.coinmetrics.io/api/v4/
  - https://github.com/coinmetrics/data
  - https://status.coinmetrics.io/

Disposition: **DATA-PROVENANCE / VERSIONING REQUIREMENT**

## 3. Mechanism extraction

### IEI-MECH-020 — Protocol fundamental adoption/security state

Lanes:
- IEI-01 Predictive Alpha
- IEI-06 Cross-sectional
- IEI-10 Meta Research

Economic mechanism:
- network participation and resources committed to network security can represent
  adoption / economic utility / security investment not contained in price alone.

Candidate class:
- strictly lagged network-fundamental state -> Spot long/cash or cross-sectional
  long-only selection.

Important independence decision:
- active-user and hashrate factor-mimicking portfolios are **not two independent
  YATL edges by default**.
- the 2026 source reports very high correlations among multiple FMP variants.
- YATL should initially treat them as manifestations of one economic mechanism and
  require incremental-information testing before splitting them.

Required data:
- historically versioned active-address/network-size metric;
- hashrate/difficulty for PoW chains only;
- point-in-time asset eligibility;
- explicit chain-specific metric definitions;
- immutable snapshot/version identity.

Leakage/data risks:
- current provider definitions projected backward;
- historical metric recalculation;
- privacy-chain missingness;
- ETH PoW->PoS structural break;
- current universe projected backward;
- mixing incomparable definitions across account/UTXO chains.

Falsification:
- compare against Spot momentum, size, liquidity and market beta;
- show incremental information beyond a single composite fundamental factor;
- reject if predictive power is carried by BTC exposure or current-universe bias;
- reject separate User/Hash candidates if residual independence disappears.

Status: **SOURCE_BOUND / PIT VERSIONING REQUIRED**

### IEI-MECH-021 — Token dilution / vesting supply pressure

Lanes:
- IEI-01 Predictive Alpha
- IEI-06 Cross-sectional
- IEI-07 Scheduled Event Structure
- IEI-08 Public Alternative Data

Economic mechanism:
- publicly scheduled releases of previously restricted supply can increase tradable
  float and potential sell inventory;
- limited attention and low liquidity may prevent complete advance pricing.

Two sub-hypotheses must remain separate:
1. **continuous dilution state:** lagged growth in circulating supply / FDV-to-float;
2. **scheduled unlock event:** known unlock size relative to then-circulating supply.

Do not combine them after seeing outcomes.

Required data:
- point-in-time circulating supply;
- total/max supply where economically meaningful;
- vesting schedule known-at-time snapshots;
- token age;
- PIT Spot eligibility/liquidity;
- holder type only if historically documented.

Central data problem:
- circulating supply is not an immutable chain primitive for many tokens.
- providers may exclude team/treasury/vested wallets using labels supplied by
  projects.
- historical supply and market cap can be revised after the date.
- re-querying a modern API is therefore not automatically a point-in-time dataset.

Falsification:
- freeze release-availability timestamp, event size and threshold before outcomes;
- compare against momentum, size, liquidity, age and BTC/market return;
- separate anticipation window from post-unlock pressure;
- reject if result is concentrated in tiny illiquid tokens only;
- reject if modern supply labels are needed to reconstruct historical state.

Status: **BLOCKED_DATA / HIGH ECONOMIC INTEREST**

### IEI-MECH-022 — Regulated ETF off-exchange short-pressure

Lanes:
- IEI-01 Predictive Alpha
- IEI-07 Time Structure
- IEI-08 Public Alternative Data

Economic mechanism:
- informed or inventory-motivated short selling in regulated Spot-Bitcoin ETF
  vehicles may reveal negative information / sentiment pressure before it is fully
  reflected in BTC Spot.

Public availability:
- FINRA daily short-sale files are available by 18:00 ET on the same trade date;
- eligibility begins only after the actual file publication, never from the close
  or transaction time if the aggregate was not yet public.

Critical semantic warning:
- FINRA short-sale volume is not short interest;
- it covers publicly disseminated off-exchange activity and is not consolidated
  with exchange data;
- YATL must not call it total market short positioning.

Possible YATL adaptation:
- lagged FINRA off-exchange short-pressure state across the approved spot BTC ETFs
  -> next Spot BTC long/cash decision.
- no ETF shorting and no Futures leg.

Required data:
- immutable FINRA daily files;
- point-in-time ETF ticker universe;
- ETF shares-outstanding data if reproducing the paper's denominator;
- BTC Spot completed bars;
- ETF flow and BTC momentum controls.

Falsification:
- compare with simple BTC momentum, ETF net flow and sentiment;
- test whether short flow adds information beyond same-day ETF return;
- require robustness across major ETF subset and leave-one-ETF-out tests;
- reject if predictive content disappears when using only information available
  after 18:00 ET;
- reject if one ETF or one stress episode drives the result.

Status: **METHOD-SPECIFIED / DATA ADMISSIBILITY AUDIT NEXT**

### IEI-MECH-023 — Spot-Bitcoin-ETF institutional flow persistence

Lanes:
- IEI-01 Predictive Alpha
- IEI-03 Liquidity & Capacity
- IEI-08 Public Alternative Data

Economic mechanism:
- creation/redemption demand for physically backed spot Bitcoin ETFs can represent
  persistent institutional demand/supply that transmits into Bitcoin inventory and
  price impact.

Adversarial interpretation:
- flows and returns have bidirectional feedback;
- a persistent flow sequence can look like permanent alpha even when individual
  flow shocks later reverse;
- raw flow/return correlation is therefore insufficient.

Required PIT data:
- issuer or otherwise versioned daily shares outstanding / creation-redemption
  information;
- actual publication/availability time;
- BTC Spot;
- no revised provider value substituted for the historical value originally known.

Falsification:
- control for prior BTC return;
- separate new flow innovation from predictable flow persistence;
- distinguish same-day impact from next-day incremental predictability;
- reject if modern revised ETF-flow data are required;
- test whether MECH-022 and MECH-023 are one common institutional-demand state.

Status: **SOURCE_BOUND / PIT FLOW SNAPSHOT REQUIRED**

## 4. Negative evidence / rejected candidate inflation

### A. Hashrate and active users are not two free edges
Source-level correlations are too high to count them as independent candidates
without residual-information evidence.

### B. Mining difficulty is likely highly endogenous
Older Bitcoin literature often finds price leading difficulty/hashrate over relevant
horizons. A naive "difficulty rose -> buy BTC" rule is therefore not promoted.

Disposition: **NO SEPARATE MINING-DIFFICULTY CANDIDATE**

### C. Active-address value evidence is not directly reproducible from the original
large cross-section
The value-premium paper relies on proprietary data. A YATL candidate must be rebuilt
from a public, versioned definition rather than importing its reported result.

Disposition: **BLOCKED_REPRODUCIBILITY**

### D. ETF price discovery is not itself an alpha
ETF leadership provides mechanism support, but "ETF price moved first -> buy Spot"
would collapse into an existing lead-lag family unless a materially different
public-flow variable is used.

Disposition: **GENERIC ETF PRICE LEAD REJECTED_DUPLICATE**

## 5. Data-integrity finding

This sweep strengthens a project-wide rule:

> **Historical queryability is not point-in-time availability.**

Two current examples:
- CoinGecko documents provisional/revised circulating-supply-driven historical
  market-cap values and 2026 changes to historical timestamp-aligned values.
- Coin Metrics publicly reported a September 2026 historical recalculation of BTC
  ETF flow metrics spanning prior dates.

Therefore future external-data adapters should preserve:
- retrieval timestamp;
- provider version/status;
- raw payload hash;
- original publication/availability timestamp;
- revision lineage.

A modern API response must not silently replace what a historical strategy could
have known.

## 6. Priority update

| Priority | Mechanism | State |
|---|---|---|
| A1 | IEI-MECH-011 CFTC regulated trader positioning | SOURCE_BOUND / prereg-ready |
| A2 | IEI-MECH-022 FINRA ETF short-pressure | METHOD-SPECIFIED / data audit next |
| A3 | IEI-MECH-009 order-flow toxicity / jump-risk | SOURCE_BOUND / exact spec next |
| A4 | IEI-MECH-002 cross-sectional same-weekday | BLOCKED on PIT universe |
| A5 | IEI-MECH-020 protocol fundamental state | SOURCE_BOUND / versioning needed |
| A6 | IEI-MECH-013 derivatives basis -> Spot | SOURCE_BOUND |
| A7 | IEI-MECH-021 token dilution / unlock pressure | BLOCKED_DATA |
| A8 | IEI-MECH-023 ETF institutional-flow persistence | SOURCE_BOUND / revision risk |

The table is a **research-queue priority**, not a performance ranking and not an
economic winner declaration.

## 7. Recommended next allowed work

### RIE-006-IEI-FINRA-SPEC-001 — CHAT_DIRECTOR
Freeze:
- FINRA file set;
- publication-time eligibility;
- ETF universe;
- short-pressure denominator;
- BTC Spot action clock;
- controls;
- opportunity-preservation measures;
- exact falsification rules.

No performance read.

### RIE-006-IEI-FUND-PIT-001 — CHAT_DIRECTOR
Define whether a public network-fundamental dataset can satisfy:
- historical metric definitions;
- revision lineage;
- PoW/PoS transitions;
- chain comparability;
- PIT universe membership.

### RIE-006-IEI-DILUTION-PIT-001 — CHAT_DIRECTOR
Specify admissible supply/vesting evidence and fail closed if historical schedule or
supply labels cannot be reconstructed as they were known at the time.

No Work/Astra gate is reached by these bounded specifications.

## 8. Closeout

- new deep-reviewed source groups: **11**
- materially distinct mechanisms: **4**
- formal Registry candidates created: **0**
- candidate inflation prevented: **hashrate/user split, mining difficulty, ETF price lead**
- new high-priority public-data mechanism: **FINRA ETF short-pressure**
- major data-integrity rule strengthened: **historical queryability != PIT availability**
- backtests: **0**
- performance data read: **0**
- Fresh OOS / recent reserve: **SEALED / NOT READ**
- P10 read/write: **false / false**
- P11: **LOCKED**
- Futures execution: **NONE**
- Live authority: **NONE**

**MERGED=NO**
