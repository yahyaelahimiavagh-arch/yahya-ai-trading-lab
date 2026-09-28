# RIE-006-IEI-SWEEP-001 — Institutional / Public Alpha Intelligence Sweep

Status: **COMPLETE / SOURCE-INTELLIGENCE ONLY / NO BACKTEST / NO PERFORMANCE READ / NO SEALED-EVIDENCE READ**

Retrieval date: **2026-09-28**

GitHub authoritative starting state:
- main: **ce8e7b747f712779ed5e16144d74bda013226948**
- branch: **research-institutional-edge-intelligence**
- starting branch HEAD: **bb53172fd0b1dfe55ce2520710214d9ce79c6e7b**
- PR: **#152 — OPEN / DRAFT / UNMERGED**
- P10: **UNTOUCHED**
- P11: **LOCKED**
- Fresh OOS: **NOT READ**
- recent reserve: **NOT READ**
- Live authority: **NONE**
- LIVE_MASTER_LOCK: **OFF**

## 1. Work-unit boundary

This work unit is a bounded public/legal source sweep. It does not:
- run a historical backtest;
- read strategy outcome data;
- read Fresh OOS or recent reserve;
- read or mutate P10 evidence;
- change any existing failed candidate;
- retune any existing candidate;
- create order, quantity, leverage, Futures, short, Live or AI-execution authority;
- merge any branch or PR.

The objective is to extract distinct economic mechanisms, falsify duplicates early,
identify point-in-time data requirements, and nominate only mechanisms that are
economically distinct and testable.

External returns, Sharpe ratios, reported profits and capacity claims are treated
as **UNTRUSTED METADATA** until independently tested by YATL.

## 2. Bounded research plan

1. Review approximately twenty high-quality, materially different public sources.
2. Separate documented facts from YATL researcher inference.
3. Extract economic mechanisms, not company names or indicator labels.
4. Deduplicate against Registry v2, Generation-1 / HSSE, Generation-2 and
   MCF-PROD-001 before candidate nomination.
5. Record point-in-time, execution, cost, capacity and leakage requirements.
6. Prioritize only mechanisms that fit the current Spot long-only research path or
   can be studied as execution/capacity infrastructure without changing that path.
7. Do not spend Fresh OOS or promote anything to Forward.

## 3. Existing-search fingerprint used for deduplication

### Registry v2

Current Registry v2 contains **31 candidates**:
- AF-TREND: 12
- AF-REGIME: 11
- AF-MEANREV: 4
- AF-BREAKOUT: 2
- AF-VOLUME: 2

All 31 still carry the legacy economic-mechanism placeholder
**LEGACY_UNCLASSIFIED**, so title/family matching alone is not sufficient.

Important retained negative evidence:
- RIE-CAND-0025: structural data invalidation of the frozen 183-day volatility
  estimator; no economic no-edge conclusion.
- RIE-CAND-0027 / GEN2-003: downside-volatility scaling did not establish
  incremental superiority over total-volatility scaling under the frozen protocol.
- RIE-CAND-0030 / GEN2-001 lineage: the preregistered stop-overlay test produced
  zero proposals; no same-evidence rescue is allowed.
- Generation-1 / HSSE: the six historical survivors are one strongly correlated
  trend cluster and failed HSSE-005 all-regime crisis/regime certification.

### MCF-PROD-001

MCF-PROD-001 already freezes **12 mechanism families** and an expected **8,640**
structurally valid candidates before performance:
- trend crossover;
- breakout channel;
- short-horizon mean reversion;
- crash rebound;
- volume-confirmed direction;
- session-time effect;
- liquidity-conditioned entry;
- BTC/ETH lead-lag;
- price-volume interaction;
- simple statistical deviation;
- trade-count-confirmed direction;
- range-compression breakout.

MCF also records **MULTI_VENUE_DISLOCATION** as a pre-performance blocked family.

Consequences for this sweep:
- generic momentum / trend / EMA-like mechanisms are duplicates;
- generic BTC/ETH leader-lag is a duplicate;
- generic “only trade when liquid” directional filtering is a duplicate;
- generic session gating is a duplicate;
- simple price-volume and trade-count confirmation are duplicates;
- a cross-venue arbitrage/dislocation rule cannot be reintroduced under a new name;
- novelty requires a materially different economic mechanism.

## 4. Public/legal source corpus

