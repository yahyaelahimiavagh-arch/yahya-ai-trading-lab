# P5 — Local Paper execution, reconciliation and recovery plan

Status: **P5-001 TO P5-003 RUNTIME ACCEPTED AND MERGED — P5-004 UNOPENED**

Entry baseline: P4 runtime accepted and merged in checkpoint `f3a5575`; the
authoritative documentation closeout is `c0d94d2`. The complete baseline suite
contains 401 tests. P5 may begin only from that exact baseline.

Exit condition: a deterministic local Paper executor consumes only a complete P4
`RiskAuthorization`, applies at most one local effect for each authorization,
persists and reconstructs its state, reconciles orders/fills/portfolio projections
before becoming ready after startup, and fails closed on every ambiguous recovery
condition. P5 acceptance cannot grant exchange TRADE permission.

## Fixed boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF` remain hard invariants.
- P5 begins with **local Paper execution only**. Spot Testnet remains limited to
  the existing read-only account request; no order request is permitted.
- No Short, Margin, Futures, leverage, withdrawal, broker, exchange-order endpoint
  or permission-changing request may be added.
- Strategies and AI cannot call the executor. The only admissible execution input
  is a complete, reconstructable P4 `RiskAuthorization`.
- Exact approved quantity is immutable. P5 cannot size, increase or substitute it.
- Current accepted strategy candidates remain `INSUFFICIENT_EVIDENCE`; therefore
  they cannot create a Paper entry. Qualified inputs are engineering fixtures only.
- Recovery readiness starts fail closed. No exposure-increasing Paper effect is
  permitted until deterministic reconciliation evidence is accepted.
- The accepted P2 fill, cost and portfolio rules are reused rather than duplicated.
- Financial values remain validated plain decimal strings and deterministic
  `Decimal` arithmetic. No float or implicit rounding is permitted.
- No credential, `.env`, account client or external execution transport belongs in
  `yatl/execution`.
- No new dependency is planned. `uv.lock` must remain unchanged.

## Delivery sequence

### P5-001 — Local Paper contracts and recovery boundary

Define frozen policy, recovery-readiness evidence and immutable execution decisions.
Bind each decision to the complete P4 authorization with canonical SHA-256. A
qualified P4 approval remains blocked during fail-closed startup and becomes only a
local Paper authorization after reconciliation evidence is present. Rejected or
insufficient-evidence entries never carry quantity or an executable action.

Acceptance: focused unit tests, deterministic offline CLI, full regression suite,
compile/whitespace/lock checks and restricted-source scans proving no credential,
account client, network transport or exchange-order endpoint in the P5 package.

Local evidence: **PASS, 2026-09-13.** Thirteen focused P5-001 tests and the complete
suite passed **414/414**. `paper-execution-contract-check` deterministically recorded
`startup=BLOCKED/RECOVERY_NOT_READY`,
`candidate=BLOCKED/RISK_NOT_APPROVED`, qualified fixture
`entry=ACCEPT_LOCAL_PAPER`, exact quantity `18.894653` and decision SHA-256
`4de1cda05b4dd3778e5dd18e1b8f633b76e77e8ba0572e6d1e4ce2e819c51f05`.
Compile, whitespace, lock and restricted-source scans passed; `uv.lock` remained
unchanged. Final-HEAD GitHub Actions run `34782981428` passed both jobs on commit
`b665f2b`, including **414/414** complete tests, **13/13** focused tests, the P5
runtime and safety scan. PR #14 was squash-merged at checkpoint
`557747194fe8cdda75704d1bc3d067901f184450`. P5-001 is runtime accepted and merged;
P5-002 subsequently opened and completed as recorded below.

### P5-002 — Transactional intent journal and idempotency

Persist accepted local intents in a transactional SQLite journal using the standard
library. Enforce one durable effect identity per authorization SHA-256 and export a
canonical JSON evidence view. Duplicate delivery returns the existing result and
cannot create a second effect.

Acceptance: transaction rollback, uniqueness, canonical export, reopen and
concurrent-attempt tests; SQLite binary bytes are not treated as deterministic
evidence.

Local candidate evidence: **PASS, 2026-09-14.** Twelve focused tests and the
complete suite passed **426/426**. Tests cover rollback after an injected
post-insert failure, exactly one effect under four concurrent duplicate attempts,
same-authorization conflict, reopen, sorted canonical export, schema drift and
tamper detection. `paper-execution-journal-check` recorded one effect, identical
retry/reopen, exact quantity `18.894653`, intent SHA-256
`206920d659e27113762959457eb88e7124582eb365963694fbd70c56af4e620a` and canonical
evidence SHA-256
`fd7aa4412b9c2fd6b10a5167465aae27bee0d515cf02cf8e7112ea435b881cb6`.
Compile, whitespace, lock and restricted-source scans passed; no dependency or
`uv.lock` change exists. Final-HEAD GitHub Actions run `34899971951` passed both
jobs on commit `b498759`, including **426/426** tests and all runtime, safety,
replay and audit gates. PR #16 was squash-merged at checkpoint
`ab9d38a55688f772c2c7ca166584e0978fd6163d`; P5-002 is runtime accepted and
merged, and P5-003 subsequently opened and completed below.

### P5-003 — Local Paper order state machine

Implement explicit local-only lifecycle transitions for accepted Paper intents.
Reject impossible, skipped, duplicate, stale or out-of-order transitions without
mutating durable state. The model must not contain a venue endpoint or remote-order
transport.

