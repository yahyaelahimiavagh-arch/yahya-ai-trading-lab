# YATL Alpha Factory — Master Plan v1.0

Status: **AUTHORITATIVE PROGRAM LAYER / RESEARCH ONLY / P10 UNTOUCHED / P11 LOCKED**

Date established: **2026-09-27**

This document defines the program above individual Generation protocols. Existing
frozen protocols and canonical outcomes are not rewritten. Generation 2 remains a
bounded research track inside this larger program.

## 1. North-star objective

YATL is not merely a strategy validator. Its research program is now explicitly
designed as an **Alpha Discovery + Validation + Portfolio + Capacity system**.

The long-term objective is:

> Discover multiple economically meaningful, independently auditable opportunity
> sources that remain positive after realistic costs, survive genuinely unseen
> data and adverse regimes, preserve sufficient opportunity capture, and can be
> combined and scaled without violating risk or liquidity constraints.

The economic ambition is large-scale capital growth and opportunity capture. No
research result is allowed to imply or guarantee any fixed wealth outcome. The
program optimizes for **repeatable net dollar opportunity under risk and capacity
constraints**, not attractive historical percentage returns alone.

## 2. Non-negotiable boundaries

The following remain binding unless a future explicitly authorized protocol
changes them:

- PAPER / RESEARCH ONLY;
- `LIVE_MASTER_LOCK=OFF`;
- no Futures execution;
- no leverage;
- no shorting in the current path;
- no live execution;
- no order endpoint;
- no AI direct execution;
- P10 Forward remains isolated and untouched;
- P11 remains locked;
- negative results are retained;
- no hidden trial or post-outcome rescue tuning on the same evidence;
- Fresh OOS and reserve evidence stay sealed until their registered gate;
- repository merge remains Director-authorized; research continuation is not
  merge authorization.

## 3. Three-plane architecture

### Plane A — Alpha Discovery

Purpose: maximize the breadth and quality of independent hypotheses without
contaminating validation evidence.

Responsibilities:
- literature/repository/transcript research;
- point-in-time data expansion;
- candidate registry and deduplication;
- exact method extraction;
- bounded Development search;
- independent alpha-family coverage.

Plane A may generate many failures. Failure volume is not a problem if the
evidence chain is clean.

### Plane B — Adjudication

Purpose: determine whether an apparent edge is real enough to deserve scarce
unseen evidence.

Responsibilities:
- exact recomputation;
- anti-leakage audit;
- neighboring-parameter robustness;
- multiple-testing accounting;
- cost/slippage stress;
- opportunity-starvation checks;
- correlation and common-factor diagnostics;
- Fresh OOS;
- crisis/regime certification;
- independent audit.

Plane B never invents a rescue parameter after seeing the result.

### Plane C — Forward & Capital

Purpose: determine whether a historically validated edge can survive time,
execution friction and capital scale.

Responsibilities:
- isolated shadow/Paper forward validation;
- execution-quality measurement;
- liquidity/capacity analysis;
- portfolio capital allocation research;
- only after separate explicit authorization: consideration of a Tiny Live
  candidate.

Plane C cannot inherit Live authority from historical evidence.

## 4. Alpha-family map

YATL must stop treating many variations of one trend family as many independent
edges. Every candidate receives an `alpha_family_id` and an
`economic_mechanism_id`.

Initial family map:

1. **AF-TREND** — time-series momentum / trend continuation.
2. **AF-BREAKOUT** — range breakout / volatility expansion.
3. **AF-MEANREV** — short-horizon and extreme-move mean reversion.
4. **AF-CRASHREB** — panic, liquidation-like shock, rebound and dislocation.
5. **AF-VOLUME** — volume-conditioned signals and volume-price disagreement.
6. **AF-LIQUIDITY** — spread/liquidity/impact proxies and liquidity regimes.
7. **AF-TIME** — session, weekday, month-boundary and recurring time effects.
8. **AF-RELATIVE** — relative-strength / lead-lag / cross-asset information using
   a point-in-time liquid Spot universe.
9. **AF-REGIME** — deterministic or probabilistic market-state gating.
10. **AF-EVENT** — point-in-time external/event context, only when immutable
    timestamped data are available.
11. **AF-MICRO** — order-book/microstructure research only after a trustworthy
    historical microstructure dataset exists.

