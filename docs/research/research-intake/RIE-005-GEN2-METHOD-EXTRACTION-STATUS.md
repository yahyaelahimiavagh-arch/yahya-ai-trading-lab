# RIE-005 — Generation-2 Method Extraction Status

Status: **ACTIVE / GEN2-001 CLOSED NEGATIVE / GEN2-002 CLOSED INVALIDATED / AF-03A COMPLETE / RIE-CAND-0027 METHOD SPECIFIED**

The preregistered reproduction queue is executed in order. A candidate may be
temporarily bypassed only for a documented source-access/reproducibility blocker
discovered before any performance run. A later candidate does not permanently
inherit priority from that bypass.

## Current queue state

| Candidate | State | Reason |
|---|---|---|
| RIE-CAND-0011 | BLOCKED_REPRODUCIBILITY | Conventional crypto momentum construction is exposed, but this paper's exact risk-scaling implementation is still not sufficiently bound to reproduce without importing assumptions from another source. |
| RIE-CAND-0022 | BLOCKED_SOURCE | Three regime concepts are exposed, but exact RV horizons, normalized-momentum equation, thresholds and update semantics remain unavailable. |
| RIE-CAND-0027 | METHOD_SPECIFIED / NEXT ELIGIBLE | Full source text exposes downside-volatility equations, lag semantics and real-time expanding-window scaling. YATL adaptation protocol is still required before any performance run. |
| RIE-CAND-0030 | CANONICAL COMPLETE / 0 PROPOSALS | GEN2-001 executed exactly once on registered Development evidence and remains negative evidence. |
| RIE-CAND-0025 | CANONICAL INVALIDATED / 0 PROPOSALS | GEN2-002 was invalidated before economic evaluation due structurally incomplete frozen 183-day estimator windows; no rescue is allowed on the same evidence. |

AF-03A closeout:
`docs/research/research-intake/AF-03A-SOURCE-UNBLOCK-SPRINT-v0.1.0.md`

## RIE-CAND-0027 exact-method finding

Source:
Feifei Wang and Xuemin Sterling Yan,
*Downside risk and the performance of volatility-managed portfolios*,
Journal of Banking & Finance 131 (2021) 106198.

Author-hosted full text:
`https://www.lehigh.edu/~xuy219/research/Downside.pdf`

The source computes:

`sigma_Total,t = sqrt(sum_j f_j^2)`

`sigma_Down,t = sqrt(sum_j f_j^2 * I[f_j < 0])`

where `f_j` is a daily return inside month `t`.

If fewer than three negative daily returns occur in month `t`, downside
volatility is computed using negative daily returns from both month `t` and
month `t-1`.

The downside-volatility-managed portfolio is:

`f_Down_sigma,t = c_tilde* / sigma_Down,t-1 * f_t`

so the managed month-`t` return uses only lagged downside volatility.

The paper's real-time construction uses:
- an initial `K = 120 months` training period;
- an expanding estimation window;
- before each out-of-sample month, a real-time scaling parameter estimated from
  the prior training sample so original and managed portfolios have equal
  estimated volatility over that training sample.

The source also studies fixed relative weights (10%, 25%, 50%, 75%, 90%)
between unmanaged and volatility-managed portfolios to reduce estimation-risk
instability.

## YATL boundary for 0027

The exact source method is now sufficiently exposed to remove the original
reproducibility blocker, but this does **not** authorize Development performance.

A new YATL internal adaptation must be preregistered before any outcome. It must
freeze at minimum:
- crypto sampling/calendar mapping;
- downside-volatility estimator window;
- update boundary;
- no-leverage cap;
- quantity/rebalance semantics;
- missing-data behavior;
- base/stress costs;
- opportunity-preservation gates;
- bounded comparison set.

The source is monthly equity-factor/anomaly evidence and may imply leverage.
YATL remains BTCUSDT/ETHUSDT long-only Spot, no leverage, research only.

## Queue consequence

Because `RIE-CAND-0027` was bypassed only while blocked and is now
`METHOD_SPECIFIED`, it becomes the **next eligible Queue-A candidate**.

`RIE-CAND-0028` (3-state HMM) remains Queue B and must not pre-empt 0027 merely
because 0027 was previously blocked.

## Next allowed action

Prepare a fresh preregistered YATL adaptation protocol for
`RIE-CAND-0027`.

No performance run is authorized until:
1. the adaptation choices are frozen before outcomes;
2. deterministic implementation/tests exist;
3. Final HEAD CI is green.

P10 remains untouched. Fresh OOS and recent reserve remain sealed.
P11 remains locked. `LIVE_MASTER_LOCK=OFF`.