Source tier follows the existing RIE convention where possible. Official regulator
and exchange documents are marked **A-PRIMARY** for factual provenance only; this
does not make them performance evidence.

| ID | Source | Class / tier | Mechanism or research use | Sweep disposition |
|---|---|---|---|---|
| IEI-SRC-001 | CFTC, JPMorgan spoofing/manipulation settlement, 2020 — https://www.cftc.gov/PressRoom/PressReleases/8260-20 | REGULATORY / A-PRIMARY | Manipulated displayed liquidity/orders can contaminate microstructure assumptions. | FALSIFICATION SOURCE |
| IEI-SRC-002 | SEC, Gotbit litigation release, 2026 — https://www.sec.gov/enforcement-litigation/litigation-releases/lr-26598 | REGULATORY / A-PRIMARY | Artificial volume / wash trading can contaminate volume and liquidity signals. | FALSIFICATION SOURCE |
| IEI-SRC-003 | Cont, Kukanov, Stoikov, “The Price Impact of Order Book Events” — https://arxiv.org/abs/1011.6402 | A | Order-flow imbalance at best bid/ask; impact sensitivity to depth. | METHOD_SPECIFIED |
| IEI-SRC-004 | Almgren, Chriss, “Optimal Execution of Portfolio Transactions” — https://doi.org/10.21314/JOR.2001.041 | A | Explicit trade-off between market impact, volatility risk and execution schedule. | METHOD_SPECIFIED |
| IEI-SRC-005 | Obizhaeva, Wang, “Optimal Trading Strategy and Supply/Demand Dynamics” — https://www.nber.org/papers/w11444 | A | Liquidity resilience/replenishment is dynamic; static spread/depth is insufficient. | METHOD_SPECIFIED |
| IEI-SRC-006 | Gatheral, “No-Dynamic-Arbitrage and Market Impact” — https://doi.org/10.1080/14697680903373692 | A | Impact/decay models must satisfy no-dynamic-arbitrage restrictions. | METHOD_SPECIFIED |
| IEI-SRC-007 | Frazzini, Israel, Moskowitz, “Trading Costs of Asset Pricing Anomalies” — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2294498 | A | Realized implementation shortfall, price impact, cost-aware portfolio construction and capacity. | METHOD_SPECIFIED |
| IEI-SRC-008 | Hasbrouck, “Trading Costs and Returns for U.S. Equities” — https://doi.org/10.1111/j.1540-6261.2009.01469.x | A | Low-frequency effective-cost estimation can be validated against transaction data. | METHOD_SPECIFIED / EXTERNAL-ASSET |
| IEI-SRC-009 | Kyle, Obizhaeva, “Market Microstructure Invariance: Empirical Hypotheses” — https://doi.org/10.3982/ECTA10486 | A | Cost/size scaling with dollar volume and volatility; capacity sanity framework. | METHOD_SPECIFIED / EXTERNAL-ASSET |
| IEI-SRC-010 | Binance Spot Liquidity Provider Program, 2026 — https://www.binance.com/en/support/announcement/detail/5ac98eff7ca3466583ffd0d81db4ad9e | EXCHANGE / A-PRIMARY | Maker economics depend on tier, maker-volume share and rebates; fee model is endogenous to scale/status. | COST/CAPACITY SOURCE |
| IEI-SRC-011 | Coinbase Market Maker Program, 2020 — https://www.coinbase.com/blog/coinbase-december-2020-market-maker-program | EXCHANGE / A-PRIMARY | Liquidity incentives weight pair liquidity and change fee tiers; venue economics are not a constant fee assumption. | COST/CAPACITY SOURCE |
| IEI-SRC-012 | Makarov, Schoar, “Trading and Arbitrage in Cryptocurrency Markets” — https://dspace.mit.edu/entities/publication/7f91bfb5-ba77-4d0e-9c79-ec75e104e6cc | A | Cross-venue price dispersion, capital mobility and exchange-specific signed-flow information. | SOURCE_BOUND / DEDUPE REQUIRED |
| IEI-SRC-013 | Brandvold et al., “Price Discovery on Bitcoin Exchanges” — https://doi.org/10.1016/j.intfin.2015.02.010 | A | Exchange price leadership varies over time; information-share leadership is dynamic. | SOURCE_BOUND / HISTORICAL-VENUE CAVEAT |
| IEI-SRC-014 | Liu et al., “Liquidity Commonality in Cryptocurrencies” — https://doi.org/10.1016/j.frl.2025.108187 | A | Market-wide liquidity co-movement and weekday liquidity structure. | SOURCE_BOUND |
| IEI-SRC-015 | Long et al., “Seasonality in the Cross-Section of Cryptocurrency Returns” — https://doi.org/10.1016/j.frl.2020.101566 | A | Cross-sectional same-weekday return ranking distinct from simple intraday session gating. | METHOD_SPECIFIED |
| IEI-SRC-016 | “Scheduled FOMC Statements and Intraday Macro Event Risk in Cryptocurrency Markets” — https://doi.org/10.1016/j.frl.2026.110073 | A | Predictable timing of volatility/liquidity demand around scheduled FOMC releases; not return-direction forecasting. | METHOD_SPECIFIED |
| IEI-SRC-017 | “The Influence of Stablecoin Issuances on Cryptocurrency Markets” — https://doi.org/10.1016/j.frl.2020.101867 | A | Public stablecoin issuance events as possible market-wide liquidity/flow events. | SOURCE_BOUND |
| IEI-SRC-018 | Hoang, Vo, “Google Search and Cross-Section of Cryptocurrency Returns and Trading Activities” — https://doi.org/10.1016/j.jbef.2024.100991 | A | Public attention / price-pressure hypothesis. | BLOCKED_DATA |
| IEI-SRC-019 | Bailey, López de Prado, “The Deflated Sharpe Ratio” — https://doi.org/10.3905/jpm.2014.40.5.094 | A | Multiple-testing / selection-bias falsification. | REJECTED_DUPLICATE AS NEW TRACK — ALREADY GOVERNED |
| IEI-SRC-020 | Bailey et al., “The Probability of Backtest Overfitting” — https://doi.org/10.21314/JCF.2016.322 | A | CSCV / probability-of-backtest-overfitting diagnostics. | REJECTED_DUPLICATE AS NEW TRACK — ALREADY GOVERNED |
| IEI-SRC-021 | Han, Kang, Ryu, “Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions” — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565 | A | Negative-control source: realistic assumptions weaken many reported momentum profits; cross-sectional momentum evidence is reported as weak. | DUPLICATE / NEGATIVE SOURCE EVIDENCE |