Acceptance: transition table tests, monotonic sequence/time, immutable reason codes,
hash-chained events and atomic failure behavior.

Accepted evidence: **PASS, 2026-09-15.** Fourteen focused tests and the
complete suite passed **440/440**. The only lifecycle is `PENDING_LOCAL` →
`ACTIVE_LOCAL` → `CANCELLED_LOCAL`; impossible, skipped, duplicate, stale,
out-of-order and tampered transitions fail closed without durable mutation. Event
and projection writes are atomic, and replay verifies the event SHA-256 chain and
materialized state. `paper-order-state-check` recorded three events, replay
equality, final-state SHA-256
`a5d3bbee2a561b5a195ef92e3c6c5a08f3442a2e91bc0fe2c25d54bbdbdb9796` and
canonical evidence SHA-256
`6364285fae61a03cacde2f20bf5e42a0c6f4f7e674b387c76a68973dee8f25fe`.
Compile, whitespace, lock and restricted-source scans passed; no dependency or
`uv.lock` change exists. Implementation-head GitHub Actions run `35029425081`
passed both jobs on commit `fbca913`. Final-HEAD run `35029938678` passed both jobs
on commit `f52b0ff`, including **440/440** tests and all runtime, safety, replay and
audit gates. PR #18 was squash-merged at checkpoint
`c96293f038436258a30c9030cbce778750180c1f`; P5-003 is runtime accepted and
merged. P5-004 remains unopened. No fill, credential, external transport, TRADE
permission or order endpoint was added.

### P5-004 — Accepted P2 fill and cost integration

Route an accepted local intent through the existing P2 next-candle, conservative
same-bar, volume, fee and slippage contracts. P5 must not reimplement alternative
fill economics.

Acceptance: exact P4 quantity reaches P2; missing/open/future/gapped fill candles,
volume breaches and cost-policy mismatches fail atomically.

### P5-005 — Atomic fill and portfolio projection

Apply local order event, fill identity, cash, asset, position and realized-PnL
projection in one transaction. A retry cannot apply the same fill twice and an
incomplete projection cannot be visible.

Acceptance: hand-calculated entry/exit vectors, duplicate fill rejection, rollback
at each write boundary and exact reconciliation with accepted P2 portfolio results.

### P5-006 — Startup reconciliation

Independently replay the journal and compare canonical order, fill and portfolio
state with materialized state. The executor remains unavailable until the complete
comparison passes.

Acceptance: clean rebuild, empty-store startup, stale materialization, missing or
extra event, digest mismatch and unsupported schema tests.

### P5-007 — Snapshot and fail-closed recovery

Introduce versioned snapshots as rebuild accelerators, never as authority. Validate
the snapshot and replay the journal tail. Corruption, truncation, gaps, changed
policy, ambiguous commit outcome or unknown state enters `RECOVERY_REQUIRED`; no
automatic reset or guessed repair is permitted.

Acceptance: crash-point matrix, snapshot deletion/rebuild, corrupt tail, policy
drift, manual-confirmation boundary and repeatable recovery evidence.

### P5-008 — Guarded local runner and operator CLI

Add bounded local commands for status, reconciliation check and explicit recovery.
Outputs are sanitized, deterministic JSON/text with stable exit codes. Commands may
not accept secrets, endpoint URLs, arbitrary imports or exchange permissions.

Acceptance: ready/not-ready/stale/corrupt states, non-interactive behavior, bounded
output and command source scans.

### P5-009 — Deterministic adversarial execution matrix

Replay duplicate, crash, stale authorization, out-of-order event, journal/snapshot
corruption, missing fill candle, cost mismatch and uncertain-state cases for
BTCUSDT and ETHUSDT. Build the complete matrix twice and compare canonical evidence
byte for byte.

Acceptance: fixed scenario ordering, exact expected decisions, atomic state checks,
two identical runs and published evidence index SHA-256.

### P5-010 — Independent final audit and checkpoint

Independently validate the frozen P5 policy, reconstruct all local state from the
journal, recompute evidence digests and adversarial outcomes, and run every safety
and regression gate. P5 is accepted only at final HEAD after all jobs pass.

Acceptance: complete suite, focused P5 suite, locked dependency sync, compile and
whitespace gates, restricted-source scans, two-run equality and independent audit.
P6 remains unopened and no TRADE permission is granted.

## Intended module boundaries

```text
yatl/execution/contracts.py       immutable P5 policy/readiness/decision records
yatl/execution/journal.py         transactional intent/event journal
yatl/execution/state.py           local Paper order state machine
yatl/execution/fills.py           guarded integration with accepted P2 fill rules
yatl/execution/portfolio.py       atomic Paper portfolio projection
yatl/execution/reconcile.py       independent startup reconciliation
yatl/execution/recovery.py        snapshot validation and explicit recovery
yatl/execution/runner.py          bounded local runner and operator status
yatl/execution/scenarios.py       deterministic adversarial matrix
yatl/execution/audit.py           independent final P5 acceptance gate
```

## Runtime evidence policy

Every checkpoint records its branch, commit, focused/full test counts, runtime
command result, GitHub Actions run, safety scan and deterministic digest in
`docs/STATUS.md`. Local success is implementation evidence only; acceptance requires
the matching final-HEAD GitHub Actions result. No checkpoint or phase is merged
without explicit user approval.

## External design inputs

The frozen provenance and allowed conceptual lessons are recorded in
[`OPEN-SOURCE-DESIGN-REFERENCES.md`](OPEN-SOURCE-DESIGN-REFERENCES.md). They are
references only: no source code is copied and no package is added.
