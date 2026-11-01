"""Deterministic offline tests for public historical wallet candidate ranking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

try:
    import duckdb
except ImportError:
    duckdb = None

from research.smart_money_lab.public_wallet_discovery import (
    posterior_rate, run, save_results, select_count,
)

A = "A" * 33
B = "B" * 33


@unittest.skipIf(duckdb is None, "install pinned duckdb for candidate tests")
class PublicWalletDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "data"
        self.folder.mkdir()
        c = duckdb.connect()
        c.execute("""CREATE TABLE toks(
                   sample_id BIGINT, token_address VARCHAR,
                   captured_at TIMESTAMPTZ, liquidity_usd DOUBLE,
                   reaches_2x BOOLEAN)""")
        c.execute("""CREATE TABLE trades(
                   wallet VARCHAR, token_address VARCHAR, side VARCHAR,
                   amount_usd DOUBLE, ts TIMESTAMPTZ)""")
        start = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
        self.start = start
        token_rows = []
        trade_rows = []
        for day in range(10):
            stamp = start + timedelta(days=day)
            token = f"TOKEN{day:03}" + "X" * 28
            winner = day % 2 == 0
            token_rows.append((day, token, stamp, 24000, winner))
            # Prove duplicate snapshots never create extra wallet events:
            if day == 0:
                token_rows.append((1000, token, stamp + timedelta(minutes=3),
                                   25000, not winner))
            wallet = A if winner else B
            trade_rows.append((wallet, token, "buy", 30.0,
                               stamp - timedelta(minutes=4)))
            # Repeated fills from the SAME wallet/token must be one event.
            trade_rows.append((wallet, token, "buy", 15.0,
                               stamp - timedelta(minutes=2)))
            # Future trades and remote stale trades must not be admitted.
            trade_rows.append((A, token, "buy", 900.0,
                               stamp + timedelta(minutes=1)))
            trade_rows.append((B, token, "sell", 100.0,
                               stamp - timedelta(minutes=1)))
        c.executemany("INSERT INTO toks VALUES (?,?,?,?,?)", token_rows)
        c.executemany("INSERT INTO trades VALUES (?,?,?,?,?)", trade_rows)
        c.execute(f"COPY toks TO '{self.folder / 'tokens.parquet'}' (FORMAT PARQUET)")
        for i in range(4):
            c.execute(f"""COPY (SELECT * FROM trades WHERE
                       {'TRUE' if i == 0 else 'FALSE'})
                       TO '{self.folder / f'trades-{i:03}.parquet'}'
                       (FORMAT PARQUET)""")
        c.close()
        self.cutoff = int((start + timedelta(days=6)).timestamp())

    def tearDown(self):
        self.temp.cleanup()

    def test_qualified_training_rank_and_future_holdout(self):
        outcome = run(self.folder, cutoff=self.cutoff,
                      min_train_tokens=2, min_train_days=2,
                      top_fraction=1, max_wallets=2)
        c = outcome["counts"]
        self.assertEqual(c["labeled_unique_token_snapshots"], 10)
        self.assertEqual(c["qualified_training_wallets"], 2)
        self.assertEqual(c["selected_top_training_wallets"], 2)
        selected = outcome["wallet_candidates"]
        self.assertEqual(selected[0]["wallet"], A)
        self.assertEqual(selected[1]["wallet"], B)
        self.assertEqual(selected[0]["train_2x_tokens"], 3)
        self.assertEqual(selected[0]["holdout_token_buys"], 2)
        self.assertEqual(selected[0]["holdout_2x_tokens"], 2)
        self.assertEqual(selected[1]["train_2x_tokens"], 0)
        self.assertEqual(selected[1]["holdout_token_buys"], 2)
        self.assertIn("2x_is_future_max_not_realized_sell", outcome["limits"])
        self.assertNotIn("equity_usd", json.dumps(outcome))
        self.assertNotIn("realized_pnl", json.dumps(outcome))

    def test_selection_is_pre_cutoff_even_when_test_outcomes_change(self):
        first = run(self.folder, cutoff=self.cutoff, min_train_tokens=2,
                    min_train_days=2, top_fraction=.01)["wallet_candidates"]
        # Flip ALL holdout token labels. Training rank must remain the same.
        c = duckdb.connect()
        path = str(self.folder / "tokens.parquet")
        c.execute("CREATE TABLE altered AS SELECT * FROM read_parquet(?)", [path])
        c.execute("UPDATE altered SET reaches_2x = NOT reaches_2x WHERE captured_at >= ?",
                  [datetime.fromtimestamp(self.cutoff, timezone.utc)])
        c.execute(f"COPY altered TO '{path}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)")
        c.close()
        second = run(self.folder, cutoff=self.cutoff, min_train_tokens=2,
                     min_train_days=2, top_fraction=.01)["wallet_candidates"]
        self.assertEqual([x["wallet"] for x in first],
                         [x["wallet"] for x in second])
        self.assertEqual([x["train_shrunk_hit_rate"] for x in first],
                         [x["train_shrunk_hit_rate"] for x in second])

    def test_no_qualified_candidate_is_not_promoted(self):
        data = run(self.folder, cutoff=self.cutoff,
                   min_train_tokens=15, min_train_days=3)
        self.assertEqual(data["status"], "no_train_qualified_candidates")
        self.assertEqual(data["wallet_candidates"], [])

    def test_cutoff_and_threshold_guards(self):
        with self.assertRaises(ValueError):
            run(self.folder, cutoff=int(self.start.timestamp()) - 1)
        with self.assertRaises(ValueError):
            run(self.folder, cutoff=self.cutoff, min_liquidity_usd=-1)
        with self.assertRaises(ValueError):
            run(self.folder, cutoff=self.cutoff, min_train_days=0)
        with self.assertRaises(ValueError):
            run(self.folder, cutoff=self.cutoff, top_fraction=0)

    def test_report_writes_json_and_csv(self):
        data = run(self.folder, cutoff=self.cutoff, min_train_tokens=2,
                   min_train_days=2, top_fraction=1)
        a, b = save_results(data, Path(self.temp.name) / "report")
        self.assertEqual(json.loads(a.read_text())["kind"],
                         "YATL_PUBLIC_WALLET_DISCOVERY_V1")
        self.assertIn(A, b.read_text())
        self.assertIn("validation_status", b.read_text())

    def test_missing_data_detected_before_sql(self):
        (self.folder / "trades-003.parquet").unlink()
        with self.assertRaises(FileNotFoundError):
            run(self.folder, cutoff=self.cutoff)


class PriorTests(unittest.TestCase):
    def test_prior_shrinkage_and_top_one_percent(self):
        self.assertEqual(select_count(1500, fraction=.01, max_wallets=50), 15)
        self.assertEqual(select_count(10, fraction=.01, max_wallets=50), 1)
        self.assertEqual(select_count(0, fraction=.01, max_wallets=50), 0)
        self.assertAlmostEqual(posterior_rate(4, 10, .1), .2)
        with self.assertRaises(ValueError):
            posterior_rate(11, 10, .1)


if __name__ == "__main__":
    unittest.main()
