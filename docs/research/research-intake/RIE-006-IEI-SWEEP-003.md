# RIE-006-IEI-SWEEP-003 — Derivatives Context for Spot-Long Research

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch: **research-institutional-edge-intelligence**
- starting branch HEAD: **1cef8c3674f6c61a612dde5b4e468cbe2a544704**
- PR: **#152 — OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS: **NOT READ**
- recent reserve: **NOT READ**
- Futures execution authority: **NONE**

## 1. Research question

Can public derivatives-market state improve a **Spot long-only** research process
without introducing Futures execution, leverage, shorting or a renamed trend signal?

This sweep treats derivatives variables only as public context / information-state
inputs. Any future strategy action remains Spot long/cash.

## 2. Deep-reviewed public sources

### IEI-SRC-030 — Dunbar & Owusu-Amoako (2023)
**Predictability of crypto returns: The impact of trading behavior**
- peer-reviewed;
- uses weekly U.S. CFTC Commitment of Traders data for Bitcoin futures;
- documents predictive association between changes in speculative/non-commercial
  net-short positioning and subsequent crypto returns;
- controls include attention, uncertainty, sentiment and prior returns.

Disposition: **SOURCE_BOUND / HIGH-PRIORITY PUBLIC POSITIONING MECHANISM**

### IEI-SRC-031 — Baur & Smales (2022)
**Trading behavior in bitcoin futures: Following the "smart money"**
- peer-reviewed;
- also uses CFTC Commitment of Traders data;
- reports leveraged-money traders as important market participants and documents
  timing behavior concentrated in adjustments to short positions.

Disposition: **MECHANISM SUPPORT / DEDUPE WITH COT POSITIONING**

### IEI-SRC-032 — Shen, Li & Luo (2026)
**Option positions, non-momentum trading, and Bitcoin futures returns**
- peer-reviewed Finance Research Letters article published in 2026;
- uses weekly CFTC trader-category data for CME Bitcoin futures and options;
- reports asset-manager option positions containing selective predictive information
  for second-week-ahead Bitcoin futures returns beyond futures positions;
- explicitly attributes predictive content to a non-momentum positioning component
  rather than simple return chasing.

Disposition: **SOURCE_BOUND / DISTINCT POSITIONING SUB-MECHANISM**

### IEI-SRC-033 — CFTC official COT archive
**Commitments of Traders — CME Bitcoin**
- primary U.S. regulatory source;
- weekly dated futures-only reports expose non-commercial, commercial and
  non-reportable long/short/spread positions plus changes and open interest;
- archived historical reports provide point-in-time provenance.

Disposition: **A-PRIMARY DATA SOURCE**

### IEI-SRC-034 — Lee, El Meslmani & Switzer (2020)
**Pricing Efficiency and Arbitrage in the Bitcoin Spot and Futures Markets**
- peer-reviewed;
- reports Bitcoin futures basis containing information about future spot-price
  changes and risk premia, while also warning that basis is a biased predictor.

Disposition: **SOURCE_BOUND / BASIS-TO-SPOT INFORMATION MECHANISM**

### IEI-SRC-035 — Chi (2023)
**An empirical investigation on risk factors in cryptocurrency futures**
- peer-reviewed;
- cross-sectional crypto futures study;
- identifies basis as the strongest reported cross-sectional signal among the
  tested basis/momentum families;
- basis-momentum loses significance after controlling for basis;
- short holding horizon dominates longer holding horizons in the reported source.

Disposition: **MECHANISM SUPPORT / REPORTED RETURNS UNTRUSTED**

### IEI-SRC-036 — He, Manela, Ross & von Wachter (2022; revised 2025/2026)
**Fundamentals of Perpetual Futures**
- derives no-arbitrage pricing logic for perpetual futures;
- documents that perpetual/spot deviations can be larger than traditional FX,
  comove across cryptocurrencies and diminish over time;
- funding is part of the mechanism tethering perpetual price to spot.

Disposition: **METHOD / ECONOMIC-MECHANISM SOURCE**

### IEI-SRC-037 — Frino et al. (2025)
**Price Discovery in Bitcoin Spot or Futures? The Jury Is Out**
- peer-reviewed;
- uses 1-second sampling and explicitly addresses noise differences;
- reports futures generally leading spot in its sample, but leadership varies
  day by day;
- reports stronger futures contribution to price discovery around macro surprises
  and Tether minting tweets.

Disposition: **PRICE-DISCOVERY SUPPORT / DYNAMIC-LEADERSHIP WARNING**

