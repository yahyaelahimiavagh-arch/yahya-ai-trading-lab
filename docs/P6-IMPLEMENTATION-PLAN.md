# P6 — AI Analyst implementation plan

Status: **P6-001 / P6-002 / P6-003 / P6-004 / P6-005 / P6-006 / P6-007 / P6-008 / P6-009 / P6-010 RUNTIME ACCEPTED / MERGED — PHASE CLOSED**

Entry baseline: P5 runtime accepted and merged at checkpoint
`cd5ff5651e2d1df509dba6de8bc717a3ba7bf34f`. Final P5 Actions run
`35449752993` passed **524/524** complete tests and the independent final audit.

## Purpose

P6 adds a structured AI-analysis layer for research and operator decision support.
It is **not** an execution layer. AI output can describe market context, summarize
evidence, identify uncertainty and recommend `NO_TRADE`/further review, but it
cannot create a P5 execution decision, RiskAuthorization, quantity, order, fill or
permission change.

## Non-negotiable boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF`.
- NO FUTURES, NO MARGIN, NO LEVERAGE, NO SHORT.
- NO WITHDRAWAL API.
- NO TRADE PERMISSION and NO ORDER ENDPOINTS.
- NO AI DIRECT EXECUTION.
- P6 may not import or call P5 executor/journal/order/fill/portfolio write paths.
- P6 may not manufacture or modify P4 `RiskAuthorization`.
- Current strategies remain `INSUFFICIENT_EVIDENCE`; AI cannot upgrade that label.
- Analysis inputs must be point-in-time and provenance-bound.
- Model/provider text is untrusted input and must pass exact schema validation.
- Secrets, credentials, account identifiers and raw private account payloads are
  outside P6 evidence and prompts.
- No dependency or network/provider integration is added unless a later P6
  checkpoint explicitly requires and separately audits it.

## Delivery sequence

### P6-001 — Analyst policy and immutable contracts

Define a frozen analysis-only policy and canonical records for analyst input,
evidence references and output. Output must distinguish facts, derived observations,
uncertainty and unsupported claims. The only operator-facing disposition is
`NO_TRADE`, `REVIEW` or `INSUFFICIENT_DATA`; none is executable.

Acceptance: deterministic construction/reconstruction, canonical SHA-256,
invalid-field rejection and source scan proving no execution import/capability.

Accepted: PR #30 was squash-merged at
`0b2fe2768cf355faba173a3498b48b359a5a04a0` after matching final-head Actions
run `35450498559` passed both jobs, the **542/542** complete suite, **18/18**
focused P6-001 tests, the safety scan and deterministic analyst runtime. P6-001
remains analysis-only and grants no execution, quantity, RiskAuthorization or
trade authority.

### P6-002 — Point-in-time evidence bundle

Build a read-only evidence bundle from accepted public market data, P3 strategy
evidence and P4/P5 safety status. Inputs are timestamp-bound and provenance-bound;
future data, mutable ambient state and raw credentials are forbidden.

Acceptance: future-isolation, missing/stale evidence, cross-symbol mismatch and
canonical bundle digest tests.

Accepted: PR #31 was squash-merged at
`75749bb0cf28d366cea1045cceadb8c4841567ca` after matching final-head Actions
run `35451469100` passed both jobs, the **560/560** complete suite, **18/18**
focused P6-002 tests, the strengthened safety scan and deterministic evidence
runtime. P3 remained `INSUFFICIENT_EVIDENCE` for both current strategy
candidates. P6-002 remains read-only and grants no execution, quantity,
RiskAuthorization or trade authority.

### P6-003 — Deterministic analyst baseline

Create a non-AI deterministic baseline that turns the evidence bundle into a
structured analysis record. This baseline is the safety/reference implementation
against which later model output is checked.

Acceptance: deterministic replay, conservative uncertainty behavior and
`INSUFFICIENT_EVIDENCE` preservation.