Adding a family requires a registry update and a reason; renaming the same
economic idea does not create a new family.

## 5. Candidate lifecycle

Every candidate must move through the same explicit state machine:

`DISCOVERED`
→ `SOURCE_BOUND`
→ `METHOD_SPECIFIED`
→ `PREREGISTERED`
→ `IMPLEMENTED`
→ `DEVELOPMENT_EVALUATED`
→ either `REJECTED_NEGATIVE_EVIDENCE` or `DEVELOPMENT_SURVIVOR`
→ `FROZEN_FOR_OOS`
→ either `OOS_REJECTED` or `OOS_SURVIVOR`
→ `CRISIS_CERTIFIED`
→ `INDEPENDENT_AUDIT_PASS`
→ `FORWARD_CANDIDATE`.

Allowed non-terminal blocker states:
- `BLOCKED_SOURCE`;
- `BLOCKED_DATA`;
- `BLOCKED_REPRODUCIBILITY`;
- `INVALIDATED_BEFORE_ECONOMICS`.

No blocked candidate is silently converted into a weaker test.

## 6. Program stages and gates

### AF-00 — Program Governance & Architecture Lock

Goal: make Alpha Factory the authoritative program layer without rewriting frozen
Generation evidence.

Deliverables:
- this master plan;
- machine-readable stage-gate contract;
- explicit relationship between P10, Generation tracks and Alpha Factory;
- candidate lifecycle and family taxonomy.

Exit gate:
- documents committed;
- no frozen protocol altered;
- CI green.

Current state: **ACTIVE / THIS CHECKPOINT**.

---

### AF-01 — Opportunity Data Foundation

Goal: build data infrastructure broad enough to discover opportunity, not merely
replay BTC/ETH trend rules.

Workstreams:
- preserve current BTCUSDT/ETHUSDT canonical history as reference;
- generalize loaders/manifests to a point-in-time **liquid Spot research
  universe** without survivorship-by-current-listing;
- maintain listing/delisting and symbol eligibility history;
- expose 15m/1h/4h/1d derived research views from canonical data;
- record gap maps rather than silently filling missing observations;
- add point-in-time volume/liquidity proxies available from admitted market data;
- design optional external-context adapters with immutable release timestamps;
- no Futures/leverage/short execution capability is added.

Exit gate:
- immutable universe policy;
- quality manifests;
- reproducible symbol eligibility;
- gap-aware research API;
- no read path to sealed OOS from Development jobs.

---

### AF-02 — Alpha Taxonomy & Candidate Registry v2

Goal: ensure hypothesis diversity is measurable.

Every candidate records at minimum:
- alpha family;
- economic mechanism;
- data dependency;
- holding horizon;
- expected opportunity frequency;
- expected turnover;
- capacity sensitivity;
- regime hypothesis;
- implementation complexity;
- relationship/duplication fingerprint versus existing candidates.

Exit gate:
- all active candidates classified;
- duplicate families/clones identified;
- registry can report candidate count by **independent economic family**, not just
  by parameter set.

---

### AF-03 — Research Intake / Opportunity Sweep

Goal: continuously create high-quality hypotheses from independent mechanisms.

Sources:
- academic papers;
- reproducible repositories;
- professional books/lectures/transcripts;
- credible English/Chinese research;
- internally observed market-structure questions.

Minimum sweep objective:
- at least 5 materially distinct alpha families represented before declaring a
  broad discovery cycle exhausted;
- no quota forces a weak candidate to be tested;
- source-reported performance is never YATL evidence.

Current immediate subtask:
- make one bounded source/reproducibility attempt to unblock
  `RIE-CAND-0011`, `0022`, and `0027`;
- retain blockers if exact specification remains unavailable;
- proceed according to the preregistered queue without guessing missing rules.

Exit gate for each candidate:
- exact source identity where available;
- exact signal/equations;
- lag and timestamp rules;
- missing-data behavior;
- parameter/search domain;
- cost mapping;
- no-lookahead tests;
- explicit source-vs-YATL adaptation notes.

---

### AF-04 — Standalone Alpha Development

Goal: test each economic idea **standalone** before combinations hide weakness.

Rules:
- Development-only evidence;
- all search domains preregistered;
- no candidate is saved by another candidate;
- every trial retained;
- realistic base and stress costs;
- sparse strategies may be sparse by design, but cannot pass risk metrics simply
  by sitting in cash.

