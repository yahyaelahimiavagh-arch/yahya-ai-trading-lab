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

## 14. Blind-spot audit and conditional-edge track

Authoritative cross-cutting governance:

docs/research/alpha-factory/BLIND-SPOT-AND-CONDITIONAL-EDGE-GOVERNANCE-v1.0.md

Alpha Factory must not treat every gate failure as proof of no edge.

Every meaningful rejection now requires a failure classification and salvage
review. The standard classifications include NO_EDGE, CONDITIONAL_EDGE,
OVERFIT, DATA_BLOCKED, EXECUTION_LIMITED, CAPACITY_LIMITED, REGIME_MISMATCH,
REDUNDANT_EDGE, IMPLEMENTATION_INVALIDATED, INSUFFICIENT_EVIDENCE and
UNKNOWN_FAILURE_MECHANISM.

Two economic deployment profiles are recognized:

- ALL_REGIME_EDGE — intended to remain economically valid across the
  preregistered operating regime set.
- REGIME_CONDITIONAL_EDGE — intended to operate only inside a preregistered
  envelope and judged outside that envelope primarily on detection, containment,
  capital preservation and safe re-entry.
- UNKNOWN_EDGE_SCOPE — default until enough evidence exists.

A failed all-regime claim may motivate a new conditional-edge hypothesis, but
the failed candidate remains immutable negative evidence. A conditional
reinterpretation requires a new candidate ID, a new preregistered detector /
operating envelope, and a fresh evidence budget.

The six HSSE-004A survivors therefore remain non-certified for all-regime use.
Their prior crisis failure is retained. A normal-regime / conditional
deployment hypothesis is now explicitly permitted as a separate future research
track, but is not itself approved and does not create Live authority.

### Mandatory blind-spot questions

At rejection, generation closeout, and major portfolio checkpoints the Director
must ask whether:
- a useful conditional edge is being killed by an all-regime gate;
- robustness is being purchased by opportunity starvation;
- search breadth is creating false discoveries;
- improvement comes from signal, timing, sizing, execution or diversification;
- a simpler benchmark explains most of the result;
- detector delay, venue dependence, quote-asset dependence or strategy decay
  has been ignored;
- early capacity makes further research economically pointless.

### Work-token conservation

Work is no longer the default for broad planning.

Governance, protocol design, assumption audits, rejection reviews, narrow
source extraction, candidate classification, queue decisions and localized
documentation remain CHAT_DIRECTOR whenever safe.

WORK_REQUIRED is reserved for substantial implementation, bulk data work,
large deterministic analysis, repository-wide migration, coordinated
multi-file artifact work, or test/build workflows that materially benefit from
Work.

Before every Work gate the Director must first decide whether the task can be
completed safely in CHAT_DIRECTOR. If yes, stay in chat.

Astra remains reserved for corpus-scale synthesis.


## 15. Million-Idea Discovery Program — DS-00..DS-08 (2026-10-21)

**Status: approved research direction only; no performance-run, deployment,
live-order or unlimited-crawl authorization.** Long-term scalable target:
**1,000,000+ preregistered, provenance-bound idea/candidate specifications**.
The currently accepted 1k → 10k → 100k MCF engineering targets remain
*mandatory intermediate capacity gates*, not a ceiling or a license to run
one million economic trials. Count economically independent mechanisms,
canonical specs, effective trials, tested candidates and survivors separately.
One million parameter variants do not imply one million independent ideas.

### 15.1 Reconciled starting inventory

- **RIE external hypothesis intake:** 24 candidates/20 sources initially;
  currently **31 candidate records referencing 27 distinct source URLs**
  in `docs/research/research-intake/CANDIDATE-REGISTRY-V2-v1.0.json`.
  The 31 records comprise 28 published/working-paper-derived hypothesis
  records plus 3 Chinese FMZ lecture/strategy-library records. Registrations
  include SSRN, ScienceDirect, arXiv, NBER, Wiley and FMZ provenance; source
  publication or claimed Sharpe never counts as YATL evidence. Many remain
  `SOURCE_BOUND`, with blocked and negative records retained.
