# CRL-007 — Severity model and random windows

Goal: reduce narrative bias and make stress intensity comparable.

Research a versioned S1–S5 severity model from predeclared market measurements:
- return magnitude/speed;
- realized volatility;
- jump/gap behavior;
- volume anomaly;
- spread/liquidity degradation when valid data exists;
- optional cross-asset dislocation in a separately sourced extension.

Also create reproducible random historical windows using a frozen seed/selection
rule and fixed window lengths.

No severity threshold may be tuned after seeing final strategy outcomes.

Exit gate: frozen severity version + random-window registry + reproducible selection
evidence.
