# YATL Institutional Benchmark 001 — Systematic Trading Systems & Alpha Factories

Date: 2026-09-30  
Status: RESEARCH ONLY / NO PERFORMANCE AUTHORIZATION  
Repository baseline: `main` after PR #169 (`ab3eea1436cc72c8e0a33631215bc649192c7c95` observed at benchmark start)

## Scope

This benchmark compares YATL with 20 public or publicly documented systematic-trading systems, firms, research platforms and open-source projects.

The goal is **not** to copy proprietary strategies or infer secret alpha. The goal is to identify transferable process architecture:

- alpha discovery;
- point-in-time / OOS discipline;
- multiple-testing control;
- cost and market-impact modeling;
- portfolio construction;
- execution reconciliation;
- promotion / demotion;
- live feedback;
- capacity and scalability;
- evidence provenance.

No live execution, no order endpoint, no Fresh OOS read, no recent reserve read, no P10 read/write, no futures, no leverage and no shorting are authorized by this document.

---

## Evidence classes

- **A — public capital / real performance evidence:** product, fund, real-money track record or institutional capital is publicly evidenced.
- **B — real production system, strategy performance private:** strong evidence of live systematic trading, but specific alpha performance is not public.
- **C — public forward/paper evidence:** broker/exchange-linked paper or forward evidence exists, but long-term real-money proof is absent.
- **D — research/platform evidence:** useful architecture or tooling, but no attributable profitable strategy evidence.

These labels describe **public evidence strength**, not a quality ranking.

---

## 20-system benchmark

| # | System / Firm | Evidence | Publicly visible architecture / lesson | Transferable YATL implication |
|---|---|---|---|---|
| 1 | AQR | A | Economic intuition + empirical research + disciplined portfolio construction; long-running managed-futures products publish returns and AUM. | Do not optimize only candidate PnL; require portfolio-level diversification and risk-adjusted evidence. |
| 2 | Man AHL | A | Scientific/empirical systematic manager; hundreds of markets; only trades ideas it can test and evidence. | Preserve hypothesis lineage and mechanism-level evidence, not just parameter winners. |
| 3 | Two Sigma | B | Data sourcing → modeling → portfolio construction → execution; tens of thousands of simulations daily. | Separate alpha scoring from portfolio construction and execution; build a consensus layer after survivor selection. |
| 4 | Jane Street | B | Researchers analyze large datasets, build/test models, create strategies and implement production code. | Shorten research→production feedback while preserving explicit safety gates. |
| 5 | Citadel Securities | B | Scientific hypothesis formation, large-scale data, automated strategies, rapid market feedback. | Add post-deployment falsification and feedback loops rather than treating promotion as final. |
| 6 | WorldQuant BRAIN | B | Large-scale alpha generation ecosystem with data, simulation, performance dashboards and broad contributor base. | Treat candidate generation as a factory with standardized admissibility and comparable metrics. |
| 7 | Numerai | A | Thousands of independent models are scored, staked and combined into a Meta Model used by a hedge fund. | Build an ensemble/meta-alpha layer after de-correlation, rather than selecting only one “best” candidate. |
| 8 | XTX Markets | B | ML-based price forecasts over tens of thousands of instruments; large compute/storage; forecasts feed trading and liquidity. | Feature/model diversity and scalable compute become first-class capabilities once candidate validation is stable. |
| 9 | Optiver | B | Full model lifecycle: hypothesis, data, simulation, failure analysis, deployment, live feedback. | Formalize model failure analysis and live drift monitoring. |
| 10 | IMC Trading | B | Hypothesis→execution with ML, large-scale experiments, trading simulation and live-market feedback. | Add explicit research-to-production measurement and real-time validation contracts. |
| 11 | Wintermute | B | Proprietary-capital crypto trading, ML/quant signals, low-latency execution, cross-venue arbitrage, CeFi + DeFi. | Crypto execution and venue effects can dominate weak statistical alpha; execution-aware validation is mandatory. |
| 12 | GSR | B | Institutional crypto market making; proprietary execution database; automated reporting; large historical trading footprint. | Build immutable exchange-fill truth and execution-quality reporting before real-money scale-up. |
| 13 | Cumberland / DRW | B | Principal crypto trading, electronic two-way pricing, API execution, liquidity/market-impact emphasis. | Capacity and liquidity constraints must be modeled before capital allocation. |
| 14 | CoinShares Alternatives | A/B | Systematic digital-asset strategies, proprietary alpha signals, risk framework and dedicated execution infrastructure. | Treat risk architecture and execution infrastructure as independent layers from alpha research. |
| 15 | QuantConnect / LEAN | D | Backtest→paper/live parity, live-vs-OOS reconciliation and brokerage-state reconciliation. | Add a canonical simulated-vs-forward-vs-live reconciliation report with fill-level deviations. |
| 16 | Freqtrade | D | Backtest, dry-run/forward mode, lookahead analysis, recursive analysis; explicitly warns impressive backtests may be unrealistic. | Add automated lookahead/recursive-equivalence diagnostics across all candidate families. |
| 17 | Superalgos | D | Integrated data mining, backtesting, paper/live trading and distributed task execution. | Operational orchestration can be separated from strategy logic and scaled independently. |
| 18 | Mr. Scrooge V6 | A/C | Shadow→promotion→probe→demotion, broker-fill truth, pre-registered forward test, BH multiple-testing control; also documents catastrophic earlier drawdowns. | Strong template for shadow/probe governance, but forward success must not authorize large live capital. |
| 19 | renee-jia/trading-bot | C | Alpaca-linked paper account; publishes performance and drawdown; explicitly documents survivorship bias and noisy residual edge. | Require benchmark decomposition and attribution so beta/universe effects are not mistaken for alpha. |
| 20 | Sentinel Trader | C/D | Explicitly falsifies directional/LLM/stat-arb ideas; realistic costs erase apparent edge; uses walk-forward, bootstrap and capacity curves. | Make “disprove first” tests, cost sweeps and capacity curves mandatory before promotion. |