Mandatory scorecard:
- completed trades / opportunity count;
- net PnL after costs;
- expectancy;
- profit factor or equivalent payoff ratio;
- maximum drawdown;
- positive fold fraction;
- base/stress cost sensitivity;
- turnover;
- exposure time;
- notional opportunity utilization;
- concentration/outlier dependence;
- parameter-neighborhood stability.

Exit:
- `REJECTED_NEGATIVE_EVIDENCE`, or
- `DEVELOPMENT_SURVIVOR`.

---

### AF-05 — Robust Search & False-Discovery Control

Goal: prevent the Alpha Factory from becoming a backtest lottery.

Controls:
- exact trial ledger;
- candidate/family deduplication;
- walk-forward Development folds;
- neighboring-parameter sensitivity;
- bootstrap confidence intervals where appropriate;
- explicit multiple-testing accounting;
- PBO / Deflated-Sharpe-style diagnostics where mathematically applicable;
- reality-check/SPA-style family tests where justified;
- complexity penalty when two candidates have comparable economics.

A statistical diagnostic is supporting evidence, not permission to bypass
economic gates.

Exit gate:
- reproducible survivor ranking;
- full rejected-trial ledger;
- no hidden retry;
- frozen implementation digest for survivors.

---

### AF-06 — Independence, Correlation & Opportunity-Coverage Gate

Goal: distinguish many strategy names from many actual edges.

For every survivor set measure:
- return/PnL correlation;
- trade-time overlap;
- loss-event overlap;
- sign agreement;
- shared regime dependence;
- shared underlying signal ancestry;
- marginal contribution versus strongest existing edge.

Outputs:
- **independent-edge clusters**;
- common-factor clusters;
- regime coverage map;
- opportunity coverage map.

Important:
- a single exceptional standalone edge is allowed to continue;
- portfolio construction is not blocked merely because only one edge survives;
- but six highly correlated parameter variants count as one cluster, not six
  independent edges.

---

### AF-07 — Portfolio / Ensemble Laboratory

Goal: combine only evidence-backed standalone components.

Combination unlock:
- each component has standalone Development evidence;
- correlations and common failure regimes are known;
- combination has a new preregistered protocol and new trial budget.

Research targets:
- equal-risk or bounded-risk allocation;
- regime-conditioned allocation;
- diversification benefit;
- turnover interaction;
- portfolio drawdown;
- net PnL after combined costs;
- opportunity coverage;
- concentration;
- marginal edge contribution.

Forbidden:
- arbitrary optimizer weights fitted to holdout;
- combining weak candidates solely to manufacture a smooth equity curve.

Exit:
- standalone survivor and/or portfolio survivor frozen for Fresh OOS.

---

### AF-08 — Fresh OOS Adjudication

Goal: spend scarce unseen evidence only on frozen survivors.

Rules:
- implementation, parameters and portfolio weights frozen first;
- Fresh OOS opened once per frozen evaluation protocol;
- no same-OOS retune;
- failed OOS becomes permanent negative evidence;
- no parameter replacement from nearby winners after seeing OOS.

Primary question:
> Did the edge survive data it had no role in choosing itself?

Exit:
- `OOS_REJECTED`, or
- `OOS_SURVIVOR`.

---

### AF-09 — Crisis / Regime / Adversarial Certification

Goal: learn where the edge breaks before capital does.

Tests:
- known historical crises;
- trend, chop, panic, rebound, low-vol and high-vol regimes;
- cost shocks;
- missing-data and delayed-fill behavior;
- liquidity deterioration scenarios;
- parameter-neighbor stress;
- cluster-level simultaneous failure.

Certification does not require every regime to be profitable. It requires the
failure profile to be bounded, understood and compatible with the candidate's
preregistered risk contract.

Exit:
- crisis rejection, or
- `CRISIS_CERTIFIED`.

---

### AF-10 — Independent Audit

Goal: make promotion reproducible by someone not relying on the original
researcher's narrative.

Audit:
- data provenance;
- code digest;
- trial count;
- leakage;
- costs;
- arithmetic;
- failed-trial retention;
- OOS access history;
- crisis result;
- family/cluster classification;
- P10 isolation.

