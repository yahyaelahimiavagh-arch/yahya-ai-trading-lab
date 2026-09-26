# RIE-004 — Generation-2 Risk/Regime Literature Sweep

Status: **SOURCE DISCOVERY COMPLETE / REPRODUCTION PRIORITIZATION ACTIVE**

Canonical Generation-2 registry snapshot: `CANDIDATE-REGISTRY-GEN2-v0.1.0.json`.
The historical `CANDIDATE-REGISTRY-v0.1.0.json` remains byte-immutable because HSSE-002 binds its Git blob SHA.

Trigger: HSSE-005 produced a canonical 0/6 crisis/regime pass result for the
Generation-1 MA-trend survivors. This sweep does not retune those survivors.
It searches for independently motivated control layers and alternative
hypotheses that can seed a new research generation.

## Core finding from literature

The literature is not unanimous. Momentum/trend crash risk is state dependent,
and several papers report benefits from volatility- or regime-managed exposure,
but broader real-time/OOS studies show that total-volatility management is not
universally beneficial. Crypto-specific studies also report severe tail risk
that can persist even after volatility scaling.

Therefore YATL treats every paper as hypothesis input, not evidence.

## Priority lanes

### Lane A — simple exposure control
- Existing `RIE-CAND-0011`: crypto risk-managed momentum.
- New `RIE-CAND-0025`: momentum-specific lagged-volatility scaling.
- New `RIE-CAND-0027`: downside-volatility scaling.
- Existing `RIE-CAND-0022`: realized-volatility structure + normalized momentum.

### Lane B — panic/crash protection
- New `RIE-CAND-0026`: lagged drawdown + volatility panic state.
- New `RIE-CAND-0030`: stop-loss overlay.

### Lane C — explicit regime models
- New `RIE-CAND-0028`: bounded 3-state crypto HMM.
- New `RIE-CAND-0029`: 4-state NHHM / predictor-rich regime model.

### Lane D — alternative momentum timing
- New `RIE-CAND-0031`: dynamic time-series momentum / online turning condition.

## Contradictory / falsification sources retained

These are mandatory controls, not inconvenient exceptions:

1. Cederburg, O'Doherty, Wang & Yan (2020), *On the performance of
   volatility-managed portfolios*: broad real-time/OOS evidence is mixed and
   warns that ex-post spanning-regression weights are not implementable.
2. Grobys et al. (2025), *Cryptocurrency momentum has (not) its moments*:
   volatility management can reduce crash severity in some crypto constructions
   while extreme tail risk can remain very large.
3. Hurst, Ooi & Pedersen (2017), *A Century of Evidence on Trend-Following
   Investing*: diversified long/short multi-asset trend often performs well in
   crises; YATL must not assume this transfers to BTC/ETH long-only Spot.

## Generation-2 ordering

1. Reproduce the simplest point-in-time candidates first:
   `0011`, `0022`, `0025`, `0027`, `0030`.
2. Only if simple layers fail to explain/improve the weakness should HMM/NHHM
   complexity (`0028`, `0029`) enter controlled Development.
3. Candidate `0031` is an alternate signal-timing hypothesis, not a risk layer,
   and must be evaluated separately before combinations.
4. No combinations are permitted until individual components have standalone
   Development evidence.
5. HSSE-005 units may be used as Development diagnostics in Generation 2 only
   after a new protocol explicitly reclassifies them; they can never again be
   called blind.
6. 2025-2026 Audit Holdout and the recent reserve remain sealed until a new
   preregistered Generation-2 evaluation protocol defines their role.

## Safety / evidence boundary

- Research only.
- No P10 read/write.
- No P11 unlock.
- No live authority.
- No paper claim is YATL strategy evidence.
- No retuning of the failed Generation-1 six.
