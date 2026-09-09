import argparse
import sys
from datetime import datetime, timezone

from .market_data import HOSTS, INTERVALS, MarketDataError, candles, ping, save_csv
from .account import AccountError, read_account
from .paper_workflow import PaperWorkflowError, load_and_validate


def main():
    parser = argparse.ArgumentParser(description="YATL paper-only data and Testnet account tools")
    parser.add_argument("--environment", choices=HOSTS, default="testnet")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ping", help="Check public API connectivity")
    account = commands.add_parser("account", help="Read Spot Testnet account summary (no orders)")
    account.add_argument("--env-file", default=".env", help="Explicit local environment file")
    paper = commands.add_parser("paper-check", help="Validate the local P0 paper workflow fixture")
    paper.add_argument("--fixture", default="fixtures/p0-paper-workflows.json")
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
        else:
            rows = candles(args.environment, args.symbol, args.interval, args.limit)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            output = args.output or f"data/{args.environment}/{args.symbol.upper()}_{args.interval}_{stamp}.csv"
            path = save_csv(rows, output)
            print(f"Saved {len(rows)} candles to {path}")
            print("The latest candle may still be open; timestamps are Unix milliseconds (UTC).")
    except (AccountError, MarketDataError, PaperWorkflowError, ValueError, OSError) as exc:
        # OSError messages can expose local paths; keep their display generic.
        message = "Cannot create output file; check permissions or use a new filename" if isinstance(exc, OSError) else str(exc)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
