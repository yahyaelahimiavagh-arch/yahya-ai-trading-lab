# YATL Research Intake Engine (RIE)

Status: **RIE-001 IMPLEMENTATION CANDIDATE**

RIE converts external research into explicit, provenance-bound research
candidates. It does **not** trust reported performance and it has no execution,
risk, quantity, P10, P11, or Live authority.

## RIE-001 — Candidate Registry

The canonical registry is:

`docs/research/research-intake/CANDIDATE-REGISTRY-v0.1.0.json`

Validate it with:

```bash
uv run --locked python -m research.research_intake.registry validate \
  --registry docs/research/research-intake/CANDIDATE-REGISTRY-v0.1.0.json
```

Each candidate records:
- source identity, tier, language, type, title, HTTPS provenance URI and authors;
- technique family, market scope and timeframe;
- a falsifiable hypothesis plus extracted entry/exit/stop/sizing/lookback rules;
- source-reported cost assumptions and performance claims as **untrusted metadata**;
- implementation availability;
- known limitations and leakage risks;
- lifecycle status and explicit duplicate linkage.

## Source tiers

- **A — Research-grade:** strong academic / methodological source with clear
  method and preferably reproducible material.
- **B — Reproducible implementation:** inspectable repository/notebook with
  explicit strategy logic and provenance.
- **C — Idea mining:** public strategy libraries, lectures, transcripts and
  community material. Useful for hypothesis generation only.

Source tier is not a performance score and cannot promote a strategy.

## Deduplication

RIE computes a deterministic fingerprint from strategy logic and market scope,
excluding source title and reported performance. Repeated hypotheses must be
retained as `DUPLICATE` and linked to the first matching candidate. They may
not be silently reintroduced under a new source or name.

## Status lifecycle

`NEW → REPRODUCIBLE → READY_FOR_TRAIN_SEARCH`

Alternative terminal research statuses:
- `DUPLICATE`
- `REJECTED_SOURCE`

`READY_FOR_TRAIN_SEARCH` requires explicit entry/exit rules and cost
assumptions. It still grants no historical qualification or Forward authority.

## Isolation

RIE validation:
- performs no network calls;
- reads no credentials;
- writes nothing to P10;
- never creates Strategy Evidence;
- never creates trade/order/quantity/risk authority;
- leaves P11 locked.

External claims become YATL evidence only after independent YATL testing through
the later HSSE / OOS / Crisis / Forward pipeline.
