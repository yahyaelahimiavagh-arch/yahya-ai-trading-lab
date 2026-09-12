import argparse
import sys
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .market_data import HOSTS, INTERVALS, MarketDataError, candles, ping, save_csv
from .account import AccountError, read_account
from .paper_workflow import PaperWorkflowError, load_and_validate
from .strategy import (DecisionReason, LongSetup, StrategyAction,
                       StrategyContext, StrategyContractError, StrategyDecision,
                       StrategyIdentity, FeatureError, atr, ema, rolling_high,
                       rolling_low, rsi, simple_return, sma, RegimeError,
                       classify_regime, ParameterRule, RegistryError,
                       StrategyDefinition, StrategyRegistry,
                       TREND_PULLBACK_CONFIGURATION, TREND_PULLBACK_IDENTITY,
                       TrendStrategyError, evaluate_trend_pullback,
                       BREAKOUT_CONFIGURATION, BREAKOUT_IDENTITY,
                       BreakoutStrategyError, evaluate_breakout,
                       FIXED_RESEARCH_QUANTITY, ResearchSignalAdapter,
                       SignalAdapterError, EvaluationError, EvaluationPlan,
                       EvidenceLabel, SymbolEvidence, assess_evidence,
                       CandidateRunError, candidate_matrix_sha256,
                       run_and_write_candidate_matrix,
                       P3AuditError, audit_p3)
from .risk import (PortfolioRiskState, RiskContractError, RiskDecision,
                   RiskDisposition, RiskReason, RiskRequest,
                   RiskSizingError, size_entry,
                   RiskLimitError, assess_entry_limits)
from .backtest import (AcceptedBacktestDataset, ArtifactError, BacktestClock,
                       BacktestClockError, BacktestConfigError,
                       BacktestContractError, BacktestLoadError, BacktestSpec,
                       DecisionEvent, EXECUTION_PRICE_POLICY, FillModelError, FillReason,
                       FillReference, CostModelError, IntentAction, MarketSnapshot,
                       MetricsError, PaperFillEngine, PortfolioError, PortfolioLedger,
                       EquityPoint, PaperIntent, apply_costs, artifact_json,
                       build_run_manifest, calculate_metrics, write_run_manifest,
                       ScenarioError, run_real_scenario_matrix,
                       P2AuditError, audit_p2,
                       latest_spec_from_manifest, load_accepted_dataset)
from .data import (BinancePublicRestClient, Candle, CandleStore,
                   ClosedCandleConflict, DATA_SOURCE, HistoricalDownloadError,
                   INTERVAL_MILLISECONDS, NormalizationError, PublicRestError,
                   QualityError, StorageError, SYMBOLS, analyze_open_times,
                   PublicKlineStream, StreamError, download_range,
                   DatasetError, HealthError, build_datasets, build_health_report,
                   normalize_rest_kline, write_manifest, AuditError, audit_p1_manifest,
                   CheckpointRebuildError, rebuild_accepted_database)


def _storage_runtime_check():
    base = Candle(
        source=DATA_SOURCE,
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=1_699_999_200_000,
        close_time_ms=1_700_002_799_999,
        open="26000.10000000",
        high="26250.00000000",
        low="25900.00000000",
        close="26100.25000000",
        base_volume="123.45000000",
        quote_volume="3210000.12345678",
        trade_count=1234,
        is_closed=False,
    )
    updated = replace(base, close="26150.25000000", base_volume="124.00000000",
                      quote_volume="3220000.00000000", trade_count=1240)
    finalized = replace(updated, is_closed=True)
    Path("data").mkdir(exist_ok=True)
    database = Path("data") / f"p1-storage-{uuid4().hex}.sqlite3"
    sidecars = (database, Path(f"{database}-wal"), Path(f"{database}-shm"))
    try:
        with CandleStore(database) as store:
            statuses = (store.write(base), store.write(base), store.write(updated),
                        store.write(finalized))
            if statuses != ("inserted", "unchanged", "updated", "finalized"):
                raise StorageError("Storage lifecycle did not complete safely")
        with CandleStore(database) as reopened:
            if reopened.schema_version() != 1 or reopened.count() != 1:
                raise StorageError("Reopened database failed verification")
            if reopened.get(finalized.key) != finalized:
                raise StorageError("Stored candle changed after database reopen")
            try:
                reopened.write(updated)
            except ClosedCandleConflict:
                pass
            else:
                raise StorageError("Closed candle protection failed")
    finally:
        for path in sidecars:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise StorageError("Cannot remove temporary storage-check data") from None


