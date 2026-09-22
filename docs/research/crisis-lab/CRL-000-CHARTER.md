# CRL-000 — Charter and isolation

Status: **ACCEPTED — 2026-09-22**

Goal: freeze the research boundary before data collection.

## Required invariants

- **RESEARCH ONLY.**
- Active P10 candidate/configuration, gate registry, sealed window, fee/slippage,
  risk thresholds and evidence remain byte-for-byte untouched.
- P11 remains locked.
- No TRADE permission, exchange-order endpoint, quantity authority or AI direct
  execution.
- Findings may only inform a future, separately versioned research/candidate
  iteration after the active P10 experiment has completed under its own gates.
- Development, named blind-holdout, random-window and synthetic evidence stay
  separate.
- Negative results are never deleted, hidden, relabeled or converted into a
  different evidence class.
- News, macro labels, event names and AI output are metadata only in this track
  and are not inputs to the v0.1 decision path.

## P10 isolation inventory

The audit of `main` at
`8f47fefb0dc05a1cd3f3c9d5a65a4377d54c2b60` confirms the production forward
collector owns:

- `/var/lib/yatl/p10/p10-forward.sqlite3`;
- `/var/lib/yatl/p10/snapshot.json`;
- the accepted P10 candidate/gate/window chain documented in
  `docs/P10-OPERATIONS.md`.

Crisis Lab runtime data is isolated under `data/research/crisis-lab/` and is
already excluded by the root `/data/` gitignore rule.

A Crisis Lab acquisition/replay process must fail closed if an input/output path
resolves inside `/var/lib/yatl/p10/`, or if it is asked to mutate a P10
candidate, registration, database, snapshot or evidence artifact. Copying P10
runtime evidence into the research corpus is also prohibited.

Production YATL modules must not import from `research/crisis_lab/`. Research
code may reuse documented contracts only through an explicitly versioned
research adapter in a later checkpoint; it must not create a write path back to
production validation state.

## Holdout boundary

"Blind holdout" in CRL-001 means **blind to BTCUSDT/ETHUSDT outcomes and YATL
replay results after registration**, not that the public identity of a named
historical event is secret.

For named holdouts:
- event identity, source and timestamp metadata may be visible;
- no BTC/ETH return summary, plot, strategy result or parameter choice may be
  derived from the holdout before final evaluation;
- structural acquisition/quality checks may run non-interactively and may expose
  only metadata such as row counts, gaps and digests;
- holdout OHLCV values must not be used to design thresholds.

CRL-007 must additionally create reproducible random windows, including a
stronger sealed subset whose identities are not used for strategy design.

## Timestamp and leakage boundary

- "First publicly knowable" means the earliest retained, source-verifiable
  timestamp found for the **specific catalogued event/milestone**.
- If only a date, approximate time or conflicting source time exists, uncertainty
  is recorded explicitly; precision is never invented.
- An event with unresolved timestamp conflict can be acquired but is not
  replay-eligible until the conflict is resolved.
- Window lengths come from predeclared templates and may not be trimmed to later
  BTC/ETH highs, lows, liquidation points, drawdown extrema or recovery dates.
- Event labels are unavailable to the trading decision engine during replay.
- Later-edited articles/post-mortems may document a historical timestamp, but
  their later knowledge cannot enter the decision stream.

## CRL-000 audit result

No blocking defect was found in the original charter. This revision makes the
already intended isolation enforceable/auditable by explicitly documenting:
P10-owned runtime paths, holdout access, timestamp uncertainty, no-write rules
and the v0.1 exclusion of News/Macro/AI from the decision path.

Exit gate:
1. directory structure accepted — **PASS**;
2. research evidence taxonomy frozen — **PASS**;
3. P10 isolation checks documented — **PASS**;
4. CRL-001 event/data work may begin — **PASS**.