## 5. Mechanism extraction and candidate decisions

The IDs below are **sweep mechanism IDs**, not Registry-v2 candidate IDs. This work
unit intentionally does not mutate Registry v2. Formal candidate IDs require the
next preregistration work unit.

### IEI-MECH-001 — Scheduled-event execution-risk window

Lane:
- IEI-02 Execution Alpha
- IEI-07 Time / Event Structure

Source:
- IEI-SRC-016

Documented fact:
- The source studies 41 scheduled FOMC statements from 2021 through January 2026.
- It reports a reproducible adjacent-hour increase in BTC/ETH absolute returns and
  trading volume around the scheduled 14:00 ET statement window.
- The source explicitly frames the effect as predictable **timing of risk and
  liquidity demand**, not directional return prediction.

YATL inference:
- A preregistered execution policy may be able to reduce implementation shortfall
  or adverse-selection exposure around known event windows without improving the
  directional signal itself.

Exact hypothesis:
- For an unchanged frozen directional candidate, an event-aware execution policy
  defined before outcomes should lower modeled/observed after-cost implementation
  loss around scheduled FOMC windows after accounting for delayed-entry
  opportunity cost.

Required data:
- immutable historical Federal Reserve meeting/statement release timestamps;
- completed-bar Spot OHLCV;
- a preregistered spread/slippage/implementation-shortfall estimator;
- unchanged underlying candidate signals for attribution tests.

Timestamp semantics:
- event becomes eligible only from the historically published scheduled release
  time;
- no use of statement content before public release;
- no revised calendar knowledge may be backfilled into a timestamp where it was
  not public.

Opportunity profile:
- low event frequency, high concentration;
- not a standalone trading-frequency source;
- must report the number of otherwise-valid entries affected, delayed, skipped and
  later recovered.

Cost/capacity:
- potentially broad because it is an execution overlay;
- benefit can disappear if delaying entry loses more alpha than it saves in cost.

Leakage risks:
- wrong historical release time / daylight-saving conversion;
- using final event classifications unavailable at decision time;
- silently applying the rule only to events known ex post to be volatile.