---

## Primary public sources

Institutional/system sources:

- AQR systematic equities: https://www.aqr.com/learning-center/systematic-equities
- AQR managed futures fund: https://funds.aqr.com/funds/aqr-managed-futures-strategy-fund
- Man AHL: https://www.man.com/ahl
- Two Sigma Investment Management: https://www.twosigma.com/businesses/investment-management/
- Jane Street Quantitative Research: https://www.janestreet.com/quantitative-research/
- Citadel Securities Quantitative Research: https://www.citadelsecurities.com/careers/quantitative-research/
- WorldQuant BRAIN: https://www.worldquant.com/brain/
- Numerai docs: https://docs.numer.ai/
- Numerai hedge fund: https://numer.ai/fund
- Numerai 2024 performance / JPMorgan capacity: https://blog.numer.ai/jpmorgan-secures-500m-capacity/
- XTX Markets: https://www.xtxmarkets.com/
- Optiver research: https://www.optiver.com/what-we-do/research/
- IMC Trading: https://www.imc.com/us/what-we-do
- Wintermute algorithmic trading: https://www.wintermute.com/algorithmic-trading
- GSR market making: https://www.gsr.io/services/trading-market-making
- Cumberland: https://www.cumberland.io/about
- CoinShares active strategies: https://coinshares.com/us/active-strategies/
- QuantConnect live reconciliation: https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation
- Freqtrade strategy testing: https://www.freqtrade.io/en/stable/strategy-101/

Open-source/public-project sources:

- Superalgos: https://github.com/Superalgos/Superalgos
- Mr. Scrooge V6: https://github.com/BrockStar3540/mr-scrooge-v6
- renee-jia/trading-bot: https://github.com/renee-jia/trading-bot
- Sentinel Trader: https://github.com/blitzcrieg1/sentinel-trader-research

---

## Observations that matter most for YATL

### 1. Alpha selection is not enough

Institutional systems repeatedly separate:

`signal discovery → validation → portfolio construction → execution → live feedback`

YATL is currently strongest in evidence integrity and pre-performance freezing. The next architecture should avoid collapsing survivor selection directly into “the strategy.”

### 2. Multiple-testing control must become explicit

A large candidate factory creates a statistical selection problem even when data provenance is perfect.

Required future controls should include:

- family-wise candidate accounting;
- Benjamini–Hochberg/FDR or a documented alternative;
- Deflated Sharpe Ratio where applicable;
- Probability of Backtest Overfitting / combinatorial cross-validation where applicable;
- explicit research degrees-of-freedom ledger.

### 3. Correlated survivors are not independent alpha

A candidate portfolio must detect:

- duplicate mechanisms;
- highly correlated return streams;
- common beta/regime exposure;
- parameter-neighbor clones.

Promotion count must not be interpreted as independent edge count.

### 4. Cost modeling must become adversarial

Static fees are insufficient.

Future stress should include:

- fee tiers;
- spread;
- adverse selection;
- slippage;
- market impact;
- participation constraints;
- latency / stale signal effects;
- fill probability;
- capacity curves by symbol and strategy family.

### 5. Promotion must be reversible

Institutional feedback loops and Mr. Scrooge’s governor both imply that “promoted” is not permanent.

YATL should eventually support:

`SHADOW → PROBE → PAPER → TINY_LIVE → GRADUATED`

with:

`DEGRADE → DEMOTE → RETIRE`

No transition to any live state is authorized by this benchmark.