Exit:
- `INDEPENDENT_AUDIT_PASS`, or rejection.

---

### AF-11 — Forward Opportunity Validation

Goal: test whether the edge survives the passage of real time.

Rules:
- separate Forward generation/protocol;
- shadow/Paper only under current authority;
- enough elapsed time **and** opportunity count required;
- compare predicted opportunity frequency versus realized frequency;
- measure signal latency, missing fills, slippage sensitivity and starvation;
- historical success cannot shorten the registered Forward gate.

Exit:
- Forward reject;
- continue collecting evidence;
- or `FORWARD_CANDIDATE`.

P10 current forward evidence remains a separate sealed track and is never
retroactively repurposed.

---

### AF-12 — Capacity & Capital-Scaling Research

Goal: answer not only “does it make money?” but “how many dollars can this edge
realistically absorb?”

For each Forward-capable edge estimate:
- turnover;
- typical and stressed liquidity;
- expected market participation;
- slippage curve;
- capacity decay;
- concentration by symbol/time;
- marginal expected PnL versus deployed capital;
- drawdown under larger notional;
- portfolio-level capital bottlenecks.

Capital objective:
- maximize **expected net dollar PnL** subject to risk, liquidity, evidence and
  operational constraints;
- never maximize leverage to compensate for weak edge.

No Live capital is authorized by this stage. Any future Tiny Live path requires
a separate protocol and explicit Director authorization.

---

### AF-13 — Adaptive Research Loop

Goal: continuously learn without contaminating old evidence.

After each closed candidate:
1. retain the negative/positive evidence;
2. identify the failure mechanism;
3. decide whether it invalidates the hypothesis or exposes a new hypothesis;
4. create a **new candidate ID** for materially new logic;
5. assign new Development/search budget;
6. never overwrite the failed candidate.

This is how YATL evolves without post-hoc curve fitting.

## 7. Two-speed execution model

### Fast lane — Discovery

Used for:
- source research;
- method extraction;
- data diagnostics;
- candidate specification;
- synthetic/unit tests;
- Development exploration within a registered budget.

The fast lane should maximize learning velocity.

### Hard lane — Promotion

Used for:
- canonical Development adjudication;
- survivor freeze;
- Fresh OOS;
- crisis certification;
- independent audit;
- Forward promotion.

The hard lane deliberately moves slower because evidence is scarce.

This prevents excessive bureaucracy from slowing discovery while preserving
strict gates at promotion boundaries.

## 8. Opportunity-preservation doctrine

YATL must not become so conservative that “never trade” is the easiest way to
pass.

Every candidate must declare its expected opportunity profile before evaluation:
- expected signal frequency;
- intended holding horizon;
- intended exposure behavior;
- conditions under which being in cash is part of the hypothesis.

Where a candidate modifies an existing strategy, report:
- directional signal preservation;
- completed-trade preservation;
- active-exposure ratio;
- notional-exposure ratio;
- skipped profitable-opportunity diagnostics where measurable without leakage.

A risk layer that merely suppresses almost all opportunity is not automatically
a superior strategy.

## 9. Billion-scale architecture principle

Large absolute outcomes require more than high backtest returns. YATL therefore
treats these as separate research dimensions:

1. **Edge quality** — after-cost expected value.
2. **Edge breadth** — number of genuinely independent opportunity sources.
3. **Edge persistence** — survival across time/regimes.
4. **Capacity** — deployable capital before impact destroys the edge.
5. **Diversification** — ability to combine edges without common collapse.
6. **Execution** — ability to realize theoretical opportunity.
7. **Compounding** — disciplined capital reuse over long horizons.

The program does not claim that any specific wealth target is achievable. Its
architecture is designed so that, if strong scalable edges are discovered, they
are not trapped inside a small single-strategy system.

## 10. Current canonical position — 2026-09-27

Known evidence:
- Generation-1 trend survivors were strongly correlated and failed HSSE-005
  crisis/regime certification;
- GEN2-001 stop overlay: canonical complete, 0 proposals;
- GEN2-002 volatility scaling: canonical structural invalidation before economic
  evaluation, 0 proposals;
- Fresh OOS for Generation 2 remains sealed;
- P10 real-forward path remains independent;
- P11 remains locked.

