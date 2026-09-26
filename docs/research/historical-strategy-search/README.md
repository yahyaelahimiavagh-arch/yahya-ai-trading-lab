# YATL Historical Strategy Search Engine (HSSE)

HSSE is the controlled search layer between Research Intake and future
historical/forward qualification. It exists to search broadly without turning
historical holdouts into tuning surfaces.

## HSSE-001 — Search Protocol & Data Boundaries

Canonical protocol:

`docs/research/historical-strategy-search/HSSE-001-SEARCH-PROTOCOL-v0.1.0.json`

Validate:

```bash
uv run --locked python -m research.historical_strategy_search.protocol validate \
  --protocol docs/research/historical-strategy-search/HSSE-001-SEARCH-PROTOCOL-v0.1.0.json
```

### Historical evidence partitions

- **Development:** 2020-01-01 → 2023-01-01. This period has already been exposed
  by HSL. It is explicitly allowed for search and development CV and can never
  be described as fresh OOS again.
- **Blind OOS:** 2023-01-01 → 2025-01-01. Structurally acquired/validated only
  until HSSE-004. Strategy outcomes, returns and plots are forbidden before the
  survivor set is frozen.
- **Final historical audit:** 2025-01-01 → 2026-07-01. Remains sealed until
  HSSE-006 and is never a tuning surface.
- **Recent reserve:** 2026-07-01 onward. Not used by HSSE-001 through HSSE-006.

Warmup acquisition may precede an analysis boundary, but scored decisions may
not cross the registered boundary.

### Search budget

The first-generation ceiling is:
- maximum 8 eligible strategy families;
- maximum 5,000 trials per family;
- maximum 20,000 trials total;
- every failed/duplicate/executed trial counts;
- the budget cannot be increased after outcomes are observed.

This is a ceiling, not a target. A source grid larger than its budget must have
a deterministic reduction/hierarchical search registered before execution.

### Development survivor gate

Search is not allowed to select only by raw PnL. Development survivors must
satisfy sample, positive net-after-cost PnL, positive expectancy, profit factor,
cross-fold stability, drawdown, concentration, doubled-cost stress and
parameter-neighborhood robustness requirements.

Ranking is Pareto-first, then deterministic lexicographic tie-breaking.
Maximum 3 survivors per family and 12 total may be frozen for Blind OOS. These
are caps, not quotas.

### No holdout recycling

After the survivor freeze:
- parameters cannot change before Blind OOS;
- Blind OOS runs exactly once for the frozen generation;
- a Blind OOS failure is retained and cannot be repaired by retuning on that
  same period;
- the final audit holdout is used only after HSSE-004 and cannot select or tune
  the survivor.

P10 is not read or mutated. P11 remains locked.

## HSSE-002 — Deterministic Search Runner

The first frozen search plan is
`HSSE-002-TREND-MA-SEARCH-PLAN-v0.1.0.json`.

SMA, EMA and DEMA are three independent multiple-testing families. Each family
searches the exact public-code step-10 grid `range(1,1000,10)` with
`n1<n2`: 4,950 trials per family and 14,850 total.

The entire search is Development-only. Binary64 is permitted only for this
high-throughput discovery layer; every proposed survivor must be independently
recomputed with canonical exact accounting in HSSE-003 before survivor freeze.
Paper-reported returns remain external context and never become YATL evidence.