### 6. Broker/exchange truth must outrank internal logs

Before any future real-capital phase, YATL should reconcile:

- expected orders;
- submitted orders;
- acknowledgements;
- fills;
- fees;
- realized PnL;
- exchange/broker balance movements;
- internal ledger.

The external venue record must be the authoritative performance source.

### 7. Performance needs attribution

Every survivor and portfolio should answer:

- How much came from market beta?
- How much came from universe selection?
- How much came from timing?
- How much came from sizing?
- How much came from exit geometry?
- How much was lost to execution?
- Is the mechanism stable across regimes?

---

## Current YATL baseline observed from PR #169

The current production-input contract already provides unusually strong pre-performance governance:

- frozen executable candidate identity;
- frozen point-in-time monthly membership;
- 175-symbol union;
- 15m / 1h / 4h runtime data;
- 525 content-addressed datasets;
- immutable hashes and provenance;
- cost-policy identity;
- sealed performance boundary;
- `performance_authorized=false`;
- Fresh OOS and recent reserve remain sealed;
- P10 is isolated;
- no free input fallback;
- no candidate performance execution in the preparation/freeze step.

This is a strength and should be preserved.

---

## Gap analysis

### Already strong / preserve

- deterministic evidence identities;
- fail-closed data handling;
- point-in-time universe membership;
- immutable candidate freeze;
- explicit Director authorization;
- negative-evidence preservation;
- separation of preparation from performance;
- sealed OOS reserves;
- paper/research-only safety state.

### Highest-priority missing or not-yet-proven institutional capabilities

1. **MCF statistical multiplicity layer**
   - family-aware FDR;
   - DSR/PBO-style overfit diagnostics;
   - research degrees-of-freedom accounting.

2. **Alpha dependency / redundancy graph**
   - return correlation;
   - regime correlation;
   - mechanism similarity;
   - parameter-neighbor collapse.

3. **Portfolio synthesis layer**
   - survivor ensemble;
   - exposure/risk limits;
   - concentration controls;
   - diversification objective;
   - turnover-aware optimization.

4. **Adversarial execution-cost layer**
   - spread/slippage/impact;
   - liquidity/capacity curve;
   - fill sensitivity.

5. **Forward promotion state machine**
   - SHADOW;
   - PROBE;
   - PAPER;
   - explicit minimum evidence per state;
   - reversible demotion.

6. **Execution reconciliation**
   - model vs simulated fill;
   - paper vs OOS;
   - future broker/exchange truth vs internal ledger.

7. **Alpha decay / drift monitor**
   - rolling expectation;
   - change-point or degradation evidence;
   - automatic hold/demotion recommendation.

8. **Performance attribution**
   - beta/universe/timing/sizing/exit/execution decomposition.

---

## Proposed next work units

### IB-002 — Statistical Multiplicity & Overfit Guard Contract

Research/design only.

Define:

- candidate families;
- multiple-testing family boundaries;
- FDR procedure;
- DSR/PBO applicability;
- minimum independent observations;
- no-peek rules;
- immutable outputs and hashes;
- synthetic falsification tests.

### IB-003 — Alpha Dependency & Survivor Redundancy Contract

Research/design only.

Define:

- return-stream similarity;
- mechanism similarity;
- parameter-neighbor identity;
- cluster/family collapse;
- independent-edge count;
- survivor diversity report.

### IB-004 — Execution Cost, Liquidity & Capacity Contract

Research/design only.

Define:

- static + dynamic cost model;
- spread/slippage sensitivity;
- square-root impact or documented crypto-appropriate alternative;
- participation caps;
- symbol-specific capacity;
- net-edge survival curve.

### IB-005 — Promotion / Demotion State Machine Contract

Research/design only.

Define future states without authorizing live trading:

`RESEARCH → SHADOW → PROBE → PAPER → ELIGIBLE_FOR_TINY_LIVE`

and reversible:

`HOLD → DEMOTE → RETIRE`

The final state must remain locked behind a separate Director work unit and LIVE_MASTER_LOCK.

### IB-006 — Portfolio Synthesis & Meta-Alpha Contract

Only after candidate performance and multiplicity controls are accepted.

Define:

- de-correlated survivor set;
- ensemble/meta-alpha;
- risk budget;
- turnover and cost-aware weighting;
- concentration limits;
- benchmark attribution.

---

## Decision from this benchmark

The strongest transferable pattern is not any specific indicator or strategy.

It is:

> Generate broadly, falsify aggressively, control selection bias, collapse redundant alpha, model execution honestly, allocate at portfolio level, and keep every promoted edge on probation.

YATL should continue as an **alpha research and evidence factory**, not evolve into a single-strategy bot.

No performance execution or live-capital transition is authorized by this report.
