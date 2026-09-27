# AF-03A — Source Unblock Sprint — Closeout v0.1.0

Status: **COMPLETE / 1 UNBLOCKED / 2 BLOCKED / NO PERFORMANCE RUN**

Date: **2026-09-27**

Scope was intentionally bounded to the three preregistered blocked Queue-A
candidates:

- `RIE-CAND-0011`
- `RIE-CAND-0022`
- `RIE-CAND-0027`

No Development backtest, parameter sweep, Fresh OOS read, crisis adjudication,
Forward test, P10 read/write, or merge was performed.

## Decision summary

| Candidate | Closeout state | Decision |
|---|---|---|
| RIE-CAND-0011 | BLOCKED_REPRODUCIBILITY | Conventional crypto momentum construction is exposed, but the exact risk-scaling rule used by this paper is still not fully exposed in the accessible source surface. |
| RIE-CAND-0022 | BLOCKED_SOURCE | The abstract exposes the three regime concepts but not the exact short/long realized-volatility horizons, normalized-momentum equation, or regime thresholds. |
| RIE-CAND-0027 | METHOD_SPECIFIED | Full source text exposes the downside-volatility estimator, lag semantics, volatility-managed scaling equation, and real-time expanding-window construction. YATL adaptation still requires a new preregistered protocol. |

## RIE-CAND-0011 — remains blocked

Source:
- Ao Yang, *Cryptocurrency market risk-managed momentum strategies*,
  Finance Research Letters 85 (2025) 107879.
- Publisher URL:
  https://www.sciencedirect.com/science/article/pii/S1544612325011377
- DOI: 10.1016/j.frl.2025.107879

Accessible method details:
- weekly cross-sectional cryptocurrency momentum;
- 2-week cumulative-return formation;
- 1-week holding;
- weekly quintile sort;
- highest quintile Winner, lowest quintile Loser;
- value-weighted Winner-minus-Loser portfolio;
- weekly rolling rebalance;
- paper explicitly states adaptation of Barroso-Santa-Clara risk-managed momentum.

Remaining blocker:
- the accessible full-text surface does not expose enough of this paper's own
  risk-scaling implementation to bind the exact estimator horizon, target/scaling
  constant, update convention and any crypto-specific alterations without
  importing assumptions from a different paper.

Decision:
- `BLOCKED_REPRODUCIBILITY`;
- do not substitute the Barroso-Santa-Clara specification by assumption;
- do not create a Development protocol from the accessible evidence.

## RIE-CAND-0022 — remains blocked

Source:
- Kaustuv Banerjee, *Detecting Volatility Regimes in Crypto Markets using
  Realized Volatility Structure and Normalized Momentum*.
- SSRN abstract 5920642:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5920642
- Written 2025-12-14; posted 2026-01-13.

Accessible method details:
- strategy-agnostic regime detector;
- three states: Expansion / Neutral / Contraction;
- regime classification combines:
  - relationship between short-horizon and long-horizon realized volatility;
  - directional movement normalized relative to recent history;
- high-frequency BTC evidence over 2024 and 2025 YTD.

Remaining blocker:
- exact short-horizon RV window;
- exact long-horizon RV window;
- exact normalized-momentum equation;
- exact state thresholds/boundaries;
- state transition/update semantics.

Decision:
- `BLOCKED_SOURCE`;
- abstract-level description is insufficient for deterministic reproduction;
- no thresholds or equations may be guessed.

## RIE-CAND-0027 — unblocked at method level

Source:
- Feifei Wang and Xuemin Sterling Yan,
  *Downside risk and the performance of volatility-managed portfolios*,
  Journal of Banking & Finance 131 (2021) 106198.
- Publisher URL:
  https://www.sciencedirect.com/science/article/pii/S0378426621001576
- Author-hosted full text:
  https://www.lehigh.edu/~xuy219/research/Downside.pdf
- DOI: 10.1016/j.jbankfin.2021.106198

### Exact source estimator

For month `t`, using daily returns `f_j` in that month:

`sigma_Total,t = sqrt(sum_j f_j^2)`

`sigma_Down,t = sqrt(sum_j f_j^2 * I[f_j < 0])`

The source notes that if fewer than three negative daily returns occur in month
`t`, downside volatility uses negative daily returns over both month `t` and
month `t-1`.

### Exact source scaling

For the original portfolio return `f_t`:

`f_sigma,t = c* / sigma_(t-1) * f_t`

The downside-volatility-managed form is:

`f_Down_sigma,t = c_tilde* / sigma_Down,(t-1) * f_t`

Thus only volatility completed before the managed-return month enters the
scaler.

The paper prefers lagged realized volatility rather than variance because it
produces less extreme investment weights and lower turnover/trading cost.

### Source real-time construction

The source explicitly addresses the ex-post scaling-constant problem.

Real-time evaluation:
- initial training period: `K = 120 months`;
- expanding-window estimation;
- at the beginning of each out-of-sample month `t`, estimate the scaling
  parameter from the training period ending before month `t`;
- the scaling parameter is chosen so that the original and volatility-managed
  portfolios have the same estimated volatility over the prior training sample;
- real-time portfolio decisions then use only parameters available before the
  evaluation month.

The paper also evaluates fixed relative weights between unmanaged and managed
portfolios (10%, 25%, 50%, 75%, 90%) to reduce instability from estimated
optimal portfolio weights.

### What this does and does not unblock

This is enough to close the original source-method blocker:
- downside estimator is exact;
- lag is exact;
- managed-return equation is exact;
- real-time expanding-window construction is documented.

It is **not** an authorization to run YATL performance.

The source studies monthly equity factors/anomaly portfolios and allows
volatility-managed exposures that can imply leverage. YATL is long-only
BTCUSDT/ETHUSDT Spot with no leverage. Therefore a new YATL adaptation must
preregister, before any outcome:
- crypto sampling interval and calendar mapping;
- downside-volatility estimator window;
- update boundary;
- no-leverage cap;
- quantity/rebalance mechanics;
- missing-data behavior;
- transaction-cost mapping;
- opportunity-preservation gates;
- bounded comparison set against control and, if justified, total-volatility
  scaling.

No source-reported performance is YATL evidence.

## Queue consequence

The availability-skip rule says a blocked candidate can be bypassed temporarily
but its priority is not permanently changed by later outcomes.

Therefore:
- 0011 remains blocked;
- 0022 remains blocked;
- **0027 is now the next eligible Queue-A method for Generation-2
  specification**;
- Queue-B candidate 0028 must not pre-empt 0027 merely because 0027 was
  previously blocked.

## Evidence and safety state

- Fresh OOS: SEALED
- recent reserve: SEALED
- P10 read: false
- P10 write: false
- P11: LOCKED
- LIVE_MASTER_LOCK: OFF
- performance runs executed by AF-03A: 0
- merge authorization implied: false
