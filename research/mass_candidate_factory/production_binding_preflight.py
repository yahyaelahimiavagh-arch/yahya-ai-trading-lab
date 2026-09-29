"""Streaming MCF-PROD-001 production-binding preflight.

Reads only AF-01C Development population provenance/data-quality metadata and
lagged quote-volume bars needed by the frozen universe policy. It never reads
strategy performance, Fresh OOS, recent reserve, P10 or Live state.
"""
from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from research.opportunity_data.models import (
    OpportunityError,
    canonical as opportunity_canonical,
    development_path,
    digest as opportunity_digest,
    sha256,
)
from research.opportunity_data.pc_population import (
    SUCCESS_STATES,
    _load_bound_plan,
    _validate_ledger,
)
from research.opportunity_data.storage import read_canonical

from .models import MCFError, canonical, digest, guard_root, safe_path, write_once
from .production import DEVELOPMENT_END_MS, DEVELOPMENT_START_MS
from .production_generator import UNIVERSE_POLICY, UNIVERSE_POLICY_SHA256

VERSION = "MCF_PRODUCTION_BINDING_PREFLIGHT/1.0.0"
CLASSIFICATION_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_MAP/1.0.0"
EVIDENCE_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0"
EXPECTED_POPULATION_RECONCILIATION_SHA256 = (
    "1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17"
)
DAY_MS = 86_400_000
CADENCE_MS = 900_000
HISTORY_DAYS = 60
CONTINUITY_DAYS = 30
EXPECTED_WINDOW_BARS = CONTINUITY_DAYS * DAY_MS // CADENCE_MS
MIN_CONTINUITY = Decimal("0.995")
MAX_MEMBERS = 50
KNOWN_LEVERAGED = frozenset({
    "BTCUPUSDT", "BTCDOWNUSDT", "ETHUPUSDT", "ETHDOWNUSDT",
    "BNBUPUSDT", "BNBDOWNUSDT", "BTCBULLUSDT", "BTCBEARUSDT",
    "ETHBULLUSDT", "ETHBEARUSDT",
})


def _month_starts() -> tuple[int, ...]:
    start = datetime.fromtimestamp(DEVELOPMENT_START_MS / 1000, timezone.utc)
    current = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    out = []
    while int(current.timestamp() * 1000) < DEVELOPMENT_END_MS:
        out.append(int(current.timestamp() * 1000))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    return tuple(out)


def _read_canonical_json(root: Path, relative: str) -> tuple[dict, bytes]:
    path = safe_path(root, relative)
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing classification artifact")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid classification JSON") from exc
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("noncanonical classification JSON")
    return doc, raw


def _classification_map(root: Path | None, relative: str | None) -> tuple[dict[str, str], str]:
    if root is None or relative is None:
        doc = {
            "schema": CLASSIFICATION_SCHEMA,
            "generation_id": "MCF-PROD-001",
            "state": "AUDIT_ONLY_EMPTY",
            "entries": {},
        }
        return {}, digest(doc)
    root = guard_root(root)
    doc, raw = _read_canonical_json(root, relative)
    entries = doc.get("entries")
    if (
        doc.get("schema") != CLASSIFICATION_SCHEMA
        or doc.get("generation_id") != "MCF-PROD-001"
        or doc.get("state") != "FROZEN_BEFORE_PERFORMANCE"
        or not isinstance(entries, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in entries.items())
    ):
        raise MCFError("invalid historical product classification map")
    return dict(entries), sha256(raw)


def _classification_evidence(root: Path, symbol: str, relative: str) -> tuple[str, str]:
    doc, raw = _read_canonical_json(root, relative)
    classification = doc.get("classification")
    identity = sha256(raw)
    if (
        doc.get("schema") != EVIDENCE_SCHEMA
        or doc.get("symbol") != symbol
        or classification not in {"ORDINARY_SPOT_CONFIRMED", "NONORDINARY_CONFIRMED"}
        or doc.get("reviewed") is not True
        or doc.get("source_type") != "INDEPENDENT_HISTORICAL_PRODUCT_RECORD"
        or not isinstance(doc.get("source_reference"), str)
        or not doc["source_reference"].strip()
        or "exchangeinfo" in doc["source_reference"].lower()
        or not relative.endswith(f"{identity}.json")
    ):
        raise MCFError("invalid independent historical product classification evidence")
    return str(classification), identity


