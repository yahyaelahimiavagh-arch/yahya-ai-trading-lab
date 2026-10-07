# RIE-006 — IEI-MECH-002 AF-04A Exact Preregistration v1.0

Status: **FROZEN BEFORE PERFORMANCE / PERFORMANCE NOT AUTHORIZED**

Date: 2026-10-07

Execution route: `CHAT_DIRECTOR` under `EXECUTION-MODE-MATRIX-v1.0`.

## Authoritative starting refs

- current `main`: `58b6c74a834d51f0d68e06fbe5f1885057e9df9a`
- Research branch starting HEAD: `f5e71ee7a8183bf04522a97e2a688bb9704618df`
- PR #152: OPEN / DRAFT / UNMERGED
- predecessor: `RIE-006-IEI-MECH-002-CURRENT-MAIN-DEDUPE-002.md`
- predecessor disposition: `AF-04A_PREREGISTRATION_READY / PERFORMANCE_NOT_AUTHORIZED`

No candidate return, PnL, Sharpe, drawdown, outcome ranking, Fresh OOS, recent reserve, P10, crisis, Forward or sealed evidence was read to choose this protocol.

## 1. Safety and evidence boundary

PAPER / RESEARCH ONLY. `LIVE_MASTER_LOCK=OFF`. Spot long/cash only. No Futures execution, leverage, short, Live/order endpoint or AI execution authority. P10 is neither read nor written. P11 remains locked. No broad RIE-006 sweep is restarted. Existing negative evidence remains binding, including the failed/blocked COT PIT provenance path and unresolved MECH-021 PIT label/snapshot blocker.

This document freezes the candidate protocol only. It does not authorize AF-04B implementation or any performance run.

## 2. Economic fingerprint and taxonomy

Frozen fingerprint:

`PIT-eligible Spot cross-section | completed historical same-weekday observations only | cross-sectional weekday ranking | long/cash allocation | lagged admitted price + frozen monthly membership`

The mechanism remains in existing TIME/RELATIVE mechanism space. It does not create a new Alpha Factory family and must not inflate mechanism counts.

## 3. Decision clock and information set

For calendar day `D`, the decision clock is `D 00:00:00 UTC`.

Only information whose completed observation and eligibility/publication state is known strictly before that clock may be used. The day being decided, any later bar, revised future label, future membership, future delisting knowledge, or future source repair is forbidden.

Daily observations are formed from completed UTC calendar days only. AF-04B must derive a daily close deterministically from admitted completed-bar Spot data without reading outcomes during protocol selection. No same-day partial observation may enter the score.

## 4. PIT universe and membership

Eligibility for day `D` is bound to the accepted frozen MCF-PROD-001 monthly ordinary-Spot membership applicable at the decision clock.

Rules:
- use only membership known/frozen for that month;
- never backfill, carry forward, repair or infer an empty/source-gap month after outcome observation;
- delisted/failed assets remain governed by their contemporaneous PIT eligibility rather than modern survivor lists;
- a symbol without the required admitted price history is ineligible for ranking that day;
- membership gaps and price-data gaps are recorded, not imputed.

## 5. Frozen same-weekday score

For each eligible symbol and decision day `D`:

1. identify the weekday of `D` in UTC;
2. walk backward through prior completed calendar observations having exactly that weekday;
3. use at most the most recent **52** valid same-weekday observations;
4. require at least **26** valid same-weekday observations for that symbol;
5. define each historical observation as that completed UTC day's simple close-to-close return using only then-admitted price data;
6. score the symbol by the arithmetic mean of those valid historical same-weekday returns.

No winsorization, volatility scaling, exponential weighting, median substitution, outlier deletion, regime filter, symbol-specific window, or alternate score is permitted in v1.0.

## 6. Cross-sectional ranking and deterministic ties

A decision day requires at least **4** score-valid PIT-eligible symbols.

Rank score-valid symbols from highest to lowest frozen score. Ties are resolved deterministically by ascending symbol identifier; no outcome-aware tie handling is permitted.

The selected long set is the top quartile of score-valid symbols, with count:

`max(1, floor(N / 4))`

where `N` is the number of score-valid symbols on that decision day.

Selected symbols receive equal target weight. All unselected capital remains cash. No short leg is allowed.

## 7. Holding/rebalance rule