Duplicate fingerprint:
- not generic AF-TIME session gating;
- not directional event prediction;
- no direct duplicate in Registry v2 or MCF-PROD-001.

Falsification:
- fail if event-aware execution does not improve net implementation economics
  after delay/opportunity cost;
- fail if apparent benefit is isolated to a few outlier meetings;
- fail if benefit disappears under conservative cost assumptions;
- fail if opportunity removal, rather than better execution, explains the result.

Status: **METHOD_SPECIFIED**

### IEI-MECH-002 — Cross-sectional same-weekday seasonality

Lane:
- IEI-06 Cross-sectional / Lead-Lag
- IEI-07 Time / Event Structure

Source:
- IEI-SRC-015

Documented fact:
- The source studies 151 cryptocurrencies over 2016–2019.
- It reports that average historical same-weekday returns positively predict the
  subsequent cross-section, with controls reported for momentum, size, beta,
  idiosyncratic risk and liquidity.

YATL inference:
- A long-only Spot adaptation can rank the point-in-time eligible universe by a
  strictly lagged same-weekday historical statistic, hold only the stronger
  subset, and compare against an equal-exposure liquid-universe baseline.

Required data:
- point-in-time historical Spot universe;
- delisting/listing history;
- daily completed returns;
- point-in-time liquidity eligibility;
- explicit minimum-history rule.

Timestamp semantics:
- use only completed observations from prior occurrences of the same weekday;
- no current-2026 universe projected backward;
- no future delisting survival knowledge.

Opportunity profile:
- daily cross-sectional ranking;
- materially broader opportunity count than BTC/ETH-only strategies;
- opportunity utilization must be reported, not inferred from performance.

Cost/capacity:
- turnover and breadth can make costs first-order;
- capacity depends on liquid-universe membership and concentration;
- long-only adaptation may differ materially from source portfolio construction.

Leakage risks:
- survivorship/current-universe bias;
- selecting lookback length after seeing results;
- using future liquidity rank;
- local-time vs UTC weekday mismatch;
- exchange-history availability bias.

Duplicate fingerprint:
- materially distinct from MCF SESSION_TIME_EFFECT because the mechanism is
  **cross-sectional historical same-weekday ranking**, not an intraday session gate;
- not a trend/EMA clone;
- overlaps AF-TIME and AF-RELATIVE by design.

Falsification:
- compare against equal-weight / liquidity-matched baselines;
- require net-of-cost benefit;
- test whether ordinary momentum explains the ranking;
- require sufficient completed trades and exposure;
- reject if only tiny illiquid coins drive the effect.

Status: **BLOCKED_DATA**
Reason: the mechanism is sufficiently specified, but the full point-in-time
multi-symbol AF-01C historical universe must be populated/admitted before a
canonical Development test.

### IEI-MECH-003 — Market-wide liquidity commonality state

Lane:
- IEI-03 Liquidity & Capacity
- IEI-06 Cross-sectional
- IEI-07 Time Structure

Source:
- IEI-SRC-014

Documented fact:
- The source reports strong co-movement between individual-coin and market-wide
  liquidity and a recurring intraweek liquidity pattern.

YATL inference:
- A lagged market-wide liquidity state may be more informative for cost,
  participation and position capacity than a symbol-only liquidity threshold.

Required data:
- point-in-time multi-symbol liquidity proxy;
- ideally bid-ask spread or a validated crypto-specific spread estimator;
- volume and volatility;
- target-excluded cross-sectional market-liquidity aggregate.

Timestamp semantics:
- market state at t may use only symbols/data eligible and completed at t;
- target symbol must be excluded from its own market-wide aggregate where needed;
- no current constituent list may be projected backward.

Opportunity profile:
- potentially daily or intraday;
- acts primarily as cost/capacity/execution-state information rather than a
  directional predictor.

Cost/capacity:
- directly relevant;
- must test whether state-based participation actually improves net dollar
  economics rather than merely reducing trade count.

Leakage risks:
- future-universe membership;
- using contemporaneous target liquidity in a way unavailable before decision;
- unstable spread proxy on illiquid bars.

Duplicate fingerprint:
- distinct from MCF LIQUIDITY_CONDITIONED_ENTRY, which gates a positive-return
  directional rule using symbol liquidity percentile;
- this mechanism is **systemic cross-sectional liquidity commonality / state**.

Falsification:
- fail if market-wide state does not predict future/realized execution friction or
  capacity-relevant outcomes;
