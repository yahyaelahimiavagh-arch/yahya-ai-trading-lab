# MCF-PROD-001 — VPS Pre-Outcome Freeze Materialization v1.0

Status: **PRE-PERFORMANCE / NO MARKET DATA READ**

Purpose: materialize the already accepted MCF-PROD-001 executable identity
freeze on the Director VPS and verify byte-for-byte reproduction before any
Development strategy outcome is read.

## Accepted source state

This procedure starts from main after PR #160:

`69dc1c6d167b216bf26e2a8ade42e55f845dd417`

Expected canonical identities:

- raw candidates: `9176`
- structurally valid: `8640`
- blocked before performance: `1788`
- executable: `6852`
- candidate ledger SHA-256:
  `084150778f2270c2ce96dac631f2e0fb1e6f84fed3325a197a80aa3d59db8e73`
- neighbor graph SHA-256:
  `4eb36ca827b5b458147e6ba2a74308353dfa047cd368d72e106f568b1f4fc4bb`
- executable freeze SHA-256:
  `84d4f8ec6234ffb5afccf44ea044661d72af8b4de525b111118ae087907d1dc6`

## VPS commands

Use a Development-research path that is separate from P10 and sealed evidence:

```bash
sudo install -d -o yatl -g yatl -m 0750 /var/lib/yatl/research/mcf-prod-001

cd /opt/yatl/app
git fetch origin
git checkout main
git pull --ff-only origin main

sudo -u yatl /opt/yatl/app/.venv/bin/python -m   research.mass_candidate_factory.production_freeze   materialize   --root /var/lib/yatl/research/mcf-prod-001
```

Expected terminal status:

`"status": "VERIFIED"`

Then run a separate read-back verification:

```bash
cd /opt/yatl/app

sudo -u yatl /opt/yatl/app/.venv/bin/python -m   research.mass_candidate_factory.production_freeze   verify   --root /var/lib/yatl/research/mcf-prod-001
```

The second command must return the same three SHA-256 identities and
`executable_candidate_count = 6852`.

## Materialized artifacts

Under:

`/var/lib/yatl/research/mcf-prod-001/mcf-prod-001-preoutcome-freeze/`

the command writes exactly:

- `freeze-summary.json`
- `registered-candidates.jsonl`
- `blocked-candidates.jsonl`
- `neighbor-graph.json`
- `manifest.json`

The writes are immutable/idempotent. Existing mismatched content fails closed
rather than being overwritten.

## Safety boundary

This command does not read:
- AF-01C candles;
- strategy returns;
- PnL;
- Sharpe;
- drawdown;
- Fresh OOS;
- recent reserve;
- P10.

It cannot place orders or authorize Live.

Hard state remains:

- PAPER / RESEARCH ONLY
- LIVE_MASTER_LOCK=OFF
- NO FUTURES
- NO LEVERAGE
- NO SHORT
- NO LIVE EXECUTION
- NO ORDER ENDPOINT
- NO AI DIRECT EXECUTION
- Fresh OOS sealed
- recent reserve sealed
- P10 untouched
- P11 locked

## Gate to the Development run

MCF-PROD-001 Development performance remains unauthorized until:

1. this VPS materialization returns `VERIFIED`;
2. the manifest SHA identities match the accepted checkpoint;
3. the AF-01C Development population and point-in-time universe binding are
   independently bound and audited;
4. the Development runner input manifest is frozen before the first candidate
   outcome is emitted.