The mechanism is evaluated at the daily UTC decision clock. The target basket is recomputed once per UTC day from information eligible at that clock.

AF-04B must use YATL's existing deterministic next-primary-open execution convention for entries/exits and may not introduce same-bar fills or candidate-specific execution timing.

If a symbol loses eligibility or leaves the selected set at the next decision, the target becomes cash for that allocation at the next permitted execution reference.

## 8. Costs

The base implementation is bound to the existing YATL P2 `BacktestSpec` defaults and exact Decimal cost accounting:

- fee: **10 bps per fill side**;
- adverse slippage: **5 bps per fill side**;
- execution policy: `NEXT_PRIMARY_OPEN`.

AF-04B must reuse the canonical cost machinery rather than implement candidate-specific cost arithmetic. No fee/slippage value may be selected from MECH-002 outcomes.

Any later stress-cost analysis is a separately preregistered robustness unit and cannot rescue a failed canonical result.

## 9. Missing data and opportunity-starvation accounting

Every UTC decision day must receive exactly one primary opportunity state:

- `OPPORTUNITY_AVAILABLE`
- `EMPTY_PIT_MEMBERSHIP`
- `MEMBERSHIP_SOURCE_GAP`
- `INSUFFICIENT_HISTORY`
- `INSUFFICIENT_CROSS_SECTION`
- `PRICE_DATA_GAP`

The implementation must preserve calendar denominators and report explicit zero-opportunity periods. Missing/source-gap periods are not successful avoidance, not cash alpha, and not silently removed from opportunity counts.

When multiple failures could apply, AF-04B must implement and test one deterministic precedence order before any performance execution; the precedence may affect only diagnostic labeling, never whether an otherwise invalid day becomes tradable.

## 10. Frozen comparators

The standalone falsification packet must include these prespecified non-promoting comparators using the same admissible universe/clock/cost discipline where applicable:

1. **CASH** — no exposure.
2. **EQUAL_WEIGHT_PIT_CROSS_SECTION** — equal-weight all score-valid PIT-eligible symbols.
3. **DETERMINISTIC_SHUFFLED_WEEKDAY_CONTROL** — deterministic placebo weekday mapping fixed by implementation/test fixture before outcomes.
4. **PREVIOUS_DAY_RETURN_RANK** — rank the same eligible cross-section by prior completed UTC day's return, using the same top-quartile long/cash construction.

Comparator results cannot be promoted automatically into new candidates. A comparator that looks better is falsification/diagnostic evidence only and requires a new preregistration before any candidate treatment.

## 11. One-shot / no-retune boundary

After the first candidate outcome is exposed, the following are immutable for this evidence set:

- UTC decision clock and daily aggregation;
- 52-observation maximum lookback;
- 26-observation minimum history;
- PIT membership binding;
- minimum cross-section of 4;
- arithmetic-mean score;
- top-quartile selection rule;
- deterministic tie rule;
- equal weighting;
- long/cash construction;
- missing-data and source-gap policy;
- cost binding;
- comparator definitions.

No grid search, parameter sweep, symbol-specific tuning, threshold rescue, alternative weekday definition, post-hoc outlier removal, relabeling, or retry on the same evidence is allowed.

If implementation reveals a structural ambiguity that cannot be resolved without changing economic behavior, stop before performance, record `PREREGISTRATION_IMPLEMENTATION_BLOCKED`, amend only through a new version, and preserve this v1.0 unchanged.

## 12. AF-04B acceptance contract

AF-04B may implement only this frozen rule and deterministic tests. Before any canonical Development outcome, tests must demonstrate at minimum:

- no future membership/price access;
- correct UTC weekday selection;
- 52/26 history bounds;
- deterministic ties;
- minimum cross-section behavior;
- exact top-quartile count;
- equal-weight long/cash behavior;
- source-gap/empty-month fail-closed behavior;
- explicit opportunity-state accounting;
- canonical next-open fill binding;
- canonical fee/slippage binding;
- deterministic comparator construction.

AF-04B is `WORK_REQUIRED` and cannot begin without the exact mandatory Work gate warning and execution in Work mode.

## 13. Disposition

`IEI-MECH-002 = AF-04A_PREREGISTERED / AF-04B_NOT_STARTED / PERFORMANCE_NOT_AUTHORIZED`

No merge is authorized by this document.

**MERGED=NO**
