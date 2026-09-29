"""Point-in-time MCF-PROD-001 monthly universe builder from accepted AF-01B index."""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from research.opportunity_data.index import UniverseIndex
from research.opportunity_data.models import CADENCE_MS, OpportunityError, digest as opportunity_digest

from .models import MCFError, digest
from .production import (
    DEVELOPMENT_END_MS,
    DEVELOPMENT_START_MS,
    MembershipSnapshot,
    ProductionUniverseBinding,
)
from .production_generator import UNIVERSE_POLICY, UNIVERSE_POLICY_SHA256

VERSION = "MCF_PRODUCTION_UNIVERSE_BUILDER/1.0.0"
BASE_INTERVAL = "15m"
DAY_MS = 86_400_000
HISTORY_DAYS = 60
CONTINUITY_DAYS = 30
MIN_CONTINUITY = Decimal("0.995")
MAX_MEMBERS = 50


@dataclass(frozen=True)
class MonthlyUniverseAudit:
    effective_ms: int
    eligible_count: int
    selected_count: int
    selected_symbols: tuple[str, ...]
    eligibility_sha256: str
    ranking_sha256: str


def _sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _month_starts(start_ms: int, end_ms: int) -> tuple[int, ...]:
    dt = datetime.fromtimestamp(start_ms / 1000, timezone.utc)
    current = datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    values = []
    while int(current.timestamp() * 1000) < end_ms:
        values.append(int(current.timestamp() * 1000))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    return tuple(values)


def _validate_frozen_policy() -> None:
    evidence = UNIVERSE_POLICY.get("evidence", {})
    membership = UNIVERSE_POLICY.get("membership", {})
    if (
        UNIVERSE_POLICY.get("policy_id") != "MCF-PROD-001-UNIVERSE-EVIDENCE"
        or evidence.get("partition") != "DEVELOPMENT"
        or evidence.get("scored_search_start_utc") != "2020-03-01T00:00:00Z"
        or evidence.get("development_end_exclusive_utc") != "2023-01-01T00:00:00Z"
        or evidence.get("fresh_oos_read_allowed") is not False
        or evidence.get("recent_reserve_read_allowed") is not False
        or evidence.get("p10_read_allowed") is not False
        or evidence.get("p10_write_allowed") is not False
        or UNIVERSE_POLICY.get("venue") != "BINANCE_SPOT"
        or UNIVERSE_POLICY.get("quote_asset") != "USDT"
        or UNIVERSE_POLICY.get("canonical_base_interval") != BASE_INTERVAL
        or membership.get("mode") != "MONTHLY_LAGGED_LIQUIDITY_RANK"
        or membership.get("reconstitution") != "UTC_MONTH_START"
        or membership.get("rank_metric") != "TRAILING_30D_QUOTE_VOLUME"
        or membership.get("maximum_members") != MAX_MEMBERS
        or membership.get("minimum_admitted_history_days") != HISTORY_DAYS
        or membership.get("continuity_window_days") != CONTINUITY_DAYS
        or Decimal(membership.get("minimum_continuity_fraction", "0")) != MIN_CONTINUITY
        or membership.get("ordinary_spot_required") is not True
        or membership.get("known_leveraged_token_excluded") is not True
        or membership.get("unresolved_product_classification") != "BLOCK_PRODUCTION_ELIGIBILITY"
    ):
        raise MCFError("frozen production universe policy changed")


def _index_digest(index: UniverseIndex) -> str:
    expected = opportunity_digest(index.payload())
    if index.index_sha256 != expected:
        raise MCFError("AF-01B index digest mismatch")
    return expected