- fail if simple symbol liquidity explains all incremental information;
- audit opportunity starvation.

Status: **SOURCE_BOUND**
Reason: exact YATL liquidity estimator and forecast target still require a frozen
method packet.

### IEI-MECH-004 — Liquidity resilience / replenishment after a shock

Lane:
- IEI-02 Execution Alpha
- IEI-03 Liquidity & Capacity
- IEI-05 Market Microstructure

Source:
- IEI-SRC-005

Documented fact:
- Obizhaeva-Wang models execution around the dynamic recovery of supply/demand;
  the key variable is liquidity resilience, not only static spread/depth.

YATL inference:
- Post-shock refill/recovery speed may distinguish a temporary liquidity
  dislocation from a continuing liquidity vacuum and may determine whether entry
  timing is economically executable.

Required data:
- trustworthy historical L2 order-book snapshots/events;
- trades;
- exchange sequence/timestamp semantics;
- explicit gap/drop detection.

Opportunity profile:
- high-frequency / event-driven;
- expected to be sparse after strict data-quality filters;
- capacity sensitive.

Leakage risks:
- reconstructing book state from incomplete snapshots;
- sequence gaps;
- using future refill path to classify the current state;
- survivor-biased venue selection.

Duplicate fingerprint:
- distinct from static liquidity percentile filtering;
- distinct from CRASH_REBOUND price-only logic because the mechanism is
  **liquidity replenishment dynamics**.

Falsification:
- preregister the measurement horizon;
- test whether lagged resilience predicts future cost/recovery after controls;
- reject if price-only shock variables explain the result;
- stress missing book events and spread expansion.

Status: **BLOCKED_DATA**
Reason: current AF-01/AF-01C kline-oriented historical corpus is not a trustworthy
L2 microstructure dataset.

### IEI-MECH-005 — Order-flow imbalance scaled by depth

Lane:
- IEI-05 Market Microstructure
- IEI-02 Execution Alpha
- IEI-01 Predictive Alpha, only if independently validated in crypto

Source:
- IEI-SRC-003

Documented fact:
- The source reports a short-horizon linear relationship between order-flow
  imbalance and price changes, with sensitivity inversely related to market depth;
  simple trade volume is reported as noisier/less robust.

YATL inference:
- In crypto Spot, lagged OFI/depth could be tested as a short-horizon
  information/adverse-selection variable, but equity evidence cannot be assumed to
  transfer.

Required data:
- complete historical best-bid/best-ask order events or equivalent L2 feed;
- exact cancel/add/trade ordering;
- venue-specific tick/lot rules.

Opportunity profile:
- high signal frequency if data exist;
- high turnover;
- latency and capacity sensitivity are first-order.

Leakage risks:
- event sequencing;
- incomplete cancel events;
- timestamp aggregation;
- using post-decision depth;
- spoofed displayed liquidity.

Duplicate fingerprint:
- distinct from MCF trade-count and price-volume families;
- distinct from simple bid-ask spread.

Falsification:
- crypto-specific replication required;
- compare OFI against trade volume and simple return baselines;
- enforce conservative latency;
- reject if net edge disappears at realistic costs;
- run market-integrity contamination audit.

Status: **BLOCKED_DATA**

### IEI-MECH-006 — Stablecoin issuance as a public liquidity-flow event

Lane:
- IEI-08 Public Alternative Data
- IEI-07 Event Structure

Source:
- IEI-SRC-017

Documented fact:
- The source studies 565 issuance events across seven stablecoins in 2019–2020
  and reports distinct market behavior around issuance.

YATL inference:
- Public on-chain mint/issuance events may contain information about market-wide
  crypto liquidity demand, but “mint” is not automatically equivalent to “capital
  entering an exchange.”

Required data:
- canonical historical stablecoin contract addresses;
- mint/burn events with block timestamps and chain finality;
- point-in-time stablecoin supply;
- Spot market data;
- no future-known exchange-address labels unless the label itself has historical
  provenance.

Timestamp semantics:
- event becomes known only after the relevant block/event is public and confirmed
  under a frozen confirmation rule;
- no mempool/private information;
- no retroactive exchange attribution.

Opportunity profile:
- irregular event-driven;
- lower frequency than price/volume candidates;
- broad market impact is possible but must be measured, not assumed.

Cost/capacity:
- if real, potentially broad market capacity;
- directional implementation may still be cost- and timing-sensitive.

