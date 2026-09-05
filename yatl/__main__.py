import argparse
import sys
from datetime import datetime, timezone

from .market_data import HOSTS, INTERVALS, MarketDataError, candles, ping, save_csv


def main():
    parser = argparse.ArgumentParser(description="YATL public market-data tools")
    parser.add_argument("--environment", choices=HOSTS, default="testnet")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ping", help="Check public API connectivity")
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
        else:
            rows = candles(args.environment, args.symbol, args.interval, args.limit)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            output = args.output or f"data/{args.environment}/{args.symbol.upper()}_{args.interval}_{stamp}.csv"
            path = save_csv(rows, output)
            print(f"Saved {len(rows)} candles to {path}")
            print("The latest candle may still be open; timestamps are Unix milliseconds (UTC).")
    except (MarketDataError, ValueError, OSError) as exc:
        # OSError messages can expose local paths; keep their display generic.
        message = "Cannot create output file; check permissions or use a new filename" if isinstance(exc, OSError) else str(exc)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