def _month_eligibility(index: UniverseIndex, effective_ms: int) -> tuple[list[dict], list[dict]]:
    cadence = CADENCE_MS[BASE_INTERVAL]
    expected_bars = CONTINUITY_DAYS * DAY_MS // cadence
    lower = effective_ms - CONTINUITY_DAYS * DAY_MS
    admitted_before = effective_ms - HISTORY_DAYS * DAY_MS
    eligible = []
    rejected = []

    by_symbol = {
        dataset.symbol: dataset
        for dataset in index.datasets
        if dataset.interval == BASE_INTERVAL
    }
    for lifecycle in index.records:
        lifecycle.validate()
        reason = None
        if lifecycle.quote_asset != "USDT" or lifecycle.venue != "BINANCE_SPOT":
            reason = "MARKET_SCOPE"
        elif lifecycle.instrument_type != "SPOT" or not lifecycle.spot_allowed or lifecycle.leveraged_token_flag:
            reason = "PRODUCT_CLASSIFICATION"
        elif not lifecycle.existed_at(effective_ms):
            reason = "NOT_HISTORICALLY_ADMITTED"
        elif lifecycle.first_admitted_data_ms > admitted_before:
            reason = "MINIMUM_HISTORY_LT_60D"

        dataset = by_symbol.get(lifecycle.symbol)
        if reason is None and dataset is None:
            reason = "MISSING_CANONICAL_15M"
        if dataset is not None:
            dataset.validate_binding()
            if dataset.venue != lifecycle.venue:
                raise MCFError("dataset/lifecycle venue mismatch")

        if reason is not None:
            rejected.append({"symbol": lifecycle.symbol, "reason": reason})
            continue

        rows = [
            row for row in dataset.rows
            if lower <= row.open_time_ms < effective_ms and row.close_time_ms < effective_ms
        ]
        observed = len(rows)
        continuity = Decimal(observed) / Decimal(expected_bars)
        # Duplicate timestamps or bars outside the exact cadence window are not
        # allowed to inflate continuity.
        expected_times = set(range(lower, effective_ms, cadence))
        observed_times = {row.open_time_ms for row in rows}
        if len(observed_times) != observed or not observed_times <= expected_times:
            raise MCFError("noncanonical bars in production liquidity window")
        if continuity < MIN_CONTINUITY:
            rejected.append({
                "symbol": lifecycle.symbol,
                "reason": "CONTINUITY_LT_0_995",
                "observed_bars": observed,
                "expected_bars": expected_bars,
            })
            continue

        quote_volume = sum((Decimal(row.values[7]) for row in rows), Decimal(0))
        payload = {
            "symbol": lifecycle.symbol,
            "effective_ms": effective_ms,
            "dataset_id": dataset.dataset_id,
            "content_sha256": dataset.content_sha256,
            "quality_sha256": dataset.quality_sha256,
            "gap_sha256": dataset.gap_sha256,
            "first_admitted_data_ms": lifecycle.first_admitted_data_ms,
            "window_start_ms": lower,
            "window_end_ms": effective_ms,
            "observed_bars": observed,
            "expected_bars": expected_bars,
            "continuity_fraction": str(continuity),
            "trailing_30d_quote_volume": str(quote_volume),
        }
        eligible.append({**payload, "eligibility_record_sha256": digest(payload)})

    return eligible, rejected


def build(index: UniverseIndex, *, population_manifest_sha256: str) -> tuple[ProductionUniverseBinding, tuple[MonthlyUniverseAudit, ...], dict]:
    """Create all monthly snapshots without reading any strategy performance."""
    _validate_frozen_policy()
    if not _sha(population_manifest_sha256):
        raise MCFError("invalid AF-01C population manifest SHA")
    index_sha = _index_digest(index)

    snapshots = []
    audits = []
    monthly_evidence = []
    for effective_ms in _month_starts(DEVELOPMENT_START_MS, DEVELOPMENT_END_MS):
        eligible, rejected = _month_eligibility(index, effective_ms)
        ranked = sorted(
            eligible,
            key=lambda row: (-Decimal(row["trailing_30d_quote_volume"]), row["symbol"]),
        )
        selected_ranked = ranked[:MAX_MEMBERS]
        if not selected_ranked:
            raise MCFError("production universe month has zero eligible symbols")
        selected_symbols = tuple(sorted(row["symbol"] for row in selected_ranked))
        ranking_payload = {
            "schema": VERSION,
            "effective_ms": effective_ms,
            "rank_metric": "TRAILING_30D_QUOTE_VOLUME",
            "eligible_ranked": tuple(
                (row["symbol"], row["trailing_30d_quote_volume"], row["eligibility_record_sha256"])
                for row in ranked
            ),
            "selected_ranked": tuple(row["symbol"] for row in selected_ranked),
        }
        ranking_sha = digest(ranking_payload)
        eligibility_payload = {
            "schema": VERSION,
            "effective_ms": effective_ms,
            "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
            "index_sha256": index_sha,
            "population_manifest_sha256": population_manifest_sha256,
            "ranking_sha256": ranking_sha,
            "selected_symbols": selected_symbols,
        }
        eligibility_sha = digest(eligibility_payload)
        snapshots.append(MembershipSnapshot(effective_ms, selected_symbols, eligibility_sha))
        audits.append(MonthlyUniverseAudit(
            effective_ms,
            len(eligible),
            len(selected_symbols),
            selected_symbols,
            eligibility_sha,
            ranking_sha,
        ))
        monthly_evidence.append({
            "effective_ms": effective_ms,
            "eligible": tuple(eligible),
            "rejected": tuple(sorted(rejected, key=lambda x: x["symbol"])),
            "ranking": ranking_payload,
            "eligibility": eligibility_payload,
        })

    binding = ProductionUniverseBinding(
        universe_evidence_id="MCF-PROD-001-UNIVERSE-EVIDENCE",
        population_manifest_sha256=population_manifest_sha256,
        quality_index_sha256=index_sha,
        universe_policy_sha256=UNIVERSE_POLICY_SHA256,
        membership_snapshots=tuple(snapshots),
        evidence_partition="DEVELOPMENT",
    )
    binding.validate()
    audit_doc = {
        "schema": VERSION,
        "state": "POINT_IN_TIME_UNIVERSE_BOUND",
        "population_manifest_sha256": population_manifest_sha256,
        "index_sha256": index_sha,
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "month_count": len(snapshots),
        "monthly_evidence": tuple(monthly_evidence),
        "safety": {
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
        },
    }
    return binding, tuple(audits), {**audit_doc, "audit_sha256": digest(audit_doc)}
