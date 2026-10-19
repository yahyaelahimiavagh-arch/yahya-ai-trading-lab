"""Research-only streaming Development CSV reader; no candidate execution."""
from __future__ import annotations

from array import array
import csv
import hashlib
import io
import json
from pathlib import Path

from research.crisis_lab.acquisition import CANONICAL_COLUMNS, CanonicalRow
from research.opportunity_data.canonical import validate_rows
from research.opportunity_data.models import OpportunityError, development_path, sha256

from .models import MCFError, canonical
from .production import CADENCE_MS, DEVELOPMENT_END_MS
from .production_features import POPULATION_START_MS, ProductionBars
from .production_runtime_data import BOUNDS, TIMEFRAMES, VERSION, read_json

COLUMNS = (1, 2, 3, 4, 5, 7, 8)
CHUNK_SIZE = 256


def load_streaming_bars(root: Path, row: dict) -> ProductionBars:
    timeframe = row["timeframe"]
    if timeframe not in TIMEFRAMES:
        raise MCFError("unregistered streaming timeframe")

    path = development_path(root, row["data_ref"])
    if not path.is_file():
        raise MCFError("missing bound CSV")

    # Preserve the legacy digest-before-parsing error precedence.
    # Hash incrementally without materializing the entire CSV.
    file_sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            file_sha.update(block)

    if file_sha.hexdigest() != row["content_sha256"]:
        raise OpportunityError("canonical file digest mismatch")

    cadence = CADENCE_MS[timeframe]
    times = array("q")
    values = [array("d") for _ in COLUMNS]
    ranges = []
    cursor = POPULATION_START_MS
    previous = -1
    count = 0
    checksum = hashlib.sha256()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    chunk = []

    def consume_chunk():
        nonlocal previous, cursor, count
        if not chunk:
            return

        # Exact canonical bytes and whole-file SHA are already checked.
        # Keep every row validation, omit only the unused chunk SHA.
        validate_rows(
            chunk, timeframe, as_of_ms=DEVELOPMENT_END_MS,
            hash_canonical=False,
        )

        for item in chunk:
            opened = item.open_time_ms
            if opened < POPULATION_START_MS or opened <= previous:
                raise MCFError("streaming chronology violation")

            if opened > cursor:
                ranges.append((cursor, opened - cadence))

            cursor = opened + cadence
            previous = opened
            times.append(opened)

            for output, index in zip(values, COLUMNS):
                output.append(float(item.values[index]))

            count += 1

        chunk.clear()

    try:
        with path.open("r", encoding="utf-8", newline="") as parsed:
            with path.open("rb") as original:
                reader = csv.reader(parsed)

                def verify_exact_bytes(fields):
                    buffer.seek(0)
                    buffer.truncate(0)
                    writer.writerow(fields)
                    expected_record = buffer.getvalue().encode("utf-8")
                    raw = original.read(len(expected_record))

                    if raw != expected_record:
                        raise MCFError("noncanonical streaming CSV")

                    checksum.update(raw)

                try:
                    header = next(reader)
                except StopIteration:
                    raise MCFError("empty CSV") from None

                if tuple(header) != CANONICAL_COLUMNS:
                    raise MCFError("incorrect CSV header")

                verify_exact_bytes(header)

                for fields in reader:
                    if len(fields) != len(CANONICAL_COLUMNS):
                        raise MCFError("incorrect CSV column count")

                    verify_exact_bytes(fields)
                    chunk.append(CanonicalRow(tuple(fields)))

                    if len(chunk) >= CHUNK_SIZE:
                        consume_chunk()

                consume_chunk()

                if original.read(1):
                    raise MCFError("unexpected trailing CSV bytes")

    except (UnicodeError, csv.Error) as exc:
        raise MCFError("invalid streaming CSV encoding or syntax") from exc

    if not count:
        raise OpportunityError("unsupported cadence or empty data")

    if checksum.hexdigest() != row["content_sha256"]:
        raise OpportunityError("canonical file digest mismatch")

    if cursor < DEVELOPMENT_END_MS:
        ranges.append((cursor, DEVELOPMENT_END_MS - cadence))

    gap_payload = {
        "schema": VERSION,
        "symbol": row["symbol"],
        "timeframe": timeframe,
        "dataset_id": row["dataset_id"],
        "evidence_bounds": BOUNDS,
        "cadence_ms": cadence,
        "missing_ranges": tuple(ranges),
        "gap_count": sum(
            (b - a) // cadence + 1 for a, b in ranges
        ),
        "repair": "NONE",
    }

    try:
        gap, raw = read_json(root, row["gap_ref"])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MCFError("invalid streaming gap JSON") from exc

    if (
        sha256(raw) != row["gap_sha256"]
        or canonical(gap_payload) != raw
        or count != row["row_count"]
        or times[0] != row["first_time_ms"]
        or times[-1] != row["last_time_ms"]
        or gap["gap_count"] != row["gap_count"]
        or row["validity"] != (
            "PASS_WITH_GAPS" if gap["gap_count"]
            else "PASS_CONTIGUOUS"
        )
    ):
        raise MCFError("streaming dataset/gap binding mismatch")

    bars = ProductionBars(
        row["dataset_id"], row["symbol"], timeframe,
        times, *values
    )
    bars.validate()
    return bars