def _verify_population_reconciliation(root: Path, relative: str) -> dict:
    path = development_path(root, relative)
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing AF-01C population reconciliation")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid AF-01C population reconciliation") from exc
    if opportunity_canonical(doc) != raw:
        raise MCFError("noncanonical AF-01C population reconciliation")
    if (
        sha256(raw) != EXPECTED_POPULATION_RECONCILIATION_SHA256
        or doc.get("schema") != "AF-01C-PC-RECONCILIATION/1"
        or doc.get("state") not in {"POPULATION_COMPLETE", "POPULATION_COMPLETE_WITH_SOURCE_GAPS"}
        or doc.get("final_count") != 9306
    ):
        raise MCFError("AF-01C population reconciliation binding mismatch")
    return doc


def _month_stat(rows: Sequence[object], times: Sequence[int], effective_ms: int) -> dict | None:
    if not rows:
        return None
    if rows[0].open_time_ms > effective_ms - HISTORY_DAYS * DAY_MS:
        return None
    lower = effective_ms - CONTINUITY_DAYS * DAY_MS
    left = bisect_left(times, lower)
    right = bisect_left(times, effective_ms)
    observed = right - left
    if observed <= 0:
        return None
    continuity = Decimal(observed) / Decimal(EXPECTED_WINDOW_BARS)
    if continuity < MIN_CONTINUITY:
        return None
    expected_times = range(lower, effective_ms, CADENCE_MS)
    window_times = times[left:right]
    # 99.5% continuity permits sparse documented gaps, but every observed bar
    # must still be exactly on the frozen 15m UTC grid.
    if any((t - lower) % CADENCE_MS for t in window_times):
        raise MCFError("noncanonical timestamp in production liquidity window")
    if len(set(window_times)) != observed:
        raise MCFError("duplicate timestamp in production liquidity window")
    quote_volume = sum((Decimal(rows[i].values[7]) for i in range(left, right)), Decimal(0))
    return {
        "observed_bars": observed,
        "expected_bars": EXPECTED_WINDOW_BARS,
        "continuity_fraction": str(continuity),
        "trailing_30d_quote_volume": str(quote_volume),
    }


