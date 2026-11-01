import contextlib
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.model_lab import ai_paper_week as paper


START = 1790964000000


def snapshot(at=START, btc="100", eth="100"):
    return {"schema": "YATL_AI_PUBLIC_SNAPSHOT/1", "observed_at_ms": at,
            "tickers": {symbol: {"url": paper.ticker_url(symbol), "raw": {
                "symbol": symbol, "lastPrice": value, "openPrice": "100",
                "highPrice": "1000", "lowPrice": "1",
                "openTime": at - paper.DAY, "closeTime": at - 1000}}
                for symbol, value in zip(paper.SYMBOLS, (btc, eth))}}


def proposals(quote, action="BUY", symbol="BTCUSDT", stop="0.04"):
    return {"schema": "YATL_AI_SHADOW_PROPOSALS/1",
            "snapshot_sha256": paper.digest(quote),
            "created_at_ms": quote["observed_at_ms"] + 1000,
            "model_identity": "CHATGPT_RUNTIME_UNPINNED",
            "profiles": {name: {"action": action, "symbol": symbol,
                "stop_fraction": stop if action == "BUY" else None,
                "rationale": "Synthetic fixture, never a market decision."}
                for name in paper.PROFILES}}


def event(quote, decisions, previous=None):
    return {"snapshot": quote, "decisions": decisions,
            "previous_event_sha256": paper.digest(previous) if previous else None}


