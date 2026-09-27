"""UTC-aligned complete-bucket views; gaps never filled."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from research.crisis_lab.acquisition import CanonicalRow

from .canonical import validate_rows
from .models import CADENCE_MS, OpportunityError, digest
from .quality import GapMap


def derive(rows: Sequence[CanonicalRow], symbol: str, dataset_id: str,
           source_interval: str, target_interval: str, *, as_of_ms: int) -> tuple[tuple[CanonicalRow, ...], GapMap]:
    validate_rows(rows, source_interval, as_of_ms=as_of_ms)
    if target_interval not in CADENCE_MS or CADENCE_MS[target_interval] < CADENCE_MS[source_interval]:
        raise OpportunityError("invalid target interval")
    source, target = CADENCE_MS[source_interval], CADENCE_MS[target_interval]
    if target % source:
        raise OpportunityError("nonintegral interval")
    buckets: dict[int, list[CanonicalRow]] = {}
    for row in rows:
        start = row.open_time_ms // target * target
        buckets.setdefault(start, []).append(row)
    result = []
    for start, group in sorted(buckets.items()):
        if (len(group) != target // source or group[0].open_time_ms != start
                or group[-1].close_time_ms != start + target - 1
                or any(b.open_time_ms != start + i * source for i, b in enumerate(group))
                or start + target > as_of_ms):
            continue  # exposed as missing target bucket in the returned gap map
        first, last = group[0].values, group[-1].values
        high = max(Decimal(r.values[2]) for r in group)
        low = min(Decimal(r.values[3]) for r in group)
        sums = {i: sum((Decimal(r.values[i]) for r in group), Decimal(0)) for i in (5, 7, 9, 10)}
        result.append(CanonicalRow((str(start), first[1], str(high), str(low), last[4],
                                    str(sums[5]), str(start + target - 1), str(sums[7]),
                                    str(sum(int(r.values[8]) for r in group)), str(sums[9]),
                                    str(sums[10]), "0")))
    if not result:
        raise OpportunityError("no complete target buckets")
    validated = tuple(result)
    validate_rows(validated, target_interval, as_of_ms=as_of_ms)
    # Include incomplete leading/trailing buckets as missing, not merely holes
    # between produced rows. Their absence must remain visible downstream.
    first_bucket = rows[0].open_time_ms // target * target
    last_bucket = rows[-1].open_time_ms // target * target
    actual = {r.open_time_ms for r in validated}
    missing = [b for b in range(first_bucket, last_bucket + target, target) if b not in actual]
    ranges = []
    for b in missing:
        if ranges and ranges[-1][1] + target == b:
            ranges[-1] = (ranges[-1][0], b)
        else:
            ranges.append((b, b))
    initial = GapMap(symbol, target_interval, dataset_id, target,
                     validated[0].open_time_ms, validated[-1].open_time_ms,
                     tuple(ranges), len(missing), "")
    return validated, GapMap(**{**initial.payload(), "gap_sha256": digest(initial.payload())})
