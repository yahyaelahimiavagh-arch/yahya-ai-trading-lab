# RIE-006 — IEI ETH Supply + Finality Provenance Audit 001

Work Unit ID: `RIE-006-IEI-ETH-SUPPLY-FINALITY-PROVENANCE-AUDIT-001`  
Status: **FINALITY RULE CLOSABLE / SUPPLY DENOMINATOR BLOCKED / MECH-024 CLOSED PRE-PERFORMANCE / NO PERFORMANCE READ**  
Date: 2026-09-29  
Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

Starting GitHub state verified directly before execution:
- `main`: `f3803ebe0bd9ec43f71940d463098fde58aa4d1d`
- branch: `research-institutional-edge-intelligence`
- starting branch HEAD: `a2e230b32257bc7c82be3b25a0aeb02154f474b5`
- PR #152: OPEN / DRAFT / UNMERGED
- branch relation to current main: DIVERGED; 19 commits ahead / 99 commits behind; merge base `ce8e7b747f712779ed5e16144d74bda013226948`

Parent:
- `RIE-006-IEI-ETH-FEE-DATA-SPEC-AUDIT-001.md`
- AF-03D bounded queue / `IEI-MECH-024`

Boundary:
- PAPER / RESEARCH ONLY
- `LIVE_MASTER_LOCK=OFF`
- NO Futures execution / leverage / short / Live / order endpoint / AI execution
- no prices, returns, PnL, Sharpe, hit rate, backtest, parameter sweep, candidate promotion or outcome read
- Fresh OOS SEALED / NOT READ
- recent reserve SEALED / NOT READ
- P10 UNTOUCHED / NOT READ / NOT WRITTEN
- P11 LOCKED
- no merge / rebase / force-push / history rewrite / lineage reconciliation

## 1. Exact blocker this unit must close

Determine whether the two remaining MECH-024 blockers can be closed with a
**finite, reproducible protocol** before any performance evidence is spent:

1. consensus-native finality / UTC-day close and decision eligibility;
2. historical ETH supply denominator provenance for the frozen post-Dencun track.

Research-sprawl stop rule:

If either denominator provenance or finality requires disproportionate historical
reconstruction, unverifiable assumptions, or a modern provider scalar treated as
historical truth, terminate the normalized mechanism as:

`BLOCKED_DATA / ECONOMIC_TEST_NOT_AUTHORIZED`.

Do not create another ETH audit merely because more chain detail can be studied.

## 2. Cheapest falsification

The cheapest falsification is source/protocol inspection only:

- Can canonical finalized state be identified from protocol-native consensus data?
- Can the relevant execution blocks be tied to finalized consensus ancestry?
- Does an official protocol-native historical scalar provide total ETH supply at
  the frozen starting date with admissible provenance?
- If not, can a finite starting checkpoint be established without reconstructing
  historical issuance/burn/state from much earlier chain history?

No acquisition or computation is required to answer these protocol questions.

Official sources inspected:
- https://ethereum.org/developers/docs/consensus-mechanisms/pos/
- https://ethereum.org/developers/docs/consensus-mechanisms/pos/gasper/
- https://ethereum.org/developers/docs/apis/json-rpc/
- https://ethereum.org/eth/supply
- https://ethereum.org/roadmap/merge/issuance/
- https://ethereum.github.io/consensus-specs/
- https://ethereum.github.io/consensus-specs/specs/phase0/beacon-chain/
- https://ethereum.github.io/consensus-specs/specs/bellatrix/beacon-chain/
- https://eips.ethereum.org/EIPS/eip-1559
- https://eips.ethereum.org/EIPS/eip-4844

## 3. Finality / UTC-day blocker — CLOSED AT PROTOCOL LEVEL

Ethereum proof-of-stake exposes explicit finalized checkpoints. The consensus
state contains a `finalized_checkpoint`, and finalized checkpoints finalize their
ancestor chain. Bellatrix and later consensus state also commits to the latest
execution payload header, while an execution payload is carried by the beacon
block.

A finite rule can therefore be frozen without inventing a fixed wall-clock lag.

### 3.1 Frozen day-close rule

For UTC day `D`:

1. aggregate execution/blob fee inputs only from canonical execution blocks whose
   execution timestamp satisfies:
   `D 00:00:00Z <= timestamp < D+1 00:00:00Z`;
2. identify the last canonical execution block in that interval;
3. identify the beacon block carrying that execution payload;
4. wait until a consensus state reports a finalized checkpoint whose finalized
   chain includes that beacon block as an ancestor;
5. only then mark the complete UTC-day observation finalized;
6. `decision_eligibility_time` is no earlier than the first consensus observation
   that proves the required finalized ancestry, plus any later preregistered
   processing/bar boundary.

