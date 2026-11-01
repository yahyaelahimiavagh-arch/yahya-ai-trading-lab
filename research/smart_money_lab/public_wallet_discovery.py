"""YATL public-data wallet candidate discovery, not a PnL / copyability engine.

Dataset: ian05012/solana-memecoin-dataset (June 2026, MIT).
No Helius, RPC, exchange, wallet, or price API calls. This module reads
already-downloaded local Parquet files via DuckDB.

What it CAN test:
  Does a wallet repeatedly BUY in the 15 minutes BEFORE a recorded token
  detection snapshot, followed by the token reaching 2x within 24h?
  Is that descriptive outcome repeated after a strict time cutoff?

What it CANNOT test:
  Trader realized PnL, inventory, profitable exits, follower execution prices,
  genuine lead-time observation or live trading skill. 2x MAXIMUM price is not
  a realizable exit and GMGN sampled tokens are highly selection biased.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
import json
import math
from pathlib import Path

FILES = (
    "tokens.parquet",
    "trades-000.parquet",
    "trades-001.parquet",
    "trades-002.parquet",
    "trades-003.parquet",
)
SOURCE = "ian05012/solana-memecoin-dataset"
PRIOR_STRENGTH = 20.0
LABEL_HORIZON_SECONDS = 86400


def _number(value):
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def select_count(eligible: int, *, fraction: float, max_wallets: int) -> int:
    """Top percentage of *training-qualified* wallets, not entire Solana."""
    if eligible < 0 or not 0 < fraction <= 1 or max_wallets < 1:
        raise ValueError("invalid ranking count parameters")
    return min(max_wallets, max(1, math.ceil(eligible * fraction))) if eligible else 0


def posterior_rate(wins: int, n: int, baseline: float,
                   prior_strength: float = PRIOR_STRENGTH) -> float:
    if not 0 <= wins <= n or n < 0 or not 0 <= baseline <= 1 or prior_strength <= 0:
        raise ValueError("invalid posterior parameters")
    return (wins + baseline * prior_strength) / (n + prior_strength)


def _required_files(folder: Path):
    if not folder.is_dir():
        raise FileNotFoundError(f"missing data folder: {folder}")
    files = {}
    for name in FILES:
        p = folder / name
        if not p.is_file() or p.stat().st_size < 100:
            raise FileNotFoundError(f"missing or empty dataset file: {p}")
        with p.open("rb") as fp:
            digest = hashlib.file_digest(fp, "sha256").hexdigest()
        files[name] = {"bytes": p.stat().st_size, "sha256": digest}
    return files


def _columns(con, parquet: str) -> set[str]:
    return {row[0] for row in
            con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [parquet]).fetchall()}


def _dicts(cursor) -> list[dict]:
    fields = [x[0] for x in cursor.description]
    return [dict(zip(fields, item)) for item in cursor.fetchall()]


def _base_rate(con, clause: str, cutoff: int):
    # Parameterized guard against future labels entering TRAINING.
    if clause == "train":
        sql = """SELECT COUNT(*) n, AVG(CAST(hit AS DOUBLE)) rate
                 FROM token_sample WHERE epoch(captured_at) + ? < ?"""
        return con.execute(sql, [LABEL_HORIZON_SECONDS, cutoff]).fetchone()
    if clause == "holdout":
        sql = """SELECT COUNT(*) n, AVG(CAST(hit AS DOUBLE)) rate
                 FROM token_sample WHERE epoch(captured_at) >= ?"""
        return con.execute(sql, [cutoff]).fetchone()
    raise ValueError("invalid time split")


def run(folder: Path, *, cutoff: int | None = None,
        min_liquidity_usd: float = 20000,
        min_buy_usd: float = 10,
        min_train_tokens: int = 10,
        min_train_days: int = 3,
        top_fraction: float = 0.01,
        max_wallets: int = 100,
        max_memory: str = "1GB") -> dict:
    try:
        import duckdb
    except ImportError as e:
        raise RuntimeError("Install free dependency duckdb==1.4.1 first") from e
    if (not 0 <= min_liquidity_usd < 1e12 or not 0 < min_buy_usd < 1e9
            or not 2 <= min_train_tokens <= 10000 or not 1 <= min_train_days <= 100
            or not 0 < top_fraction <= 1 or max_wallets < 1):
        raise ValueError("invalid research thresholds")
    manifest = _required_files(Path(folder))
    c = duckdb.connect(database=":memory:")
    try:
        c.execute("SET threads TO 2")
        c.execute(f"SET memory_limit = '{max_memory}'")
        token_file = str(Path(folder) / "tokens.parquet")
        trade_glob = str(Path(folder) / "trades-*.parquet")
        if not {"sample_id","token_address","captured_at","liquidity_usd",
                "reaches_2x"}.issubset(_columns(c, token_file)):
            raise ValueError("token parquet schema mismatch")
        if not {"wallet","token_address","side","amount_usd","ts"}.issubset(
                _columns(c, str(Path(folder) / "trades-000.parquet"))):
            raise ValueError("trade parquet schema mismatch")
        # Earliest *eligible* detection of each token. One token observation
        # prevents overlapping later snapshots from inflating sample size.
        c.execute("""
            CREATE TEMP TABLE token_sample AS
            SELECT token_address, captured_at, reaches_2x AS hit, liquidity_usd
            FROM read_parquet(?)
            WHERE token_address IS NOT NULL
              AND captured_at IS NOT NULL
              AND reaches_2x IS NOT NULL
              AND isfinite(liquidity_usd) AND liquidity_usd >= ?
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY token_address ORDER BY captured_at, sample_id
            ) = 1
        """, [token_file, min_liquidity_usd])
        token_n, earliest, latest = c.execute("""
            SELECT COUNT(*), CAST(MIN(epoch(captured_at)) AS BIGINT),
                   CAST(MAX(epoch(captured_at)) AS BIGINT)
            FROM token_sample""").fetchone()
        if token_n < 3:
            raise ValueError("insufficient labeled token snapshots; keep liquidity guard")
        if cutoff is None:
            # Calendar-time split (not row-density quantile): ~2/3 training,
            # ~1/3 future holdout. Avoid a 3-day test window just because
            # the dataset is much denser during its final days.
            cutoff = int(earliest + (latest - earliest) * 2 / 3)
        if type(cutoff) is not int or not earliest < cutoff < latest:
            raise ValueError("cutoff must be inside recorded snapshot interval")
        # Join all four trade shards; no wallet-score/profile fields are used.
        # All buys precede detection. Dedup repeated snapshots and fills,
        # one event per wallet/token. Timestamp boundaries are explicit.
        c.execute("""
            CREATE TEMP TABLE evidence AS
            SELECT wallet, token_address, captured_at, hit, liquidity_usd,
                   buy_ts, buy_usd,
                   CAST(epoch(captured_at)-epoch(buy_ts) AS BIGINT)
                       AS seconds_before_snapshot
            FROM (
              SELECT b.wallet, b.token_address, t.captured_at, t.hit,
                     t.liquidity_usd, b.ts AS buy_ts, b.amount_usd AS buy_usd,
                     ROW_NUMBER() OVER (
                       PARTITION BY b.wallet,b.token_address
                       ORDER BY b.ts DESC, b.amount_usd DESC
                     ) AS rn
              FROM read_parquet(?) b JOIN token_sample t
                ON b.token_address=t.token_address
              WHERE lower(b.side)='buy' AND b.amount_usd>=?
                AND b.ts <= t.captured_at
                AND b.ts >= t.captured_at - INTERVAL '15 minutes'
                AND b.wallet IS NOT NULL
                AND length(b.wallet) BETWEEN 32 AND 44
            ) w WHERE rn=1
        """, [trade_glob, min_buy_usd])
        evidence_n, wallet_n = c.execute("""
            SELECT COUNT(*),COUNT(DISTINCT wallet) FROM evidence
        """).fetchone()
        train_tokens, train_baseline = _base_rate(c, "train", cutoff)
        holdout_tokens, holdout_baseline = _base_rate(c, "holdout", cutoff)
        if not train_tokens or not holdout_tokens:
            raise ValueError("split has insufficient matured train or holdout tokens")
        c.execute("""
            CREATE TEMP TABLE train_wallets AS
            SELECT wallet, COUNT(*) AS train_tokens,
                   SUM(CAST(hit AS INT)) AS train_hits,
                   COUNT(DISTINCT CAST(captured_at AS DATE)) AS train_days,
                   MEDIAN(seconds_before_snapshot) AS median_lead_seconds
            FROM evidence
            WHERE epoch(captured_at) + ? < ?
            GROUP BY wallet
        """, [LABEL_HORIZON_SECONDS, cutoff])
        # Filter based ONLY on observations before frozen cutoff.
        qualified_n = c.execute("""
            SELECT COUNT(*) FROM train_wallets
            WHERE train_tokens >= ? AND train_days >= ?
        """, [min_train_tokens, min_train_days]).fetchone()[0]
        top_n = select_count(qualified_n, fraction=top_fraction,
                             max_wallets=max_wallets)
        ranked = []
        if top_n:
            ranked = _dicts(c.execute("""
                SELECT wallet, train_tokens, train_hits, train_days,
                       median_lead_seconds,
                       (train_hits + ? * ?) / (train_tokens + ?) AS train_posterior
                FROM train_wallets
                WHERE train_tokens >= ? AND train_days >= ?
                ORDER BY train_posterior DESC, train_hits DESC,
                         train_tokens DESC, wallet
                LIMIT ?
            """, [PRIOR_STRENGTH, train_baseline, PRIOR_STRENGTH,
                  min_train_tokens, min_train_days, top_n]))
        # This is an OUT-OF-SAMPLE DESCRIPTION only. Never rerank based on it.
        heldout = {}
        if ranked:
            c.execute("CREATE TEMP TABLE selected(wallet VARCHAR)")
            c.executemany("INSERT INTO selected VALUES (?)",
                          [(r["wallet"],) for r in ranked])
            heldout = {x["wallet"]: x for x in _dicts(c.execute("""
                SELECT e.wallet, COUNT(*) AS n, SUM(CAST(e.hit AS INT)) AS hits,
                       COUNT(DISTINCT CAST(e.captured_at AS DATE)) AS days
                FROM evidence e JOIN selected s USING(wallet)
                WHERE epoch(e.captured_at) >= ?
                GROUP BY e.wallet
            """, [cutoff]))}
        # Training-only behavior grouping, using token overlap instead of
        # treating near-identical wallet strategies as independent discoveries.
        # Similar overlap does not establish shared ownership or wash trading.
        training_tokens_by_wallet = {r["wallet"]: set() for r in ranked}
        if ranked:
            for wallet, token in c.execute("""
                SELECT e.wallet, e.token_address FROM evidence e
                JOIN selected s USING(wallet)
                WHERE epoch(e.captured_at) + ? < ?
            """, [LABEL_HORIZON_SECONDS, cutoff]).fetchall():
                training_tokens_by_wallet[wallet].add(token)
        rows = []
        behavior_anchors = []
        for rank, r in enumerate(ranked, start=1):
            v = heldout.get(r["wallet"], {"n": 0, "hits": 0, "days": 0})
            observed = v["n"] > 0
            tokens = training_tokens_by_wallet[r["wallet"]]
            closest = 0.0
            cluster = None
            for group_id, previous in behavior_anchors:
                union = len(tokens | previous)
                overlap = len(tokens & previous) / union if union else 0.0
                if overlap > closest:
                    closest = overlap
                if cluster is None and overlap >= .80:
                    cluster = group_id
            if cluster is None:
                cluster = len(behavior_anchors) + 1
                behavior_anchors.append((cluster, tokens))
            rows.append({
                "rank_train_only": rank,
                "training_behavior_group": cluster,
                "max_token_overlap_with_group_anchors": round(closest, 5),
                "wallet": r["wallet"],
                "train_token_buys": int(r["train_tokens"]),
                "train_active_days": int(r["train_days"]),
                "train_2x_tokens": int(r["train_hits"]),
                "train_hit_rate": round(r["train_hits"]/r["train_tokens"], 5),
                "train_shrunk_hit_rate": round(r["train_posterior"], 5),
                "median_buy_lead_seconds": _number(r["median_lead_seconds"]),
                "holdout_token_buys": int(v["n"]),
                "holdout_active_days": int(v["days"]),
                "holdout_2x_tokens": int(v["hits"]),
                "holdout_hit_rate": round(v["hits"]/v["n"], 5) if observed else None,
                "holdout_uplift_vs_all_tokens": (
                    round(v["hits"]/v["n"]-holdout_baseline, 5)
                    if observed else None),
                "validation_status": (
                    "observed_not_proven" if v["n"] >= 5 else
                    "insufficient_holdout_activity"),
            })
        selected_holdout_distinct_tokens = 0
        selected_holdout_2x_distinct_tokens = 0
        if ranked:
            selected_holdout_distinct_tokens, selected_holdout_2x_distinct_tokens = c.execute("""
                SELECT COUNT(DISTINCT e.token_address),
                       COUNT(DISTINCT CASE WHEN e.hit THEN e.token_address END)
                FROM evidence e JOIN selected s USING(wallet)
                WHERE epoch(e.captured_at) >= ?
            """, [cutoff]).fetchone()
        token_outcomes = c.execute("""
            SELECT COUNT(*) AS matched_tokens,
                   SUM(CAST(hit AS INT)) AS hits
            FROM (SELECT DISTINCT token_address, hit FROM evidence)
        """).fetchone()
        return {
            "kind": "YATL_PUBLIC_WALLET_DISCOVERY_V1",
            "source": SOURCE,
            "source_period": "2026-06-10 to 2026-06-30",
            "selection_cutoff_utc": _utc(cutoff),
            "cutoff_unix": cutoff,
            "label_horizon_hours": 24,
            "feature_window": "only buys 0-15m before the earliest eligible token detection",
            "selection_rule": (
                "rank ONLY pre-cutoff token-level 2x labels using a 20-event "
                "prior shrunk to the training token baseline; no future profile fields"),
            "limits": {
                "snapshot_price_is_not_follower_execution": True,
                "2x_is_future_max_not_realized_sell": True,
                "source_transactions_lack_token_quantity": True,
                "one_market_regime_and_gmgn_selection_bias": True,
                "holdout_not_used_for_selection": True,
                "concentration_and_coordinated_wallets_not_resolved": True,
                "token_behavior_overlap_does_not_prove_shared_owner": True,
                "no_real_money_or_alpha_claim": True,
            },
            "thresholds": {
                "liquidity_at_snapshot_usd": min_liquidity_usd,
                "minimum_buy_usd": min_buy_usd,
                "minimum_training_token_buys": min_train_tokens,
                "minimum_training_active_days": min_train_days,
                "top_fraction_of_qualified": top_fraction,
                "max_selected": max_wallets,
                "prior_pseudo_events": PRIOR_STRENGTH,
            },
            "counts": {
                "source_files": manifest,
                "labeled_unique_token_snapshots": token_n,
                "unique_wallets_with_pretime_buy": wallet_n,
                "wallet_token_observations": evidence_n,
                "distinct_matched_tokens": int(token_outcomes[0] or 0),
                "qualified_training_wallets": qualified_n,
                "selected_top_training_wallets": len(rows),
                "distinct_training_behavior_groups_in_selection": len(behavior_anchors),
                "selected_with_80pct_token_overlap": sum(
                    x["max_token_overlap_with_group_anchors"] >= .80 for x in rows),
                "selected_with_5plus_holdout_tokens": sum(
                    x["holdout_token_buys"] >= 5 for x in rows),
                "selected_distinct_holdout_tokens": int(selected_holdout_distinct_tokens),
                "selected_distinct_holdout_2x_tokens": int(selected_holdout_2x_distinct_tokens),
            },
            "baselines": {
                "train_unique_token_n": int(train_tokens),
                "train_2x_rate": round(train_baseline, 5),
                "holdout_unique_token_n": int(holdout_tokens),
                "holdout_2x_rate": round(holdout_baseline, 5),
                "matched_token_2x_rate": (
                    round(token_outcomes[1]/token_outcomes[0], 5)
                    if token_outcomes[0] else None),
            },
            "wallet_candidates": rows,
            "status": ("candidate_screen_completed_unverified"
                       if rows else "no_train_qualified_candidates"),
            "warning": (
                "These are real public wallet addresses with a historical association "
                "to tokens that later peaked at 2x, NOT confirmed profitable traders "
                "or copyable return. No transaction quantities, realized exits, "
                "verified source latency or follower DEX quotes in this dataset."),
        }
    finally:
        c.close()


def save_results(result: dict, output_dir: Path):
    """Write only derived public-wallet ranking; never put raw data in Git."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "public_wallet_candidates.json"
    csv_path = output_dir / "public_wallet_candidates.csv"
    tmp = json_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False,
                              indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(json_path)
    tmpcsv = csv_path.with_suffix(".csv.tmp")
    columns = list(result["wallet_candidates"][0]) if result["wallet_candidates"] else [
        "rank_train_only", "wallet", "train_token_buys", "train_2x_tokens",
        "holdout_token_buys", "holdout_2x_tokens", "validation_status"]
    with tmpcsv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(result["wallet_candidates"])
    tmpcsv.replace(csv_path)
    return (json_path, csv_path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--cutoff", type=int, default=None,
                   help="Unix UTC cutoff, default 2/3 of calendar observation window")
    p.add_argument("--min-liquidity", type=float, default=20000)
    p.add_argument("--min-train-tokens", type=int, default=10)
    p.add_argument("--min-train-days", type=int, default=3)
    p.add_argument("--top-fraction", type=float, default=0.01)
    args = p.parse_args(argv)
    result = run(args.data_dir, cutoff=args.cutoff,
                 min_liquidity_usd=args.min_liquidity,
                 min_train_tokens=args.min_train_tokens,
                 min_train_days=args.min_train_days,
                 top_fraction=args.top_fraction)
    a, b = save_results(result, args.output_dir)
    print(json.dumps({
        "status": result["status"], "wallets": result["counts"]["unique_wallets_with_pretime_buy"],
        "qualified_training": result["counts"]["qualified_training_wallets"],
        "selected": result["counts"]["selected_top_training_wallets"],
        "holdout_active_5plus": result["counts"]["selected_with_5plus_holdout_tokens"],
        "train_baseline": result["baselines"]["train_2x_rate"],
        "holdout_baseline": result["baselines"]["holdout_2x_rate"],
        "json": str(a), "csv": str(b),
        "classification_not_profitability": True,
    }))


if __name__ == "__main__":
    main()