Leakage risks:
- future address labels;
- contract migrations;
- treating treasury/internal mints as market inflows;
- survivorship of stablecoin set;
- event timestamp normalization across chains.

Duplicate fingerprint:
- not a trend, volume confirmation or generic macro-event rule;
- fits AF-EVENT; no new alpha-family ID is required.

Falsification:
- separate mint events from exchange transfers;
- test stablecoin-specific and aggregate effects;
- require robustness across eras/stablecoins;
- reject if a few Tether-era events dominate;
- benchmark against market regime and BTC trend.

Status: **SOURCE_BOUND**

### IEI-MECH-007 — Public attention pressure

Lane:
- IEI-08 Public Alternative Data
- IEI-06 Cross-sectional

Sources:
- IEI-SRC-018
- supporting literature class represented by public attention research

Documented fact:
- The source reports that abnormal Google search volume is associated with later
  cross-sectional return, volatility and trading-volume differences.

YATL inference:
- Attention may represent temporary demand pressure or information arrival.

Required data:
- historically reproducible query definitions;
- point-in-time Google Trends observations exactly as they would have been seen at
  each historical decision timestamp;
- stable scaling/normalization semantics.

Leakage risks:
- Google Trends normalization changes with query window;
- revised/resampled history;
- keyword selection after seeing outcomes;
- current token names mapped backward;
- missing historical delisted-token attention.

Duplicate fingerprint:
- economically distinct from price/volume momentum;
- no current Registry-v2 attention family candidate.

Falsification:
- first prove point-in-time reproducibility;
- freeze query universe before outcomes;
- test whether price/volume already explains the effect;
- reject if historical values cannot be reconstructed without revision leakage.

Status: **BLOCKED_DATA**
Reason: current public Google Trends history is not accepted as point-in-time
evidence until a reproducible archival protocol exists.

## 6. Sources/mechanisms deliberately not promoted

### Cross-venue arbitrage / generic dislocation

Makarov-Schoar and Brandvold are useful public market-structure sources, but a
direct cross-venue dislocation candidate is **REJECTED_DUPLICATE** for this sweep:
- MCF-PROD-001 already records MULTI_VENUE_DISLOCATION as blocked;
- current YATL path is long-only Spot and does not assume synchronized transfer,
  borrow or cross-venue inventory;
- historical price-leadership evidence involving defunct venues cannot be
  transferred to current venues without new point-in-time data.

A future **dynamic price-discovery leadership** hypothesis could be economically
distinct, but it must receive its own data protocol rather than being smuggled in
as a renamed multi-venue arbitrage rule.

### Generic BTC/ETH lead-lag

**REJECTED_DUPLICATE** — MCF-P1-F08 LEAD_LAG already covers lagged BTC/ETH peer
response in momentum/reversal modes.

### Generic liquidity-filtered momentum

**REJECTED_DUPLICATE** — MCF-P1-F07 LIQUIDITY_CONDITIONED_ENTRY already covers a
directional return rule gated by point-in-time liquidity rank.

### Momentum / cross-sectional momentum / trend overlays

**REJECTED_DUPLICATE** — already heavily represented in Registry v2, HSSE and
Generation-2 lineage. IEI-SRC-021 is retained as source-level negative evidence
that attractive reported momentum results can deteriorate under more realistic
assumptions. It is not YATL performance evidence and does not rewrite historical
YATL outcomes.

### DSR / PBO as a “new alpha idea”

**REJECTED_DUPLICATE AS META-RESEARCH** — DSR and PBO/CSCV are already named in
Blind-Spot & Conditional-Edge Governance and AF-05 multiple-testing policy. They
remain useful tools but are not new candidate families.

## 7. Institutional execution/capacity mechanisms retained as infrastructure

The following are important but are **not directional strategy candidates**:

### Execution efficient frontier

Almgren-Chriss provides a framework for balancing market impact and volatility
risk during execution. YATL use:
- execution-cost model design;
- implementation-shortfall attribution;
- deterministic comparison of immediate vs staged/delayed execution.

### No-dynamic-arbitrage impact constraints

Gatheral provides falsification constraints on market-impact decay models. YATL
use:
- reject internally inconsistent impact simulators before capacity claims;
- prevent a cost model from manufacturing free profit through impact assumptions.

### Realized implementation shortfall / cost-aware capacity