- **MCF deterministic family expansion:** 12 preregistered mechanism families,
  **9,176 raw combinations**, **8,640 structurally admissible** and **6,852
  technically executable** preregistered candidates. **1,788** variants from
  two incompletely specified families remain pre-performance blocked.
  Source: `MCF-PROD-001-PREOUTCOME-FREEZE-CHECKPOINT-v1.0.json`.
  These are variants of 12 family domains, **not** direct extractions from
  6,852 external publications; missing RIE-to-MCF lineage cannot be inferred.
- Current *technical* milestone: merged MCF streaming loader PR #184 passed
  frozen-cache admission at 4h (175 symbols, 606,900 candles) and 15m
  (175 symbols, 9,710,400 candles). **Draft PR #186** targets rolling MA200
  bottlenecks; CI passed but real old/new code parity and performance gate
  is pending. Neither milestone is economic candidate performance acceptance.

### 15.2 Scalable funnel (new DS track; no gate preaccepted)

| Stage | Research deliverable | Non-negotiable acceptance |
|---|---|---|
| **DS-00 Inventory** | Versioned RIE and MCF baseline, source/idea/spec/family/effective-trial counters | Provenance, negative records and distinct-count definitions independently reconciled |
| **DS-01 Discover** | Connectors for papers/citations, preprints, open code/notebooks, books/transcripts, reproducible libraries, EN/ZH and additional licensed markets | Immutable URL/author/license/retrieval timestamp/version/commit/content digest; provider ToS, copyright, robots and rate caps; no unauthorized scraping |
| **DS-02 Extract** | Exact equations, entry/exit/stop/sizing, horizon, lag, data, point-in-time timing, costs, caveats and falsifiable mechanism | Missing method/source is BLOCKED, never an AI-invented fill; reported source metrics are untrusted |
| **DS-03 Canonicalize** | Append-only source and mechanism lineage, normalized-rule fingerprint, parameter-neighbor and family dedupe | Truly duplicated/reworded variants are not independent alpha; immutable spec identities before any outcome |
| **DS-04 Generate** | Lazy deterministic Cartesian generator, sharded ledgers, content-addressed manifests, resume and batch audit | Cheap and bounded 1k → 10k → 100k → 1M+ *registrations* only after throughput/RAM/storage/idempotency gates; no one PR/file per variant |
| **DS-05 Pre-screen** | F0 structure, source feasibility, observable point-in-time features, data gaps, estimated cost/activity, duplicate and implementation blockers | Fully outcome-free, all rejection reasons retained; million-scale candidates do not automatically become a million backtests |
| **DS-06 Development** | Approved small/bounded economic batches with fixed universe/calendar/trials/fees/slippage/baselines, resource quotas | **Separate explicit performance-run authorization for every new budgeted batch**; P10 unaffected; all negative trials retained |
| **DS-07 Adjudicate** | Walk-forward chronology, no-lookahead audit, family/neighbor robustness, economic-cost and regime stress, correlated-trial multiple-testing correction | Zero survivors valid; no ranking-based gate bypass, no new post-outcome tuning to rescue rejected trials |
| **DS-08 Promote** | Freeze audited shortlist, exact independent recompute, Fresh OOS then crisis/Forward in calendar time | No OOS reuse; P10/P11 current locks retained; no live authority inherited from historical results |

### 15.3 Scale gates and engineering design

- **1k spec calibration:** source quality, method extraction, numerical parity,
  deterministic IDs, rejection ledger, unit resource cost.
- **10k spec expansion:** diversity of mechanism families, dedupe false
  positives/false negatives, reproducible sharding, complete trial accounting.
- **100k spec registration/pre-screen:** bounded memory and streaming I/O,
  CPU/disk throughput curves, restart/retry idempotence, manifest reconciliation,
  stop/backpressure protection against interfering with P10.
- **1M+ spec registration/pre-screen:** permitted only after the previous
  acceptance evidence, finite explicit storage/compute budget, effective-trial
  burden characterization and review of marginal independent family diversity.
  This milestone is **not** approval for 1M market-performance tests.

Do not allocate one huge in-memory Cartesian array; use streaming/lazy
enumeration and content-addressed shards, compact columnar datasets where
appropriate, checkpoints and atomic durable append-only result ledgers.
Report `discovered_sources`, `unique_source_uris`, `unique_methods`,
`raw_candidates`, `structurally_valid`, `technically_executable`,
`effective_trials`, `development_tested`, `OOS_tested`,
`independent_mechanisms`, `negative_closeouts` and `survivors`;
each field has a documented denominator and artifact hash.

