import hashlib
import inspect
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path

from yatl.analytics import (
    AcceptedTradeFill,
    AnalyticsSourceKind,
    CompletedPaperTrade,
    PerformanceMetricsError,
    PerformanceMetricsStatus,
    StrategyEvidenceState,
    TradeBookStatus,
    UpstreamSourceSpec,
    calculate_performance_metrics,
    reconstruct_paper_trades,
)
from yatl.analytics.timeline_runtime import P6_OBSERVED, SNAPSHOT, START, _create_p5, _create_p6
from yatl.analytics.trade_runtime import _close_fixture


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fill(seed, action, cash_delta, gross_quote, fee="1", slippage="0.5", time_ms=1):
    quantity = "1"
    return AcceptedTradeFill(
        seed * 64,
        (seed.upper() if seed.isalpha() else "a") * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        0,
        action,
        "BTCUSDT",
        time_ms,
        time_ms,
        quantity,
        gross_quote,
        "TEST",
        "10",
        "5",
        gross_quote,
        gross_quote,
        fee,
        slippage,
        cash_delta,
        quantity if action == "ENTER_LONG" else "-1",
    )


def trade(index, pnl, entry_gross="100", holding=1000):
    entry_cash = str(-(Decimal(entry_gross) + Decimal("1")))
    exit_cash = str(-Decimal(entry_cash) + Decimal(pnl))
    exit_gross = str(Decimal(exit_cash) + Decimal("1"))
    entry = fill("1", "ENTER_LONG", entry_cash, entry_gross, time_ms=index * 10000 + 1)
    exit_fill = fill(
        "2",
        "EXIT_LONG",
        exit_cash,
        exit_gross,
        time_ms=index * 10000 + 1 + holding,
    )
    return CompletedPaperTrade(
        index,
        "BTCUSDT",
        entry,
        exit_fill,
        str(Decimal(pnl)),
        "2",
        "1.0",
        holding,
    )


class PerformanceMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p5 = self.root / "p5.sqlite3"
        self.p6 = self.root / "p6.sqlite3"
        _create_p5(self.p5)
        _close_fixture(self.p5)
        _create_p6(self.p6)
        self.specs = (
            UpstreamSourceSpec(
                "SOURCE_P5",
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                "BTCUSDT",
                START + 90,
                self.p5,
                file_sha(self.p5),
            ),
            UpstreamSourceSpec(
                "SOURCE_P6",
                AnalyticsSourceKind.P6_ANALYST_TRACE,
                "BTCUSDT",
                P6_OBSERVED,
                self.p6,
                file_sha(self.p6),
            ),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_real_reconstruction_metrics_are_deterministic_and_read_only(self):
        before = tuple(file_sha(item.database_path) for item in self.specs)
        book = reconstruct_paper_trades(SNAPSHOT, self.specs)
        first = calculate_performance_metrics(book)
        second = calculate_performance_metrics(book)
        after = tuple(file_sha(item.database_path) for item in self.specs)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.metrics_sha256, second.metrics_sha256)
        self.assertEqual(before, after)
        self.assertEqual(first.status, PerformanceMetricsStatus.DESCRIPTIVE)
        self.assertEqual(first.completed_trade_count, 1)

    def test_returns_match_accepted_trade_fields(self):
        book = reconstruct_paper_trades(SNAPSHOT, self.specs)
        report = calculate_performance_metrics(book)
        item = book.completed[0]
        with localcontext() as context:
            context.prec = 256
            gross_expected = (
                Decimal(item.exit.gross_quote) - Decimal(item.entry.gross_quote)
            ) / Decimal(item.entry.gross_quote)
            net_expected = (
                Decimal(item.realized_pnl_quote) / -Decimal(item.entry.cash_delta)
            )
        self.assertEqual(Decimal(report.gross_return), gross_expected)
        self.assertEqual(Decimal(report.net_return), net_expected)

    def test_empty_completed_set_is_explicitly_insufficient(self):
        book = reconstruct_paper_trades(SNAPSHOT, self.specs)
        empty = replace(
            book,
            completed=(),
            open_trade=None,
            final_portfolio=None,
            status=TradeBookStatus.NO_FILLS,
        )
        report = calculate_performance_metrics(empty)
        self.assertEqual(report.status, PerformanceMetricsStatus.INSUFFICIENT_DATA)
        self.assertIsNone(report.gross_return)
        self.assertIsNone(report.net_return)
        self.assertIsNone(report.win_rate)
        self.assertIsNone(report.average_holding_time_ms)
        self.assertEqual(report.realized_pnl_quote, "0")

    def test_win_loss_breakeven_and_drawdown_are_exact(self):
        from yatl.analytics.metrics import _aggregate, _trade_metric

        trades = (
            trade(0, "10"),
            trade(1, "-5"),
            trade(2, "-20"),
            trade(3, "7"),
        )
        values = _aggregate(tuple(_trade_metric(item) for item in trades))
        self.assertEqual(values.winning_trades, 2)
        self.assertEqual(values.losing_trades, 2)
        self.assertEqual(values.breakeven_trades, 0)
        self.assertEqual(values.completed_trade_count, 4)
        self.assertEqual(Decimal(values.win_rate), Decimal("0.5"))
        self.assertEqual(Decimal(values.maximum_realized_drawdown_quote), Decimal("25"))
        self.assertEqual(Decimal(values.realized_pnl_quote), Decimal("-8"))

    def test_breakeven_trade_is_not_a_win_or_loss(self):
        from yatl.analytics.metrics import _aggregate, _trade_metric

        values = _aggregate((_trade_metric(trade(0, "0")),))
        self.assertEqual(values.winning_trades, 0)
        self.assertEqual(values.losing_trades, 0)
        self.assertEqual(values.breakeven_trades, 1)
        self.assertEqual(values.win_rate, "0")

    def test_holding_aggregates_are_decimal_safe(self):
        from yatl.analytics.metrics import _aggregate, _trade_metric

        values = _aggregate(
            (
                _trade_metric(trade(0, "1", holding=1000)),
                _trade_metric(trade(1, "1", holding=2001)),
            )
        )
        self.assertEqual(values.total_holding_time_ms, 3001)
        self.assertEqual(values.minimum_holding_time_ms, 1000)
        self.assertEqual(values.maximum_holding_time_ms, 2001)
        self.assertEqual(Decimal(values.average_holding_time_ms), Decimal("1500.5"))

    def test_append_trade_keeps_bounded_monotonic_counts_costs_and_drawdown(self):
        from yatl.analytics.metrics import _aggregate, _trade_metric

        first = _aggregate((_trade_metric(trade(0, "10")),))
        second = _aggregate(
            (
                _trade_metric(trade(0, "10")),
                _trade_metric(trade(1, "-20")),
            )
        )
        self.assertGreaterEqual(second.completed_trade_count, first.completed_trade_count)
        self.assertGreaterEqual(Decimal(second.total_fee_quote), Decimal(first.total_fee_quote))
        self.assertGreaterEqual(
            Decimal(second.total_slippage_quote),
            Decimal(first.total_slippage_quote),
        )
        self.assertGreaterEqual(
            Decimal(second.maximum_realized_drawdown_quote),
            Decimal(first.maximum_realized_drawdown_quote),
        )

    def test_report_tamper_is_rejected(self):
        book = reconstruct_paper_trades(SNAPSHOT, self.specs)
        report = calculate_performance_metrics(book)
        with self.assertRaises(PerformanceMetricsError):
            replace(report, realized_pnl_quote="999")

    def test_strategy_evidence_is_never_upgraded(self):
        book = reconstruct_paper_trades(SNAPSHOT, self.specs)
        report = calculate_performance_metrics(book)
        self.assertEqual(
            report.strategy_evidence,
            StrategyEvidenceState.INSUFFICIENT_EVIDENCE,
        )

    def test_invalid_input_fails_closed(self):
        for value in (None, object(), ()):
            with self.subTest(value=type(value)), self.assertRaises(PerformanceMetricsError):
                calculate_performance_metrics(value)

    def test_source_has_no_execution_backtest_account_risk_network_or_provider_import(self):
        import yatl.analytics.metrics as module

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
