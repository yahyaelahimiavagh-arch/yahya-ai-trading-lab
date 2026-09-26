# RIE-002 — English/Chinese Research Sweep #001

Status: **SOURCE DISCOVERY COMPLETE / REPRODUCTION PENDING**

This sweep registers 24 research candidates from 20 public sources. It is an
idea-discovery artifact only. No source performance claim is YATL evidence.

## Scope

- English research: academic/published/working-paper sources covering
  time-series momentum, volume-weighted momentum, trend, breakout, reversal,
  low-volatility selection, volatility-managed momentum, regime filters and
  candlestick predictors.
- Chinese research/community sources: FMZ material covering dual-MA trend,
  sub-10-second trade-flow trend and multi-exchange lead/lag.
- Current lifecycle for every candidate: `NEW`.
- Source bytes are not yet frozen; therefore none may be marked
  `REPRODUCIBLE` or `READY_FOR_TRAIN_SEARCH`.

## Candidate allocation

- `RIE-CAND-0001..0016`: English academic/research hypotheses.
- `RIE-CAND-0017..0019`: Chinese FMZ hypotheses.
- `RIE-CAND-0020..0024`: additional reproducibility/regime/pattern hypotheses.

The canonical machine-readable records are in
`CANDIDATE-REGISTRY-v0.1.0.json`.

## Next gate — RIE-003

For a candidate to leave `NEW`, RIE-003 must:
1. freeze source bytes or an exact immutable source snapshot and SHA-256;
2. extract exact signal equations/rules and timing semantics;
3. identify source data/universe and survivorship assumptions;
4. reconstruct cost and execution assumptions;
5. bind code/notebook to an exact immutable revision when available;
6. document leakage and multiple-testing risks;
7. reject unsupported or non-reproducible claims rather than filling gaps by guess.

Only then can a candidate become `REPRODUCIBLE`; only a fully specified,
cost-aware candidate can become `READY_FOR_TRAIN_SEARCH`.

P10 remains untouched and P11 remains locked.
