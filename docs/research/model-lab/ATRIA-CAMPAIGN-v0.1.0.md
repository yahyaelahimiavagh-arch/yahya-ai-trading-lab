# Atria Research Campaign Runner v0.1.0

Status: **IMPLEMENTED / FINAL-HEAD CI PENDING**

This layer orchestrates the accepted single-task Atria worker. It does not
change P6, P10, P11, strategy evidence, risk authority, or execution.

A campaign manifest contains 1–24 sorted tasks. Each task has:
- a fixed registered objective;
- 1–12 research-only JSON artifacts;
- a bounded output-token ceiling.

Hard campaign limits:
- maximum 24 tasks;
- maximum 131,072 requested output tokens per campaign;
- sequential execution only;
- no arbitrary prompt field;
- no P10 runtime root;
- no trade/order/quantity/risk authority.

## Plan first

```bash
uv run --locked python -m research.model_lab.atria_campaign plan \
  --runtime-root data/research/crisis-lab \
  --campaign docs/research/model-lab/my-campaign.json
```

Planning reads and validates artifacts but performs no network call and reads no
credential.

## Explicit run

```bash
export ATRIA_API_KEY='atr_...'

uv run --locked python -m research.model_lab.atria_campaign run \
  --runtime-root data/research/crisis-lab \
  --campaign docs/research/model-lab/my-campaign.json
```

Every completed task receives a deterministic receipt under
`data/research/crisis-lab/model-lab/atria/campaigns/<campaign-id>/`.

If the same campaign is run again with the same task packet, the receipt is
reused and that task does not call Atria again. If a campaign stops part-way,
the next run resumes by skipping already receipted tasks.

Receipts never contain the API key. Provider output remains untrusted research,
with `strategy_evidence_effect=NONE`, `p10_evidence_effect=NONE`, and
`ai_direct_execution=false`.

The intended first campaign will compare accepted crisis replay, ordinary
controls, strategy-active source states and synthetic shock evidence after those
artifacts pass their deterministic YATL gates.