Interpretation:
- continuing to patch one trend family indefinitely is not the program;
- Generation 2 may continue its preregistered queue;
- in parallel, Alpha Factory expands independent alpha discovery and data
  breadth without spending sealed evidence.

## 11. Immediate execution sequence

The next checkpoints are fixed in this order unless a preregistered blocker
requires a documented bypass:

1. **AF-00 closeout** — commit this architecture + machine-readable gates; CI.
2. **GEN2-002 closeout CI** — preserve canonical invalidation; no rescue.
3. **AF-03A Source Unblock Sprint** — one bounded attempt on RIE-CAND-0011,
   0022 and 0027; no guessing.
4. **GEN2 queue continuation** — if those remain blocked, proceed to the next
   eligible preregistered candidate (currently Queue B begins with 0028) under a
   fresh protocol.
5. **AF-01 Opportunity Data Design** — specify point-in-time liquid Spot universe,
   universe history, gap policy and capacity metadata before mass expansion.
6. **AF-02 Registry v2** — add alpha-family/economic-mechanism/capacity fields.
7. **AF-03B Independent Alpha Sweep #2** — deliberately source candidates outside
   the current trend-overlay cluster, prioritizing mean reversion, volume/liquidity,
   time effects, crash/rebound and relative/lead-lag mechanisms.
8. **AF-04 Standalone Development** — no portfolio combinations yet.
9. **AF-06 Independence Gate** — cluster survivors by true economic behavior.
10. **AF-07+** only after standalone evidence justifies combination or promotion.

## 12. Program scorecard

The Director dashboard for Alpha Factory must eventually report:

- candidates discovered;
- candidates source-bound;
- candidates development-evaluated;
- negative-evidence count;
- survivors by alpha family;
- independent edge-cluster count;
- median/aggregate after-cost expectancy by family;
- opportunity count and utilization;
- OOS survivor count;
- crisis-certified count;
- Forward candidate count;
- estimated capacity by edge/portfolio;
- sealed-evidence status;
- P10 isolation status;
- P11 lock status.

The principal progress metric is **validated independent edge count and capacity**,
not code volume, test count or number of backtests.

## 13. Execution-mode routing — Chat / Work / Astra

Authoritative routing matrix:

`docs/research/alpha-factory/EXECUTION-MODE-MATRIX-v1.0.md`

Alpha Factory is intentionally split into smaller work packages. Each package is
routed to one of four execution classes:

- `CHAT_DIRECTOR` — protocol, decisions, narrow repo edits, blocker handling,
  canonical-run supervision;
- `WORK_REQUIRED` — substantial multi-file/dataset/browser execution;
- `ASTRA_REQUIRED` — corpus-scale synthesis across very large research/evidence
  contexts;
- `WORK_AND_ASTRA_REQUIRED` — both large execution scope and large-context
  synthesis.

### Mandatory pre-stage warning

The Director must warn Yahya **before** entering any Work/Astra-required package.
A generic `ادامه` or `بریم` cannot silently cross such a gate.

Required warnings:

- `⚠️ WORK GATE` before `WORK_REQUIRED`;
- `⚠️ ASTRA GATE` before `ASTRA_REQUIRED`;
- `⚠️ WORK + ASTRA GATE` before `WORK_AND_ASTRA_REQUIRED`.

Execution begins only after the required-mode warning has been shown and Yahya
continues in the appropriate mode.

### Conditional Astra thresholds

Astra is reserved for corpus-scale work, not ordinary hard problems. Important
automatic triggers include:

- >=50 materially distinct deep-reviewed sources since the prior corpus synthesis;
- >=25 new reproducible methods since the prior corpus synthesis;
- >=100 registered candidates for global mechanism clustering;
- >=20 survivor variants for global independence synthesis;
- >=10 independent edge clusters for large portfolio-architecture synthesis;
- >=3 completed research generations for multi-generation failure synthesis.

When such a threshold is reached, the relevant package becomes
`ASTRA_GATE_PENDING` and the Director warning is mandatory before proceeding.

### Important exception: sealed evidence

Fresh OOS and other scarce canonical evidence are **not** handed to autonomous
Work/Astra execution merely because those modes are available. Their actual
opening/run/adjudication remains directly Director-supervised. Work/Astra may
prepare supporting analysis/audit packs but may not silently spend sealed
evidence or promote a candidate.

