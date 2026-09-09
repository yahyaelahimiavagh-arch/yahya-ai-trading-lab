import argparse
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .market_data import HOSTS, INTERVALS, MarketDataError, candles, ping, save_csv
from .account import AccountError, read_account
from .paper_workflow import PaperWorkflowError, load_and_validate
from .data import (BinancePublicRestClient, Candle, CandleStore,
                   ClosedCandleConflict, DATA_SOURCE, HistoricalDownloadError,
                   INTERVAL_MILLISECONDS, NormalizationError, PublicRestError,
                   QualityError, StorageError, SYMBOLS, analyze_open_times,
                   PublicKlineStream, StreamError, download_range,
                   HealthError, build_health_report, normalize_rest_kline)


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
    stream = commands.add_parser("stream-check", help="Read bounded public Spot kline messages")
    stream.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    stream.add_argument("--interval", choices=INTERVAL_MILLISECONDS, default="1h")
    stream.add_argument("--messages", type=int, choices=range(1, 11), default=1)
    health = commands.add_parser("health-check", help="Build deterministic P1 data health report")
    health.add_argument("--json", action="store_true", help="Print deterministic JSON")
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
        else:
            rows = candles(args.environment, args.symbol, args.interval, args.limit)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            output = args.output or f"data/{args.environment}/{args.symbol.upper()}_{args.interval}_{stamp}.csv"
            path = save_csv(rows, output)
            print(f"Saved {len(rows)} candles to {path}")
            print("The latest candle may still be open; timestamps are Unix milliseconds (UTC).")
    except (AccountError, HistoricalDownloadError, MarketDataError, NormalizationError,
            HealthError, PaperWorkflowError, PublicRestError, QualityError,
            StorageError, StreamError,
            ValueError, OSError) as exc:
        # OSError messages can expose local paths; keep their display generic.
        message = "Cannot create output file; check permissions or use a new filename" if isinstance(exc, OSError) else str(exc)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