def _backtest_contract_runtime_check():
    decision = 1_699_999_200_000

    def completed(interval):
        duration = INTERVAL_MILLISECONDS[interval]
        opened = (decision // duration) * duration - duration
        return (Candle(
            source=DATA_SOURCE, symbol="BTCUSDT", interval=interval,
            open_time_ms=opened, close_time_ms=opened + duration - 1,
            open="100", high="110", low="90", close="105",
            base_volume="10", quote_volume="1000", trade_count=20,
            is_closed=True,
        ),)

    spec = BacktestSpec("BTCUSDT", decision, decision + 86_400_000)
    view = MarketSnapshot(symbol=spec.symbol, decision_time_ms=decision,
                          primary=completed("1h"), context=completed("15m"),
                          regime=completed("4h"))
    if view.latest_primary.close_time_ms >= view.decision_time_ms:
        raise BacktestContractError("Point-in-time boundary failed")
    return spec, view


def _backtest_fill_runtime_check():
    spec, view = _backtest_contract_runtime_check()
    event = DecisionEvent(0, view.decision_time_ms, view.decision_time_ms, view)
    duration = INTERVAL_MILLISECONDS["1h"]
    bar = Candle(
        source=DATA_SOURCE, symbol=spec.symbol, interval="1h",
        open_time_ms=view.decision_time_ms,
        close_time_ms=view.decision_time_ms + duration - 1,
        open="100", high="111", low="94", close="105",
        base_volume="10", quote_volume="1000", trade_count=20,
        is_closed=True,
    )
    fills = PaperFillEngine(spec.symbol).process(
        event, PaperIntent(IntentAction.ENTER_LONG, view.decision_time_ms,
                           "1", "95", "110"), bar,
    )
    if len(fills) != 2 or fills[-1].reason.value != "AMBIGUOUS_STOP_PRIORITY":
        raise FillModelError("Conservative fill lifecycle failed")
    return fills


def _backtest_cost_runtime_check():
    references = _backtest_fill_runtime_check()
    start = references[0].decision_time_ms
    spec = BacktestSpec(references[0].symbol, start, start + 3_600_000)
    fills = tuple(apply_costs(reference, spec) for reference in references)
    fee = sum((item.fee_quote for item in fills), start=Decimal(0))
    slippage = sum((item.slippage_quote for item in fills), start=Decimal(0))
    return fills, fee, slippage


def _backtest_portfolio_runtime_check():
    start = 1_699_999_200_000
    spec = BacktestSpec("BTCUSDT", start, start + 2 * 3_600_000,
                        initial_cash="1000")
    references = (
        FillReference(IntentAction.ENTER_LONG, spec.symbol, start, start,
                      "2", "100", FillReason.NEXT_PRIMARY_OPEN),
        FillReference(IntentAction.EXIT_LONG, spec.symbol, start + 3_600_000,
                      start + 3_600_000, "2", "100", FillReason.SCRIPTED_EXIT),
    )
    ledger = PortfolioLedger(spec)
    ledger.apply_many(tuple(apply_costs(item, spec) for item in references))
    view = ledger.snapshot("100")
    if view.asset_quantity != 0 or view.equity_quote != view.cash:
        raise PortfolioError("Portfolio round trip did not balance")
    return view


def _backtest_completed_run():
    start = 1_699_999_200_000
    spec = BacktestSpec("BTCUSDT", start, start + 3 * 3_600_000,
                        initial_cash="1000")
    ledger = PortfolioLedger(spec)
    points = [EquityPoint(start, ledger.snapshot("100"))]
    entry = FillReference(IntentAction.ENTER_LONG, spec.symbol, start + 3_600_000,
                          start + 3_600_000, "2", "100",
                          FillReason.NEXT_PRIMARY_OPEN)
    entry_fill = apply_costs(entry, spec)
    ledger.apply(entry_fill)
    points.append(EquityPoint(start + 3_600_000, ledger.snapshot("100")))
    exit_fill = FillReference(IntentAction.EXIT_LONG, spec.symbol,
                              start + 2 * 3_600_000, start + 2 * 3_600_000,
                              "2", "110", FillReason.SCRIPTED_EXIT)
    costed_exit = apply_costs(exit_fill, spec)
    ledger.apply(costed_exit)
    points.append(EquityPoint(start + 2 * 3_600_000, ledger.snapshot("110")))
    return spec, (entry_fill, costed_exit), calculate_metrics(tuple(points))


def _backtest_metrics_runtime_check():
    _, _, report = _backtest_completed_run()
    if report.gross_pnl_quote != Decimal("20") or report.trade_count != 1:
        raise MetricsError("Hand-computed performance scenario failed")
    return report


def _backtest_artifact_runtime_check():
    spec, fills, report = _backtest_completed_run()

    def closed(interval, opened):
        duration = INTERVAL_MILLISECONDS[interval]
        return Candle(DATA_SOURCE, spec.symbol, interval, opened,
                      opened + duration - 1, "100", "110", "90", "100",
                      "10", "1000", 10, True)

    four_hours = INTERVAL_MILLISECONDS["4h"]
    dataset = AcceptedBacktestDataset(
        spec, spec.end_time_ms + 1,
        (closed("1h", spec.start_time_ms - 3_600_000),),
        (closed("15m", spec.start_time_ms - 900_000),),
        (closed("4h", (spec.start_time_ms // four_hours - 1) * four_hours),),
    )
    manifest = build_run_manifest(dataset, fills, report)
    encoded = artifact_json(manifest)
    Path("data").mkdir(exist_ok=True)
    target = Path("data") / f"p2-artifact-check-{uuid4().hex}.json"
    try:
        write_run_manifest(manifest, target)
        if target.read_text(encoding="utf-8") != encoded:
            raise ArtifactError("Atomic artifact bytes changed after write")
    finally:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            raise ArtifactError("Cannot remove temporary artifact check") from None
    return manifest


def _strategy_contract_runtime_check():
    _, snapshot = _backtest_contract_runtime_check()
    context = StrategyContext(StrategyIdentity("TREND_PULLBACK", "1.0.0"), snapshot)
    no_trade = StrategyDecision(context, StrategyAction.NO_TRADE,
                                DecisionReason.SETUP_ABSENT)
    entry = StrategyDecision(context, StrategyAction.ENTER_LONG,
                             DecisionReason.TREND_PULLBACK_ENTRY,
                             LongSetup("105", "95", "115"))
    if no_trade.context_sha256 != entry.context_sha256:
        raise StrategyContractError("Strategy context identity changed across decisions")
    return no_trade, entry


def _risk_contract_runtime_check():
    _, entry = _strategy_contract_runtime_check()
    flat = PortfolioRiskState(
        entry.symbol, entry.decision_time_ms, "10000", "10000", "0", "105",
        "10100",
    )
    blocked_request = RiskRequest(entry, EvidenceLabel.INSUFFICIENT_EVIDENCE, flat)
    blocked = RiskDecision(
        blocked_request, RiskDisposition.REJECT, RiskReason.EVIDENCE_NOT_QUALIFIED,
    )
    exit_decision = StrategyDecision(
        entry.context, StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT,
    )
    positioned = PortfolioRiskState(
        exit_decision.symbol, exit_decision.decision_time_ms, "9900", "9000",
        "0.01", "105", "10100", "-100", 3, 1, True,
    )
    exit_request = RiskRequest(
        exit_decision, EvidenceLabel.INSUFFICIENT_EVIDENCE, positioned,
    )
    approved_exit = RiskDecision(
        exit_request, RiskDisposition.APPROVE_PAPER,
        RiskReason.EXIT_REDUCES_RISK, "0.01",
    )
    return blocked, approved_exit


def _risk_sizing_runtime_check():
    blocked, _ = _risk_contract_runtime_check()
    try:
        size_entry(blocked.request)
    except RiskSizingError:
        pass
    else:
        raise RiskSizingError("Insufficient-evidence entry was sized")
    qualified_fixture = replace(
        blocked.request, evidence_label=EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH,
    )
    result = size_entry(qualified_fixture)
    if result != size_entry(qualified_fixture):
        raise RiskSizingError("Position sizing replay mismatch")
    return result


def _risk_limit_runtime_check():
    position_size = _risk_sizing_runtime_check()
    normal = assess_entry_limits(position_size)
    low_cash_request = replace(
        position_size.request,
        portfolio=replace(position_size.request.portfolio, cash_quote="500"),
    )
    low_cash = assess_entry_limits(size_entry(low_cash_request))
    replay = (assess_entry_limits(position_size),
              assess_entry_limits(size_entry(low_cash_request)))
    if (normal, low_cash) != replay:
        raise RiskLimitError("Entry-limit replay mismatch")
    return normal, low_cash


def _strategy_adapter_runtime_check():
    start = 1_699_999_200_000

    def snapshot(decision):
        def completed(interval):
            duration = INTERVAL_MILLISECONDS[interval]
            opened = (decision // duration) * duration - duration
            return (Candle(
                DATA_SOURCE, "BTCUSDT", interval, opened,
                opened + duration - 1, "100", "106", "99", "100",
                "10", "1000", 20, True,
            ),)
        return MarketSnapshot("BTCUSDT", decision, completed("1h"),
                              completed("15m"), completed("4h"))

    def fill_bar(decision, price, low, high):
        return Candle(
            DATA_SOURCE, "BTCUSDT", "1h", decision, decision + 3_600_000 - 1,
            price, high, low, price, "10", "1000", 20, True,
        )

    adapter = ResearchSignalAdapter(TREND_PULLBACK_IDENTITY, "BTCUSDT")
    first_view = snapshot(start)
    first_event = DecisionEvent(0, start, start, first_view)
    entry = StrategyDecision(
        StrategyContext(TREND_PULLBACK_IDENTITY, first_view),
        StrategyAction.ENTER_LONG, DecisionReason.TREND_PULLBACK_ENTRY,
        LongSetup("100", "95", "110"))
    first = adapter.process(first_event, entry,
                            fill_bar(start, "100", "99", "106"))

    end = start + 3_600_000
    second_view = snapshot(end)
    second_event = DecisionEvent(1, end, end, second_view)
    exit_decision = StrategyDecision(
        StrategyContext(TREND_PULLBACK_IDENTITY, second_view),
        StrategyAction.EXIT_LONG, DecisionReason.STRATEGY_EXIT)
    second = adapter.process(second_event, exit_decision,
                             fill_bar(end, "105", "104", "106"))

    spec = BacktestSpec("BTCUSDT", start, end + 3_600_000,
                        initial_cash="1000")
    costed = tuple(apply_costs(item, spec)
                   for item in first.fills + second.fills)
    ledger = PortfolioLedger(spec)
    ledger.apply_many(costed)
    final = ledger.snapshot("105")
    if (adapter.has_position or final.asset_quantity != 0
            or final.closed_trades != 1
            or final.total_fee_quote <= 0 or final.total_slippage_quote <= 0):
        raise SignalAdapterError("Research adapter round trip failed")
    return first, second, final


def _strategy_evaluation_runtime_check():
    day = 86_400_000

    def build_plan(days):
        return EvaluationPlan(
            TREND_PULLBACK_IDENTITY, TREND_PULLBACK_CONFIGURATION.sha256,
            1000 * day, 1180 * day, 1180 * day, (1180 + days) * day)

    def evidence(plan, symbol, **changes):
        values = {
            "symbol": symbol, "plan_sha256": plan.sha256,
            "configuration_sha256": plan.configuration_sha256,
            "evaluation_start_ms": plan.evaluation_start_ms,
            "evaluation_end_ms": plan.evaluation_end_ms,
            "dataset_sha256": ("a" if symbol == "BTCUSDT" else "b") * 64,
            "trade_count": 30, "total_return": "0.12",
            "maximum_drawdown": "0.08", "total_cost_quote": "10",
            "buy_hold_return": "0.05",
            "buy_hold_maximum_drawdown": "0.15",
            "segment_returns": ("0.03", "0.04", "0.05"),
            "replay_equal": True, "point_in_time_verified": True,
            "future_isolation_verified": True,
        }
        values.update(changes)
        return SymbolEvidence(**values)

    short = build_plan(30)
    insufficient = assess_evidence(
        short, tuple(evidence(short, symbol, trade_count=2)
                     for symbol in SYMBOLS))
    full = build_plan(180)
    rejected = assess_evidence(
        full, tuple(evidence(full, symbol, replay_equal=False)
                    for symbol in SYMBOLS))
    qualified = assess_evidence(
        full, tuple(evidence(full, symbol) for symbol in SYMBOLS))
    if (insufficient.label is not EvidenceLabel.INSUFFICIENT_EVIDENCE
            or rejected.label is not EvidenceLabel.REJECTED
            or qualified.label is not EvidenceLabel.QUALIFIED_FOR_P4_RESEARCH
            or qualified != assess_evidence(
                full, tuple(evidence(full, symbol) for symbol in SYMBOLS))):
        raise EvaluationError("Evaluation label or replay gate failed")
    return insufficient, rejected, qualified


def _strategy_feature_runtime_check():
    start = 1_699_977_600_000
    duration = INTERVAL_MILLISECONDS["1h"]
    values = []
    for index, close in enumerate(("10", "11", "12", "13")):
        opened = start + index * duration
        price = Decimal(close)
        values.append(Candle(
            DATA_SOURCE, "BTCUSDT", "1h", opened, opened + duration - 1,
            close, format(price + 1, "f"), format(price - 1, "f"), close,
            "0", "0", 0, True,
        ))
    candles = tuple(values)
    decision = start + 4 * duration
    results = (simple_return(candles, 2, decision),
               rolling_high(candles, 3, decision),
               rolling_low(candles, 3, decision),
               sma(candles, 3, decision), ema(candles, 3, decision),
               atr(candles, 3, decision), rsi(candles, 3, decision))
    if not all(item.available for item in results):
        raise FeatureError("Strategy feature runtime vector is unavailable")
    return results


def main():
    parser = argparse.ArgumentParser(description="YATL paper-only data and Testnet account tools")
    parser.add_argument("--environment", choices=HOSTS, default="testnet")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ping", help="Check public API connectivity")
    account = commands.add_parser("account", help="Read Spot Testnet account summary (no orders)")
    account.add_argument("--env-file", default=".env", help="Explicit local environment file")
    paper = commands.add_parser("paper-check", help="Validate the local P0 paper workflow fixture")
    paper.add_argument("--fixture", default="fixtures/p0-paper-workflows.json")
    commands.add_parser("data-check", help="Check credential-free Binance Spot public data")
    commands.add_parser("history-check", help="Check bounded historical pagination for P1")
    commands.add_parser("normalize-check", help="Normalize live public REST klines for P1")
    commands.add_parser("storage-check", help="Verify temporary SQLite candle storage for P1")
    commands.add_parser("quality-check", help="Verify deterministic gap and duplicate detection")
    commands.add_parser("backtest-contract-check",
                        help="Verify the local point-in-time P2 contract")
    commands.add_parser("backtest-fill-check",
                        help="Verify the local conservative P2 fill lifecycle")
    commands.add_parser("backtest-cost-check",
                        help="Verify exact Decimal P2 fee and slippage accounting")
    commands.add_parser("backtest-portfolio-check",
                        help="Verify the exact P2 portfolio ledger")
    commands.add_parser("backtest-metrics-check",
                        help="Verify deterministic P2 performance metrics")
    commands.add_parser("backtest-artifact-check",
                        help="Verify canonical atomic P2 run artifacts")
    scenarios = commands.add_parser("backtest-scenario-check",
                                    help="Run fixed P2 scenarios on accepted real data")
    scenarios.add_argument("--database", default="data/p1/market.sqlite3")
    scenarios.add_argument("--manifest", default="manifests/p1-market-data.json")
    scenarios.add_argument("--hours", type=int, default=24)
    p2_audit = commands.add_parser("p2-audit",
                                   help="Run the complete local P2 acceptance audit")
    p2_audit.add_argument("--database", default="data/p1/market.sqlite3")
    p2_audit.add_argument("--manifest", default="manifests/p1-market-data.json")
    p2_audit.add_argument("--hours", type=int, default=24)
    commands.add_parser("strategy-contract-check",
                        help="Verify the P3 research-only signal boundary")
    commands.add_parser("risk-contract-check",
                        help="Verify the P4 paper-only risk boundary")
    commands.add_parser("risk-sizing-check",
                        help="Verify exact cost-aware P4 position sizing")
    commands.add_parser("risk-limit-check",
                        help="Verify P4 cash, notional and exposure limits")
    commands.add_parser("strategy-feature-check",
                        help="Verify point-in-time Decimal P3 features")
    commands.add_parser("strategy-registry-check",
                        help="Verify immutable versioned research configuration")
    trend = commands.add_parser("strategy-trend-check",
                                help="Evaluate frozen trend-pullback research rules")
    trend.add_argument("--database", default="data/p1/market.sqlite3")
    trend.add_argument("--manifest", default="manifests/p1-market-data.json")
    breakout = commands.add_parser("strategy-breakout-check",
                                   help="Evaluate frozen range-breakout research rules")
    breakout.add_argument("--database", default="data/p1/market.sqlite3")
    breakout.add_argument("--manifest", default="manifests/p1-market-data.json")
    commands.add_parser("strategy-adapter-check",
                        help="Verify P3 decisions through the P2 paper lifecycle")
    commands.add_parser("strategy-evaluation-check",
                        help="Verify pre-registered P3 evidence labels")
    candidate_runs = commands.add_parser(
        "strategy-candidate-check",
        help="Run the frozen P3 candidates and baselines on accepted data")
    candidate_runs.add_argument("--database", default="data/p1/market.sqlite3")
    candidate_runs.add_argument("--manifest", default="manifests/p1-market-data.json")
    candidate_runs.add_argument("--output", default="data/p3/p3-009-evidence")
    p3_audit = commands.add_parser(
        "p3-audit", help="Run the complete P3 acceptance audit")
    p3_audit.add_argument("--database", default="data/p1/market.sqlite3")
    p3_audit.add_argument("--manifest", default="manifests/p1-market-data.json")
    p3_audit.add_argument("--evidence", default="data/p3/p3-009-evidence")
    regime = commands.add_parser("strategy-regime-check",
                                 help="Classify accepted closed 4h data for both symbols")
    regime.add_argument("--database", default="data/p1/market.sqlite3")
    regime.add_argument("--manifest", default="manifests/p1-market-data.json")
    loader = commands.add_parser("backtest-load-check",
                                 help="Load accepted P1 data read-only for P2")
    loader.add_argument("--database", default="data/p1/market.sqlite3")
    loader.add_argument("--manifest", default="manifests/p1-market-data.json")
    loader.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    loader.add_argument("--hours", type=int, default=24)
    clock = commands.add_parser("backtest-clock-check",
                                help="Replay the deterministic P2 event clock")
    clock.add_argument("--database", default="data/p1/market.sqlite3")
    clock.add_argument("--manifest", default="manifests/p1-market-data.json")
    clock.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    clock.add_argument("--hours", type=int, default=24)
    stream = commands.add_parser("stream-check", help="Read bounded public Spot kline messages")
    stream.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    stream.add_argument("--interval", choices=INTERVAL_MILLISECONDS, default="1h")
    stream.add_argument("--messages", type=int, choices=range(1, 11), default=1)
    health = commands.add_parser("health-check", help="Build deterministic P1 data health report")
    health.add_argument("--json", action="store_true", help="Print deterministic JSON")
    dataset = commands.add_parser("dataset-build", help="Build fixed public-real P1 datasets")
    dataset.add_argument("--days", type=int, default=30)
    dataset.add_argument("--database", default="data/p1/market.sqlite3")
    dataset.add_argument("--manifest", default="manifests/p1-market-data.json")
    restore = commands.add_parser(
        "dataset-restore-checkpoint",
        help="Rebuild the accepted public dataset without changing its manifest")
    restore.add_argument("--database", default="data/p1/market.sqlite3")
    restore.add_argument("--manifest", default="manifests/p1-market-data.json")
    audit = commands.add_parser("p1-audit", help="Audit the fixed P1 acceptance manifest")
    audit.add_argument("--manifest", default="manifests/p1-market-data.json")
    collect = commands.add_parser("candles", help="Save recent candles to CSV")
    collect.add_argument("--symbol", default="BTCUSDT")
    collect.add_argument("--interval", choices=sorted(INTERVALS), default="1h")
    collect.add_argument("--limit", type=int, default=100)
    collect.add_argument("--output", help="New CSV path; existing files are protected")
    args = parser.parse_args()
    try:
        if args.command == "ping":
            ping(args.environment)
            print(f"OK: {args.environment} public API")
        elif args.command == "account":
            summary = read_account(args.env_file, args.environment)
            print("OK: authenticated Spot Testnet account read")
            print(f"SPOT: {summary['assets']} assets; {summary['nonzero_assets']} with nonzero test balances")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No execution endpoints")
        elif args.command == "paper-check":
            summaries = load_and_validate(args.fixture)
            print("OK: P0 manual paper workflow fixture")
            for item in summaries:
                print(f"{item['symbol']}: entry={item['entry']} stop={item['stop']} "
                      f"target={item['target']} size={item['position_size']} "
                      f"max_loss={item['max_loss']} R:R={item['risk_reward_ratio']}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No exchange order submitted")
        elif args.command == "data-check":
            client = BinancePublicRestClient()
            server_time = client.server_time()
            print(f"OK: Binance Spot public server time ({server_time})")
            for symbol in SYMBOLS:
                info = client.exchange_info(symbol)
                rows = client.klines(symbol, "1h", limit=2)
                print(f"{symbol}: status={info['status']} 1h_klines={len(rows)}")
            print("PUBLIC DATA ONLY | No credentials | No execution endpoints")
        elif args.command == "history-check":
            client = BinancePublicRestClient()
            server_time = client.server_time()
            for symbol in SYMBOLS:
                for interval, duration in INTERVAL_MILLISECONDS.items():
                    end = (server_time // duration) * duration
                    start = end - (2 * duration)
                    batch = download_range(client, symbol, interval, start, end, page_limit=1)
                    print(f"{symbol} {interval}: rows={len(batch.rows)} pages={batch.pages}")
            print("PUBLIC CLOSED-RANGE CHECK | No persistence | No credentials | No execution")
        elif args.command == "normalize-check":
            client = BinancePublicRestClient()
            server_time = client.server_time()
            for symbol in SYMBOLS:
                for interval in INTERVAL_MILLISECONDS:
                    rows = client.klines(symbol, interval, limit=2)
                    candles = [normalize_rest_kline(symbol, interval, row, server_time)
                               for row in rows]
                    states = ",".join("closed" if candle.is_closed else "open" for candle in candles)
                    print(f"{symbol} {interval}: rows={len(candles)} states={states}")
            print("CANONICAL PUBLIC CANDLES | No persistence | No credentials | No execution")
        elif args.command == "storage-check":
            _storage_runtime_check()
            print("OK: SQLite migration, idempotency, finalization, reopen and conflict protection")
            print("TEMPORARY LOCAL DATA ONLY | No credentials | No execution endpoints")
        elif args.command == "quality-check":
            duration = INTERVAL_MILLISECONDS["1h"]
            start = 1_699_999_200_000
            current_open = start + (5 * duration)
            report = analyze_open_times(
                DATA_SOURCE, "BTCUSDT", "1h", start, current_open + duration,
                [start, start + duration, start + duration,
                 start + (3 * duration), start + (4 * duration)],
                current_open + 1,
            )
            expected_repair = ((start + (2 * duration), start + (3 * duration)),)
            if (report.duplicate_open_times != (start + duration,)
                    or report.repair_ranges != expected_repair
                    or not report.expected_current_open_missing):
                raise QualityError("Quality classification failed")
            print("OK: duplicate, historical gap and expected open interval classified")
            print("BOUNDED REPAIR RANGES ONLY | No network | No credentials | No execution")
        elif args.command == "backtest-contract-check":
            _backtest_contract_runtime_check()
            print(f"OK: point-in-time backtest contract; price_policy={EXECUTION_PRICE_POLICY}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No exchange order")
        elif args.command == "backtest-fill-check":
            fills = _backtest_fill_runtime_check()
            print(f"OK: paper fill-reference lifecycle; references={len(fills)} "
                  f"exit_reason={fills[-1].reason.value} costs_pending=P2-005")
            print("PAPER ONLY | Local simulation | No credentials | No exchange order")
        elif args.command == "backtest-cost-check":
            fills, fee, slippage = _backtest_cost_runtime_check()
            cash = sum((item.cash_delta for item in fills), start=Decimal(0))
            print(f"OK: exact Decimal costs; fills={len(fills)} fee_quote={fee} "
                  f"slippage_quote={slippage} net_cash_delta={cash}")
            print("PAPER ONLY | Explicit adverse costs | No credentials | No exchange order")
        elif args.command == "backtest-portfolio-check":
            view = _backtest_portfolio_runtime_check()
            print(f"OK: balanced portfolio round trip; cash={view.cash} "
                  f"realized_pnl={view.realized_pnl_quote} closed_trades={view.closed_trades}")
            print("PAPER ONLY | Exact local ledger | No credentials | No exchange order")
        elif args.command == "backtest-metrics-check":
            report = _backtest_metrics_runtime_check()
            print(f"OK: deterministic performance metrics; trades={report.trade_count} "
                  f"gross_pnl={report.gross_pnl_quote} net_pnl={report.net_pnl_quote} "
                  f"max_drawdown={report.maximum_drawdown}")
            print("PAPER ONLY | Decimal descriptive metrics | No credentials | No exchange order")
        elif args.command == "backtest-artifact-check":
            manifest = _backtest_artifact_runtime_check()
            print(f"OK: canonical atomic run artifact; input_sha256={manifest['input_sha256']} "
                  f"trades={len(manifest['trades'])}")
            print("PAPER ONLY | No paths or credentials | No exchange order")
        elif args.command == "backtest-scenario-check":
            results = run_real_scenario_matrix(args.database, args.manifest,
                                               hours=args.hours)
            print(f"OK: accepted real-data scenario matrix; runs={len(results)}")
            for result in results:
                drag = result.zero_cost_net_pnl_quote - result.report.net_pnl_quote
                print(f"{result.symbol} {result.name}: trades={result.report.trade_count} "
                      f"net_pnl={result.report.net_pnl_quote} cost_drag={drag}")
            print("PAPER ONLY | Public-real data | No credentials | No exchange order")
        elif args.command == "p2-audit":
            result = audit_p2(args.database, args.manifest, hours=args.hours)
            print(f"OK: P2 final acceptance audit; symbols={result.symbols} "
                  f"scenarios={result.scenarios} artifacts={result.artifacts} "
                  f"trades={result.trades}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No credentials | No exchange order")
        elif args.command == "strategy-contract-check":
            no_trade, entry = _strategy_contract_runtime_check()
            print(f"OK: P3 signal contract; actions={no_trade.action.value}/"
                  f"{entry.action.value} context_sha256={entry.context_sha256}")
            print("PAPER ONLY | No sizing | No credentials | No exchange order")
        elif args.command == "risk-contract-check":
            blocked, approved_exit = _risk_contract_runtime_check()
            if (blocked, approved_exit) != _risk_contract_runtime_check():
                raise RiskContractError("Risk contract replay mismatch")
            print(f"OK: P4 risk contract; entry={blocked.disposition.value}/"
                  f"{blocked.reason.value} "
                  f"exit_under_kill_switch={approved_exit.disposition.value} "
                  f"request_sha256={blocked.request_sha256}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No credentials | No exchange order")
        elif args.command == "risk-sizing-check":
            result = _risk_sizing_runtime_check()
            print(f"OK: P4 exact position sizing; "
                  f"qualified_fixture_quantity={result.quantity} "
                  f"risk_budget={result.risk_budget_quote} "
                  f"planned_loss={result.planned_loss_quote} "
                  f"request_sha256={result.request_sha256}")
            print("current_candidates=BLOCKED/INSUFFICIENT_EVIDENCE | "
                  "PAPER ONLY | No credentials | No exchange order")
        elif args.command == "risk-limit-check":
            normal, low_cash = _risk_limit_runtime_check()
            print(f"OK: P4 entry limits; normal={normal.status.value}/"
                  f"{normal.reason.value} low_cash={low_cash.status.value}/"
                  f"{low_cash.reason.value} "
                  f"notional={normal.entry_notional_quote} "
                  f"cap={normal.position_limit_quote}")
            print("PAPER ONLY | No approval | No leverage | No exchange order")
        elif args.command == "strategy-registry-check":
            identity = StrategyIdentity("RESEARCH_FIXTURE", "1.0.0")
            registry = StrategyRegistry((StrategyDefinition(identity, (
                ParameterRule("lookback", "integer", 2, 200),
                ParameterRule("threshold", "decimal", "0", "1"),
            )),))
            first = registry.configure(identity, {"lookback": 20, "threshold": "0.0020"})
            replay = registry.configure(identity, {"threshold": "0.002", "lookback": 20})
            changed = registry.configure(identity, {"lookback": 21, "threshold": "0.002"})
            if first.to_json() != replay.to_json() or first.sha256 != replay.sha256 or first.sha256 == changed.sha256:
                raise RegistryError("Configuration replay gate failed")
            rejected = 0
            for invalid in ({"lookback": 201, "threshold": "0.002"},
                            {"lookback": 20, "threshold": "0.002", "quantity": 1}):
                try:
                    registry.configure(identity, invalid)
                except RegistryError:
                    rejected += 1
            if rejected != 2:
                raise RegistryError("Configuration rejection gate failed")
            print("OK: research registry; replay_equal=true changed_digest=true rejected=2")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No credentials | No execution")
        elif args.command == "strategy-trend-check":
            for symbol in SYMBOLS:
                spec = latest_spec_from_manifest(args.manifest, symbol, hours=24)
                dataset = load_accepted_dataset(args.database, args.manifest, spec)
                context = StrategyContext(
                    TREND_PULLBACK_IDENTITY,
                    dataset.snapshot_at(spec.start_time_ms))
                decision = evaluate_trend_pullback(context)
                if decision != evaluate_trend_pullback(context):
                    raise TrendStrategyError("Trend-pullback replay mismatch")
                print(f"OK: {symbol} action={decision.action.value} "
                      f"reason={decision.reason.value} replay_equal=true")
            print(f"config_sha256={TREND_PULLBACK_CONFIGURATION.sha256}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No sizing | No exchange order")
        elif args.command == "strategy-breakout-check":
            for symbol in SYMBOLS:
                spec = latest_spec_from_manifest(args.manifest, symbol, hours=24)
                dataset = load_accepted_dataset(args.database, args.manifest, spec)
                context = StrategyContext(
                    BREAKOUT_IDENTITY,
                    dataset.snapshot_at(spec.start_time_ms))
                decision = evaluate_breakout(context)
                if decision != evaluate_breakout(context):
                    raise BreakoutStrategyError("Breakout replay mismatch")
                print(f"OK: {symbol} action={decision.action.value} "
                      f"reason={decision.reason.value} replay_equal=true")
            print(f"config_sha256={BREAKOUT_CONFIGURATION.sha256}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No sizing | No exchange order")
        elif args.command == "strategy-adapter-check":
            first, second, final = _strategy_adapter_runtime_check()
            if (first, second, final) != _strategy_adapter_runtime_check():
                raise SignalAdapterError("Research adapter replay mismatch")
            print(f"OK: signal adapter; intents={first.intent.action.value}/"
                  f"{second.intent.action.value} fills={len(first.fills) + len(second.fills)} "
                  f"fixed_quantity={FIXED_RESEARCH_QUANTITY} flat=true")
            print(f"costs_applied=true closed_trades={final.closed_trades} replay_equal=true")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No account sizing | No exchange order")
        elif args.command == "strategy-evaluation-check":
            insufficient, rejected, qualified = _strategy_evaluation_runtime_check()
            print(f"OK: evaluation labels={insufficient.label.value}/"
                  f"{rejected.label.value}/{qualified.label.value}")
            print(f"minimum_days=180 minimum_trades=30_per_symbol/60_pooled "
                  f"replay_equal=true report_sha256={qualified.sha256}")
            print("RESEARCH ONLY | Qualification is not trading approval | No exchange order")
        elif args.command == "strategy-candidate-check":
            result = run_and_write_candidate_matrix(
                args.database, args.manifest, args.output)
            print(f"OK: accepted-data candidate matrix; runs={len(result.runs)} "
                  f"index_sha256={candidate_matrix_sha256(result)}")
            for evaluation in result.evaluations:
                print(f"{evaluation.plan.identity.strategy_id}/"
                      f"{evaluation.plan.identity.version}: "
                      f"label={evaluation.label.value} trades={evaluation.total_trades} "
                      f"report_sha256={evaluation.sha256}")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | Public data | No exchange order")
        elif args.command == "p3-audit":
            result = audit_p3(args.database, args.manifest, args.evidence)
            print(f"OK: P3 final acceptance audit; candidates={result.candidates} "
                  f"symbols={result.symbols} runs={result.runs} "
                  f"files={result.files} p2_artifacts={result.p2_artifacts} "
                  f"trades={result.trades}")
            print(f"index_sha256={result.index_sha256} "
                  "labels=INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No exchange order")
        elif args.command == "strategy-regime-check":
            for symbol in SYMBOLS:
                spec = latest_spec_from_manifest(args.manifest, symbol, hours=24)
                dataset = load_accepted_dataset(args.database, args.manifest, spec)
                context = StrategyContext(
                    StrategyIdentity("RESEARCH_REGIME", "1.0.0"),
                    dataset.snapshot_at(spec.start_time_ms))
                result = classify_regime(context)
                if result != classify_regime(context):
                    raise RegimeError("Regime replay mismatch")
                print(f"OK: {symbol} 4h regime={result.regime.value} "
                      f"reason={result.reason.value} version={result.version} "
                      f"observed={len(context.snapshot.regime)} replay_equal=true")
            print("PAPER ONLY | LIVE_MASTER_LOCK=OFF | No exchange order")
        elif args.command == "strategy-feature-check":
            results = _strategy_feature_runtime_check()
            by_name = {item.name: item for item in results}
            print(f"OK: P3 point-in-time Decimal features; count={len(results)} "
                  f"SMA={by_name['SMA'].value} EMA={by_name['EMA'].value} "
                  f"ATR={by_name['ATR'].value} RSI={by_name['RSI'].value}")
            print("PAPER ONLY | Closed candles | No credentials | No exchange order")
        elif args.command == "backtest-load-check":
            spec = latest_spec_from_manifest(args.manifest, args.symbol, hours=args.hours)
            loaded = load_accepted_dataset(args.database, args.manifest, spec)
            view = loaded.snapshot_at(spec.start_time_ms)
            print(f"OK: accepted P1 dataset loaded read-only; symbol={spec.symbol} "
                  f"stored={len(loaded.primary)}/{len(loaded.context)}/{len(loaded.regime)} "
                  f"visible={len(view.primary)}/{len(view.context)}/{len(view.regime)}")
            print("PAPER ONLY | Point-in-time data | No credentials | No exchange order")
        elif args.command == "backtest-clock-check":
            spec = latest_spec_from_manifest(args.manifest, args.symbol, hours=args.hours)
            loaded = load_accepted_dataset(args.database, args.manifest, spec)
            clock = BacktestClock(loaded)

            def replay():
                return tuple((item.sequence, item.decision_time_ms,
                              item.eligible_fill_open_time_ms,
                              item.snapshot.latest_primary.open_time_ms,
                              item.snapshot.latest_context.open_time_ms,
                              item.snapshot.latest_regime.open_time_ms)
                             for item in clock.events())

            first = replay()
            second = replay()
            if not first or first != second or len(first) != clock.event_count:
                raise BacktestClockError("Deterministic clock replay failed")
            print(f"OK: deterministic event clock; symbol={spec.symbol} events={len(first)} "
                  f"first={first[0][1]} last={first[-1][1]} replay_equal=true")
            print("PAPER ONLY | Point-in-time events | No credentials | No exchange order")
        elif args.command == "stream-check":
            with CandleStore(":memory:") as store:
                result = PublicKlineStream(
                    [(args.symbol, args.interval)], store, max_reconnects=1,
                ).run(args.messages)
                rows = store.count()
            print(f"OK: public Spot kline stream messages={result.messages} stored_rows={rows} "
                  f"reconnects={result.reconnects} backfilled={result.backfilled_rows}")
            print("PUBLIC MARKET DATA ONLY | Memory storage | No credentials | No execution")
        elif args.command == "health-check":
            duration = INTERVAL_MILLISECONDS["1h"]
            start = 1_699_999_200_000
            current = start + (3 * duration)
            values = [Candle(
                source=DATA_SOURCE, symbol="BTCUSDT", interval="1h",
                open_time_ms=open_time, close_time_ms=open_time + duration - 1,
                open="26000.0", high="26250.0", low="25900.0", close="26100.0",
                base_volume="123.0", quote_volume="3210000.0", trade_count=100,
                is_closed=open_time < current,
            ) for open_time in range(start, current + duration, duration)]
            report = build_health_report(DATA_SOURCE, "BTCUSDT", "1h", start,
                                         current + duration, values, current + 1)
            print(report.to_json() if args.json else report.to_text())
            print("PUBLIC CANONICAL DATA | No credentials | No execution")
            if not report.backtest_ready:
                return 1
        elif args.command == "dataset-build":
            with CandleStore(args.database) as store:
                manifest = build_datasets(store, days=args.days)
            path = write_manifest(manifest, args.manifest)
            for report in manifest["datasets"]:
                print(f"{report['symbol']} {report['interval']}: "
                      f"rows={report['total_rows']} backtest_ready={str(report['backtest_ready']).lower()}")
            print(f"OK: {len(manifest['datasets'])} public-real closed datasets; manifest={path}")
            print("SPOT PUBLIC DATA ONLY | No credentials | No execution")
        elif args.command == "dataset-restore-checkpoint":
            result = rebuild_accepted_database(args.database, args.manifest)
            print(f"OK: accepted dataset checkpoint rebuilt; datasets={result.datasets} "
                  f"closed_rows={result.closed_rows} "
                  f"manifest_generated_at_ms={result.manifest_generated_at_ms}")
            print("SPOT PUBLIC DATA ONLY | No credentials | No execution | Manifest unchanged")
        elif args.command == "p1-audit":
            result = audit_p1_manifest(args.manifest)
            print(f"OK: P1 manifest acceptance gate; datasets={result.datasets} "
                  f"closed_rows={result.closed_rows} range_days={result.range_days}")
            print("SPOT PUBLIC DATA ONLY | No credentials | No execution")
        else:
            rows = candles(args.environment, args.symbol, args.interval, args.limit)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            output = args.output or f"data/{args.environment}/{args.symbol.upper()}_{args.interval}_{stamp}.csv"
            path = save_csv(rows, output)
            print(f"Saved {len(rows)} candles to {path}")
            print("The latest candle may still be open; timestamps are Unix milliseconds (UTC).")
    except (AccountError, AuditError, BacktestClockError, BacktestConfigError,
            BacktestContractError,
            ArtifactError, BacktestLoadError, CostModelError, FillModelError,
            MetricsError, P2AuditError, PortfolioError, ScenarioError,
            HistoricalDownloadError, MarketDataError, NormalizationError,
            DatasetError, FeatureError, RegimeError, RegistryError, TrendStrategyError,
            BreakoutStrategyError, SignalAdapterError,
            EvaluationError,
            CandidateRunError,
            P3AuditError,
            RiskContractError,
            RiskSizingError,
            RiskLimitError,
            CheckpointRebuildError,
            HealthError, PaperWorkflowError,
            PublicRestError, QualityError,
            StorageError, StrategyContractError, StreamError,
            ValueError, OSError) as exc:
        # OSError messages can expose local paths; keep their display generic.
        message = "Cannot create output file; check permissions or use a new filename" if isinstance(exc, OSError) else str(exc)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