Frazzini-Israel-Moskowitz demonstrates why theoretical signal returns and
realized institutional execution economics can differ materially. YATL use:
- separate signal alpha from execution alpha;
- estimate net-dollar capacity, not only return percentage;
- report tracking/opportunity cost when trading more slowly.

### Low-frequency cost proxy validation

Hasbrouck shows that a low-frequency cost estimator can be validated against
transaction-level costs in another asset class. YATL use:
- methodology inspiration only;
- a crypto-specific proxy must be validated before being trusted.

### Market-microstructure invariance

Kyle-Obizhaeva provides scalable cost/size hypotheses tied to volume and
volatility. YATL use:
- capacity sanity checks and stress priors;
- no assumption that equity calibration constants transfer to crypto.

### Exchange maker programs

Binance and Coinbase public programs show that realized maker economics can
depend on tier, volume share, pair classification and rebates. YATL use:
- fee schedule must be versioned by date/venue/account state;
- institutional rebates must never be assumed unless the tested account/profile
  actually qualifies;
- scale can change costs discontinuously.

## 8. Adversarial AI findings / blind spots

### A. Volume is not automatically trustworthy economic demand

CFTC spoofing enforcement and SEC crypto wash-trading allegations show that
displayed orders or executed volume can be artificial/manipulative in some
markets.

Mandatory implication:
- volume/liquidity candidates must treat raw volume as a fallible measurement;
- small/illiquid symbols require integrity filters;
- no manipulation method is operationalized;
- the legal sources are used only to design falsification and data-quality tests.

### B. Static liquidity is not enough

A single volume percentile or spread snapshot can miss:
- refill/recovery speed;
- impact decay;
- adverse selection;
- systemic market-wide liquidity stress.

This is a genuine blind spot in kline-only research.

### C. “Execution alpha” should not become a fake new alpha family

Execution improvement is economically important, but it is usually an
**attribution dimension** rather than a new directional forecasting family.
This sweep therefore does **not** add AF-EXECUTION. It records execution
mechanisms under IEI-02 and AF-EVENT / AF-LIQUIDITY / AF-MICRO as appropriate.

### D. Point-in-time alternative data is harder than “public data”

Public availability today does not prove historical point-in-time availability.
Google Trends, exchange-address labels, token metadata and revised datasets can
silently inject future knowledge.

### E. Opportunity starvation remains a failure mode

Any event/liquidity/risk gate must report:
- opportunities removed;
- entries delayed;
- missed profitable moves;
- active exposure;
- completed trades;
- net benefit after opportunity cost.

“Trade less” is not accepted as execution alpha by itself.

## 9. Candidate prioritization after deduplication

Priority is based on economic plausibility, distinctness, reproducibility,
point-in-time data, Spot-long-only compatibility, after-cost potential,
opportunity frequency, capacity, falsifiability and implementation realism — not
source-reported return.

| Priority | Mechanism | Why it survives this sweep | Primary blocker |
|---|---|---|---|
| A1 | IEI-MECH-001 Scheduled-event execution-risk window | Distinct execution timing; public immutable schedule; reproducible; directly tests after-cost realization. | Need frozen cost/IS estimator. |
| A2 | IEI-MECH-002 Cross-sectional same-weekday seasonality | Distinct from current session gate and trend cluster; broad opportunity set; long-only adaptation possible. | AF-01C point-in-time broad universe must be populated/admitted. |
| A3 | IEI-MECH-003 Market-wide liquidity commonality state | New systemic-liquidity mechanism versus symbol-only filter; strong execution/capacity relevance. | Exact crypto liquidity proxy/adaptation not frozen. |
| A4 | IEI-MECH-006 Stablecoin issuance flow | Distinct public on-chain event mechanism; historically reconstructable in principle. | Point-in-time event taxonomy and contract lineage. |
| B1 | IEI-MECH-004 Liquidity resilience | Strong economic mechanism and execution relevance. | Trustworthy L2 historical data absent. |
| B2 | IEI-MECH-005 OFI/depth | Falsifiable microstructure mechanism; distinct from volume/trade count. | Trustworthy order-event data absent; latency/cost sensitivity. |
| BLOCKED | IEI-MECH-007 Public attention pressure | Economically distinct but cannot be trusted yet. | Point-in-time Google Trends reconstruction. |

## 10. Strongest new economic families / coverage

No new Alpha Factory family ID is justified yet. The current family map is broad
enough if used correctly.

