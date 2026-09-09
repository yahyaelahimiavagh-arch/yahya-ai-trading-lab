"""Fail-closed acceptance audit for the fixed P1 dataset manifest."""

import json
from dataclasses import dataclass
from pathlib import Path

from .config import DATA_SOURCE, INTERVAL_MILLISECONDS, SYMBOLS


MAX_MANIFEST_BYTES = 256 * 1024
DATASET_KIND = "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV"
EXPECTED_DAYS = 30


class AuditError(Exception):
    """P1 acceptance evidence is missing or invalid."""


@dataclass(frozen=True)
class P1AuditResult:
    datasets: int
    closed_rows: int
    range_days: int


def _read_manifest(path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise AuditError("P1 manifest path is invalid")
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise AuditError("P1 manifest cannot be read") from None
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise AuditError("P1 manifest size is invalid")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AuditError("P1 manifest JSON is invalid") from None
    if not isinstance(value, dict):
        raise AuditError("P1 manifest schema is invalid")
    return value


def audit_p1_manifest(path="manifests/p1-market-data.json"):
    manifest = _read_manifest(path)
    if (manifest.get("schema_version") != 1
            or manifest.get("database_schema_version") != 1
            or manifest.get("dataset_kind") != DATASET_KIND
            or manifest.get("range_days") != EXPECTED_DAYS
            or type(manifest.get("generated_at_ms")) is not int
            or manifest["generated_at_ms"] <= 0):
        raise AuditError("P1 manifest identity or range is invalid")

    datasets = manifest.get("datasets")
    expected_pairs = {(symbol, interval) for symbol in SYMBOLS
                      for interval in INTERVAL_MILLISECONDS}
    if not isinstance(datasets, list) or len(datasets) != len(expected_pairs):
        raise AuditError("P1 manifest dataset coverage is invalid")

    seen = set()
    total = 0
    for report in datasets:
        if not isinstance(report, dict):
            raise AuditError("P1 health report is invalid")
        pair = (report.get("symbol"), report.get("interval"))
        if pair not in expected_pairs or pair in seen or report.get("source") != DATA_SOURCE:
            raise AuditError("P1 dataset identity is invalid")
        seen.add(pair)
        expected_rows = EXPECTED_DAYS * 86_400_000 // INTERVAL_MILLISECONDS[pair[1]]
        start = report.get("requested_start_time_ms")
        end = report.get("requested_end_time_ms")
        first = report.get("stored_first_open_time_ms")
        last = report.get("stored_last_open_time_ms")
        freshness = report.get("freshness_ms")
        integer_zeros = ("open_rows", "malformed_rows", "conflicting_rows")
        empty_lists = ("duplicate_open_times", "historical_gap_open_times",
                       "unexpected_open_times", "repair_ranges", "failure_reasons")
        if (report.get("backtest_ready") is not True
                or report.get("fresh") is not True
                or any(report.get(field) != 0 for field in integer_zeros)
                or any(report.get(field) != [] for field in empty_lists)
                or report.get("total_rows") != expected_rows
                or report.get("unique_rows") != expected_rows
                or report.get("closed_rows") != expected_rows
                or any(type(value) is not int for value in
                       (start, end, first, last, freshness))
                or start <= 0 or end <= start or freshness < 0
                or first != start
                or last != end - INTERVAL_MILLISECONDS[pair[1]]):
            raise AuditError("P1 dataset health gate failed")
        total += expected_rows

    if seen != expected_pairs or total != 7_560:
        raise AuditError("P1 dataset acceptance total is invalid")
    return P1AuditResult(datasets=len(seen), closed_rows=total,
                         range_days=EXPECTED_DAYS)
