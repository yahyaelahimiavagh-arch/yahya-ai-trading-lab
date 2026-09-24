# YATL Atria Research Model Lab v0.1.0

Status: **IMPLEMENTED / FINAL-HEAD CI PENDING / NO REAL API CALL RECORDED**

## Purpose

Use Atria Dawn Preview as an external, high-volume research critic for YATL
artifacts without weakening any accepted P6/P10/P11 boundary.

This is **not** a replacement for the P6 analyst. P6 intentionally remains
provider-neutral and transport-free. The Atria worker lives under
`research/model_lab/` and its output has no strategy-evidence, risk,
quantity, trade, order, or Live authority.

## Provider contract

- provider: Atria;
- model: `Atria-Dawn-Preview`;
- interface: OpenAI-compatible Responses API;
- endpoint: `https://api.atria-asi.ai/v1/responses`;
- credential environment variable: `ATRIA_API_KEY`;
- text/JSON input only;
- default output ceiling: 4096 tokens;
- worker-side ceiling: 16384 tokens.

The API key is read only for the explicit `run` command. It is never placed in
Git, the research packet, request artifact, result artifact, or CLI output.

## Hard isolation

The worker rejects:
- `/var/lib/yatl/p10` as a runtime root;
- non-JSON inputs;
- symlink/path-escape inputs;
- artifacts that are not `research_only=true`;
- artifacts where `p10_write_allowed` is not exactly false;
- artifacts where `p11_locked` is not exactly true;
- JSON containing credential/account/secret-shaped keys;
- model output with execution/order/quantity/credential-shaped fields;
- model evidence references that do not bind to an input artifact SHA-256;
- malformed or oversized model output.

A successful result still records:
- `provider_output_trusted=false`;
- `strategy_evidence_effect=NONE`;
- `p10_evidence_effect=NONE`;
- `trade_permission=false`;
- `order_endpoint=false`;
- `quantity_authority=false`;
- `risk_authorization_mutation=false`;
- `ai_direct_execution=false`;
- `p11_locked=true`.

## Registered research objectives

v0.1.0 supports only:
- `COMPARE_EVIDENCE`;
- `FIND_ANOMALIES`;
- `PROPOSE_FALSIFIABLE_TESTS`.

Adding a new objective requires a code change and tests. Arbitrary prompt text is
not accepted from the CLI.

## Dry plan

Always plan first. This performs no network call and does not read the API key:

```bash
uv run --locked python -m research.model_lab.atria_worker plan \
  --runtime-root data/research/crisis-lab \
  --artifact replay/event-catalog-v0.1.0/CRL-E003/<replay>.json \
  --objective FIND_ANOMALIES
```

The plan prints packet identity, bounded size, artifact count and model identity.

## Explicit run

On the VPS, set the secret outside Git:

```bash
export ATRIA_API_KEY='atr_...'
```

Then run the same packet explicitly:

```bash
uv run --locked python -m research.model_lab.atria_worker run \
  --runtime-root data/research/crisis-lab \
  --artifact replay/event-catalog-v0.1.0/CRL-E003/<replay>.json \
  --objective FIND_ANOMALIES
```

Validated results are written immutably below:

`data/research/crisis-lab/model-lab/atria/`

The entire `data/` tree is ignored by Git.

## Intended workflow

1. Deterministic YATL code produces evidence.
2. The evidence passes its normal deterministic gate first.
3. A bounded research packet is built from accepted research-only JSON.
4. Atria reviews that packet as an external critic.
5. The response must pass the worker's strict inert schema.
6. Atria findings may suggest a new **research test**.
7. Only deterministic YATL code/tests can accept or reject that hypothesis.
8. Atria output never modifies the frozen P10 candidate and never opens P11.

## First use in Crisis Lab

After the ordinary-market control corpus is acquired and replayed, use Atria to:
- compare crisis vs ordinary evidence;
- find repeated failure/flat/no-trade patterns;
- propose falsifiable transition and shock tests;
- challenge interpretations of CRL-004/005/006 evidence.

Do not use Atria to select favorable historical windows, tune the current P10
candidate, or discard negative evidence.