### IEI-SRC-038 — Yang (2026)
**Apparent Roughness and Funding-Rate Asymmetry: Evidence from Bitcoin and Ether Perpetuals**
- September 2026 public SSRN preprint;
- separates positive funding from negative-funding magnitude;
- reports asymmetric relationships rather than treating funding as an absolute
  symmetric state variable.

Disposition: **SOURCE_BOUND / FUNDING-ASYMMETRY RISK-STATE IDEA**

### IEI-SRC-039 — Palazzi, Raimundo Júnior & Klotzle (2026)
**From Network Fundamentals to Macro-Financial Integration: The Evolving Predictability of Bitcoin Returns**
- public 2026 research;
- reports crypto-native positioning variables, including funding and open interest,
  as predictive inputs across multiple regimes;
- also emphasizes structural breaks and changing information flows.

Disposition: **SOURCE SUPPORT / EXACT ADAPTATION NOT FROZEN**

### IEI-SRC-040 — Binance USD-M Futures market-data documentation
- public funding-rate history endpoint includes symbol, funding rate, funding time
  and associated mark price;
- historical open-interest endpoint exists but the REST history endpoint documents
  only the latest one month for open-interest statistics.

Disposition: **PRIMARY DATA SOURCE / OI LONG-HISTORY LIMITATION**

### IEI-SRC-041 — Binance public-data archive / issue evidence
Public archive and issue tracker document:
- historical Futures trades/aggTrades and checksum infrastructure;
- historical metrics archives containing open-interest-related fields;
- known missing-data defects in metrics;
- a reported 2026 metrics timestamp-labeling change;
- a reported 2026 funding-rate archive/ticker-reuse anomaly.

Disposition: **DATA-QUALITY WARNING / MUST FAIL CLOSED**

## 3. Mechanism extraction

### IEI-MECH-011 — Regulated trader-positioning pressure

Lanes:
- IEI-01 Predictive Alpha
- IEI-07 Time / Event Structure
- IEI-08 Public Alternative Data

Economic mechanism:
- futures trader categories may reveal changes in risk transfer, speculative
  pressure and inventory demand that are not observable from Spot OHLCV alone;
- the state variable is the change in category-specific net positioning, not price
  momentum.

Candidate hypothesis:
- a weekly, strictly lagged CFTC Bitcoin positioning state may contain incremental
  information for future Spot long/cash allocation after controlling for Bitcoin
  return momentum, volatility and market trend.

Required data:
- official CFTC dated COT archive;
- publication/release timestamp, not only "positions as of" date;
- CME Bitcoin contract-unit history;
- Spot BTC data;
- preregistered mapping of trader categories and net-position formula.

Critical timestamp rule:
- a report describing Tuesday positions is not knowable on Tuesday.
- eligibility begins only at the actual public CFTC release timestamp.
- holidays/delayed releases must preserve real publication timing.

Opportunity profile:
- weekly;
- low turnover;
- high potential capacity if effect is real;
- naturally compatible with Spot long/cash.

Distinctness:
- not momentum;
- not MCF lead-lag;
- not generic sentiment scraping;
- not on-chain flow;
- not session timing.

Falsification:
- compare against CASH, Buy-and-Hold and lagged-return baselines;
- control for volatility and broad crypto trend;
- test whether the signal is merely delayed price momentum;
- require stability across contract-size / Micro Bitcoin era changes;
- no threshold selected after outcomes;
- report opportunity starvation if long/cash gating removes most weeks.

Status: **SOURCE_BOUND**
Reason: exact source transformation / release-lag equation still needs
preregistration.

### IEI-MECH-012 — Non-momentum option-position pressure

Lanes:
- IEI-01 Predictive Alpha
- IEI-08 Public Alternative Data

Economic mechanism:
- trader-category option positioning may encode risk-transfer / inventory pressure
  distinct from recent returns.

YATL adaptation:
- use only public CFTC Bitcoin option/futures category data;
- residualize or otherwise preregister the "non-momentum" positioning component
  before any outcome test;
- research action remains Spot BTC long/cash.

Distinctness:
- child mechanism of public regulated positioning, but economically distinct from
  raw speculative net-short because the source attributes information to an option
  positioning component beyond futures positions and momentum.

Leakage / complexity risks:
- reproducing the paper's residualization incorrectly;
- choosing lags after seeing outcomes;
- small weekly sample;
- category-definition or reporting changes.

Falsification:
- must beat raw COT positioning and simple return baselines;
- must show incremental information after exact frozen residualization;
- reject if only one downside-risk episode drives results.