Statistical safeguards must account for correlated parameter neighbors and
family reuse, sample selection, repeated looks and multiple comparisons;
predeclare how error rates and effective tests are estimated. Historical
Development processing can speed up; independent Fresh OOS/Forward
**cannot** be shortened by adding compute. Stop when marginal diversity
or validity stops improving, even if the million-count target is unmet.

### 15.4 Next work order and frozen boundary

1. Complete Draft **PR #186** real Development BTCUSDT old-vs-new
   numerical-parity and MA200 benchmark before merge decision.
2. If the `production_features.py` code change is accepted, repeat official
   525-dataset reconciliation and create a **new** frozen runner input;
   old frozen input code-identity must not be bypassed.
3. Design/version DS-00..DS-05 schemas, source discovery connectors and
   dedupe tests on an isolated research branch; then run **small nonperformance
   intake/calibration tests** before any mass-generation milestone.
4. Request new explicit human authorization for **each** Development
   performance batch; do not automatically schedule million-scale runs.
5. Preserve P10 timer/service/config and P11 locked status. No deployment,
   Live/Futures/leverage/orders or sealed Fresh OOS/recent-reserve reads.

Canonical global summary: `docs/MASTER-PLAN.md`.
This program is an **architecture + staged research plan**, not an assertion
that million-scale collection, execution or an economic edge currently exists.

## Mass Canonical Candidate Factory — MCF track

Authoritative design:
`docs/research/alpha-factory/MASS-CANONICAL-CANDIDATE-FACTORY-v1.0.md`

Alpha Factory is no longer restricted to candidate-by-candidate research.
It must support high-throughput canonical strategy discovery across materially
different economic mechanisms.

Engineering target:
- architecture supports 100,000+ canonical candidate specifications over time;
- no candidate-count hard ceiling in the core design;
- no one-branch / one-PR / one-file-per-candidate workflow.

Research expansion is staged:
- calibration batch around 1,000 candidates;
- expansion batch around 10,000 candidates;
- large-scale batch up to 100,000 once throughput, deterministic repeatability,
  storage, false-discovery accounting and exact-recompute paths are accepted.

These counts are capacity targets, not survivor quotas.

### MCF stages

MCF-00 — Governance / architecture  
MCF-01 — Family-manifest and candidate-spec schema  
MCF-02 — Deterministic generator / canonical ID / dedupe  
MCF-03 — High-throughput Development screening  
MCF-04 — Neighbor stability / multiple-testing / clustering  
MCF-05 — Exact recompute / mechanism survivor freeze  
MCF-06 — Fresh OOS handoff

### Required filter cascade

F0 structural validity  
F1 opportunity/activity validity  
F2 after-cost Development economics  
F3 temporal robustness  
F4 neighbor stability  
F5 multiple-testing / false-discovery control  
F6 duplication/common-factor clustering  
F7 mechanism survivor freeze  
F8 Fresh OOS  
F9 all-regime or conditional-edge certification  
F10 independent audit / Forward

No hard gate may be bypassed by a ranking score.

### Research-scale interpretation

Historical research throughput may be compressed by compute and automation.
Forward evidence cannot be compressed because it depends on future calendar-time
market observations.

YATL may therefore accelerate:
- candidate generation;
- historical Development;
- robustness analysis;
- historical crisis replay;
- clustering;
- multiple-testing diagnostics;
- exact recomputation.

YATL may not fabricate or compress:
- real Forward time;
- future regime exposure;
- live execution experience;
- time-dependent operational reliability.

### Diversity requirement

Broad MCF generations must span independent economic mechanisms rather than
produce tens of thousands of near-identical trend parameterizations.

Raw candidate count, effective trial count, economic mechanism count,
common-factor cluster count and independent-family count must all be reported.

The six historical HSSE survivors remain one correlated trend cluster and are
not the center of future candidate generation.

### Work-token conservation for MCF

Design, trial budgets, manifests, filter policies, batch classification and
closeout stay CHAT_DIRECTOR whenever safe.

Work may be used once for substantial reusable engine implementation or major
data plumbing. Work is not invoked per candidate or per batch result.

Large canonical runs execute as MANUAL_VPS / BATCH_RUNTIME jobs.

