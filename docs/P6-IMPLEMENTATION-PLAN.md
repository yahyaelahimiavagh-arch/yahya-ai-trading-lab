# P6 — AI Analyst implementation plan

Status: **P6-001 / P6-002 / P6-003 RUNTIME ACCEPTED / MERGED — P6-004 CURRENT CANDIDATE**

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

Current candidate: branch `p6-004-model-request-boundary` adds an offline,
provider-neutral request envelope generated solely from an accepted P6-002 evidence
bundle. Fixed analyst instructions are code-owned and never derived from evidence;
bundle strings are serialized only beneath an explicit `UNTRUSTED_DATA_ONLY`
material boundary. Material is canonical JSON with a fixed byte ceiling, digest
binding and allowlisted accepted evidence only. The envelope declares
`transport=NONE` and has no provider, network, environment, credential, account,
execution, quantity, RiskAuthorization, order or trade capability. Matching
final-head GitHub Actions evidence is required before P6-004 can be accepted.

### P6-005 — Strict model-response schema

Parse model output as untrusted data. Reject unknown fields, executable commands,
quantities, credentials, URLs/actions and malformed or over-sized responses.

Acceptance: adversarial response matrix, canonical validated output and
fail-closed fallback to `INSUFFICIENT_DATA`.

### P6-006 — Claim/evidence grounding gate

Every factual or derived claim must point to evidence IDs from the accepted bundle.
Unsupported claims, contradictions, stale evidence or invented identifiers fail
closed and cannot be promoted to operator guidance.

Acceptance: exact grounding tests and deterministic rejection reasons.

### P6-007 — Analyst journal and reproducible trace

Persist canonical analysis input/output evidence locally for audit without storing
secrets or mutable provider internals. Duplicate replay is idempotent.

Acceptance: transaction rollback, duplicate replay, reopen and tamper tests.

### P6-008 — Guarded analyst CLI

Add bounded local commands for building evidence, validating a response and viewing
a sanitized analysis report. No command accepts exchange credentials, endpoint URLs
or execution permissions.

Acceptance: stable exit codes, bounded output, noninteractive behavior and source
scans.

### P6-009 — Adversarial analyst matrix

Run fixed scenarios for prompt injection, unsupported certainty, fabricated
evidence, stale/future inputs, schema smuggling, executable-action requests and
provider-response corruption for BTCUSDT and ETHUSDT.

Acceptance: two byte-identical runs, exact fail-closed outcomes and published
canonical evidence.

### P6-010 — Independent final audit

Independently recompute P6 policy, evidence bundles, adversarial outcomes, source
safety and accepted artifacts. P6 closes only after matching final-head GitHub
Actions pass.

## Exit condition

P6 is complete only when an analyst can consume accepted point-in-time evidence and
produce a deterministic, auditable, grounded **analysis-only** record while every
attempt to create executable authority, quantity, order capability or unsupported
certainty fails closed.

P6 completion does not grant TRADE permission, does not open P11, and does not
change the P3 evidence label.
