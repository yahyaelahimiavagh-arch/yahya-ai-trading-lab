-- YATL distributed coordinator control-plane schema.
-- No strategy outcomes or market data belong in D1.

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
  node_id TEXT PRIMARY KEY,
  token_sha256 TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  max_workers INTEGER NOT NULL DEFAULT 1 CHECK (max_workers BETWEEN 1 AND 32),
  last_seen_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS batches (
  batch_code TEXT PRIMARY KEY,
  batch_sha256 TEXT NOT NULL,
  plan_sha256 TEXT NOT NULL,
  candidate_count INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (
    state IN ('AVAILABLE','CLAIMED','AWAITING_INGEST','INGESTED','BLOCKED')
  ),
  owner_node TEXT,
  lease_until_ms INTEGER,
  updated_at_ms INTEGER NOT NULL,
  result_manifest_sha256 TEXT,
  result_count INTEGER,
  transfer_mode TEXT CHECK (transfer_mode IN ('R2','DIRECT_PULL') OR transfer_mode IS NULL),
  FOREIGN KEY(owner_node) REFERENCES nodes(node_id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_ms INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  node_id TEXT,
  batch_code TEXT,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_batches_state_code
  ON batches(state, batch_code);

CREATE INDEX IF NOT EXISTS idx_batches_lease
  ON batches(state, lease_until_ms);

CREATE INDEX IF NOT EXISTS idx_events_batch
  ON events(batch_code, id);