def _rank_data_eligible(rows: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    """Classification-neutral deterministic lagged-liquidity order."""
    return tuple(sorted(
        rows,
        key=lambda row: (-Decimal(str(row["trailing_30d_quote_volume"])), str(row["symbol"])),
    ))


def _symbol_rows(root: Path, plan: dict, inventory: dict, entries: Sequence[dict]) -> tuple[tuple[object, ...], tuple[str, ...]]:
    rows = []
    refs = []
    for entry in entries:
        record = _validate_ledger(root, plan, inventory, entry)
        if record["state"] not in SUCCESS_STATES:
            continue
        relative = record.get("canonical_ref")
        expected = record.get("canonical_sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise MCFError("successful AF-01C ledger missing canonical identity")
        part = read_canonical(root, relative, expected)
        rows.extend(part)
        refs.append(str(record["record_sha256"]))
    rows.sort(key=lambda row: row.open_time_ms)
    if len({row.open_time_ms for row in rows}) != len(rows):
        raise MCFError("duplicate AF-01C bars across monthly ledgers")
    return tuple(rows), tuple(refs)


def audit(*, pc_root: Path, plan_relative: str, inventory_relative: str,
          population_reconciliation_relative: str,
          classification_root: Path | None = None,
          classification_map_relative: str | None = None) -> dict:
    """Run the no-performance population/classification preflight."""
    guard_root(pc_root)
    plan, inventory = _load_bound_plan(pc_root, plan_relative, inventory_relative)
    reconciliation = _verify_population_reconciliation(pc_root, population_reconciliation_relative)
    entries_by_symbol: dict[str, list[dict]] = defaultdict(list)
    for entry in plan["periods"]:
        entries_by_symbol[str(entry["symbol"])].append(entry)

    cmap, cmap_sha = _classification_map(classification_root, classification_map_relative)
    if classification_root is not None:
        classification_root = guard_root(classification_root)

    months = _month_starts()
    data_eligible_by_month: dict[int, list[dict]] = {m: [] for m in months}
    eligible_by_month: dict[int, list[dict]] = {m: [] for m in months}
    unresolved_by_month: dict[int, list[str]] = {m: [] for m in months}
    symbol_audit = []

    for symbol in sorted(entries_by_symbol):
        rows, refs = _symbol_rows(pc_root, plan, inventory, entries_by_symbol[symbol])
        times = tuple(row.open_time_ms for row in rows)

        if symbol in KNOWN_LEVERAGED:
            classification = "NONORDINARY_CONFIRMED"
            classification_sha = digest({"symbol": symbol, "rule": "KNOWN_LEVERAGED"})
        elif symbol in cmap:
            if classification_root is None:
                raise MCFError("classification map supplied without classification root")
            classification, classification_sha = _classification_evidence(
                classification_root, symbol, cmap[symbol]
            )
        else:
            classification = "PRODUCT_CLASSIFICATION_UNRESOLVED"
            classification_sha = None

        data_eligible_months = 0
        for month in months:
            stat = _month_stat(rows, times, month)
            if stat is None:
                continue
            data_eligible_months += 1
            stat_payload = {
                "symbol": symbol,
                "effective_ms": month,
                "classification": classification,
                "classification_sha256": classification_sha,
                **stat,
            }
            stat_record = {
                **stat_payload,
                "eligibility_record_sha256": digest(stat_payload),
            }
            data_eligible_by_month[month].append(stat_record)
            if classification == "PRODUCT_CLASSIFICATION_UNRESOLVED":
                unresolved_by_month[month].append(symbol)
                continue
            if classification != "ORDINARY_SPOT_CONFIRMED":
                continue
            eligible_by_month[month].append(stat_record)

        symbol_audit.append({
            "symbol": symbol,
            "classification": classification,
            "classification_sha256": classification_sha,
            "successful_period_count": len(refs),
            "first_admitted_data_ms": rows[0].open_time_ms if rows else None,
            "last_admitted_data_ms": rows[-1].open_time_ms if rows else None,
            "data_eligible_month_count": data_eligible_months,
        })

    unresolved_symbols = tuple(sorted({
        symbol for symbols in unresolved_by_month.values() for symbol in symbols
    }))
    classification_complete = not unresolved_symbols

    neutral_monthly = []
    initial_frontier: set[str] = set()
    for month in months:
        ranked = _rank_data_eligible(data_eligible_by_month[month])
        raw_top = ranked[:MAX_MEMBERS]
        unresolved_raw_top = tuple(
            row["symbol"]
            for row in raw_top
            if row["classification"] == "PRODUCT_CLASSIFICATION_UNRESOLVED"
        )
        initial_frontier.update(unresolved_raw_top)
        ranking_payload = {
            "schema": VERSION,
            "effective_ms": month,
            "rank_metric": "TRAILING_30D_QUOTE_VOLUME",
            "classification_neutral": True,
            "data_eligible_ranked": tuple(
                (
                    row["symbol"],
                    row["trailing_30d_quote_volume"],
                    row["classification"],
                    row["eligibility_record_sha256"],
                )
                for row in ranked
            ),
            "raw_top50_symbols": tuple(row["symbol"] for row in raw_top),
        }
        neutral_monthly.append({
            "effective_ms": month,
            "data_eligible_count": len(ranked),
            "raw_top50_count": len(raw_top),
            "raw_top50_symbols": tuple(row["symbol"] for row in raw_top),
            "unresolved_raw_top50_symbols": unresolved_raw_top,
            "neutral_ranking_sha256": digest(ranking_payload),
        })

    initial_frontier_symbols = tuple(sorted(initial_frontier))

    monthly = []
    if classification_complete:
        for month in months:
            ranked = _rank_data_eligible(eligible_by_month[month])
            if not ranked:
                raise MCFError("production binding month has zero eligible ordinary Spot symbols")
            selected_ranked = ranked[:MAX_MEMBERS]
            ranking_payload = {
                "schema": VERSION,
                "effective_ms": month,
                "rank_metric": "TRAILING_30D_QUOTE_VOLUME",
                "eligible_ranked": tuple(
                    (
                        row["symbol"],
                        row["trailing_30d_quote_volume"],
                        row["eligibility_record_sha256"],
                    )
                    for row in ranked
                ),
                "selected_ranked": tuple(row["symbol"] for row in selected_ranked),
            }
            monthly.append({
                "effective_ms": month,
                "eligible_count": len(ranked),
                "selected_count": len(selected_ranked),
                "selected_symbols": tuple(sorted(row["symbol"] for row in selected_ranked)),
                "ranking_sha256": digest(ranking_payload),
            })

    unresolved_month_counts = tuple(
        (month, len(unresolved_by_month[month]))
        for month in months
        if unresolved_by_month[month]
    )
    base = {
        "schema": VERSION,
        "generation_id": "MCF-PROD-001",
        "state": "READY_FOR_PRODUCTION_BINDING" if classification_complete else "CLASSIFICATION_INCOMPLETE",
        "plan_sha256": plan["plan_sha256"],
        "population_reconciliation_sha256": EXPECTED_POPULATION_RECONCILIATION_SHA256,
        "population_reconciliation_state": reconciliation["state"],
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "classification_map_sha256": cmap_sha,
        "symbol_count": len(entries_by_symbol),
        "month_count": len(months),
        "classification_complete": classification_complete,
        "unresolved_data_eligible_symbol_count": len(unresolved_symbols),
        "unresolved_data_eligible_symbols": unresolved_symbols,
        "unresolved_month_counts": unresolved_month_counts,
        "data_eligible_month_counts": tuple(
            (month, len(data_eligible_by_month[month])) for month in months
        ),
        "classification_neutral_rankings": tuple(neutral_monthly),
        "initial_classification_frontier_symbol_count": len(initial_frontier_symbols),
        "initial_classification_frontier_symbols": initial_frontier_symbols,
        "monthly_rankings": tuple(monthly),
        "symbol_audit": tuple(symbol_audit),
        "safety": {
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
            "p11_locked": True,
        },
    }
    return {**base, "preflight_sha256": digest(base)}


def materialize(*, output_root: Path, **kwargs) -> dict:
    output_root = guard_root(output_root)
    if not output_root.is_dir():
        raise MCFError("binding output root must already exist")
    result = audit(**kwargs)
    payload = canonical(result)
    relative = f"binding-preflight/preflight-{result['preflight_sha256']}.json"
    target = safe_path(output_root, relative)
    write_once(target, payload)
    return {
        "status": result["state"],
        "preflight_sha256": result["preflight_sha256"],
        "artifact": relative,
        "classification_complete": result["classification_complete"],
        "unresolved_data_eligible_symbol_count": result["unresolved_data_eligible_symbol_count"],
        "initial_classification_frontier_symbol_count": result["initial_classification_frontier_symbol_count"],
        "month_count": result["month_count"],
        "performance_read": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc-root", required=True, type=Path)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--population-reconciliation", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--classification-root", type=Path)
    parser.add_argument("--classification-map")
    args = parser.parse_args(argv)
    try:
        result = materialize(
            output_root=args.output_root,
            pc_root=args.pc_root,
            plan_relative=args.plan,
            inventory_relative=args.inventory,
            population_reconciliation_relative=args.population_reconciliation,
            classification_root=args.classification_root,
            classification_map_relative=args.classification_map,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "READY_FOR_PRODUCTION_BINDING" else 40
    except (MCFError, OpportunityError, OSError, ValueError) as exc:
        print(json.dumps({"status": "PRODUCTION_BINDING_PREFLIGHT_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