Accepted: PR #32 was squash-merged at
`0c0b018d45c1205f75aa0a33bec360209cccc60a` after matching final-head Actions
run `35457822009` passed both jobs, the **575/575** complete suite, **15/15**
focused P6-003 tests, the analyst safety scan and deterministic baseline runtime.
The accepted baseline preserved `INSUFFICIENT_EVIDENCE`, produced five grounded
claims and conservatively resolved to `REVIEW`. It grants no execution, quantity,
RiskAuthorization, order, provider/network or trade authority.

### P6-004 — Model request boundary

Define the provider-neutral request envelope and prompt/materialization boundary.
No provider call is required yet. Inputs must be bounded, redacted and generated
only from the accepted evidence bundle.

Acceptance: prompt injection strings remain inert data, bounded size, deterministic
materialization and no secret/environment access.

Accepted: PR #33 was squash-merged at
`0a5a3ddf209938cfd33e65064fae146682519e9e` after matching final-head Actions
run `35467414835` passed both jobs, the **592/592** complete suite, **17/17**
focused P6-004 tests, the analyst safety scan and deterministic request runtime.
The accepted request boundary keeps provider-like material offline with
`transport=NONE`, treats bundle strings as `UNTRUSTED_DATA_ONLY`, preserves
`INSUFFICIENT_EVIDENCE`, and grants no execution, quantity, RiskAuthorization,
order, credential, network or trade authority.

### P6-005 — Strict model-response schema

Parse model output as untrusted data. Reject unknown fields, executable commands,
quantities, credentials, URLs/actions and malformed or over-sized responses.

Acceptance: adversarial response matrix, canonical validated output and
fail-closed fallback to `INSUFFICIENT_DATA`.

Accepted: PR #34 was squash-merged at
`760ceaa38d2f6be94994ac5e69fd97e738000903` after matching final-head Actions
run `35495765457` passed both jobs, the **615/615** complete suite, **23/23**
focused P6-005 tests, the analyst safety scan and adversarial response runtime.
P6-005 accepts only the exact bounded response schema, binds canonical accepted
output to the reconstructed `AnalystReport`, preserves explicit uncertainty, and
fails every rejected model response closed to `INSUFFICIENT_DATA`. It grants no
execution, quantity, RiskAuthorization, order, credential, network or trade
authority.

### P6-006 — Claim/evidence grounding gate

Every factual or derived claim must point to evidence IDs from the accepted bundle.
Unsupported claims, contradictions, stale evidence or invented identifiers fail
closed and cannot be promoted to operator guidance.

Acceptance: exact grounding tests and deterministic rejection reasons.

Accepted: PR #35 was squash-merged at
`8ae58c2a0ca712fed0d2246930b7e3afb0d2435a` after matching final-head Actions
run `35498896415` passed both jobs, the **636/636** complete suite, **21/21**
focused P6-006 tests, the analyst safety scan and deterministic grounding runtime.
P6-006 verifies exact claim vocabulary, evidence layer, point-in-time state,
symbol/reference identity and current request/bundle binding. Unsupported,
contradictory, invented, stale, future or altered evidence remains fail-closed to
`INSUFFICIENT_DATA`, while grounded output remains `REVIEW` because P3 is
still `INSUFFICIENT_EVIDENCE`. It grants no execution, quantity,
RiskAuthorization, order, credential, network or trade authority.

### P6-007 — Analyst journal and reproducible trace

Persist canonical analysis input/output evidence locally for audit without storing
secrets or mutable provider internals. Duplicate replay is idempotent.

Acceptance: transaction rollback, duplicate replay, reopen and tamper tests.

