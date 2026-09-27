"""Research-only AF-01C command surface. No trading or strategy evaluation."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .archive_adapter import acquire_period, build_lifecycle, plan, reconcile, verify_plan
from .archive_inventory import InventoryUnproven, discover, verify
from .models import OpportunityError, canonical, development_path
from .storage import save_artifact
from research.mass_candidate_factory.models import guard_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AF-01C archive engineering only")
    parser.add_argument("--root", type=Path, default=Path("data/research/opportunity-data"))
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory")
    inventory.add_argument("--max-pages", type=int, default=20000)
    planning = commands.add_parser("plan")
    planning.add_argument("--inventory", type=str, required=True)
    planning.add_argument("--symbols", nargs="+", required=True)
    planning.add_argument("--months", nargs="+", required=True)
    pilot = commands.add_parser("pilot-acquire")
    pilot.add_argument("--plan", required=True)
    pilot.add_argument("--inventory", required=True)
    pilot.add_argument("--daily-fallback", action="store_true")
    for name in ("reconcile", "population-status", "build-lifecycle"):
        command = commands.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--inventory", required=True)
        if name == "build-lifecycle":
            command.add_argument("--symbol", required=True)
            command.add_argument("--ordinary-evidence-ref")
    args = parser.parse_args(argv)
    try:
        root = args.root
        guard_root(root)
        root.mkdir(parents=True, exist_ok=True)
        development_path(root, "inventory")
        now = datetime.now(timezone.utc)
        if args.command == "inventory":
            result = discover(root, fetched_at=now.isoformat().replace("+00:00", "Z"), max_pages=args.max_pages)
        else:
            inv = json.loads(development_path(root, args.inventory).read_bytes())
            verify(inv)
            if args.command == "plan":
                result = plan(inv, tuple(args.symbols), tuple(args.months))
                save_artifact(root, f"plans/plan-{result['plan_sha256']}.json", canonical(result))
            else:
                p = json.loads(development_path(root, args.plan).read_bytes())
                verify_plan(p, inv)
                if p["state"] != "AF01C_ENGINEERING_PILOT_NO_SELECTION" or len(p["periods"]) > 30:
                    raise OpportunityError("CLI only permits bounded engineering pilot")
                if args.command == "pilot-acquire":
                    result = [acquire_period(root, entry, retrieved_ms=int(now.timestamp()*1000),
                                             allow_daily_fallback=args.daily_fallback) for entry in p["periods"]]
                elif args.command == "build-lifecycle":
                    result = build_lifecycle(root, p, args.symbol, retrieved_ms=int(now.timestamp()*1000),
                                             ordinary_evidence_ref=args.ordinary_evidence_ref)
                else:
                    result = reconcile(root, p)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except (InventoryUnproven, OpportunityError, OSError, ValueError) as exc:
        print(json.dumps({"state": "HISTORICAL_SYMBOL_INVENTORY_UNPROVEN" if isinstance(exc, InventoryUnproven)
                          else "AF_01C_ADAPTER_IMPLEMENTATION_BLOCKED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