Do not use:
- an assumed “15 minute” constant as the eligibility rule;
- `latest` or merely `safe` execution state as a substitute for finalized state;
- provider retrieval time as block observation time;
- an execution block not yet proven to be on the finalized beacon ancestry.

### 3.2 Missed slots / delayed finality

Missed slots do not invalidate the rule. Eligibility waits for the actual finalized
checkpoint.

If finality is delayed, the daily state is delayed rather than forward-filled or
declared available at midnight.

### 3.3 Reproducibility

A future implementation would preserve:
- beacon slot/root/state root;
- finalized checkpoint epoch/root;
- execution payload block hash/number/timestamp;
- ancestry proof/identity;
- retrieval timestamp and source/client;
- parser/transformation version.

This is finite and bounded. It does not require a new research audit.

Disposition:

`FINALITY_DAY_CLOSE = METHOD_SPECIFIED / PROTOCOL_CLOSABLE`.

## 4. ETH supply denominator — FAILS THE FINITE-PROTOCOL GATE

Ethereum's official supply documentation describes total ETH supply as dynamic
under issuance and burn. Post-Merge execution-layer issuance is zero, while
consensus issuance remains and EIP-1559 burn reduces supply. Validator rewards,
penalties/slashing and protocol upgrades affect the accounting path.

However, the official execution JSON-RPC documentation inspected here does not
provide a protocol-native `total ETH supply` scalar analogous to an ERC-20
`totalSupply()` field. Ethereum.org's supply page points users to external
tracking tools for current supply rather than defining a historical canonical
checkpoint scalar that can simply be queried and proven as the value known at a
specific 2024 decision date.

Therefore the frozen normalized series:

`total_fee_paid_wei / ETH_supply`

still requires an admissible starting supply checkpoint.

### 4.1 Why a modern provider scalar is not sufficient

A modern dashboard/API value or historical backfill:
- can be revised;
- does not by itself prove historical publication/version time;
- does not establish the exact scalar available to a strategy at the frozen date;
- would violate the existing YATL rule that historical queryability is not PIT
  availability.

It cannot silently become the authoritative denominator.

### 4.2 What first-principles reconstruction would require

Without an admitted starting checkpoint, exact supply reconstruction would require
a materially broader accounting chain, including historically correct protocol
semantics across relevant eras, issuance and burn and consensus balance changes,
with upgrade boundaries and validation.

For the post-Dencun track, reconstructing an exact starting scalar at
`2024-03-14T00:00:00Z` from first principles is not a small source audit. It would
require substantial historical chain/state reconstruction or acceptance of an
external checkpoint whose PIT provenance has not been established.

That crosses the stated stop condition.

### 4.3 Work gate deliberately not crossed

A genesis/long-history reconstruction, large consensus/execution acquisition, or
large transformation pipeline would be `WORK_REQUIRED`.

This unit does **not** open that gate because the new Director stop rule explicitly
requires MECH-024 to close rather than expand indefinitely when denominator
provenance requires disproportionate reconstruction.

Disposition:

`SUPPLY_DENOMINATOR = BLOCKED_DATA / FINITE_PIT_CHECKPOINT_NOT_ESTABLISHED`.

## 5. Deduplication / simpler explanation

MECH-024 remains one paid-blockspace-demand mechanism.

Do not split:
- execution fees;
- base-fee burn;
- blob fees;
- blob-fee burn;
- total burn

into independent economic edges.

The exact normalized `Fees/Supply` hypothesis is also scientifically weaker than
it first appears unless it eventually demonstrates incremental information over
simpler raw fee/activity controls. ETH supply changes much more slowly than daily
fee demand, so normalization may add little incremental state while greatly
increasing provenance cost. This is a pre-outcome complexity objection, not a
performance conclusion.

No raw-fee candidate is created as a rescue. Replacing the blocked denominator
after seeing this blocker would be a new hypothesis requiring separate bounded
justification and deduplication.

## 6. ECONOMIC_RELEVANCE_PRE_OUTCOME

Status:

`PLAUSIBLY_MONETIZABLE_IF_EDGE_EXISTS`

This status applies to the **economic paid-blockspace-demand mechanism**, not to
an authorized strategy and not to the blocked normalized dataset.

Pre-outcome economic profile:

- plausible monetization path:
  use a finalized, lagged Ethereum demand-state observation only as a state input
  for future Spot ETH long/cash allocation or gating;
- expected holding horizon:
  daily-to-multi-day, because the measurement is frozen on complete UTC days;
- expected opportunity frequency:
  potentially daily state availability, before any filter;
- likely turnover:
  potentially low-to-moderate if the state is persistent; no threshold is
  authorized yet;
- execution sensitivity:
  lower than high-frequency order-flow mechanisms because action would occur only
  after day close/finality;
- fee/slippage sensitivity:
  must still be charged, but execution is not intrinsically microsecond/queue
  sensitive;
