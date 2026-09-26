# RIE-005 — Generation-2 Method Extraction Status

Status: **ACTIVE / ZERO GEN-2 PERFORMANCE RUNS**

The preregistered reproduction queue is being executed in order. Candidates may
be bypassed only for a source-access/reproducibility blocker discovered before
any performance run.

## Current queue state

| Candidate | State | Reason |
|---|---|---|
| RIE-CAND-0011 | BLOCKED | Exact risk-scaling method/code not fully exposed; source bytes unfrozen. |
| RIE-CAND-0022 | BLOCKED | Exact SSRN equations/thresholds unavailable in current environment; source bytes unfrozen. |
| RIE-CAND-0027 | BLOCKED | Downside-volatility concept visible, but exact real-time estimator/scaling specification incomplete. |
| RIE-CAND-0030 | METHOD READY / PROTOCOL NOT FROZEN | 30% monthly stop rule and 10/20/30/40/50 robustness thresholds are publicly described. |

No blocked candidate is rejected. No later candidate is promoted because of
trading performance; there have been no Generation-2 performance runs.

## Next engineering gate

For RIE-CAND-0030, freeze before any market outcome:
1. stop measurement basis;
2. bar-trigger semantics;
3. execution timing;
4. small bounded threshold grid and total trial count;
5. costs/slippage;
6. trade-starvation/opportunity-preservation diagnostics;
7. Development-only data boundary.

P10 remains untouched. 2025-2026 holdout/recent reserve remain sealed. P11 is
locked.
