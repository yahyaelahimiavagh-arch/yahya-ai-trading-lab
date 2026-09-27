# RIE-005 — Generation-2 Reproduction Queue

Status: **PREREGISTERED BEFORE GEN-2 STRATEGY OUTCOMES**

Purpose: turn literature hypotheses into exact, point-in-time, cost-aware YATL
specifications without choosing the order from backtest outcomes.

## Queue A — simple / deterministic first

1. `RIE-CAND-0011` — crypto-specific risk-managed momentum.
2. `RIE-CAND-0022` — realized-volatility structure + normalized momentum
   regime detector.
3. `RIE-CAND-0027` — downside-volatility exposure scaling.
4. `RIE-CAND-0030` — crypto momentum stop-loss overlay.
5. `RIE-CAND-0025` — classic momentum volatility scaling baseline.

Queue A exists to answer a narrow question: can a simple, explainable,
point-in-time control layer address the HSSE-005 regime weakness without
starving the strategy?

## Queue B — complexity only after Queue A evidence

6. `RIE-CAND-0028` — bounded 3-state crypto HMM.
7. `RIE-CAND-0029` — 4-state predictor-rich NHHM.
8. `RIE-CAND-0031` — alternate dynamic momentum timing.

Queue B is not allowed to pre-empt Queue A merely because it is more flexible.

## Reproduction gate for every candidate

Before any Development search, the reproduction packet must record:

- immutable or content-addressed source identity when available;
- exact signal/equation definitions;
- all lookbacks and estimator windows;
- decision timestamp and lag rules;
- state initialization/update rules;
- missing-data behavior;
- source transaction-cost assumptions;
- YATL fee/slippage adaptation;
- source-vs-YATL discrepancies;
- bounded parameter domain;
- number of trials implied by that domain;
- explicit no-lookahead tests.

If exact source details are inaccessible, the candidate stays `NEW` /
`PENDING_BYTES`. Missing details are never guessed.

## Availability skip rule

A candidate may be temporarily bypassed only for a documented source-access or
reproducibility blocker discovered before any candidate performance run. Such a
bypass does not change its priority based on trading results and does not
promote a later candidate.

## Combination lock

No two Queue A/B candidates may be combined until each component has been
tested standalone under a preregistered Development protocol. A combination is
a new candidate with a new trial budget, not a free extension.

## Evidence boundary

- HSSE-005 failures are known diagnostics and may motivate the research
  question, but exact HSSE-005 event outcomes cannot be used to choose candidate
  parameters.
- 2023-2024 is no longer blind for Generation 2.
- 2025-2026 Audit Holdout and recent reserve remain sealed until a new protocol
  assigns them.
- P10 remains independent and untouched.
- P11 remains locked.