Accepted: PR #36 was squash-merged at
`a40f9907c9a4dbf63cb4054ced62ec44ee2bc5af` after matching final-head Actions
run `35502217491` passed both jobs, the **655/655** complete suite, **19/19**
focused P6-007 tests, the analyst safety scan and deterministic journal runtime.
P6-007 stores only sanitized, canonical, hash-bound analysis traces in local
SQLite; duplicate replay is idempotent, transaction failure rolls back, reopen is
stable and durable row/JSON tampering fails closed. Raw model response text,
`canonical_response_json`, credentials and mutable provider internals are not
journaled. It grants no execution, quantity, RiskAuthorization, order, network or
trade authority.

### P6-008 — Guarded analyst CLI

Add bounded local commands for building evidence, validating a response and viewing
a sanitized analysis report. No command accepts exchange credentials, endpoint URLs
or execution permissions.

Acceptance: stable exit codes, bounded output, noninteractive behavior and source
scans.

Accepted: PR #37 was squash-merged at
`41bc429f4c48d582747ed94d9a26e12bf5e27ecd` after matching final-head Actions
run `35502932218` passed both jobs, the **677/677** complete suite, **22/22**
focused P6-008 tests, the analyst safety scan and guarded CLI runtime. P6-008
exposes only three bounded local commands—`evidence`, `validate`, and `show`—
with deterministic bounded JSON, stable exit codes and noninteractive behavior.
Rejected arguments and paths are not echoed, oversized response text remains a
P6-005 fail-closed outcome, and no credential, endpoint, environment, provider,
network, execution, quantity, RiskAuthorization, order or trade control is added.

### P6-009 — Adversarial analyst matrix

Run fixed scenarios for prompt injection, unsupported certainty, fabricated
evidence, stale/future inputs, schema smuggling, executable-action requests and
provider-response corruption for BTCUSDT and ETHUSDT.

Acceptance: two byte-identical runs, exact fail-closed outcomes and published
canonical evidence.

Accepted: PR #38 was squash-merged at
`9ece941fe79139d55c5c349c3774720563a4ef28` after matching final-head Actions
run `35503798774` passed both jobs, the **690/690** complete suite, **13/13**
focused P6-009 tests, byte-identical dual matrix generation and the analyst safety
scan. P6-009 published 16 canonical artifacts across eight scenarios and two
symbols with index SHA-256
`a5a09bdde1600c706bdc3665b46f334ae04fd5fc4fe364613cc9ed7913018524`.
Prompt injection remained inert untrusted data; every remaining adversarial case
failed closed at the exact evidence/response/grounding boundary. P3 remained
`INSUFFICIENT_EVIDENCE`, and no raw provider text, credentials, provider/network,
execution, quantity, RiskAuthorization, order or trade authority was added.

### P6-010 — Independent final audit

Independently recompute P6 policy, evidence bundles, adversarial outcomes, source
safety and accepted artifacts. P6 closes only after matching final-head GitHub
Actions pass.

Accepted: PR #39 was squash-merged at
`f07f2209cac5b46be8f9d74da2d162925ed8ab65` after matching final-head Actions
run `35504753305` passed both jobs, the **703/703** complete suite, **13/13**
focused P6-010 tests, source safety, exact-outcome checks and replay equality.
The independent audit froze/recomputed the analyst policy digest
`355ad5a2ed274878db4c9a56e15b14548ee6ba0c16016c7cc3b04b02120bbe44`,
the two-symbol evidence manifest digest
`93dd09b73d439ed60b781f38783f2fb716689210ad66fb7ed5a395ed7b5b5f0f`
and the accepted P6-009 index digest
`a5a09bdde1600c706bdc3665b46f334ae04fd5fc4fe364613cc9ed7913018524`.
It independently verified all 17 accepted evidence files and all eight exact
adversarial outcomes for both symbols. P6 is closed; P7 may open only with the
same safety locks preserved.

## Exit condition

P6 is complete only when an analyst can consume accepted point-in-time evidence and
produce a deterministic, auditable, grounded **analysis-only** record while every
attempt to create executable authority, quantity, order capability or unsupported
certainty fails closed.

P6 completion does not grant TRADE permission, does not open P11, and does not
change the P3 evidence label.
