# P9 — Telegram notification implementation plan

Status: **P8 RUNTIME ACCEPTED / CLOSED — P9-001 CURRENT CANDIDATE**

Entry baseline: P8 runtime accepted and squash-merged at checkpoint
`fe973e8f55f0fb1d7a76015a0e3d0d043e278f2e`. Matching final-head GitHub Actions
run `35534981625` passed both jobs, the **1139/1139** complete suite and
**32/32** focused P8-010 tests.

## Purpose

P9 adds a minimum-sufficient **read-only notification / alert surface** for YATL
so accepted, sanitized upstream status can reach an operator without turning
Telegram into a trading or administration console.

The first delivery target is outbound information only. P9 may eventually send
system status, data-quality alerts, Paper trade lifecycle notifications, Paper
signal/candidate notifications, risk/drawdown alerts, periodic summaries and
P10 forward-validation status/results. Those messages must remain descriptive,
provenance-bound and non-executable.

P9 is deliberately small so P10 Forward/Paper Validation on new data is not
delayed by chat UI, bot-command features or unrelated automation.

## Non-negotiable boundaries

- PAPER ONLY and `LIVE_MASTER_LOCK=OFF`.
- NO FUTURES, NO MARGIN, NO LEVERAGE, NO SHORT.
- NO WITHDRAWAL API.
- NO TRADE PERMISSION and NO ORDER ENDPOINTS.
- NO AI DIRECT EXECUTION.
- Telegram is not an execution console, BUY/SELL command surface or Live-control
  surface.
- P9 may not create or mutate `RiskAuthorization`, approved quantity, intent,
  order, fill, portfolio or Kill Switch authority.
- P9 may not optimize strategies or change strategy parameters.
- P9 may not upgrade current P3 evidence; candidates remain
  `INSUFFICIENT_EVIDENCE`.
- Only accepted/sanitized upstream status or alert material may be projected into
  notification content.
- Credentials, API keys, Telegram Bot tokens, chat identifiers, local source
  paths, raw private account payloads and unsanitized model/provider text may not
  enter notification payloads or evidence.
- Inbound Telegram commands, callback actions, polling receivers and webhook
  receivers are outside the minimum P9 scope unless a later plan revision is
  explicitly justified and independently audited. The current plan does not
  require them.
- Any Telegram transport introduced later must be **outbound-only**, narrowly
  allowlisted, bounded and unable to call execution/account/risk-authority paths.
- No dependency change unless a checkpoint explicitly requires and audits it.
- P9 completion is engineering/observability acceptance only; it does not prove
  profitability or open P11.

## Delivery sequence

### P9-001 — Notification policy and immutable contracts

Define frozen `P9_NOTIFICATION_V1` policy plus canonical immutable contracts for
accepted source identity, notification category/severity, information-only
messages and bounded batches.

This checkpoint is intentionally **offline**:
`transport_mode=NONE`; no Telegram API request, Bot token, Chat ID, inbound
update, command, webhook, polling receiver or network capability exists.

Required categories are fixed for future use:

- system status;
- data-quality alert;
- Paper trade lifecycle;
- Paper signal/candidate;
- risk/drawdown alert;
- periodic summary;
- P10 forward-validation status.

Acceptance: deterministic canonical reconstruction/SHA-256, bounded text/batch,
fixed PAPER/Live-lock/evidence labels, schema-smuggling rejection, secret/URL/
authority-text rejection and source scan proving no transport, execution,
account, risk-authority or provider capability.

### P9-002 — Accepted upstream projection and deterministic formatter

Project only accepted/sanitized upstream records into P9-001 contracts. Define
explicit adapters for the minimum status/alert material actually available from
closed upstream phases. Preserve source hashes and event time; do not invent
profitability, freshness, trade authority or missing values.

Render a deterministic bounded plain-text Telegram-safe message from the canonical
notification contract. Formatting is presentation only and remains offline.

Acceptance: exact provenance conservation, point-in-time/event-time checks,
deterministic formatting, bounded output, escaping and no authority/evidence
upgrade.

### P9-003 — Outbound-only Telegram transport

Add one narrowly allowlisted Telegram Bot API send path for already validated
P9 messages. This is the first checkpoint allowed to load a dedicated Bot token
and destination identifier at the transport boundary.

The transport is send-only: no `getUpdates`, webhook receiver, callback handler,
command parser or execution/control endpoint. Secrets are never printed, stored in
evidence or included in exceptions.

Acceptance: exact host/method/path allowlist, TLS, timeout/response-size bounds,
redirect/proxy restrictions, stable redacted errors, mocked transport tests and
no execution/account/risk imports.

### P9-004 — Delivery guard, deduplication and bounded retry

Add deterministic delivery identity, duplicate suppression and conservative retry/
rate-limit handling around P9-003. A notification may be retried safely but may
not mutate upstream state or create a control loop.

Acceptance: idempotency, bounded retry/backoff, rate-limit behavior, restart-safe
delivery state if persistence is required, redacted failures and unchanged
notification/source identity.

### P9-005 — Guarded notifier runner and adversarial notification matrix

Expose a minimal noninteractive notifier runner for accepted notifications and run
a fixed adversarial matrix covering source tampering, evidence upgrade, command/
authority injection, secret leakage, URL/markup injection, duplicate delivery,
cross-symbol material and transport-response corruption.

No operator command surface is added.

Acceptance: exact fail-closed outcomes, deterministic replay, canonical evidence,
stable exit codes and no upstream mutation.

### P9-006 — Independent final audit

Independently recompute the P9 policy, source/message identities, delivery
boundaries, adversarial outcomes and source safety. P9 closes only after a matching
final-head GitHub Actions run passes and the checkpoint is explicitly approved
and merged.

## AI direction after the baseline

P9 does not expand the AI pipeline.

A future YATL AI Analyst / Decision-Support layer may evaluate technical analysis,
candles/price action, volume/order flow, news/sentiment, macro/fundamental context,
regime state and proposals such as ENTER / SKIP / WAIT / EXIT CANDIDATE.

The permanent rule is **NO AI DIRECT EXECUTION**. An AI model never receives an
order endpoint, trade permission, RiskAuthorization mutation or quantity
authority.

P10 must first measure the non-AI baseline on new/forward data. AI may enter a
later decision pipeline only if its incremental value versus that baseline is
demonstrated with evidence, preferably out-of-sample/forward evidence, under the
same risk and cost controls.

## Economic gate preserved

P9 does not change the project objective:

- Profitability > Complexity.
- Evidence > Number of analyses.
- OOS/Forward evidence > attractive backtest.
- Risk-adjusted persistence > raw profit.
- One profitable edge > many unproven signals.

P10 remains the economic gate. Primary evidence is Net PnL after fees/slippage on
new data together with drawdown, sample size, consistency, regime stability,
failure/recovery behavior and risk controls. If P10 does not confirm an acceptable
edge, P11 stays locked and the project returns to research/strategy iteration.

## Exit condition

P9 is complete only when accepted/sanitized YATL status and alert material can be
delivered through a bounded outbound-only Telegram path while attempts to inject
commands, authority, credentials, unsupported evidence or upstream mutation fail
closed.

P9 completion does not grant TRADE permission, does not open Live, does not change
`INSUFFICIENT_EVIDENCE` and does not prove strategy profitability.