- liquidity/capacity:
  ETH Spot is the intended execution domain; at `$10,000` or `$100,000`
  capital this mechanism is not obviously capacity-limited by its measurement
  design alone, subject to the later selected venue, participation and cost model;
- YATL transferability:
  structurally compatible with Spot / long-cash / no leverage / no short;
- economic caveat:
  compatibility and capacity plausibility do not establish directional edge.
  The supply-normalized specification is not worth expensive reconstruction before
  any evidence that the normalization itself adds information beyond simpler
  paid-blockspace activity.

No ROI, expectancy, return or dollar-profit estimate is made.

## 7. Money / capital evidence requirements if ever reopened

If future **new evidence** supplies a valid denominator checkpoint and Director
reopens the mechanism, preregistration must define before outcomes how to measure:

- after-cost expectancy versus CASH / simple Spot baseline;
- incremental value over raw fee/activity controls;
- turnover and exposure;
- opportunities available / computable / accepted / delayed / skipped;
- completed trades and missed moves;
- fee, spread and slippage;
- opportunity cost;
- drawdown;
- capital/capacity behavior at least around `$10k` and `$100k`;
- whether execution costs dominate any observed gross effect.

No such evidence is read in this unit.

## 8. Stop decision

The finality blocker is closable.

The supply denominator blocker is not closed by a finite, low-cost PIT protocol.
Closing it would require exactly the disproportionate reconstruction path that the
Director's MECH-024 stop rule forbids from becoming another audit chain.

Therefore:

`IEI-MECH-024 = BLOCKED_DATA / ECONOMIC_TEST_NOT_AUTHORIZED`

and:

`NORMALIZED_FEES_SUPPLY = NOT_PREREGISTRATION_READY`.

No AF-04A preregistration, AF-04B implementation, Development test, OOS access or
Forward work is authorized from MECH-024.

No additional MECH-024 audit should be created unless **new external evidence**
materially changes the denominator-provenance premise, such as a verifiable
contemporaneous supply checkpoint with sufficient version/provenance guarantees.

## 9. Did this materially advance the mechanism?

**YES.**

It moved MECH-024 from:

`METHOD_SPECIFIED / BLOCKED_SUPPLY_CHECKPOINT_PROVENANCE / FINALITY_RULE_NEEDS_PROTOCOL_FREEZE`

to the terminal pre-performance state:

`BLOCKED_DATA / ECONOMIC_TEST_NOT_AUTHORIZED`.

That is a valid research outcome under the bounded funnel and prevents further
research sprawl.

## 10. Expected next state / next allowed action

MECH-024 is closed for now.

The next allowed Research action is **not another ETH audit**.

Because the Research branch is 99 commits behind current `main`, the next
mechanism-selection step should first perform a bounded current-main readiness and
deduplication check against:
- current AF-01C historical-universe status;
- current MCF-PROD-001 / MCF families;
- any newer execution/cost/statistical contracts;

then choose the next already-committed bounded mechanism by information gain.

That future readiness check is expected to be `CHAT_DIRECTOR` if kept to a
small number of current-main artifacts.

If it instead requires bulk migration, historical acquisition or large
transformation, stop before execution at the mandatory Work gate.

No next work unit is executed automatically here.

## 11. Closeout

- Work Unit ID: `RIE-006-IEI-ETH-SUPPLY-FINALITY-PROVENANCE-AUDIT-001`
- execution mode: `CHAT_DIRECTOR`
- authoritative current main at start:
  `f3803ebe0bd9ec43f71940d463098fde58aa4d1d`
- starting Research HEAD:
  `a2e230b32257bc7c82be3b25a0aeb02154f474b5`
- branch: `research-institutional-edge-intelligence`
- PR #152: OPEN / DRAFT / UNMERGED
- branch lineage: DIVERGED / 19 ahead / 99 behind current main
- exact blocker addressed:
  finite finality + supply-denominator feasibility for MECH-024
- blocker closed:
  finality/day-close protocol
- blocker remaining:
  supply denominator PIT checkpoint/provenance
- stop condition triggered:
  YES — resolving denominator requires disproportionate reconstruction or
  unverifiable/third-party checkpoint assumptions
- terminal mechanism state:
  `BLOCKED_DATA / ECONOMIC_TEST_NOT_AUTHORIZED`
- ECONOMIC_RELEVANCE_PRE_OUTCOME:
  `PLAUSIBLY_MONETIZABLE_IF_EDGE_EXISTS`
- candidate registered: NO
- performance evidence: NOT READ
- tests: source/protocol audit only; no code test
- Fresh OOS: SEALED / NOT READ
- recent reserve: SEALED / NOT READ
- P10: UNTOUCHED / NOT READ / NOT WRITTEN
- P11: LOCKED
- Research bounded-scope status: YES
- next allowed action:
  bounded current-main readiness/deduplication check before selecting the next
  already-committed mechanism
- merge status: NO

**MERGED=NO**