Status: **BLOCKED_REPRODUCIBILITY**
Reason: exact paper transformation must be extracted before candidate creation.

### IEI-MECH-013 — Derivatives basis / premium pressure for Spot

Lanes:
- IEI-01 Predictive Alpha
- IEI-06 Relative / Lead-Lag

Economic mechanism:
- futures/perpetual premium relative to Spot reflects carry, risk transfer,
  inventory pressure and arbitrage-capital constraints;
- basis can contain information not present in Spot returns alone.

Two evidence strands:
1. fixed-maturity Bitcoin futures basis has been reported to contain information
   about future Spot changes, though biased;
2. cross-sectional crypto futures research reports basis subsuming much of the
   basis-momentum premium.

YATL hypothesis class:
- use a strictly lagged, normalized derivatives basis/premium as an external state
  variable for Spot long/cash or cross-sectional Spot selection;
- do not trade the futures leg.

Distinctness:
- not MCF spot-price LEAD_LAG;
- not Spot momentum;
- not generic liquidity gating;
- not cross-venue arbitrage.

Major adaptation risk:
- a futures-return basis premium does not automatically transfer to Spot returns;
- perpetual premium/funding and fixed-maturity basis are related but not identical;
- contract rolls and expiry must not create synthetic lookahead.

Falsification:
- test basis alone before any combination with momentum;
- compare against Spot trend/volume/liquidity;
- use point-in-time contract selection;
- reject if transfer from derivatives basis to Spot adds no incremental information.

Status: **SOURCE_BOUND**

### IEI-MECH-014 — Signed funding crowding / stress state

Lanes:
- IEI-02 Execution Alpha
- IEI-04 Portfolio / Risk Alpha
- IEI-09 Edge Decay / Crowding

Economic mechanism:
- positive and negative funding are not assumed symmetric;
- extreme positive funding can represent crowded long demand / carry pressure;
- negative funding can represent a different market state;
- use funding initially as a stress/crowding variable, not a direct contrarian
  direction rule.

YATL hypothesis:
- signed lagged funding state may explain changes in future Spot execution risk,
  volatility, drawdown exposure or opportunity quality beyond Spot volatility.

Required data:
- official funding-rate history;
- funding settlement timestamp;
- mark/premium price context;
- versioned funding interval/cap changes.

Distinctness:
- not Spot momentum;
- not simple session timing;
- not funding-rate arbitrage because YATL does not take a Futures leg.

Falsification:
- positive and negative funding tested separately;
- freeze extreme-state definition before outcomes;
- reject if absolute funding performs equally well and sign adds no information;
- reject if recent Spot return explains the entire relationship.

Status: **SOURCE_BOUND**

### IEI-MECH-015 — Open-interest leverage buildup

Lanes:
- IEI-03 Liquidity & Capacity
- IEI-04 Portfolio / Risk Alpha
- IEI-09 Edge Decay / Crowding

Economic mechanism:
- rising derivatives open interest relative to liquidity/market size can proxy
  accumulated leveraged exposure and potential forced-flow sensitivity.

Potential Spot use:
- risk/execution context only;
- no Futures position or leverage.

Data problem:
- Binance public REST historical OI endpoint exposes only approximately one month;
- public metrics archives appear to contain longer OI history, but public issue
  evidence documents missing observations and a 2026 timestamp-labeling change;
- a point-in-time continuity audit is mandatory before use.

Falsification:
- first prove historical data semantics and continuity;
- compare OI change against futures volume, Spot volume and volatility;
- reject if raw price trend explains the signal;
- do not fill missing metrics silently.

Status: **BLOCKED_DATA**

## 4. Dedupe / rejected paths

### Futures price leadership as generic lead-lag
**REJECTED_DUPLICATE / DATA-HEAVY**
- MCF already contains a LEAD_LAG family;
- simple "futures move first, buy Spot" would be a renamed cross-market lead-lag;
- dynamic price discovery may still matter as a mechanism, but high-frequency
  leadership estimation requires a separate data and microstructure protocol.

### Funding-rate arbitrage
**OUT OF CURRENT EXECUTION SCOPE**
- requires derivatives positions and often leverage / hedging;
- may be studied as market-structure evidence only;
- no YATL Futures execution candidate is created.

### Liquidation cascade direct signal
**BLOCKED_DATA**
- public historical liquidation availability is currently insufficiently clean and
  stable for a canonical historical study;
- a removed/unavailable historical liquidation snapshot path and endpoint-access
  limitations have been publicly reported.
