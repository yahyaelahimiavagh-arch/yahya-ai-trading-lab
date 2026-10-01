# YATL Distributed Coordinator — Cloudflare

This directory contains the control-plane implementation for distributed
MCF-PROD-001 execution.

It is coordination infrastructure only. It never performs candidate backtests.

## Components

- `schema.sql` — D1 schema for nodes, batch leases and audit events.
- `src/index.js` — Worker API for claim, heartbeat, release, ready, ingest and status.
- `wrangler.toml.example` — binding template with no secrets.

## Security model

- Each compute node gets a unique random bearer token.
- Only SHA-256 token hashes are stored in D1.
- Plaintext node tokens stay on their node and are provided to the Python client
  via `YATL_NODE_TOKEN`.
- The VPS/admin ingest token is separate from node tokens.
- No exchange credential or sealed YATL evidence is stored here.

## Deployment outline

After the distributed plan is frozen:

1. Create a D1 database.
2. Apply `schema.sql`.
3. Emit the exact plan seed SQL with:
   `python -m research.mass_candidate_factory.production_distributed emit-d1-seed ...`
4. Apply the seed SQL.
5. Enroll NODE-VPS, NODE-LAPTOP and NODE-WORKPC with distinct token hashes.
6. Configure `YATL_ADMIN_TOKEN_SHA256` as a Worker secret/environment value.
7. Copy `wrangler.toml.example` to a local uncommitted `wrangler.toml` and set
   the real D1 database ID.
8. Deploy and verify `/health`.
9. Test claim/heartbeat/release with no strategy execution.

R2 result relay is intentionally deferred to a subsequent acceptance gate.
