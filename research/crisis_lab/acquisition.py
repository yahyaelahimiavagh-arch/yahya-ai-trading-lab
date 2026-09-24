"""CRL-002 research-only historical market-data acquisition.

This module lives outside the production yatl package. It has no account,
execution, risk, notification, AI, or P10 write capability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

ACQUISITION_IMPLEMENTATION_ID = "CRL-002/0.1.1"
CATALOG_VERSION = "0.1.0"
DEFAULT_REGISTER_PATH = Path(
    "docs/research/crisis-lab/DATA-ACQUISITION-REGISTER-v0.1.0.json"
)
DEFAULT_RUNTIME_ROOT = Path("data/research/crisis-lab")
PROTECTED_RUNTIME_PREFIXES = (Path("/var/lib/yatl/p10"),)

ARCHIVE_HOST = "data.binance.vision"
ARCHIVE_BASE = f"https://{ARCHIVE_HOST}/data/spot"
REST_HOST = "data-api.binance.vision"
REST_BASE = f"https://{REST_HOST}"

ALLOWED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
ALLOWED_INTERVALS = ("15m", "1h", "4h")
INTERVAL_MILLISECONDS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}
CANONICAL_COLUMNS = (
    "open_time_ms", "open", "high", "low", "close", "base_volume",
    "close_time_ms", "quote_volume", "trade_count",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
)

_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
_MAX_REST_BYTES = 2 * 1024 * 1024
_MAX_CHECKSUM_BYTES = 4096
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class AcquisitionError(RuntimeError):
    """Fail-closed CRL-002 acquisition error."""


@dataclass(frozen=True)
class ArchiveObject:
    cadence: str
    symbol: str
    interval: str
    period: str
    url: str
    checksum_url: str
    member_name: str
    source_timestamp_unit: str


@dataclass(frozen=True)
class DatasetPlan:
    event_id: str
    designation: str
    replay_eligible: bool
    symbol: str
    interval: str
    semantic_start_ms: int
    semantic_end_ms: int
    transport_start_ms: int
    transport_end_ms: int
    archive_objects: tuple[ArchiveObject, ...]

    @property
    def expected_rows(self) -> int:
        duration = INTERVAL_MILLISECONDS[self.interval]
        return (self.transport_end_ms - self.transport_start_ms) // duration


@dataclass(frozen=True)
class CanonicalRow:
    values: tuple[str, ...]

    @property
    def open_time_ms(self) -> int:
        return int(self.values[0])

    @property
    def close_time_ms(self) -> int:
        return int(self.values[6])


@dataclass(frozen=True)
class ArchiveEvidence:
    cadence: str
    period: str
    url: str
    checksum_url: str
    source_timestamp_unit: str
    expected_zip_sha256: str
    downloaded_zip_sha256: str
    extracted_csv_sha256: str
    rows_selected: int
    checksum_transport: dict[str, object]
    archive_transport: dict[str, object]
    archive_cache_hit: bool
    close_boundary_normalization_count: int
    close_boundary_rest_verified_count: int
    raw_zip_relative_path: str
    checksum_relative_path: str
    extracted_csv_relative_path: str

    def as_record(self) -> dict[str, object]:
        return {
            "cadence": self.cadence,
            "period": self.period,
            "url": self.url,
            "checksum_url": self.checksum_url,
            "source_timestamp_unit": self.source_timestamp_unit,
            "expected_zip_sha256": self.expected_zip_sha256,
            "downloaded_zip_sha256": self.downloaded_zip_sha256,
            "extracted_csv_sha256": self.extracted_csv_sha256,
            "rows_selected": self.rows_selected,
            "checksum_transport": self.checksum_transport,
            "archive_transport": self.archive_transport,
            "archive_cache_hit": self.archive_cache_hit,
            "close_boundary_normalization_count": (
                self.close_boundary_normalization_count
            ),
            "close_boundary_rest_verified_count": (
                self.close_boundary_rest_verified_count
            ),
            "raw_zip_relative_path": self.raw_zip_relative_path,
            "checksum_relative_path": self.checksum_relative_path,
            "extracted_csv_relative_path": self.extracted_csv_relative_path,
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpsFetcher:
    """Bounded HTTPS GET with exact-host allowlisting and no ambient proxies."""

    def __init__(
        self,
        allowed_hosts: Sequence[str],
        *,
        timeout_seconds: float = 30.0,
        attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if not allowed_hosts:
            raise AcquisitionError("HTTPS fetcher requires a host allowlist")
        if attempts < 1 or attempts > 3:
            raise AcquisitionError("HTTPS attempts must be between 1 and 3")
        self._allowed_hosts = frozenset(allowed_hosts)
        self._timeout_seconds = timeout_seconds
        self._attempts = attempts
        self._sleeper = sleeper
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        self._transport_history: dict[str, list[dict[str, object]]] = {}

    def _record_transport(
        self,
        url: str,
        *,
        attempt: int,
        outcome: str,
        status: int | None = None,
        error_class: str | None = None,
    ) -> None:
        event: dict[str, object] = {
            "attempt": attempt,
            "outcome": outcome,
        }
        if status is not None:
            event["http_status"] = status
        if error_class is not None:
            event["error_class"] = error_class
        self._transport_history.setdefault(url, []).append(event)

    def transport_summary(self, url: str) -> dict[str, object]:
        events = tuple(self._transport_history.get(url, ()))
        return {
            "attempts": len(events),
            "failures": [
                dict(item)
                for item in events
                if item.get("outcome") != "SUCCESS"
            ],
            "final_outcome": (
                events[-1]["outcome"]
                if events
                else "NOT_ATTEMPTED"
            ),
        }

    def fetch(self, url: str, *, max_bytes: int) -> bytes:
        _validate_https_url(url, self._allowed_hosts)
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "YATL-Crisis-Lab-Research/0.1",
                        "Accept": "*/*",
                    },
                    method="GET",
                )
                with self._opener.open(
                    request, timeout=self._timeout_seconds
                ) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise AcquisitionError(
                            f"unexpected HTTP status {status}"
                        )
                    declared = response.headers.get("Content-Length")
                    if declared is not None:
                        try:
                            size = int(declared)
                        except ValueError:
                            raise AcquisitionError(
                                "invalid Content-Length"
                            ) from None
                        if size < 0 or size > max_bytes:
                            raise AcquisitionError(
                                "response exceeds configured size limit"
                            )
                    payload = response.read(max_bytes + 1)
                    if len(payload) > max_bytes:
                        raise AcquisitionError(
                            "response exceeds configured size limit"
                        )
                    self._record_transport(
                        url,
                        attempt=attempt,
                        outcome="SUCCESS",
                        status=status,
                    )
                    return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                self._record_transport(
                    url,
                    attempt=attempt,
                    outcome="HTTP_ERROR",
                    status=exc.code,
                    error_class=exc.__class__.__name__,
                )
                if exc.code == 404:
                    break
                if exc.code != 429 and not (500 <= exc.code <= 599):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                self._record_transport(
                    url,
                    attempt=attempt,
                    outcome="TRANSPORT_ERROR",
                    error_class=exc.__class__.__name__,
                )
            if attempt < self._attempts:
                self._sleeper(float(attempt))
        if isinstance(last_error, urllib.error.HTTPError):
            raise AcquisitionError(
                f"HTTP fetch failed with status {last_error.code}"
            ) from None
        raise AcquisitionError(
            "HTTPS fetch failed after bounded retries"
        ) from None


def _validate_https_url(url: str, allowed_hosts: Iterable[str]) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise AcquisitionError("only HTTPS sources are permitted")
    if parsed.username is not None or parsed.password is not None:
        raise AcquisitionError("userinfo is forbidden in source URLs")
    if parsed.hostname not in frozenset(allowed_hosts):
        raise AcquisitionError("source host is not allowlisted")
    if parsed.port not in (None, 443):
        raise AcquisitionError("nonstandard source port is forbidden")
    if parsed.fragment:
        raise AcquisitionError("source URL fragments are forbidden")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(record: Mapping[str, object]) -> bytes:
    text = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return (text + "\n").encode("utf-8")


def _iso_to_ms(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AcquisitionError("UTC timestamp must end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise AcquisitionError("invalid UTC timestamp") from None
    if parsed.utcoffset() != timedelta(0):
        raise AcquisitionError("timestamp is not UTC")
    return int(parsed.timestamp() * 1000)


def _ms_to_iso(value: int) -> str:
    return (
        datetime.fromtimestamp(value / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _floor_to_interval(value: int, interval_ms: int) -> int:
    return (value // interval_ms) * interval_ms


def _ceil_to_interval(value: int, interval_ms: int) -> int:
    return ((value + interval_ms - 1) // interval_ms) * interval_ms


def source_timestamp_unit_for_day(day: date) -> str:
    return "MICROSECOND" if day >= date(2025, 1, 1) else "MILLISECOND"


def _month_last_day(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def _next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _archive_object(
    cadence: str,
    symbol: str,
    interval: str,
    period: str,
    period_day: date,
) -> ArchiveObject:
    if cadence not in ("daily", "monthly"):
        raise AcquisitionError("unsupported archive cadence")
    filename = f"{symbol}-{interval}-{period}.zip"
    url = (
        f"{ARCHIVE_BASE}/{cadence}/klines/"
        f"{symbol}/{interval}/{filename}"
    )
    return ArchiveObject(
        cadence=cadence,
        symbol=symbol,
        interval=interval,
        period=period,
        url=url,
        checksum_url=f"{url}.CHECKSUM",
        member_name=filename[:-4] + ".csv",
        source_timestamp_unit=source_timestamp_unit_for_day(period_day),
    )


def build_archive_objects(
    symbol: str,
    interval: str,
    transport_start_ms: int,
    transport_end_ms: int,
) -> tuple[ArchiveObject, ...]:
    if symbol not in ALLOWED_SYMBOLS:
        raise AcquisitionError("symbol is outside CRL-002 scope")
    if interval not in ALLOWED_INTERVALS:
        raise AcquisitionError("interval is outside CRL-002 scope")
    if transport_start_ms >= transport_end_ms:
        raise AcquisitionError("transport range is empty")

    first_day = datetime.fromtimestamp(
        transport_start_ms / 1000, timezone.utc
    ).date()
    last_day = datetime.fromtimestamp(
        (transport_end_ms - 1) / 1000, timezone.utc
    ).date()
    objects: list[ArchiveObject] = []
    cursor = first_day
    while cursor <= last_day:
        month_end = _month_last_day(cursor)
        if cursor.day == 1 and month_end <= last_day:
            period = f"{cursor.year:04d}-{cursor.month:02d}"
            objects.append(
                _archive_object("monthly", symbol, interval, period, cursor)
            )
            cursor = _next_month(cursor)
        else:
            period = cursor.isoformat()
            objects.append(
                _archive_object("daily", symbol, interval, period, cursor)
            )
            cursor += timedelta(days=1)
    return tuple(objects)


def load_acquisition_register(
    path: Path = DEFAULT_REGISTER_PATH,
) -> dict[str, object]:
    path = assert_safe_runtime_path(path)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise AcquisitionError(
            "cannot read canonical acquisition register"
        ) from None
    required = {
        "schema", "version", "catalog", "symbols", "intervals", "events",
        "protected_runtime_prefixes", "p11_locked",
    }
    if not isinstance(record, dict) or not required.issubset(record):
        raise AcquisitionError("acquisition register schema is incomplete")
    if record.get("schema") != "YATL_CRL_DATA_ACQUISITION_REGISTER":
        raise AcquisitionError("unexpected acquisition register schema")
    if record.get("version") != "0.1.0":
        raise AcquisitionError("unsupported acquisition register version")
    if record.get("p11_locked") is not True:
        raise AcquisitionError("P11 lock invariant is missing")
    if tuple(record.get("symbols", [])) != ALLOWED_SYMBOLS:
        raise AcquisitionError(
            "registered symbols differ from CRL-002 scope"
        )
    if tuple(record.get("intervals", [])) != ALLOWED_INTERVALS:
        raise AcquisitionError(
            "registered intervals differ from CRL-002 scope"
        )
    protected = tuple(record.get("protected_runtime_prefixes", []))
    if "/var/lib/yatl/p10/" not in protected:
        raise AcquisitionError("P10 protected runtime prefix is missing")
    return record


def plan_dataset(
    registration: Mapping[str, object],
    event_id: str,
    symbol: str,
    interval: str,
) -> DatasetPlan:
    if symbol not in ALLOWED_SYMBOLS or interval not in ALLOWED_INTERVALS:
        raise AcquisitionError("dataset pair is outside CRL-002 scope")
    events = registration.get("events")
    if not isinstance(events, list):
        raise AcquisitionError("acquisition register events are invalid")
    event = next(
        (
            item for item in events
            if isinstance(item, dict) and item.get("event_id") == event_id
        ),
        None,
    )
    if event is None:
        raise AcquisitionError("event is not registered")
    semantic = event.get("semantic_range")
    if not isinstance(semantic, dict):
        raise AcquisitionError("event semantic range is invalid")
    start_ms = _iso_to_ms(semantic.get("start_utc"))
    end_ms = _iso_to_ms(semantic.get("end_utc"))
    if start_ms >= end_ms:
        raise AcquisitionError("event semantic range is empty")

    duration = INTERVAL_MILLISECONDS[interval]
    transport_start = _floor_to_interval(start_ms, duration)
    transport_end = _ceil_to_interval(end_ms, duration)
    designation = event.get("designation")
    if designation not in ("DEVELOPMENT", "BLIND_HOLDOUT"):
        raise AcquisitionError("event designation is invalid")
    replay_eligible = event.get("replay_eligible")
    if not isinstance(replay_eligible, bool):
        raise AcquisitionError("event replay eligibility is invalid")
    return DatasetPlan(
        event_id=event_id,
        designation=designation,
        replay_eligible=replay_eligible,
        symbol=symbol,
        interval=interval,
        semantic_start_ms=start_ms,
        semantic_end_ms=end_ms,
        transport_start_ms=transport_start,
        transport_end_ms=transport_end,
        archive_objects=build_archive_objects(
            symbol, interval, transport_start, transport_end
        ),
    )


def assert_safe_runtime_path(
    path: Path,
    *,
    protected_prefixes: Sequence[Path] = PROTECTED_RUNTIME_PREFIXES,
) -> Path:
    candidate = path.expanduser()
    if candidate.exists() and candidate.is_symlink():
        raise AcquisitionError("symlink output path is forbidden")
    resolved = candidate.resolve(strict=False)
    for prefix in protected_prefixes:
        protected = prefix.expanduser().resolve(strict=False)
        if resolved == protected or protected in resolved.parents:
            raise AcquisitionError("P10 protected runtime path is forbidden")
    return resolved


def _ensure_runtime_root(runtime_root: Path) -> Path:
    resolved = assert_safe_runtime_path(runtime_root)
    resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(resolved, 0o700)
    except OSError:
        raise AcquisitionError(
            "cannot enforce runtime-root permissions"
        ) from None
    return resolved


def _write_immutable(
    runtime_root: Path,
    relative_path: Path,
    payload: bytes,
) -> str:
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise AcquisitionError("runtime relative path is invalid")
    root = _ensure_runtime_root(runtime_root)
    target = assert_safe_runtime_path(root / relative_path)
    try:
        target.relative_to(root)
    except ValueError:
        raise AcquisitionError(
            "runtime write escaped the research root"
        ) from None
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        if target.is_symlink():
            raise AcquisitionError("existing symlink target is forbidden")
        try:
            existing = target.read_bytes()
        except OSError:
            raise AcquisitionError(
                "cannot read existing immutable research file"
            ) from None
        if existing != payload:
            raise AcquisitionError("immutable research artifact conflict")
        return relative_path.as_posix()

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=".crl-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    except OSError:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise AcquisitionError(
            "cannot publish immutable research artifact"
        ) from None
    return relative_path.as_posix()


def parse_checksum(payload: bytes, expected_filename: str) -> str:
    if len(payload) > _MAX_CHECKSUM_BYTES:
        raise AcquisitionError("checksum payload is oversized")
    try:
        text = payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise AcquisitionError("checksum payload is not UTF-8") from None
    parts = text.split()
    if not parts or not _SHA256_RE.fullmatch(parts[0]):
        raise AcquisitionError(
            "checksum payload does not contain SHA-256"
        )
    if len(parts) >= 2:
        supplied = parts[-1].lstrip("*")
        if supplied != expected_filename:
            raise AcquisitionError(
                "checksum filename does not match archive object"
            )
    return parts[0].lower()


def _extract_archive(zip_payload: bytes, archive: ArchiveObject) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_payload), "r") as bundle:
            members = [item for item in bundle.infolist() if not item.is_dir()]
            if len(members) != 1:
                raise AcquisitionError(
                    "archive must contain exactly one file"
                )
            member = members[0]
            if Path(member.filename).name != member.filename:
                raise AcquisitionError("nested archive member is forbidden")
            if member.filename != archive.member_name:
                raise AcquisitionError(
                    "archive member name does not match source object"
                )
            if member.file_size < 0 or member.file_size > _MAX_EXTRACTED_BYTES:
                raise AcquisitionError(
                    "archive member exceeds extraction size limit"
                )
            payload = bundle.read(member)
            if len(payload) != member.file_size:
                raise AcquisitionError(
                    "archive member size changed during extraction"
                )
            return payload
    except (zipfile.BadZipFile, RuntimeError):
        raise AcquisitionError("invalid source ZIP archive") from None


def _normalize_source_timestamp(
    raw_text: str,
    unit: str,
    *,
    close_time: bool,
) -> int:
    try:
        raw = int(raw_text)
    except (TypeError, ValueError):
        raise AcquisitionError(
            "source timestamp is not an integer"
        ) from None
    if raw < 0:
        raise AcquisitionError("source timestamp is negative")
    if unit == "MILLISECOND":
        if raw < 1_000_000_000_000 or raw >= 10_000_000_000_000:
            raise AcquisitionError(
                "millisecond source timestamp magnitude is invalid"
            )
        return raw
    if unit == "MICROSECOND":
        if (
            raw < 1_000_000_000_000_000
            or raw >= 10_000_000_000_000_000
        ):
            raise AcquisitionError(
                "microsecond source timestamp magnitude is invalid"
            )
        remainder = raw % 1000
        expected = 999 if close_time else 0
        if remainder != expected:
            raise AcquisitionError(
                "microsecond timestamp is not on canonical candle boundary"
            )
        return raw // 1000
    raise AcquisitionError("unsupported source timestamp unit")


def _validate_decimal(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise AcquisitionError("source decimal field is invalid") from None
    if not value.is_finite():
        raise AcquisitionError("source decimal field is non-finite")
    return value


def _normalize_archive_csv_with_evidence(
    csv_payload: bytes,
    archive: ArchiveObject,
    plan: DatasetPlan,
) -> tuple[tuple[CanonicalRow, ...], tuple[CanonicalRow, ...]]:
    """Normalize archive rows and surface bounded close-boundary anomalies.

    Historical Binance Spot archives contain documented cases where the kline
    close-time field is inconsistent even though the open-time grid and the
    remaining row are usable. We never silently trust or discard such rows:
    the canonical close time is derived from the registered interval and every
    affected selected row is returned for exact REST verification.
    """
    try:
        text = csv_payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AcquisitionError("archive CSV is not UTF-8") from None

    selected: list[CanonicalRow] = []
    close_boundary_anomalies: list[CanonicalRow] = []
    duration = INTERVAL_MILLISECONDS[plan.interval]
    for row_number, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if len(row) != 12:
            raise AcquisitionError(
                f"archive CSV row {row_number} has wrong field count"
            )
        open_ms = _normalize_source_timestamp(
            row[0], archive.source_timestamp_unit, close_time=False
        )
        source_close_ms = _normalize_source_timestamp(
            row[6], archive.source_timestamp_unit, close_time=True
        )
        if open_ms % duration != 0:
            raise AcquisitionError(
                "source candle open is off the UTC interval grid"
            )
        canonical_close_ms = open_ms + duration - 1

        open_px = _validate_decimal(row[1])
        high_px = _validate_decimal(row[2])
        low_px = _validate_decimal(row[3])
        close_px = _validate_decimal(row[4])
        volumes = tuple(
            _validate_decimal(row[index]) for index in (5, 7, 9, 10)
        )
        if min(volumes) < 0:
            raise AcquisitionError("source volume field is negative")
        if high_px < max(open_px, close_px):
            raise AcquisitionError("source high is below open/close")
        if low_px > min(open_px, close_px) or low_px > high_px:
            raise AcquisitionError("source low is invalid")
        try:
            trade_count = int(row[8])
        except ValueError:
            raise AcquisitionError("source trade count is invalid") from None
        if trade_count < 0:
            raise AcquisitionError("source trade count is negative")

        if plan.transport_start_ms <= open_ms < plan.transport_end_ms:
            canonical = CanonicalRow(
                (
                    str(open_ms), row[1], row[2], row[3], row[4], row[5],
                    str(canonical_close_ms), row[7], str(trade_count), row[9],
                    row[10], row[11],
                )
            )
            selected.append(canonical)
            if source_close_ms != canonical_close_ms:
                close_boundary_anomalies.append(canonical)
    return tuple(selected), tuple(close_boundary_anomalies)


def normalize_archive_csv(
    csv_payload: bytes,
    archive: ArchiveObject,
    plan: DatasetPlan,
) -> tuple[CanonicalRow, ...]:
    rows, _ = _normalize_archive_csv_with_evidence(
        csv_payload, archive, plan
    )
    return rows

def _canonical_csv(rows: Sequence[CanonicalRow]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CANONICAL_COLUMNS)
    for row in rows:
        writer.writerow(row.values)
    return output.getvalue().encode("utf-8")


def _raw_base(archive: ArchiveObject) -> Path:
    return (
        Path("raw") / "binance-vision" / "spot" / archive.cadence
        / "klines" / archive.symbol / archive.interval
    )


def _raw_zip_relative_path(
    archive: ArchiveObject,
    zip_sha256: str,
) -> Path:
    stem = archive.member_name[:-4]
    return _raw_base(archive) / f"{stem}-{zip_sha256[:16]}.zip"


def _raw_relative_paths(
    archive: ArchiveObject,
    zip_sha256: str,
    csv_sha256: str,
) -> tuple[Path, Path, Path]:
    base = _raw_base(archive)
    stem = archive.member_name[:-4]
    zip_path = _raw_zip_relative_path(archive, zip_sha256)
    checksum_path = base / f"{stem}-{zip_sha256[:16]}.CHECKSUM"
    extracted_path = (
        Path("extracted") / "binance-vision" / archive.symbol
        / archive.interval / f"{stem}-{csv_sha256[:16]}.csv"
    )
    return zip_path, checksum_path, extracted_path


def _read_cached_zip(
    runtime_root: Path,
    relative_path: Path,
    expected_sha256: str,
) -> bytes | None:
    root = _ensure_runtime_root(runtime_root)
    target = assert_safe_runtime_path(root / relative_path)
    try:
        target.relative_to(root)
    except ValueError:
        raise AcquisitionError(
            "cached archive escaped the research root"
        ) from None
    if not target.exists():
        return None
    if target.is_symlink():
        raise AcquisitionError("cached archive symlink is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise AcquisitionError("cannot read cached archive") from None
    if _sha256(payload) != expected_sha256:
        raise AcquisitionError(
            "cached archive SHA-256 conflicts with official checksum"
        )
    return payload


def _transport_summary(fetcher, url: str) -> dict[str, object]:
    method = getattr(fetcher, "transport_summary", None)
    if callable(method):
        summary = method(url)
        if isinstance(summary, dict):
            return summary
    return {
        "attempts": None,
        "failures": [],
        "final_outcome": "UNINSTRUMENTED_TEST_DOUBLE",
    }


def _acquire_archive_object(
    plan: DatasetPlan,
    archive: ArchiveObject,
    *,
    runtime_root: Path,
    fetcher,
    rest_fetcher=None,
) -> tuple[tuple[CanonicalRow, ...], ArchiveEvidence]:
    checksum_payload = fetcher.fetch(
        archive.checksum_url, max_bytes=_MAX_CHECKSUM_BYTES
    )
    filename = Path(urllib.parse.urlsplit(archive.url).path).name
    expected_sha = parse_checksum(checksum_payload, filename)
    cached_relative = _raw_zip_relative_path(archive, expected_sha)
    zip_payload = _read_cached_zip(
        runtime_root,
        cached_relative,
        expected_sha,
    )
    archive_cache_hit = zip_payload is not None
    if zip_payload is None:
        zip_payload = fetcher.fetch(
            archive.url, max_bytes=_MAX_ARCHIVE_BYTES
        )
    actual_sha = _sha256(zip_payload)
    if actual_sha != expected_sha:
        raise AcquisitionError(
            "downloaded archive SHA-256 does not match official checksum"
        )
    csv_payload = _extract_archive(zip_payload, archive)
    csv_sha = _sha256(csv_payload)
    rows, close_boundary_anomalies = (
        _normalize_archive_csv_with_evidence(
            csv_payload, archive, plan
        )
    )
    close_boundary_rest_verified_count = 0
    if close_boundary_anomalies:
        if rest_fetcher is None:
            raise AcquisitionError(
                "source close-boundary anomaly requires REST verification"
            )
        anomaly_verification = _verify_exact_rest_rows(
            close_boundary_anomalies,
            symbol=plan.symbol,
            interval=plan.interval,
            fetcher=rest_fetcher,
        )
        if anomaly_verification["status"] != "MATCH":
            raise AcquisitionError(
                "source close-boundary anomaly conflicts with REST"
            )
        close_boundary_rest_verified_count = len(
            close_boundary_anomalies
        )

    raw_zip, checksum_path, extracted = _raw_relative_paths(
        archive, actual_sha, csv_sha
    )
    raw_rel = _write_immutable(runtime_root, raw_zip, zip_payload)
    checksum_rel = _write_immutable(
        runtime_root, checksum_path, checksum_payload
    )
    extracted_rel = _write_immutable(
        runtime_root, extracted, csv_payload
    )
    return rows, ArchiveEvidence(
        cadence=archive.cadence,
        period=archive.period,
        url=archive.url,
        checksum_url=archive.checksum_url,
        source_timestamp_unit=archive.source_timestamp_unit,
        expected_zip_sha256=expected_sha,
        downloaded_zip_sha256=actual_sha,
        extracted_csv_sha256=csv_sha,
        rows_selected=len(rows),
        checksum_transport=_transport_summary(
            fetcher, archive.checksum_url
        ),
        archive_transport=(
            {
                "attempts": 0,
                "failures": [],
                "final_outcome": "CACHE_HIT",
            }
            if archive_cache_hit
            else _transport_summary(fetcher, archive.url)
        ),
        archive_cache_hit=archive_cache_hit,
        close_boundary_normalization_count=len(
            close_boundary_anomalies
        ),
        close_boundary_rest_verified_count=(
            close_boundary_rest_verified_count
        ),
        raw_zip_relative_path=raw_rel,
        checksum_relative_path=checksum_rel,
        extracted_csv_relative_path=extracted_rel,
    )


def _normalize_rest_row_with_evidence(
    row: Sequence[object],
    interval: str,
    *,
    allow_close_boundary_normalization: bool,
) -> tuple[CanonicalRow, bool]:
    if len(row) < 12:
        raise AcquisitionError("REST kline row has wrong field count")
    converted = [str(item) for item in row[:12]]
    duration = INTERVAL_MILLISECONDS[interval]
    try:
        open_ms = int(converted[0])
        source_close_ms = int(converted[6])
        trade_count = int(converted[8])
    except ValueError:
        raise AcquisitionError("REST kline integer field is invalid") from None
    if open_ms % duration != 0:
        raise AcquisitionError("REST kline open boundary is invalid")
    canonical_close_ms = open_ms + duration - 1
    close_boundary_normalized = source_close_ms != canonical_close_ms
    if close_boundary_normalized and not allow_close_boundary_normalization:
        raise AcquisitionError("REST kline boundary is invalid")
    for index in (1, 2, 3, 4, 5, 7, 9, 10):
        _validate_decimal(converted[index])
    converted[0] = str(open_ms)
    converted[6] = str(canonical_close_ms)
    converted[8] = str(trade_count)
    return CanonicalRow(tuple(converted)), close_boundary_normalized


def _normalize_rest_row(
    row: Sequence[object],
    interval: str,
) -> CanonicalRow:
    normalized, _ = _normalize_rest_row_with_evidence(
        row,
        interval,
        allow_close_boundary_normalization=False,
    )
    return normalized


def _rest_kline_url(
    symbol: str,
    interval: str,
    open_time_ms: int,
) -> str:
    duration = INTERVAL_MILLISECONDS[interval]
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": interval,
            "startTime": str(open_time_ms),
            "endTime": str(open_time_ms + duration - 1),
            "limit": "1",
            "timeZone": "0",
        }
    )
    return f"{REST_BASE}/api/v3/klines?{query}"


def _verify_exact_rest_rows(
    rows: Sequence[CanonicalRow],
    *,
    symbol: str,
    interval: str,
    fetcher,
) -> dict[str, object]:
    transport: list[dict[str, object]] = []
    for target in rows:
        url = _rest_kline_url(symbol, interval, target.open_time_ms)
        payload = fetcher.fetch(url, max_bytes=_MAX_REST_BYTES)
        transport.append(
            {
                "open_time_ms": target.open_time_ms,
                "transport": _transport_summary(fetcher, url),
            }
        )
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AcquisitionError(
                "REST verification response is invalid JSON"
            ) from None
        if (
            not isinstance(body, list)
            or len(body) != 1
            or not isinstance(body[0], list)
        ):
            raise AcquisitionError(
                "REST verification did not return exactly one kline"
            )
        normalized, close_boundary_normalized = (
            _normalize_rest_row_with_evidence(
                body[0],
                interval,
                allow_close_boundary_normalization=True,
            )
        )
        transport[-1]["close_boundary_normalized"] = (
            close_boundary_normalized
        )
        if normalized.values != target.values:
            return {
                "status": "MISMATCH",
                "checked_points": len(transport),
                "close_boundary_normalization_count": sum(
                    bool(item.get("close_boundary_normalized"))
                    for item in transport
                ),
                "transport": transport,
            }
    return {
        "status": "MATCH",
        "checked_points": len(rows),
        "close_boundary_normalization_count": sum(
            bool(item.get("close_boundary_normalized"))
            for item in transport
        ),
        "transport": transport,
    }


def verify_rest_boundaries(
    rows: Sequence[CanonicalRow],
    *,
    symbol: str,
    interval: str,
    fetcher,
) -> dict[str, object]:
    if not rows:
        return {
            "enabled": True,
            "status": "NO_ROWS",
            "checked_points": 0,
            "transport": [],
        }
    targets = [rows[0]]
    if rows[-1].open_time_ms != rows[0].open_time_ms:
        targets.append(rows[-1])
    result = _verify_exact_rest_rows(
        targets,
        symbol=symbol,
        interval=interval,
        fetcher=fetcher,
    )
    return {
        "enabled": True,
        **result,
    }

def _dataset_manifest_relative_path(
    plan: DatasetPlan,
    digest: str,
) -> Path:
    return (
        Path("manifests") / f"event-catalog-v{CATALOG_VERSION}"
        / plan.event_id / plan.symbol / plan.interval
        / f"acquisition-{digest[:24]}.json"
    )


def acquire_dataset(
    plan: DatasetPlan,
    *,
    runtime_root: Path,
    archive_fetcher,
    rest_fetcher=None,
    retrieved_at_utc: str,
) -> dict[str, object]:
    _ensure_runtime_root(runtime_root)
    all_rows: list[CanonicalRow] = []
    sources: list[ArchiveEvidence] = []
    for archive in plan.archive_objects:
        rows, evidence = _acquire_archive_object(
            plan,
            archive,
            runtime_root=runtime_root,
            fetcher=archive_fetcher,
            rest_fetcher=rest_fetcher,
        )
        all_rows.extend(rows)
        sources.append(evidence)

    all_rows.sort(key=lambda item: item.open_time_ms)
    unique: dict[int, CanonicalRow] = {}
    duplicate_count = 0
    for row in all_rows:
        prior = unique.get(row.open_time_ms)
        if prior is None:
            unique[row.open_time_ms] = row
        elif prior.values == row.values:
            duplicate_count += 1
        else:
            raise AcquisitionError(
                "conflicting duplicate candle across source objects"
            )
    rows = tuple(unique[key] for key in sorted(unique))

    duration = INTERVAL_MILLISECONDS[plan.interval]
    expected = set(
        range(plan.transport_start_ms, plan.transport_end_ms, duration)
    )
    actual = set(unique)
    if actual - expected:
        raise AcquisitionError(
            "canonical selection contains out-of-range candles"
        )
    gap_count = len(expected - actual)

    canonical_payload = _canonical_csv(rows)
    canonical_sha = _sha256(canonical_payload)
    canonical_relative = (
        Path("canonical") / f"event-catalog-v{CATALOG_VERSION}"
        / plan.event_id / plan.symbol / plan.interval
        / f"dataset-{canonical_sha}.csv"
    )
    canonical_rel = _write_immutable(
        runtime_root, canonical_relative, canonical_payload
    )

    if rest_fetcher is None:
        rest_verification = {
            "enabled": False,
            "status": "NOT_RUN",
            "checked_points": 0,
            "transport": [],
        }
    else:
        rest_verification = verify_rest_boundaries(
            rows,
            symbol=plan.symbol,
            interval=plan.interval,
            fetcher=rest_fetcher,
        )

    if rest_verification["status"] == "MISMATCH":
        acquisition_status = "QUARANTINED_SOURCE_CONFLICT"
    elif gap_count or duplicate_count:
        acquisition_status = "ACQUIRED_WITH_STRUCTURAL_ANOMALY"
    elif rest_verification["status"] in ("MATCH", "NOT_RUN"):
        acquisition_status = "ACQUIRED_NEEDS_CRL003"
    else:
        acquisition_status = "ACQUIRED_VERIFICATION_INCOMPLETE"

    manifest: dict[str, object] = {
        "schema": "YATL_CRL_DATASET_ACQUISITION_PROVENANCE",
        "schema_version": "0.1.0",
        "implementation_id": ACQUISITION_IMPLEMENTATION_ID,
        "catalog_version": CATALOG_VERSION,
        "event_id": plan.event_id,
        "designation": plan.designation,
        "replay_eligible": plan.replay_eligible,
        "symbol": plan.symbol,
        "interval": plan.interval,
        "semantic_range": {
            "start_utc": _ms_to_iso(plan.semantic_start_ms),
            "end_utc": _ms_to_iso(plan.semantic_end_ms),
        },
        "transport_range": {
            "start_utc": _ms_to_iso(plan.transport_start_ms),
            "end_utc": _ms_to_iso(plan.transport_end_ms),
        },
        "retrieved_at_utc": retrieved_at_utc,
        "primary_source": "BINANCE_PUBLIC_DATA",
        "source_objects": [item.as_record() for item in sources],
        "canonical": {
            "relative_path": canonical_rel,
            "sha256": canonical_sha,
            "row_count": len(rows),
            "expected_row_count": plan.expected_rows,
            "first_open_time_ms": rows[0].open_time_ms if rows else None,
            "last_open_time_ms": rows[-1].open_time_ms if rows else None,
            "gap_count": gap_count,
            "duplicate_count": duplicate_count,
            "close_boundary_normalization_count": sum(
                item.close_boundary_normalization_count
                for item in sources
            ),
            "close_boundary_rest_verified_count": sum(
                item.close_boundary_rest_verified_count
                for item in sources
            ),
        },
        "rest_verification": rest_verification,
        "acquisition_status": acquisition_status,
        "quality_gate": "PENDING_CRL003",
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    preidentity_sha = _sha256(_canonical_json(manifest))
    manifest["manifest_sha256"] = preidentity_sha
    payload = _canonical_json(manifest)
    file_sha = _sha256(payload)
    relative = _dataset_manifest_relative_path(plan, file_sha)
    manifest_rel = _write_immutable(runtime_root, relative, payload)
    manifest["manifest_file_sha256"] = file_sha
    manifest["manifest_relative_path"] = manifest_rel
    return manifest


def _event_manifest_relative_path(event_id: str, digest: str) -> Path:
    return (
        Path("manifests") / f"event-catalog-v{CATALOG_VERSION}"
        / event_id / f"event-acquisition-{digest[:24]}.json"
    )


def _validate_retrieval_timestamp(value: str) -> str:
    return _ms_to_iso(_iso_to_ms(value))


def acquire_event(
    registration: Mapping[str, object],
    event_id: str,
    *,
    runtime_root: Path,
    archive_fetcher,
    rest_fetcher=None,
    retrieved_at_utc: str,
) -> dict[str, object]:
    retrieved_at_utc = _validate_retrieval_timestamp(retrieved_at_utc)
    datasets: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    designation: str | None = None
    replay_eligible: bool | None = None

    for symbol in ALLOWED_SYMBOLS:
        for interval in ALLOWED_INTERVALS:
            plan = plan_dataset(
                registration, event_id, symbol, interval
            )
            designation = plan.designation
            replay_eligible = plan.replay_eligible
            try:
                result = acquire_dataset(
                    plan,
                    runtime_root=runtime_root,
                    archive_fetcher=archive_fetcher,
                    rest_fetcher=rest_fetcher,
                    retrieved_at_utc=retrieved_at_utc,
                )
            except AcquisitionError as exc:
                failures.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "error_class": exc.__class__.__name__,
                        "reason": str(exc),
                    }
                )
            else:
                datasets.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "manifest_relative_path": result[
                            "manifest_relative_path"
                        ],
                        "manifest_file_sha256": result[
                            "manifest_file_sha256"
                        ],
                        "acquisition_status": result[
                            "acquisition_status"
                        ],
                        "quality_gate": result["quality_gate"],
                        "row_count": result["canonical"]["row_count"],
                        "expected_row_count": result["canonical"][
                            "expected_row_count"
                        ],
                        "gap_count": result["canonical"]["gap_count"],
                        "duplicate_count": result["canonical"][
                            "duplicate_count"
                        ],
                        "rest_verification_status": result[
                            "rest_verification"
                        ]["status"],
                    }
                )

    if designation is None or replay_eligible is None:
        raise AcquisitionError(
            "event produced no registered dataset plans"
        )
    if failures or len(datasets) != 6:
        overall = "INCOMPLETE"
    elif any(
        item["acquisition_status"] == "QUARANTINED_SOURCE_CONFLICT"
        for item in datasets
    ):
        overall = "COMPLETE_WITH_QUARANTINE"
    elif any(
        item["acquisition_status"] != "ACQUIRED_NEEDS_CRL003"
        for item in datasets
    ):
        overall = "COMPLETE_WITH_ANOMALY"
    else:
        overall = "COMPLETE"

    event_manifest: dict[str, object] = {
        "schema": "YATL_CRL_EVENT_ACQUISITION_PROVENANCE",
        "schema_version": "0.1.0",
        "implementation_id": ACQUISITION_IMPLEMENTATION_ID,
        "catalog_version": CATALOG_VERSION,
        "event_id": event_id,
        "designation": designation,
        "replay_eligible": replay_eligible,
        "retrieved_at_utc": retrieved_at_utc,
        "overall_status": overall,
        "dataset_count": len(datasets),
        "datasets": datasets,
        "failures": failures,
        "market_outcomes_exposed": False,
        "quality_gate": "PENDING_CRL003",
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
    }
    event_manifest["manifest_sha256"] = _sha256(
        _canonical_json(event_manifest)
    )
    payload = _canonical_json(event_manifest)
    file_sha = _sha256(payload)
    relative = _event_manifest_relative_path(event_id, file_sha)
    manifest_rel = _write_immutable(runtime_root, relative, payload)
    event_manifest["manifest_file_sha256"] = file_sha
    event_manifest["manifest_relative_path"] = manifest_rel
    return event_manifest


def plan_event(
    registration: Mapping[str, object],
    event_id: str,
) -> dict[str, object]:
    datasets = []
    designation = None
    replay_eligible = None
    for symbol in ALLOWED_SYMBOLS:
        for interval in ALLOWED_INTERVALS:
            plan = plan_dataset(
                registration, event_id, symbol, interval
            )
            designation = plan.designation
            replay_eligible = plan.replay_eligible
            datasets.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "semantic_start_utc": _ms_to_iso(
                        plan.semantic_start_ms
                    ),
                    "semantic_end_utc": _ms_to_iso(
                        plan.semantic_end_ms
                    ),
                    "transport_start_utc": _ms_to_iso(
                        plan.transport_start_ms
                    ),
                    "transport_end_utc": _ms_to_iso(
                        plan.transport_end_ms
                    ),
                    "archive_object_count": len(plan.archive_objects),
                    "expected_row_count": plan.expected_rows,
                }
            )
    return {
        "schema": "YATL_CRL_ACQUISITION_PLAN",
        "implementation_id": ACQUISITION_IMPLEMENTATION_ID,
        "event_id": event_id,
        "designation": designation,
        "replay_eligible": replay_eligible,
        "datasets": datasets,
        "research_only": True,
        "market_data_downloaded": False,
        "market_outcomes_exposed": False,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _print_json(record: Mapping[str, object]) -> None:
    print(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def _safe_cli_summary(
    result: Mapping[str, object],
) -> dict[str, object]:
    return {
        "event_id": result["event_id"],
        "designation": result["designation"],
        "replay_eligible": result["replay_eligible"],
        "overall_status": result["overall_status"],
        "dataset_count": result["dataset_count"],
        "failure_count": len(result["failures"]),
        "manifest_relative_path": result["manifest_relative_path"],
        "manifest_file_sha256": result["manifest_file_sha256"],
        "quality_gate": "PENDING_CRL003",
        "market_outcomes_exposed": False,
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab",
        description=(
            "YATL CRL-002 research-only historical data acquisition"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser(
        "plan", help="print a no-network acquisition plan"
    )
    plan_parser.add_argument("--event", required=True)
    plan_parser.add_argument(
        "--register", type=Path, default=DEFAULT_REGISTER_PATH
    )

    acquire_parser = sub.add_parser(
        "acquire-event",
        help=(
            "acquire one registered event into the research runtime tree"
        ),
    )
    acquire_parser.add_argument("--event", required=True)
    acquire_parser.add_argument(
        "--register", type=Path, default=DEFAULT_REGISTER_PATH
    )
    acquire_parser.add_argument(
        "--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT
    )
    acquire_parser.add_argument("--retrieved-at-utc", default=None)
    acquire_parser.add_argument(
        "--no-rest-verify",
        action="store_true",
        help="skip independent REST boundary verification",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registration = load_acquisition_register(args.register)
    if args.command == "plan":
        _print_json(plan_event(registration, args.event))
        return 0
    if args.command == "acquire-event":
        archive_fetcher = HttpsFetcher((ARCHIVE_HOST,))
        rest_fetcher = (
            None
            if args.no_rest_verify
            else HttpsFetcher((REST_HOST,))
        )
        result = acquire_event(
            registration,
            args.event,
            runtime_root=args.runtime_root,
            archive_fetcher=archive_fetcher,
            rest_fetcher=rest_fetcher,
            retrieved_at_utc=args.retrieved_at_utc or _now_utc(),
        )
        _print_json(_safe_cli_summary(result))
        return 0 if result["overall_status"] == "COMPLETE" else 2
    raise AcquisitionError("unsupported command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcquisitionError as exc:
        print(
            json.dumps(
                {
                    "code": "CRL002_ACQUISITION_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(2)