class PaperWeekTests(unittest.TestCase):
    def setUp(self):
        self.protocol = paper.make_protocol(START)

    def first(self):
        quote = snapshot()
        return event(quote, proposals(quote))

    def test_first_decision_has_no_same_quote_fill(self):
        report = paper.replay(self.protocol, [self.first()])
        for state in report["accounts"].values():
            self.assertEqual(state["fills"], [])
            self.assertEqual(state["cash_usdt"], "10000")
            self.assertIsNotNone(state["pending_proposal"])

    def test_next_quote_sizing_preserves_cost_risk_and_cash_caps(self):
        first = self.first()
        quote = snapshot(START + paper.DAY)
        report = paper.replay(self.protocol, [first, event(quote, proposals(quote, "HOLD"), first)])
        for name, state in report["accounts"].items():
            fill = state["fills"][0]
            position = state["position"]
            self.assertGreater(fill["observed_at_ms"], fill["proposal_created_at_ms"])
            self.assertLessEqual(Decimal(fill["planned_stop_loss_usdt"]),
                                 Decimal(10000) * Decimal(paper.PROFILES[name]["risk"]))
            self.assertLessEqual(Decimal(position["entry_cost"]),
                                 Decimal(10000) * Decimal(paper.PROFILES[name]["exposure"]))
            self.assertGreaterEqual(Decimal(state["cash_usdt"]), 0)
            self.assertGreater(Decimal(state["fees_usdt"]), 0)
            self.assertGreater(Decimal(state["slippage_usdt"]), 0)
        low, high = report["accounts"].values()
        self.assertLess(Decimal(low["position"]["quantity"]), Decimal(high["position"]["quantity"]))

    def test_unknown_fields_cannot_grant_quantity_or_safety_authority(self):
        for key, value in (("quantity", "999"), ("live", True), ("order_endpoint", "https://example.org")):
            quote = snapshot()
            decision = proposals(quote)
            decision["profiles"]["aggressive"][key] = value
            with self.subTest(key=key), self.assertRaises(paper.PaperWeekError):
                paper.replay(self.protocol, [event(quote, decision)])
        for key in paper.SAFETY:
            protocol = deepcopy(self.protocol)
            protocol["safety"][key] = not protocol["safety"][key]
            with self.subTest(key=key), self.assertRaises(paper.PaperWeekError):
                paper.replay(protocol, [])

    def test_protocol_model_and_source_are_frozen(self):
        for key, value in (("base_main", "0" * 40), ("source_sha256", "0" * 64),
                           ("end_ms", START + 8 * paper.DAY), ("extra_api_budget_usd", "1")):
            protocol = deepcopy(self.protocol)
            protocol[key] = value
            with self.subTest(key=key), self.assertRaises(paper.PaperWeekError):
                paper.replay(protocol, [])

    def test_bad_model_backdated_stale_or_unbound_decisions_fail(self):
        quote = snapshot()
        for key, value in (("model_identity", "gpt-claimed-model"), ("created_at_ms", START - 1),
                           ("created_at_ms", START + 900001), ("snapshot_sha256", "0" * 64)):
            decision = proposals(quote)
            decision[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(paper.PaperWeekError):
                paper.replay(self.protocol, [event(quote, decision)])

    def test_unapproved_symbols_short_bad_stops_and_nan_fail(self):
        for key, value in (("symbol", "DOGEUSDT"), ("action", "SHORT"),
                           ("stop_fraction", "0.019"), ("stop_fraction", "0.11"),
                           ("stop_fraction", "NaN"), ("stop_fraction", True)):
            quote = snapshot()
            decision = proposals(quote)
            decision["profiles"]["aggressive"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(paper.PaperWeekError):
                paper.replay(self.protocol, [event(quote, decision)])

    def test_stale_future_wrong_symbol_and_redirect_source_quotes_fail(self):
        for key, value in (("closeTime", START - 300001), ("closeTime", START + 1),
                           ("symbol", "ETHUSDT"), ("lastPrice", "NaN"), ("lastPrice", "0")):
            quote = snapshot()
            quote["tickers"]["BTCUSDT"]["raw"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(paper.PaperWeekError):
                paper.validate_snapshot(quote)
        quote = snapshot()
        quote["tickers"]["BTCUSDT"]["url"] = "https://api.binance.com/api/v3/order"
        with self.assertRaises(paper.PaperWeekError):
            paper.validate_snapshot(quote)

    def test_moved_entry_and_expired_pending_are_vetoed(self):
        first = self.first()
        for hours, mark, reason in ((24, "102", "ENTRY_PRICE_MOVED_OVER_1_PERCENT"),
                                    (48, "100", "STALE_PENDING_REJECTED")):
            quote = snapshot(START + hours * 3_600_000, btc=mark)
            report = paper.replay(self.protocol, [first, event(quote, proposals(quote, "HOLD"), first)])
            for state in report["accounts"].values():
                self.assertEqual(state["fills"], [])
                self.assertIn(reason, state["vetoes"])

    def test_observed_gap_stop_uses_observed_price_and_can_exceed_planned_risk(self):
        first = self.first()
        quote = snapshot(START + paper.DAY)
        second = event(quote, proposals(quote, "HOLD"), first)
        quote = snapshot(START + 2 * paper.DAY, btc="80")
        third = event(quote, proposals(quote, "HOLD"), second)
        report = paper.replay(self.protocol, [first, second, third])
        state = report["accounts"]["aggressive"]
        self.assertEqual(state["fills"][-1]["mark"], "80")
        self.assertLess(Decimal(state["net_pnl_usdt"]), Decimal("-100"))
        self.assertTrue(state["risk_halted"])
        self.assertIsNone(state["position"])

    def test_three_losing_trades_latch_and_prevent_new_entries(self):
        state = paper.account()
        quote = snapshot()
        for _ in range(3):
            state["position"] = {"symbol": "BTCUSDT", "quantity": Decimal(1),
                                 "entry_cost": Decimal(101), "stop": Decimal(90), "target": Decimal(110)}
            paper.close_position(state, quote, "FIXTURE")
        paper.circuit(state, quote)
        self.assertTrue(state["halted"])
        state["pending"] = {"proposal": proposals(quote)["profiles"]["aggressive"],
                            "created_at_ms": START, "reference_price": "100"}
        paper.fill_pending(state, snapshot(START + paper.DAY), "aggressive", self.protocol)
        self.assertIsNone(state["position"])

    def test_week_end_liquidates_and_forbids_entries_or_repeat(self):
        first = self.first()
        quote = snapshot(START + paper.DAY)
        second = event(quote, proposals(quote, "HOLD"), first)
        quote = snapshot(START + 7 * paper.DAY)
        final = event(quote, None, second)
        report = paper.replay(self.protocol, [first, second, final])
        self.assertEqual(report["status"], "WEEK_CLOSED")
        for state in report["accounts"].values():
            self.assertIsNone(state["position"])
            self.assertIsNone(state["pending_proposal"])
            self.assertEqual(state["closed_trades"], 1)
            self.assertLess(Decimal(state["net_pnl_usdt"]), 0)
        with self.assertRaises(paper.PaperWeekError):
            paper.replay(self.protocol, [first, second, event(quote, proposals(quote), second)])
        with self.assertRaises(paper.PaperWeekError):
            paper.replay(self.protocol, [first, second, final, final])

    def test_hash_chain_duplicate_and_window_fail(self):
        first = self.first()
        with self.assertRaises(paper.PaperWeekError):
            paper.replay(self.protocol, [first, first])
        quote = snapshot(START + paper.DAY)
        second = event(quote, proposals(quote), first)
        second["previous_event_sha256"] = "0" * 64
        with self.assertRaises(paper.PaperWeekError):
            paper.replay(self.protocol, [first, second])
        quote = snapshot(START + 8 * paper.DAY)
        with self.assertRaises(paper.PaperWeekError):
            paper.replay(self.protocol, [event(quote, None)])

    def test_read_protected_paths_and_symlinks_are_rejected(self):
        for name in ("/var/lib/yatl/p10/secret.json", "/tmp/fresh_oos/input.json"):
            with self.assertRaises(paper.PaperWeekError):
                paper.load(Path(name))
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "original").write_text("{}")
            (folder / "link").symlink_to(folder / "original")
            with self.assertRaises(paper.PaperWeekError):
                paper.load(folder / "link")
            with self.assertRaises(paper.PaperWeekError):
                paper.safe_root(folder / "elsewhere")
            with self.assertRaises(paper.PaperWeekError):
                paper.safe_input_path(Path("/var/lib/yatl/p10/inputs/quote.json"))

    def test_duplicate_json_keys_and_nonfinite_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            for payload in ('{"live":false,"live":true}', '{"price":NaN}'):
                path.write_text(payload)
                with self.subTest(payload=payload), self.assertRaises(paper.PaperWeekError):
                    paper.load(path)

    def test_public_fetch_has_only_two_fixed_anonymous_gets(self):
        quote = snapshot()
        responses = []
        for symbol in paper.SYMBOLS:
            responses.append(contextlib.nullcontext(io.BytesIO(paper.canonical(quote["tickers"][symbol]["raw"]))))
        with patch.object(paper.urllib.request, "build_opener") as opener, patch.object(paper.time, "time", return_value=START / 1000):
            opener.return_value.open.side_effect = responses
            self.assertEqual(paper.fetch_snapshot(), quote)
            self.assertEqual([call.args[0] for call in opener.return_value.open.call_args_list],
                             [paper.ticker_url(symbol) for symbol in paper.SYMBOLS])

    def test_cli_persists_once_reconstructs_report_and_rejects_backfill(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "fixture"
            with patch.object(paper, "ROOT", Path(folder)), patch.object(paper.time, "time", return_value=START / 1000), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(paper.main(["init", "--root", str(root)]), 0)
                quote = snapshot()
                quote_path, decision_path = root / "inputs" / "quote.json", root / "inputs" / "decisions.json"
                quote_path.write_bytes(paper.canonical(quote))
                decision_path.write_bytes(paper.canonical(proposals(quote)))
                with patch.object(paper.time, "time", return_value=(START + 2000) / 1000):
                    args = ["step", "--root", str(root), "--snapshot", str(quote_path), "--decisions", str(decision_path)]
                    self.assertEqual(paper.main(args), 0)
                    self.assertEqual(paper.main(args), 2)
                self.assertEqual(len(paper.history(root)), 1)
                (root / "report.json").write_text('{"equity_usdt":"9999999"}')
                self.assertEqual(paper.main(["report", "--root", str(root)]), 0)
                self.assertEqual(paper.load(root / "report.json")["accounts"]["aggressive"]["cash_usdt"], "10000")
                with patch.object(paper.time, "time", return_value=(START + paper.DAY) / 1000):
                    self.assertEqual(paper.main(args), 2)


if __name__ == "__main__":
    unittest.main()
