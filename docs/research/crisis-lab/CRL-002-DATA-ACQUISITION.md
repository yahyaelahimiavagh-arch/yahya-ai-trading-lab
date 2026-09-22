# CRL-002 — Data acquisition and provenance

Goal: collect bounded historical BTCUSDT/ETHUSDT data for catalog windows.

Initial scope:
- Binance Spot public market data;
- 15m / 1h / 4h matching accepted YATL semantics;
- optional finer-resolution research data only in a separately versioned extension.

Each acquisition must record:
- source/host/API or archive identity;
- symbol and interval;
- exact UTC start/end;
- retrieval time;
- row count;
- raw/canonical digests where applicable;
- transport failures/retries;
- provenance manifest.

Runtime data belongs under `data/research/crisis-lab/` and remains ignored by Git.
No P10 database or snapshot may be opened writable.

Exit gate: reproducible acquisition plan + provenance manifest + no-P10-write proof.