- no synthetic reconstruction from candles is accepted as "liquidation data."

## 5. Strongest finding

The cleanest new mechanism in this sweep is **regulated trader positioning**.

Why:
- official public CFTC source;
- historical archive;
- clear report dates;
- no current-universe survivorship problem;
- no wallet-label leakage;
- low-frequency and therefore potentially low turnover;
- economically distinct from the heavily explored Spot trend cluster;
- directly compatible with Spot long/cash.

Primary research risk:
- publication lag and weekly sample size.

This makes COT positioning a better immediate research candidate than Open Interest
or liquidation data, which currently have more severe historical-data-quality
problems.

## 6. Taxonomy decision

Do **not** add a new Alpha Factory family yet.

For now:
- COT positioning -> AF-EVENT / external point-in-time context;
- derivatives basis -> AF-RELATIVE;
- funding/OI stress -> AF-REGIME / AF-LIQUIDITY where attribution fits.

A future **AF-POSITIONING** family should be considered only if at least two
independent, reproducible positioning mechanisms survive Development and prove
economically distinct from event/regime context.

## 7. Adversarial AI findings

### A. Release-time leakage is the central COT trap
"Positions as of Tuesday" cannot be used for a Tuesday decision when the report is
released later. Dataset rows must carry both observation/as-of time and public
availability time.

### B. Derivatives context can accidentally repackage momentum
Funding, basis and positioning are often correlated with recent price direction.
Every candidate must prove incremental information beyond a frozen Spot momentum
baseline.

### C. Longer history does not mean usable history
OI/metrics archives with timestamp-semantic changes, missing files or ticker reuse
cannot be silently normalized into a clean panel.

### D. Futures evidence is not automatically Spot evidence
A futures-return factor must be retested as an independent Spot-long hypothesis.
No source-reported futures Sharpe/return becomes YATL evidence.

### E. Cross-market signals can double-count the same crowding state
Basis, funding, OI and COT positioning may all represent related leverage/crowding.
AF-06 independence analysis must eventually cluster them economically, not count
four independent edges by variable name.

## 8. Priority after Sweep 003

| Priority | Mechanism | Status |
|---|---|---|
| A1 | IEI-MECH-011 Regulated COT trader-positioning pressure | **SOURCE_BOUND — PREREGISTER NEXT** |
| A2 | IEI-MECH-013 Derivatives basis/premium -> Spot | **SOURCE_BOUND** |
| A3 | IEI-MECH-014 Signed funding crowding/stress | **SOURCE_BOUND** |
| B1 | IEI-MECH-012 Non-momentum option positioning | **BLOCKED_REPRODUCIBILITY** |
| B2 | IEI-MECH-015 Open-interest leverage buildup | **BLOCKED_DATA** |
| HOLD | Dynamic futures/Spot price leadership | **DEDUPE / DATA-HEAVY** |
| REJECT CURRENT | Funding arbitrage | **OUT OF EXECUTION SCOPE** |
| BLOCKED | Liquidation cascade direct signal | **BLOCKED_DATA** |

## 9. Recommended next work units

### RIE-006-IEI-COT-PREREG-001 — CHAT_DIRECTOR
Freeze:
- exact CFTC report series;
- report release timestamps;
- trader category;
- net-position equation;
- lag;
- Spot long/cash action;
- benchmark ladder;
- trial budget;
- opportunity metrics;
- falsification.

No performance read.

### RIE-006-IEI-DERIV-DATA-AUDIT-001 — CHAT_DIRECTOR
Read-only source/data admissibility audit for:
- fundingRate history;
- premium/index history;
- OI metrics archives;
- ticker reuse;
- timestamp convention changes;
- gap policy.

No bulk acquisition.

### RIE-006-IEI-BASIS-SPEC-001 — CHAT_DIRECTOR
Separate:
- fixed-maturity basis;
- perpetual premium;
- funding.
Do not merge them into one feature after seeing outcomes.

## 10. Closeout

- New deep-reviewed sources: **12**
- New serious mechanisms: **5**
- Formal Registry candidates created: **0**
- Duplicate/out-of-scope paths rejected: **3**
- Highest-priority new mechanism: **regulated CFTC trader positioning**
- Backtests: **0**
- Performance read: **0**
- Fresh OOS read: **false**
- recent reserve read: **false**
- P10 read/write: **false / false**
- P11: **LOCKED**
- Futures execution: **none**
- Live authority: **none**
- Merge authorization: **none**

**MERGED=NO**
