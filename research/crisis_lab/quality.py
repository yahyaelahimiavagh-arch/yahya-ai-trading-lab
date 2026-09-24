"""CRL-003 deterministic data-quality admission for Crisis Lab datasets.

Research-only. This module validates immutable CRL-002 acquisition artifacts and
emits bounded structural quality evidence. It never emits market prices, returns,
PnL, drawdown, strategy results, or execution authority.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

from . import acquisition as acq

QUALITY_IMPLEMENTATION_ID = "CRL-003/0.1.1"
QUALITY_SCHEMA_VERSION = "0.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_DESIGNATIONS = frozenset({"DEVELOPMENT", "BLIND_HOLDOUT"})
_ALLOWED_ACQUISITION_STATUS = "ACQUIRED_NEEDS_CRL003"


class QualityError(RuntimeError):
    """Fail-closed CRL-003 quality error."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(record: Mapping[str, object]) -> bytes:
    text = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return (text + "\n").encode("utf-8")


def _runtime_root(path: Path) -> Path:
    try:
        return acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise QualityError(str(exc)) from None


def _runtime_relative_path(runtime_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise QualityError("runtime relative path is missing")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise QualityError("runtime relative path is invalid")
    root = _runtime_root(runtime_root)
    try:
        target = acq.assert_safe_runtime_path(root / rel)
    except acq.AcquisitionError as exc:
        raise QualityError(str(exc)) from None
    try:
        target.relative_to(root)
    except ValueError:
        raise QualityError("runtime read escaped the research root") from None
    if target.is_symlink():
        raise QualityError("symlink research artifact is forbidden")
    return target


def _read_bytes(runtime_root: Path, relative: str) -> bytes:
    target = _runtime_relative_path(runtime_root, relative)
    try:
        return target.read_bytes()
    except OSError:
        raise QualityError("cannot read immutable research artifact") from None


def _load_json_bytes(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise QualityError(f"{label} is not canonical UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise QualityError(f"{label} must be a JSON object")
    return value


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise QualityError(f"{label} is not a lowercase SHA-256")
    return value


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualityError(f"{label} is not an integer")
    return value


def _parse_decimal(value: str, *, column: str, row_number: int) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise QualityError(
            f"row {row_number} column {column} is not a valid decimal"
        ) from None
    if not number.is_finite():
        raise QualityError(
            f"row {row_number} column {column} is not finite"
        )
    return number


def _iso_ms(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise QualityError(f"{label} is not a UTC timestamp")
    try:
        return acq._iso_to_ms(value)
    except acq.AcquisitionError as exc:
        raise QualityError(f"{label}: {exc}") from None


def _check_source_objects(
    dataset_manifest: Mapping[str, object],
) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    objects = dataset_manifest.get("source_objects")
    if not isinstance(objects, list) or not objects:
        return False, ("SOURCE_OBJECTS_MISSING",)
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            failures.append(f"SOURCE_OBJECT_{index}_INVALID")
            continue
        try:
            expected = _require_sha(
                item.get("expected_zip_sha256"),
                f"source object {index} expected ZIP SHA",
            )
            downloaded = _require_sha(
                item.get("downloaded_zip_sha256"),
                f"source object {index} downloaded ZIP SHA",
            )
            _require_sha(
                item.get("extracted_csv_sha256"),
                f"source object {index} extracted CSV SHA",
            )
        except QualityError:
            failures.append(f"SOURCE_OBJECT_{index}_DIGEST_INVALID")
            continue
        if expected != downloaded:
            failures.append(f"SOURCE_OBJECT_{index}_CHECKSUM_MISMATCH")
        normalized = item.get("close_boundary_normalization_count", 0)
        verified = item.get("close_boundary_rest_verified_count", 0)
        if (
            not isinstance(normalized, int)
            or isinstance(normalized, bool)
            or normalized < 0
            or not isinstance(verified, int)
            or isinstance(verified, bool)
            or verified < 0
        ):
            failures.append(
                f"SOURCE_OBJECT_{index}_CLOSE_BOUNDARY_EVIDENCE_INVALID"
            )
        elif normalized != verified:
            failures.append(
                f"SOURCE_OBJECT_{index}_CLOSE_BOUNDARY_REST_INCOMPLETE"
            )
    return not failures, tuple(failures)


def _inspect_canonical(
    *,
    runtime_root: Path,
    dataset_manifest: Mapping[str, object],
) -> dict[str, object]:
    failures: list[str] = []

    symbol = dataset_manifest.get("symbol")
    interval = dataset_manifest.get("interval")
    if symbol not in acq.ALLOWED_SYMBOLS:
        failures.append("SYMBOL_OUT_OF_SCOPE")
    if interval not in acq.ALLOWED_INTERVALS:
        failures.append("INTERVAL_OUT_OF_SCOPE")
    if failures:
        return {
            "status": "FAIL",
            "failures": sorted(set(failures)),
            "row_count": 0,
            "expected_row_count": 0,
        }

    duration = acq.INTERVAL_MILLISECONDS[str(interval)]
    canonical = dataset_manifest.get("canonical")
    if not isinstance(canonical, dict):
        return {
            "status": "FAIL",
            "failures": ["CANONICAL_METADATA_MISSING"],
            "row_count": 0,
            "expected_row_count": 0,
        }

    try:
        canonical_rel = canonical.get("relative_path")
        if not isinstance(canonical_rel, str):
            raise QualityError("canonical relative path is missing")
        expected_sha = _require_sha(
            canonical.get("sha256"), "canonical SHA-256"
        )
        manifest_rows = _require_int(
            canonical.get("row_count"), "canonical row count"
        )
        expected_rows = _require_int(
            canonical.get("expected_row_count"),
            "canonical expected row count",
        )
        first_manifest = _require_int(
            canonical.get("first_open_time_ms"),
            "canonical first open time",
        )
        last_manifest = _require_int(
            canonical.get("last_open_time_ms"),
            "canonical last open time",
        )
        gap_manifest = _require_int(
            canonical.get("gap_count"), "canonical gap count"
        )
        duplicate_manifest = _require_int(
            canonical.get("duplicate_count"),
            "canonical duplicate count",
        )
        close_boundary_normalized = _require_int(
            canonical.get(
                "close_boundary_normalization_count", 0
            ),
            "canonical close-boundary normalization count",
        )
        close_boundary_verified = _require_int(
            canonical.get(
                "close_boundary_rest_verified_count", 0
            ),
            "canonical close-boundary REST verified count",
        )
    except QualityError as exc:
        return {
            "status": "FAIL",
            "failures": ["CANONICAL_METADATA_INVALID", str(exc)],
            "row_count": 0,
            "expected_row_count": 0,
        }

    if gap_manifest != 0:
        failures.append("ACQUISITION_RECORDED_GAPS")
    if duplicate_manifest != 0:
        failures.append("ACQUISITION_RECORDED_DUPLICATES")
    if close_boundary_normalized < 0 or close_boundary_verified < 0:
        failures.append("CLOSE_BOUNDARY_EVIDENCE_INVALID")
    elif close_boundary_normalized != close_boundary_verified:
        failures.append("CLOSE_BOUNDARY_REST_VERIFICATION_INCOMPLETE")

    if Path(canonical_rel).name != f"dataset-{expected_sha}.csv":
        failures.append("CANONICAL_CONTENT_ADDRESS_MISMATCH")

    payload = _read_bytes(runtime_root, canonical_rel)
    actual_sha = _sha256(payload)
    if actual_sha != expected_sha:
        return {
            "status": "FAIL",
            "failures": ["CANONICAL_DIGEST_MISMATCH"],
            "canonical_sha256": expected_sha,
            "actual_file_sha256": actual_sha,
            "row_count": 0,
            "expected_row_count": expected_rows,
        }

    semantic = dataset_manifest.get("semantic_range")
    transport = dataset_manifest.get("transport_range")
    if not isinstance(semantic, dict) or not isinstance(transport, dict):
        return {
            "status": "FAIL",
            "failures": ["RANGE_METADATA_MISSING"],
            "canonical_sha256": expected_sha,
            "row_count": 0,
            "expected_row_count": expected_rows,
        }

    try:
        semantic_start = _iso_ms(
            semantic.get("start_utc"), "semantic start"
        )
        semantic_end = _iso_ms(
            semantic.get("end_utc"), "semantic end"
        )
        transport_start = _iso_ms(
            transport.get("start_utc"), "transport start"
        )
        transport_end = _iso_ms(
            transport.get("end_utc"), "transport end"
        )
        retrieved_ms = _iso_ms(
            dataset_manifest.get("retrieved_at_utc"), "retrieved_at_utc"
        )
    except QualityError as exc:
        return {
            "status": "FAIL",
            "failures": ["RANGE_METADATA_INVALID", str(exc)],
            "canonical_sha256": expected_sha,
            "row_count": 0,
            "expected_row_count": expected_rows,
        }

    if not (
        transport_start <= semantic_start < semantic_end <= transport_end
    ):
        failures.append("SEMANTIC_RANGE_OUTSIDE_TRANSPORT")
    if transport_start % duration != 0 or transport_end % duration != 0:
        failures.append("TRANSPORT_RANGE_NOT_GRID_ALIGNED")
    if transport_start >= transport_end:
        failures.append("TRANSPORT_RANGE_EMPTY")
    computed_expected = (
        (transport_end - transport_start) // duration
        if transport_end >= transport_start
        else -1
    )
    if computed_expected != expected_rows:
        failures.append("EXPECTED_ROW_COUNT_INCONSISTENT")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "status": "FAIL",
            "failures": ["CANONICAL_NOT_UTF8"],
            "canonical_sha256": expected_sha,
            "row_count": 0,
            "expected_row_count": expected_rows,
        }

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        return {
            "status": "FAIL",
            "failures": ["CANONICAL_HEADER_MISSING", "EMPTY_CANONICAL_DATASET"],
            "canonical_sha256": expected_sha,
            "row_count": 0,
            "expected_row_count": expected_rows,
        }
    if tuple(header) != acq.CANONICAL_COLUMNS:
        failures.append("CANONICAL_HEADER_INVALID")

    row_count = 0
    first_open: int | None = None
    last_open: int | None = None
    previous_open: int | None = None

    for row_number, row in enumerate(reader, start=2):
        row_count += 1
        if len(row) != len(acq.CANONICAL_COLUMNS):
            failures.append("COLUMN_COUNT_INVALID")
            continue

        try:
            open_ms = int(row[0])
            close_ms = int(row[6])
            trade_count = int(row[8])
        except ValueError:
            failures.append("INTEGER_FIELD_INVALID")
            continue

        try:
            open_price = _parse_decimal(
                row[1], column="open", row_number=row_number
            )
            high = _parse_decimal(
                row[2], column="high", row_number=row_number
            )
            low = _parse_decimal(
                row[3], column="low", row_number=row_number
            )
            close = _parse_decimal(
                row[4], column="close", row_number=row_number
            )
            base_volume = _parse_decimal(
                row[5], column="base_volume", row_number=row_number
            )
            quote_volume = _parse_decimal(
                row[7], column="quote_volume", row_number=row_number
            )
            taker_base = _parse_decimal(
                row[9],
                column="taker_buy_base_volume",
                row_number=row_number,
            )
            taker_quote = _parse_decimal(
                row[10],
                column="taker_buy_quote_volume",
                row_number=row_number,
            )
            _parse_decimal(
                row[11], column="ignore", row_number=row_number
            )
        except QualityError:
            failures.append("DECIMAL_FIELD_INVALID")
            continue

        if min(open_price, high, low, close) <= 0:
            failures.append("NONPOSITIVE_PRICE")
        if high < max(open_price, close, low):
            failures.append("HIGH_RELATION_INVALID")
        if low > min(open_price, close, high):
            failures.append("LOW_RELATION_INVALID")
        if min(base_volume, quote_volume, taker_base, taker_quote) < 0:
            failures.append("NEGATIVE_VOLUME")
        if taker_base > base_volume:
            failures.append("TAKER_BASE_EXCEEDS_TOTAL")
        if taker_quote > quote_volume:
            failures.append("TAKER_QUOTE_EXCEEDS_TOTAL")
        if trade_count < 0:
            failures.append("NEGATIVE_TRADE_COUNT")

        if open_ms % duration != 0:
            failures.append("OPEN_TIME_NOT_GRID_ALIGNED")
        if close_ms != open_ms + duration - 1:
            failures.append("CLOSE_TIME_INTERVAL_INVALID")
        if close_ms > retrieved_ms:
            failures.append("OPEN_CANDLE_PRESENT")
        if open_ms < transport_start or open_ms >= transport_end:
            failures.append("CANDLE_OUTSIDE_TRANSPORT_RANGE")

        if first_open is None:
            first_open = open_ms
        if previous_open is not None:
            if open_ms == previous_open:
                failures.append("DUPLICATE_TIMESTAMP")
            elif open_ms < previous_open:
                failures.append("NONMONOTONIC_TIMESTAMP")
            elif open_ms != previous_open + duration:
                failures.append("TIMESTAMP_GAP")
        previous_open = open_ms
        last_open = open_ms

    if row_count == 0:
        failures.append("EMPTY_CANONICAL_DATASET")
    if row_count != manifest_rows:
        failures.append("ROW_COUNT_MANIFEST_MISMATCH")
    if row_count != expected_rows:
        failures.append("ROW_COUNT_EXPECTED_MISMATCH")
    if first_open != first_manifest:
        failures.append("FIRST_OPEN_MANIFEST_MISMATCH")
    if last_open != last_manifest:
        failures.append("LAST_OPEN_MANIFEST_MISMATCH")
    if first_open != transport_start:
        failures.append("FIRST_OPEN_TRANSPORT_MISMATCH")
    expected_last = transport_end - duration
    if last_open != expected_last:
        failures.append("LAST_OPEN_TRANSPORT_MISMATCH")

    unique_failures = tuple(sorted(set(failures)))
    return {
        "status": "PASS" if not unique_failures else "FAIL",
        "failures": list(unique_failures),
        "canonical_sha256": expected_sha,
        "row_count": row_count,
        "expected_row_count": expected_rows,
        "first_open_time_ms": first_open,
        "last_open_time_ms": last_open,
        "transport_start_utc": transport.get("start_utc"),
        "transport_end_utc": transport.get("end_utc"),
        "semantic_start_utc": semantic.get("start_utc"),
        "semantic_end_utc": semantic.get("end_utc"),
    }


def _dataset_quality_relative_path(
    event_id: str,
    symbol: str,
    interval: str,
    digest: str,
) -> Path:
    return (
        Path("quality")
        / f"event-catalog-v{acq.CATALOG_VERSION}"
        / event_id
        / symbol
        / interval
        / f"quality-{digest[:24]}.json"
    )


def _event_quality_relative_path(event_id: str, digest: str) -> Path:
    return (
        Path("quality")
        / f"event-catalog-v{acq.CATALOG_VERSION}"
        / event_id
        / f"event-quality-{digest[:24]}.json"
    )


def _write_immutable(
    runtime_root: Path, relative: Path, payload: bytes
) -> str:
    try:
        return acq._write_immutable(runtime_root, relative, payload)
    except acq.AcquisitionError as exc:
        raise QualityError(str(exc)) from None


def validate_dataset(
    *,
    runtime_root: Path,
    event_manifest: Mapping[str, object],
    dataset_ref: Mapping[str, object],
) -> dict[str, object]:
    failures: list[str] = []

    event_id = event_manifest.get("event_id")
    designation = event_manifest.get("designation")
    replay_eligible = event_manifest.get("replay_eligible")
    symbol = dataset_ref.get("symbol")
    interval = dataset_ref.get("interval")

    if not isinstance(event_id, str):
        raise QualityError("event identity is missing")
    if designation not in _ALLOWED_DESIGNATIONS:
        raise QualityError("event designation is invalid")
    if not isinstance(replay_eligible, bool):
        raise QualityError("event replay eligibility is invalid")
    if symbol not in acq.ALLOWED_SYMBOLS:
        raise QualityError("dataset symbol is outside CRL scope")
    if interval not in acq.ALLOWED_INTERVALS:
        raise QualityError("dataset interval is outside CRL scope")

    manifest_rel = dataset_ref.get("manifest_relative_path")
    if not isinstance(manifest_rel, str):
        raise QualityError("dataset manifest path is missing")
    expected_manifest_sha = _require_sha(
        dataset_ref.get("manifest_file_sha256"),
        "dataset manifest SHA-256",
    )
    manifest_name = Path(manifest_rel).name
    expected_manifest_name = (
        f"acquisition-{expected_manifest_sha[:24]}.json"
    )
    if manifest_name != expected_manifest_name:
        failures.append("DATASET_MANIFEST_CONTENT_ADDRESS_MISMATCH")

    dataset_payload = _read_bytes(runtime_root, manifest_rel)
    actual_manifest_sha = _sha256(dataset_payload)
    if actual_manifest_sha != expected_manifest_sha:
        failures.append("DATASET_MANIFEST_DIGEST_MISMATCH")
        dataset_manifest: dict[str, object] = {}
    else:
        dataset_manifest = _load_json_bytes(
            dataset_payload, "dataset acquisition manifest"
        )

    if dataset_manifest:
        if (
            dataset_manifest.get("schema")
            != "YATL_CRL_DATASET_ACQUISITION_PROVENANCE"
        ):
            failures.append("DATASET_MANIFEST_SCHEMA_INVALID")
        if dataset_manifest.get("schema_version") != "0.1.0":
            failures.append("DATASET_MANIFEST_VERSION_INVALID")
        if dataset_manifest.get("event_id") != event_id:
            failures.append("EVENT_ID_MISMATCH")
        if dataset_manifest.get("designation") != designation:
            failures.append("DESIGNATION_MISMATCH")
        if dataset_manifest.get("replay_eligible") is not replay_eligible:
            failures.append("REPLAY_ELIGIBILITY_MISMATCH")
        if dataset_manifest.get("symbol") != symbol:
            failures.append("SYMBOL_IDENTITY_MISMATCH")
        if dataset_manifest.get("interval") != interval:
            failures.append("INTERVAL_IDENTITY_MISMATCH")
        if (
            dataset_manifest.get("acquisition_status")
            != _ALLOWED_ACQUISITION_STATUS
        ):
            failures.append("ACQUISITION_STATUS_NOT_ADMISSIBLE")
        if dataset_manifest.get("quality_gate") != "PENDING_CRL003":
            failures.append("UPSTREAM_QUALITY_STATE_INVALID")
        if dataset_manifest.get("research_only") is not True:
            failures.append("RESEARCH_ONLY_INVARIANT_MISSING")
        if dataset_manifest.get("p10_write_allowed") is not False:
            failures.append("P10_WRITE_INVARIANT_INVALID")
        if dataset_manifest.get("p11_locked") is not True:
            failures.append("P11_LOCK_INVARIANT_MISSING")
        if dataset_manifest.get("trade_permission") is not False:
            failures.append("TRADE_PERMISSION_INVARIANT_INVALID")
        if dataset_manifest.get("order_endpoint") is not False:
            failures.append("ORDER_ENDPOINT_INVARIANT_INVALID")
        if dataset_manifest.get("ai_direct_execution") is not False:
            failures.append("AI_EXECUTION_INVARIANT_INVALID")

        rest = dataset_manifest.get("rest_verification")
        if not isinstance(rest, dict) or rest.get("status") != "MATCH":
            failures.append("REST_BOUNDARY_VERIFICATION_NOT_MATCH")

        source_ok, source_failures = _check_source_objects(
            dataset_manifest
        )
        if not source_ok:
            failures.extend(source_failures)

        canonical_result = _inspect_canonical(
            runtime_root=runtime_root,
            dataset_manifest=dataset_manifest,
        )
        if canonical_result["status"] != "PASS":
            failures.extend(
                str(item)
                for item in canonical_result.get("failures", [])
            )
    else:
        canonical_result = {
            "status": "FAIL",
            "failures": ["DATASET_MANIFEST_UNTRUSTED"],
            "row_count": 0,
            "expected_row_count": 0,
        }

    unique_failures = tuple(sorted(set(failures)))
    quality_status = "PASS" if not unique_failures else "FAIL"
    report: dict[str, object] = {
        "schema": "YATL_CRL_DATASET_QUALITY_MANIFEST",
        "schema_version": QUALITY_SCHEMA_VERSION,
        "implementation_id": QUALITY_IMPLEMENTATION_ID,
        "catalog_version": acq.CATALOG_VERSION,
        "event_id": event_id,
        "designation": designation,
        "replay_eligible": replay_eligible,
        "symbol": symbol,
        "interval": interval,
        "input_acquisition_manifest_relative_path": manifest_rel,
        "input_acquisition_manifest_sha256": expected_manifest_sha,
        "quality_status": quality_status,
        "replay_admitted": bool(
            quality_status == "PASS" and replay_eligible
        ),
        "failure_codes": list(unique_failures),
        "checks": {
            "dataset_manifest_digest": (
                "PASS"
                if actual_manifest_sha == expected_manifest_sha
                else "FAIL"
            ),
            "source_integrity": (
                "PASS"
                if dataset_manifest
                and _check_source_objects(dataset_manifest)[0]
                else "FAIL"
            ),
            "rest_boundary_verification": (
                "PASS"
                if dataset_manifest
                and isinstance(
                    dataset_manifest.get("rest_verification"), dict
                )
                and dataset_manifest["rest_verification"].get("status")
                == "MATCH"
                else "FAIL"
            ),
            "canonical_integrity": canonical_result["status"],
        },
        "canonical_evidence": {
            key: canonical_result.get(key)
            for key in (
                "canonical_sha256",
                "row_count",
                "expected_row_count",
                "first_open_time_ms",
                "last_open_time_ms",
                "transport_start_utc",
                "transport_end_utc",
                "semantic_start_utc",
                "semantic_end_utc",
            )
            if key in canonical_result
        },
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    report["quality_manifest_sha256"] = _sha256(
        _canonical_json(report)
    )
    payload = _canonical_json(report)
    file_sha = _sha256(payload)
    relative = _dataset_quality_relative_path(
        event_id, str(symbol), str(interval), file_sha
    )
    relative_text = _write_immutable(runtime_root, relative, payload)
    report["quality_manifest_file_sha256"] = file_sha
    report["quality_manifest_relative_path"] = relative_text
    return report


def validate_event(
    *,
    runtime_root: Path,
    event_manifest_relative_path: str,
    event_manifest_sha256: str,
) -> dict[str, object]:
    expected_event_sha = _require_sha(
        event_manifest_sha256, "event acquisition manifest SHA-256"
    )
    if (
        Path(event_manifest_relative_path).name
        != f"event-acquisition-{expected_event_sha[:24]}.json"
    ):
        raise QualityError(
            "event acquisition manifest content-address identity mismatch"
        )
    event_payload = _read_bytes(
        runtime_root, event_manifest_relative_path
    )
    actual_event_sha = _sha256(event_payload)
    if actual_event_sha != expected_event_sha:
        raise QualityError("event acquisition manifest digest mismatch")

    event_manifest = _load_json_bytes(
        event_payload, "event acquisition manifest"
    )
    if (
        event_manifest.get("schema")
        != "YATL_CRL_EVENT_ACQUISITION_PROVENANCE"
    ):
        raise QualityError("unexpected event acquisition schema")
    if event_manifest.get("schema_version") != "0.1.0":
        raise QualityError("unsupported event acquisition schema version")
    if event_manifest.get("overall_status") != "COMPLETE":
        raise QualityError(
            "event acquisition is not COMPLETE and cannot be quality-admitted"
        )
    if event_manifest.get("quality_gate") != "PENDING_CRL003":
        raise QualityError("event is not pending CRL-003")
    if event_manifest.get("market_outcomes_exposed") is not False:
        raise QualityError("market-outcome exposure invariant is invalid")
    if event_manifest.get("research_only") is not True:
        raise QualityError("research-only invariant is missing")
    if event_manifest.get("p10_write_allowed") is not False:
        raise QualityError("P10 write invariant is invalid")
    if event_manifest.get("p11_locked") is not True:
        raise QualityError("P11 lock invariant is missing")

    event_id = event_manifest.get("event_id")
    designation = event_manifest.get("designation")
    replay_eligible = event_manifest.get("replay_eligible")
    if not isinstance(event_id, str):
        raise QualityError("event identity is missing")
    if designation not in _ALLOWED_DESIGNATIONS:
        raise QualityError("event designation is invalid")
    if not isinstance(replay_eligible, bool):
        raise QualityError("event replay eligibility is invalid")

    datasets = event_manifest.get("datasets")
    failures = event_manifest.get("failures")
    if not isinstance(datasets, list) or len(datasets) != 6:
        raise QualityError("event must contain exactly six acquired datasets")
    if failures != []:
        raise QualityError("event acquisition contains failures")

    expected_pairs = {
        (symbol, interval)
        for symbol in acq.ALLOWED_SYMBOLS
        for interval in acq.ALLOWED_INTERVALS
    }
    actual_pairs = {
        (item.get("symbol"), item.get("interval"))
        for item in datasets
        if isinstance(item, dict)
    }
    if actual_pairs != expected_pairs:
        raise QualityError("event dataset identity set is incomplete")

    reports: list[dict[str, object]] = []
    for item in datasets:
        if not isinstance(item, dict):
            raise QualityError("dataset reference is invalid")
        reports.append(
            validate_dataset(
                runtime_root=runtime_root,
                event_manifest=event_manifest,
                dataset_ref=item,
            )
        )

    pass_count = sum(
        1 for report in reports if report["quality_status"] == "PASS"
    )
    fail_count = len(reports) - pass_count
    overall = "PASS" if fail_count == 0 else "FAIL"
    replay_admitted = bool(overall == "PASS" and replay_eligible)

    event_quality: dict[str, object] = {
        "schema": "YATL_CRL_EVENT_QUALITY_MANIFEST",
        "schema_version": QUALITY_SCHEMA_VERSION,
        "implementation_id": QUALITY_IMPLEMENTATION_ID,
        "catalog_version": acq.CATALOG_VERSION,
        "event_id": event_id,
        "designation": designation,
        "replay_eligible": replay_eligible,
        "input_event_acquisition_manifest_relative_path": (
            event_manifest_relative_path
        ),
        "input_event_acquisition_manifest_sha256": expected_event_sha,
        "dataset_count": len(reports),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "overall_status": overall,
        "replay_admitted": replay_admitted,
        "admission_reason": (
            "QUALITY_PASS"
            if replay_admitted
            else (
                "CATALOG_REPLAY_INELIGIBLE"
                if overall == "PASS"
                else "QUALITY_FAILURE"
            )
        ),
        "datasets": [
            {
                "symbol": report["symbol"],
                "interval": report["interval"],
                "quality_status": report["quality_status"],
                "replay_admitted": report["replay_admitted"],
                "failure_codes": report["failure_codes"],
                "quality_manifest_relative_path": report[
                    "quality_manifest_relative_path"
                ],
                "quality_manifest_file_sha256": report[
                    "quality_manifest_file_sha256"
                ],
            }
            for report in reports
        ],
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    event_quality["quality_manifest_sha256"] = _sha256(
        _canonical_json(event_quality)
    )
    payload = _canonical_json(event_quality)
    file_sha = _sha256(payload)
    relative = _event_quality_relative_path(event_id, file_sha)
    relative_text = _write_immutable(runtime_root, relative, payload)
    event_quality["quality_manifest_file_sha256"] = file_sha
    event_quality["quality_manifest_relative_path"] = relative_text
    return event_quality


def safe_summary(result: Mapping[str, object]) -> dict[str, object]:
    return {
        "event_id": result["event_id"],
        "designation": result["designation"],
        "replay_eligible": result["replay_eligible"],
        "dataset_count": result["dataset_count"],
        "pass_count": result["pass_count"],
        "fail_count": result["fail_count"],
        "overall_status": result["overall_status"],
        "replay_admitted": result["replay_admitted"],
        "admission_reason": result["admission_reason"],
        "quality_manifest_relative_path": result[
            "quality_manifest_relative_path"
        ],
        "quality_manifest_file_sha256": result[
            "quality_manifest_file_sha256"
        ],
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab.quality",
        description="YATL CRL-003 deterministic structural quality admission",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser(
        "validate-event",
        help="validate one immutable CRL-002 event acquisition manifest",
    )
    validate.add_argument("--runtime-root", type=Path, required=True)
    validate.add_argument("--event-manifest", required=True)
    validate.add_argument("--event-manifest-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "validate-event":
        raise QualityError("unsupported CRL-003 command")
    result = validate_event(
        runtime_root=args.runtime_root,
        event_manifest_relative_path=args.event_manifest,
        event_manifest_sha256=args.event_manifest_sha256,
    )
    print(
        json.dumps(
            safe_summary(result),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0 if result["overall_status"] == "PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QualityError as exc:
        print(
            json.dumps(
                {
                    "code": "CRL003_QUALITY_ERROR",
                    "reason": str(exc),
                    "market_outcomes_exposed": False,
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(2)
