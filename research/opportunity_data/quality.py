"""Explicit cadence gaps and provenance-bound admission manifests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from research.crisis_lab.acquisition import CanonicalRow

from .canonical import validate_rows
from .models import AdmittedDataset, CADENCE_MS, OpportunityError, digest


@dataclass(frozen=True)
class GapMap:
    symbol: str
    interval: str
    dataset_id: str
    cadence_ms: int
    first_data_ms: int
    last_data_ms: int
    missing_ranges: tuple[tuple[int, int], ...]  # inclusive open-time endpoints
    gap_count: int  # missing bars, not contiguous ranges
    gap_sha256: str

    def payload(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "gap_sha256"}


def gap_map(rows: Sequence[CanonicalRow], symbol: str, interval: str, dataset_id: str) -> GapMap:
    if not rows or interval not in CADENCE_MS or not symbol or not dataset_id:
        raise OpportunityError("invalid gap-map input")
    cadence = CADENCE_MS[interval]
    ranges = []
    previous = rows[0].open_time_ms
    for row in rows[1:]:
        current = row.open_time_ms
        if current <= previous or (current - previous) % cadence:
            raise OpportunityError("invalid gap cadence")
        if current > previous + cadence:
            ranges.append((previous + cadence, current - cadence))
        previous = current
    count = sum((end - start) // cadence + 1 for start, end in ranges)
    initial = GapMap(symbol, interval, dataset_id, cadence, rows[0].open_time_ms,
                     rows[-1].open_time_ms, tuple(ranges), count, "")
    return GapMap(**{**initial.payload(), "gap_sha256": digest(initial.payload())})


def admit(*, dataset_id: str, symbol: str, interval: str, rows: Sequence[CanonicalRow],
          source: str, requested_start_ms: int, requested_end_ms: int,
          retrieved_at_ms: int, source_refs: tuple[str, ...],
          allow_gaps: bool, venue: str = "BINANCE_SPOT") -> tuple[AdmittedDataset, GapMap, dict]:
    forbidden = ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve", "blind_oos", "blind-oos")
    if not source_refs or any(any(part in ref.lower() for part in forbidden) for ref in source_refs):
        raise OpportunityError("unsafe/unbound source reference")
    if not symbol.isalnum() or not symbol.isupper() or not dataset_id or "/" not in dataset_id:
        raise OpportunityError("invalid dataset/symbol identity")
    rows = tuple(rows)
    content = validate_rows(rows, interval, as_of_ms=retrieved_at_ms)
    if rows[0].open_time_ms < requested_start_ms or rows[-1].open_time_ms >= requested_end_ms:
        raise OpportunityError("observations outside requested range")
    gaps = gap_map(rows, symbol, interval, dataset_id)
    if gaps.gap_count and not allow_gaps:
        raise OpportunityError("gaps forbidden by admission policy")
    verdict = "PASS_WITH_GAPS" if gaps.gap_count else "PASS_CONTIGUOUS"
    manifest = dict(version="AF-01B/1.0.0", dataset_id=dataset_id, symbol=symbol,
                    interval=interval, venue=venue, source=source,
                    requested_start_ms=requested_start_ms, requested_end_ms=requested_end_ms,
                    actual_first_ms=rows[0].open_time_ms, actual_last_ms=rows[-1].open_time_ms,
                    retrieved_at_ms=retrieved_at_ms, source_refs=source_refs,
                    row_count=len(rows), duplicate_count=0, gap_count=gaps.gap_count,
                    gap_sha256=gaps.gap_sha256, content_sha256=content,
                    quality_verdict=verdict, evidence_partition="DEVELOPMENT")
    quality_sha = digest(manifest)
    bound = AdmittedDataset(dataset_id, symbol, interval, venue, source,
                            requested_start_ms, requested_end_ms, retrieved_at_ms,
                            source_refs, rows, content, quality_sha, gaps.gap_sha256,
                            verdict)
    bound.validate_binding()
    return bound, gaps, manifest


def verify_quality(dataset: AdmittedDataset, manifest: dict, gaps: GapMap) -> None:
    dataset.validate_binding()
    if digest(manifest) != dataset.quality_sha256 or digest(gaps.payload()) != dataset.gap_sha256:
        raise OpportunityError("unbound quality/gap manifest")
    if manifest.get("dataset_id") != dataset.dataset_id or manifest.get("content_sha256") != dataset.content_sha256:
        raise OpportunityError("quality identity mismatch")
    if gaps.dataset_id != dataset.dataset_id or gaps.symbol != dataset.symbol:
        raise OpportunityError("gap identity mismatch")
    if validate_rows(dataset.rows, dataset.interval, as_of_ms=dataset.retrieved_at_ms) != dataset.content_sha256:
        raise OpportunityError("dataset content mismatch")
