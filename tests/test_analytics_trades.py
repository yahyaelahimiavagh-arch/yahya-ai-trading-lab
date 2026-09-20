import hashlib
import inspect
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from yatl.__main__ import _paper_execution_contract_runtime_check
from yatl.backtest import BacktestSpec, DecisionEvent
from yatl.data import Candle, DATA_SOURCE
from yatl.execution import (
    ExecutionIntentJournal,
    LocalOrderEventType,
    LocalPaperFillCostAdapter,
    LocalPaperOrderStore,
    LocalPaperPortfolioStore,
    build_local_order_event,
)
from yatl.analytics import (
    AnalyticsSourceKind,
    StrategyEvidenceState,
    TradeBookStatus,
    TradeReconstructionError,
    UpstreamSourceSpec,
    build_unified_timeline,
    reconstruct_paper_trades,
)
from yatl.analytics.timeline_runtime import _create_p6
from yatl.analytics.trades import _build_episodes


HOUR = 3_600_000


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompletedPaperTradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.entry_decision, cls.exit_decision = (
            _paper_execution_contract_runtime_check()
        )
        cls.entry_time = (
            cls.entry_decision.authorization.request.strategy_decision.decision_time_ms
        )
        cls.exit_time = (
            cls.exit_decision.authorization.request.strategy_decision.decision_time_ms
        )
        cls.snapshot = cls.exit_time + HOUR + 100

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p5 = self.root / "p5.sqlite3"
        self.p6 = self.root / "p6.sqlite3"
        _create_p6(self.p6)

    def tearDown(self):
        self.temp.cleanup()

    def _event(self, decision, sequence):
        strategy = decision.authorization.request.strategy_decision
        return DecisionEvent(
            sequence,
            strategy.decision_time_ms,
            strategy.decision_time_ms,
            strategy.context.snapshot,
        )

    def _bar(self, decision, price, low, high):
        opened = decision.authorization.request.strategy_decision.decision_time_ms
        return Candle(
            DATA_SOURCE,
            "BTCUSDT",
            "1h",
            opened,
            opened + HOUR - 1,
            price,
            high,
            low,
            price,
            "100",
            "10000",
            20,
            True,
        )

    def _durable_base(self):
        decisions = (self.entry_decision, self.exit_decision)
        with ExecutionIntentJournal(self.p5) as journal:
            intents = tuple(journal.record(decision) for decision in decisions)
        orders = []
        with LocalPaperOrderStore(self.p5) as store:
            for decision, intent in zip(decisions, intents, strict=True):
                decision_time = (
                    decision.authorization.request.strategy_decision.decision_time_ms
                )
                created = store.apply(
                    build_local_order_event(
                        intent,
                        0,
                        decision_time - 2,
                        LocalOrderEventType.CREATE,
                    )
                ).current
                active = store.apply(
                    build_local_order_event(
                        intent,
                        1,
                        decision_time - 1,
                        LocalOrderEventType.ACTIVATE,
                        created,
                    )
                ).current
                orders.append(active)
        return intents, tuple(orders)

    def _build_p5(self, mode):
        intents, orders = self._durable_base()
        spec = BacktestSpec(
            "BTCUSDT",
            self.entry_time,
            self.exit_time + HOUR,
            initial_cash="10000",
            fee_bps="10",
            slippage_bps="5",
        )
        adapter = LocalPaperFillCostAdapter("BTCUSDT", spec)
        entry = adapter.process(
            self._event(self.entry_decision, 0),
            self.entry_decision,
            intents[0],
            orders[0],
            self._bar(
                self.entry_decision,
                "100",
                "94" if mode == "same_bar" else "99",
                "116" if mode == "same_bar" else "106",
            ),
            spec,
        )
        with LocalPaperPortfolioStore(self.p5, spec) as store:
            if mode == "same_bar":
                result = store.apply(entry, "95")
                return result.projection
            first = store.apply(entry, "100").projection
            if mode == "open":
                return first
            exit_step = adapter.process(
                self._event(self.exit_decision, 1),
                self.exit_decision,
                intents[1],
                orders[1],
                self._bar(self.exit_decision, "101", "100", "102"),
                spec,
            )
            return store.apply(exit_step, "101").projection

    def _specs(self):
        return (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                self.snapshot - 2,
                self.p5,
                file_sha(self.p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                self.snapshot - 1,
                self.p6,
                file_sha(self.p6),
            ),
        )

    def test_closed_trade_preserves_accepted_p2_p5_economics(self):
        projection = self._build_p5("closed")
        book = reconstruct_paper_trades(self.snapshot, self._specs())
        self.assertEqual(book.status, TradeBookStatus.FLAT)
        self.assertEqual(len(book.completed), 1)
        self.assertIsNone(book.open_trade)
        trade = book.completed[0]
        expected = (
            Decimal(trade.entry.cash_delta)
            + Decimal(trade.exit.cash_delta)
        )
        self.assertEqual(Decimal(trade.realized_pnl_quote), expected)
        self.assertEqual(
            Decimal(trade.realized_pnl_quote),
            projection.snapshot.realized_pnl_quote,
        )
        self.assertEqual(
            Decimal(book.final_portfolio.total_fee_quote),
            projection.snapshot.total_fee_quote,
        )
        self.assertEqual(
            Decimal(book.final_portfolio.total_slippage_quote),
            projection.snapshot.total_slippage_quote,
        )
        self.assertEqual(book.final_portfolio.closed_trades, 1)

    def test_open_trade_is_explicit_and_has_no_invented_exit_or_pnl(self):
        projection = self._build_p5("open")
        book = reconstruct_paper_trades(self.snapshot, self._specs())
        self.assertEqual(book.status, TradeBookStatus.OPEN)
        self.assertEqual(book.completed, ())
        self.assertIsNotNone(book.open_trade)
        self.assertIsNone(book.open_trade.as_record()["realized_pnl_quote"])
        self.assertEqual(
            Decimal(book.final_portfolio.asset_quantity),
            projection.snapshot.asset_quantity,
        )
        self.assertEqual(
            Decimal(book.final_portfolio.cost_basis_quote),
            projection.snapshot.cost_basis_quote,
        )

    def test_same_bar_protective_exit_is_valid_completed_trade(self):
        projection = self._build_p5("same_bar")
        timeline = build_unified_timeline(self.snapshot, self._specs())
        book = reconstruct_paper_trades(self.snapshot, self._specs())
        self.assertGreater(len(timeline.entries), 0)
        self.assertEqual(book.status, TradeBookStatus.FLAT)
        self.assertEqual(len(book.completed), 1)
        trade = book.completed[0]
        self.assertEqual(trade.entry.fill_step_sha256, trade.exit.fill_step_sha256)
        self.assertEqual(trade.entry.fill_time_ms, trade.exit.fill_time_ms)
        self.assertEqual(trade.holding_time_ms, 0)
        self.assertEqual(
            Decimal(trade.realized_pnl_quote),
            projection.snapshot.realized_pnl_quote,
        )

    def test_replay_is_byte_identical_and_read_only(self):
        self._build_p5("closed")
        specs = self._specs()
        before = tuple(file_sha(item.database_path) for item in specs)
        first = reconstruct_paper_trades(self.snapshot, specs)
        second = reconstruct_paper_trades(self.snapshot, specs)
        after = tuple(file_sha(item.database_path) for item in specs)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.reconstruction_sha256, second.reconstruction_sha256)
        self.assertEqual(before, after)

    def test_trade_digest_is_deterministic_and_strategy_stays_insufficient(self):
        self._build_p5("closed")
        first = reconstruct_paper_trades(self.snapshot, self._specs())
        second = reconstruct_paper_trades(self.snapshot, self._specs())
        self.assertEqual(
            first.completed[0].trade_sha256,
            second.completed[0].trade_sha256,
        )
        self.assertEqual(
            first.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(
            first.completed[0].strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )

    def test_portfolio_realized_pnl_fabrication_fails_reconciliation(self):
        self._build_p5("closed")
        connection = sqlite3.connect(str(self.p5))
        row = connection.execute(
            "SELECT payload_json FROM local_paper_portfolios WHERE symbol='BTCUSDT'"
        ).fetchone()
        payload = json.loads(row[0])
        payload["portfolio"]["realized_pnl_quote"] = "999"
        material = {key: payload[key] for key in payload if key != "projection_sha256"}
        projection_sha = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload["projection_sha256"] = projection_sha
        connection.execute(
            "UPDATE local_paper_portfolios "
            "SET payload_json=?, projection_sha256=? WHERE symbol='BTCUSDT'",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                projection_sha,
            ),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(TradeReconstructionError):
            reconstruct_paper_trades(self.snapshot, self._specs())

    def test_missing_exit_cannot_be_silently_closed(self):
        self._build_p5("closed")
        connection = sqlite3.connect(str(self.p5))
        with connection:
            connection.execute(
                "DELETE FROM local_paper_fill_events WHERE sequence = 1"
            )
        connection.close()
        with self.assertRaises(TradeReconstructionError):
            reconstruct_paper_trades(self.snapshot, self._specs())

    def test_orphan_fill_fails_closed(self):
        self._build_p5("open")
        connection = sqlite3.connect(str(self.p5))
        with connection:
            connection.execute(
                "UPDATE local_paper_fill_events "
                "SET authorization_sha256=? WHERE sequence=0",
                ("0" * 64,),
            )
        connection.close()
        with self.assertRaises(TradeReconstructionError):
            reconstruct_paper_trades(self.snapshot, self._specs())

    def test_overlapping_episode_is_ambiguous_and_fails_closed(self):
        self._build_p5("open")
        book = reconstruct_paper_trades(self.snapshot, self._specs())
        entry = book.open_trade.entry
        with self.assertRaises(TradeReconstructionError):
            _build_episodes(
                "BTCUSDT",
                (
                    {
                        "fill_event_sha256": entry.fill_event_sha256,
                        "authorization_sha256": entry.authorization_sha256,
                        "intent_sha256": entry.intent_sha256,
                        "order_state_sha256": entry.order_state_sha256,
                        "fill_step_sha256": entry.fill_step_sha256,
                        "fill_index": entry.fill_index,
                        "payload": {
                            key: value
                            for key, value in entry.as_record().items()
                            if key not in {
                                "fill_event_sha256",
                                "authorization_sha256",
                                "intent_sha256",
                                "order_state_sha256",
                                "fill_step_sha256",
                                "fill_index",
                            }
                        },
                    },
                    {
                        "fill_event_sha256": "a" * 64,
                        "authorization_sha256": "b" * 64,
                        "intent_sha256": "c" * 64,
                        "order_state_sha256": "d" * 64,
                        "fill_step_sha256": "e" * 64,
                        "fill_index": 0,
                        "payload": {
                            **{
                                key: value
                                for key, value in entry.as_record().items()
                                if key not in {
                                    "fill_event_sha256",
                                    "authorization_sha256",
                                    "intent_sha256",
                                    "order_state_sha256",
                                    "fill_step_sha256",
                                    "fill_index",
                                }
                            },
                            "fill_time_ms": entry.fill_time_ms + HOUR,
                            "decision_time_ms": entry.decision_time_ms + HOUR,
                        },
                    },
                ),
            )

    def test_cross_symbol_source_fails_closed(self):
        self._build_p5("closed")
        p6 = replace(self._specs()[1], symbol="ETHUSDT")
        with self.assertRaises(TradeReconstructionError):
            reconstruct_paper_trades(
                self.snapshot,
                (self._specs()[0], p6),
            )

    def test_source_has_no_execution_account_risk_network_or_provider_import(self):
        import yatl.analytics.trades as module

        source = inspect.getsource(module)
        for forbidden in (
            "from yatl.execution",
            "import yatl.execution",
            "from yatl.account",
            "import yatl.account",
            "from yatl.risk",
            "import yatl.risk",
            "from yatl.backtest",
            "import yatl.backtest",
            "urllib",
            "http.client",
            "requests",
            "httpx",
            "aiohttp",
            "websockets",
            "socket",
            "openai",
            "anthropic",
            "os.getenv",
            "os.environ",
            "subprocess",
            "/api/v3/order",
            "/fapi",
            "/dapi",
            "withdraw(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