The strongest **under-covered** areas are:
1. **AF-LIQUIDITY** — systemic liquidity commonality and dynamic resilience, not
   merely a liquidity filter on a trend rule.
2. **AF-EVENT** — scheduled macro-event execution risk and public on-chain
   liquidity-flow events.
3. **AF-TIME + AF-RELATIVE intersection** — cross-sectional same-weekday
   seasonality, distinct from ordinary session timing.
4. **AF-MICRO** — OFI/depth and refill dynamics, but correctly blocked until
   trustworthy historical order-book data exist.

Powerful-idea conclusion:
- the largest immediate blind spot is not “one more predictor”;
- it is **separating signal alpha from execution/capacity alpha and measuring
  whether YATL can realize a signal after market state, cost and opportunity loss**.

## 11. Data prerequisites

### Already conceptually compatible with AF-01 / AF-01C
- completed Spot OHLCV;
- point-in-time multi-symbol eligibility;
- point-in-time volume/trade-count where admitted;
- immutable external event timestamps.

### Requires additional governed data
- historical BBO / L2 order-book events for AF-MICRO;
- versioned venue fee/rebate schedules;
- stablecoin contract lineage and on-chain mint/burn events;
- historically reconstructable alternative-data observations;
- validated crypto execution-cost/slippage estimator.

Rules:
- no silent gap filling;
- no current exchange state projected backward;
- no future-known address labels;
- no revised dataset accepted without revision semantics;
- every external timestamp must define when YATL was legally able to know it.

## 12. Negative evidence retained

1. Existing YATL momentum/trend negative and crisis evidence is unchanged.
2. Existing GEN2-001/002/003 negative evidence is unchanged.
3. MCF blocked MULTI_VENUE_DISLOCATION remains blocked; this sweep does not
   reintroduce it.
4. IEI-SRC-021 adds **source-level caution** against cross-sectional momentum under
   realistic assumptions; it is not a YATL result.
5. Market-integrity enforcement evidence is retained as a falsification warning
   for volume/order-book research, not as a trading recipe.

## 13. Recommended next work units

### RIE-006-IEI-PREREG-001 — CHAT_DIRECTOR
Bounded exact preregistration for:
- scheduled-event execution-risk window;
- cross-sectional same-weekday seasonality, only after confirming AF-01C data
  readiness without reading any performance.

Freeze:
- equations;
- timestamp semantics;
- baseline;
- cost assumptions;
- trial budget;
- opportunity-preservation metrics;
- falsification rules.

### RIE-006-IEI-LIQUIDITY-SPEC-001 — CHAT_DIRECTOR
Freeze the exact liquidity-commonality metric and define the minimum acceptable
historical BBO/L2 dataset for resilience/OFI research.

If bulk L2 acquisition is later authorized, that later acquisition stage may
reach a WORK gate. This specification stage does not.

### RIE-006-IEI-ALT-PIT-001 — CHAT_DIRECTOR
Define a point-in-time stablecoin issuance/mint dataset:
- contract lineage;
- confirmation rule;
- no future address labels;
- no market outcome read.

### RIE-006-IEI-EXEC-COST-001 — CHAT_DIRECTOR first
Preregister a crypto-specific execution-cost framework using:
- implementation shortfall;
- spread/slippage proxies;
- volatility/liquidity state;
- participation/capacity;
- conservative account fee assumptions.

Implementation may later require Work if it becomes substantial multi-file code.

### RIE-006-IEI-ADVERSARIAL-001 — CHAT_DIRECTOR
Convert the market-integrity findings into mandatory falsification tests for
volume/liquidity/microstructure candidates.

## 14. Work-unit closeout

- Sources reviewed: **21**
- Distinct mechanisms retained for serious follow-up: **7**
- New Registry-v2 candidates created: **0**
- Registry-v2 candidates modified: **0**
- Duplicates/reintroductions explicitly rejected: **5 classes**
- Data-blocked serious mechanisms: **3**
- Source-bound serious mechanisms: **2**
- Method-specified serious mechanisms: **1**
- Mechanism specified but blocked on admitted AF-01C population: **1**
- Backtests run: **0**
- Performance data read: **0**
- Fresh OOS read: **false**
- recent reserve read: **false**
- P10 read: **false**
- P10 write: **false**
- P11: **LOCKED**
- Live authority created: **none**
- Merge authorization: **none**

**MERGED=NO**
