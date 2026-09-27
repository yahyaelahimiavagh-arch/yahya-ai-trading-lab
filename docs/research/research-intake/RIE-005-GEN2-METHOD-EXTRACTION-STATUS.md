# RIE-005 — Generation-2 Method Extraction Status

Status: **ACTIVE / GEN2-001 CLOSED NEGATIVE / GEN2-002 PREREGISTERED / NO GEN2-002 PERFORMANCE RUN**

The preregistered reproduction queue is being executed in order. Candidates may
be bypassed only for a source-access/reproducibility blocker discovered before
any performance run.

## Current queue state

| Candidate | State | Reason |
|---|---|---|
| RIE-CAND-0011 | BLOCKED | Exact risk-scaling method/code not fully exposed; source bytes unfrozen. |
| RIE-CAND-0022 | BLOCKED | Exact SSRN equations/thresholds unavailable in current environment; source bytes unfrozen. |
| RIE-CAND-0027 | BLOCKED | Downside-volatility concept visible, but exact real-time estimator/scaling specification incomplete. |
| RIE-CAND-0030 | CANONICAL COMPLETE / 0 PROPOSALS | GEN2-001 ran exactly once on its registered Development evidence and remains negative evidence. |
| RIE-CAND-0025 | METHOD EXTRACTED / GEN2-002 PREREGISTERED / RUN NOT STARTED | Core 126-session inverse-volatility method and 12% annualized target are exact enough; YATL requires an explicit no-leverage 24/7 crypto adaptation. |

No blocked candidate is rejected. Queue order has not changed because of trading
performance. `RIE-CAND-0025` is reached only after the registered GEN2-001 result
for `0030`.

## RIE-CAND-0025 exact-method finding

The source method is sufficiently specified for the core risk-scaling rule:

- risk input: daily returns of the unscaled WML momentum strategy;
- estimator: previous six months / 126 trading sessions;
- source variance forecast:
  `sigma_hat_sq_t = 21 * sum_{j=0}^{125}(r_WML,d_{t-1-j}^2) / 126`;
- scaled return:
  `r_scaled_t = (target / sigma_hat_t) * r_WML_t`;
- target: 12% annualized volatility;
- update frequency: monthly;
- only lagged realized returns enter the estimate.

This is **not** a source replication inside YATL. The paper is an equity
long-short/self-financing construction and can use scale weights above one.
YATL is BTCUSDT/ETHUSDT long-only Spot with no leverage. The author page lists
an official replication package, but its bytes are not frozen in the current
evidence store.

The registered object is therefore
`GEN2-ADAPT-0002-VOL-SCALING`, explicitly classified as a
`YATL_INTERNAL_ADAPTATION`.

## GEN2-002 frozen adaptation

Before any performance outcome, GEN2-002 freezes:

1. all six HSSE-004A survivors as reference strategies, unchanged;
2. one scaler only: source target 12%, no alternate target/window/EWMA trials;
3. 183 completed UTC crypto days and 365-day annualization as the explicit
   24/7 analogue of the source six-month/126-session estimator;
4. monthly scale updates using only data completed before the UTC month boundary;
5. `scale = min(1, 0.12 / sigma_ann)` — hard no-leverage cap, no short;
6. cost-bearing month-boundary quantity rebalances while directional
   entry/exit logic remains untouched;
7. base costs 10 bps fee + 5 bps adverse slippage and stress costs 20 + 10 bps;
8. six strategies × (control + scaler) = 12 registered conditions total;
9. Development warm-up from 2020-01-01, scored range from 2020-08-01 through
   2023-01-01 exclusive;
10. a fixed opportunity-preservation gate: same directional entry/trade counts,
    full active-time preservation, and at least 25% aggregate notional exposure
    versus control.

The 25% notional floor is a YATL engineering viability gate, not a source
parameter. It is frozen before outcomes to reject a nominally active but
economically starved scaler.

## Next engineering gate

No GEN2-002 market performance run is authorized yet.

Next: implement the deterministic scaler/rebalance runner and protocol-specific
tests. Only after that implementation has a Final HEAD with passing CI may the
single registered Development run execute. A failure may not be rescued by
changing the 12% target, the 183-day window, the cap, or the opportunity floor
on the same evidence.

P10 remains untouched. 2023-2024 known diagnostics are not used for GEN2-002
selection. Fresh OOS and recent reserve remain sealed. P11 is locked.
`LIVE_MASTER_LOCK=OFF`; no AI direct execution.
