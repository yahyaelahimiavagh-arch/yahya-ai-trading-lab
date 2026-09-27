"""AF-01C archive-only Development population; no performance or order path."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from research.crisis_lab.acquisition import (
    AcquisitionError, ArchiveObject, DatasetPlan, HttpsFetcher, _canonical_csv,
    _normalize_archive_csv_with_evidence, _monthly_daily_override_days,
    parse_checksum,
)
from .archive_inventory import HOST, InventoryUnproven, parse_key, verify
from .canonical import validate_rows
from .index import build_index
from .lifecycle import Lifecycle
from .models import OpportunityError, canonical, development_path, digest, sha256
from .quality import admit, gap_map
from .storage import save_artifact
from research.mass_candidate_factory.models import guard_root

START = 1577836800000
END = 1672531200000
STATES = frozenset({"MONTHLY_SUCCESS", "DAILY_FALLBACK_SUCCESS", "MISSING_ARCHIVE",
                    "MISSING_CHECKSUM", "CHECKSUM_MISMATCH", "INVALID_ZIP",
                    "INVALID_MEMBER", "INVALID_SCHEMA", "TIMESTAMP_ANOMALY",
                    "SOURCE_GAP", "UNRECOVERABLE"})
RECOVERABLE = STATES - {"MONTHLY_SUCCESS", "DAILY_FALLBACK_SUCCESS"}
CLASSIFICATIONS = frozenset({"ORDINARY_SPOT_CONFIRMED", "NONORDINARY_CONFIRMED",
                             "PRODUCT_CLASSIFICATION_UNRESOLVED"})
# Exact known examples only; suffix heuristics would misclassify ordinary tickers.
KNOWN_LEVERAGED = frozenset({"BTCUPUSDT", "BTCDOWNUSDT", "ETHUPUSDT", "ETHDOWNUSDT",
                             "BNBUPUSDT", "BNBDOWNUSDT", "BTCBULLUSDT", "BTCBEARUSDT",
                             "ETHBULLUSDT", "ETHBEARUSDT"})


def _date_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)


def object_bounds(item: dict) -> tuple[int, int]:
    first = date.fromisoformat(item["period"] + "-01" if item["cadence"] == "monthly" else item["period"])
    if item["cadence"] == "monthly":
        last = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    else:
        last = first + timedelta(days=1)
    return _date_ms(first), _date_ms(last)


def plan(snapshot: dict, symbols: tuple[str, ...], months: tuple[str, ...], *, pilot: bool = True) -> dict:
    verify(snapshot)
    if pilot and (not symbols or len(set(symbols)) > 10 or not months or len(set(months)) > 3):
        raise OpportunityError("pilot bound exceeded")
    if len(set(symbols)) != len(symbols) or len(set(months)) != len(months):
        raise OpportunityError("duplicate pilot identity")
    requested = set(symbols)
    if any(not re.fullmatch(r"[A-Z0-9]+USDT", s) for s in requested):
        raise OpportunityError("unregistered symbol")
    if any(not re.fullmatch(r"20(?:20|21|22)-(?:0[1-9]|1[0-2])", m) for m in months):
        raise OpportunityError("outside Development range")
    objects = snapshot["objects"]
    registered = {x["symbol"] for x in objects}
    if requested - registered:
        raise OpportunityError("symbol absent from historical inventory")
    chosen = []
    by_key = {x["key"]: x for x in objects}
    for symbol in sorted(requested):
        for month in sorted(months):
            monthly_key = f"data/spot/monthly/klines/{symbol}/15m/{symbol}-15m-{month}.zip"
            days = sorted((x for x in objects if x["symbol"] == symbol and x["cadence"] == "daily"
                           and x["period"].startswith(month)), key=lambda x: x["key"])
            monthly = by_key.get(monthly_key)
            if not monthly and not days:
                continue
            chosen.append(dict(symbol=symbol, month=month, monthly=monthly, daily=days))
    if not chosen:
        raise OpportunityError("no selected archived periods")
    result = dict(version="AF-01C-PLAN/1", state="AF01C_ENGINEERING_PILOT_NO_SELECTION" if pilot else "REGISTERED_DEVELOPMENT",
                  inventory_sha256=snapshot["normalized_inventory_sha256"], population_start_ms=START,
                  population_end_exclusive_ms=END, interval="15m", periods=chosen)
    return result | {"plan_sha256": digest(result)}


def verify_plan(p: dict, snapshot: dict) -> None:
    verify(snapshot)
    base = {k: v for k, v in p.items() if k != "plan_sha256"}
    if (p.get("inventory_sha256") != snapshot["normalized_inventory_sha256"]
            or digest(base) != p.get("plan_sha256") or p.get("population_start_ms") != START
            or p.get("population_end_exclusive_ms") != END or p.get("interval") != "15m"):
        raise OpportunityError("plan/inventory binding invalid")
    known = {x["key"]: x for x in snapshot["objects"]}
    for entry in p["periods"]:
        if not re.fullmatch(r"20(?:20|21|22)-(?:0[1-9]|1[0-2])", entry["month"]):
            raise OpportunityError("outside Development range")
        for item in ([entry["monthly"]] if entry["monthly"] else []) + entry["daily"]:
            if known.get(item["key"]) != item or item["symbol"] != entry["symbol"] or not item["period"].startswith(entry["month"]):
                raise OpportunityError("unregistered plan object")


def _archive(item: dict) -> ArchiveObject:
    if parse_key(item["key"]) != item:
        raise OpportunityError("invalid archive identity")
    filename = item["key"].rsplit("/", 1)[-1]
    url = f"https://{HOST}/{item['key']}"
    return ArchiveObject(item["cadence"], item["symbol"], "15m", item["period"], url,
                         url + ".CHECKSUM", filename[:-4] + ".csv", "MILLISECOND")


def _extract(payload: bytes, member_name: str) -> tuple[bytes | None, str | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
            members = bundle.infolist()
            if len(members) != 1 or members[0].filename != member_name or members[0].is_dir():
                return None, "INVALID_MEMBER"
            if members[0].file_size > 512 * 1024 * 1024:
                return None, "INVALID_ZIP"
            with bundle.open(members[0]) as stream:
                data = stream.read(512 * 1024 * 1024 + 1)
            if len(data) != members[0].file_size:
                return None, "INVALID_ZIP"
            return data, None
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return None, "INVALID_ZIP"


def _read_object(root: Path, item: dict, fetcher, *, retrieved_ms: int) -> tuple[dict, tuple]:
    archive = _archive(item)
    refs = dict(source_url=archive.url, checksum_ref=archive.checksum_url)
    try:
        checksum = fetcher.fetch(archive.checksum_url, max_bytes=4096)
    except AcquisitionError:
        return dict(state="MISSING_CHECKSUM", **refs), ()
    try:
        expected = parse_checksum(checksum, archive.url.rsplit("/", 1)[-1])
    except AcquisitionError:
        return dict(state="MISSING_CHECKSUM", **refs), ()
    refs["expected_checksum"] = expected
    try:
        raw = fetcher.fetch(archive.url, max_bytes=256 * 1024 * 1024)
    except AcquisitionError:
        return dict(state="MISSING_ARCHIVE", **refs), ()
    observed = sha256(raw)
    refs["downloaded_sha256"] = observed
    if observed != expected:
        return dict(state="CHECKSUM_MISMATCH", **refs), ()
    extracted, error = _extract(raw, archive.member_name)
    if error:
        return dict(state=error, **refs), ()
    refs["extracted_csv_sha256"] = sha256(extracted)
    beginning, ending = object_bounds(item)
    if archive.cadence == "monthly" and any(
        beginning <= _date_ms(day) < ending for day in _monthly_daily_override_days(item["symbol"], "15m")
    ):
        return dict(state="TIMESTAMP_ANOMALY", anomaly="registered CRL monthly/daily divergence", **refs), ()
    dataset_plan = DatasetPlan("AF-01C", "DEVELOPMENT", False, item["symbol"], "15m",
                               beginning, ending, beginning, ending, (archive,))
    try:
        rows, anomalies = _normalize_archive_csv_with_evidence(extracted, archive, dataset_plan)
        if anomalies:
            raise OpportunityError("close-boundary source anomaly requires independent verification")
        if not rows:
            raise OpportunityError("empty archive")
        validate_rows(rows, "15m", as_of_ms=retrieved_ms)
    except (AcquisitionError, OpportunityError) as exc:
        kind = "TIMESTAMP_ANOMALY" if any(t in str(exc).lower() for t in ("timestamp", "boundary", "grid", "candle open")) else "INVALID_SCHEMA"
        return dict(state=kind, anomaly=str(exc), **refs), ()
    refs["canonical_sha256"] = sha256(_canonical_csv(rows))
    refs["row_count"] = len(rows)
    refs["gap_count"] = gap_map(rows, item["symbol"], "15m", "AF-01C/object").gap_count
    if refs["gap_count"]:
        return dict(state="SOURCE_GAP", **refs), ()
    refs["artifact_refs"] = {
        "checksum": f"objects/checksum-{sha256(checksum)}.txt",
        "zip": f"objects/zip-{observed}.zip",
        "extracted": f"objects/csv-{sha256(extracted)}.csv",
        "canonical": f"objects/canonical-{refs['canonical_sha256']}.csv"}
    for label, data in (("checksum", checksum), ("zip", raw), ("extracted", extracted), ("canonical", _canonical_csv(rows))):
        save_artifact(root, refs["artifact_refs"][label], data)
    return dict(state="MONTHLY_SUCCESS" if item["cadence"] == "monthly" else "DAILY_FALLBACK_SUCCESS", **refs), rows


def classify(symbol: str, confirmed_ordinary: tuple[str, ...] = ()) -> str:
    # A lexical leveraged-token signal blocks; ordinary requires independent evidence.
    if symbol in KNOWN_LEVERAGED:
        return "NONORDINARY_CONFIRMED"
    return "ORDINARY_SPOT_CONFIRMED" if symbol in confirmed_ordinary else "PRODUCT_CLASSIFICATION_UNRESOLVED"


def _ordinary_evidence(root: Path, symbol: str, relative: str | None) -> str | None:
    if relative is None:
        return None
    from .models import development_path
    path = development_path(root, relative)
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise OpportunityError("missing independent product classification evidence") from exc
    if (canonical(document) != raw or not relative.endswith(f"{sha256(raw)}.json")
            or document.get("symbol") != symbol or document.get("classification") != "ORDINARY_SPOT_CONFIRMED"
            or document.get("reviewed") is not True or document.get("source_type") != "INDEPENDENT_HISTORICAL_PRODUCT_RECORD"
            or not document.get("source_reference") or "exchangeinfo" in document["source_reference"].lower()):
        raise OpportunityError("independent product classification evidence invalid")
    return sha256(raw)


def acquire_period(root: Path, entry: dict, fetcher=None, *, retrieved_ms: int, allow_daily_fallback: bool = False) -> dict:
    try:
        guard_root(root)
    except ValueError as exc:
        raise OpportunityError("unsafe runtime root") from exc
    symbol, month = entry.get("symbol"), entry.get("month")
    if (not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]+USDT", symbol)
            or not isinstance(month, str) or not re.fullmatch(r"20(?:20|21|22)-(?:0[1-9]|1[0-2])", month)
            or not entry.get("monthly") and not entry.get("daily")):
        raise OpportunityError("unregistered Development object")
    for item in ([entry["monthly"]] if entry.get("monthly") else []) + entry.get("daily", []):
        if parse_key(item.get("key", "")) != item or item["symbol"] != symbol or not item["period"].startswith(month):
            raise OpportunityError("invalid archive period identity")
    root.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or HttpsFetcher((HOST,))
    identity = f"{entry['symbol']}-{entry['month']}"
    final_path = root / "ledger" / (identity + ".json")
    if final_path.exists():
        record = json.loads(final_path.read_bytes())
        raw = {k: v for k, v in record.items() if k != "record_sha256"}
        if digest(raw) != record.get("record_sha256") or record.get("identity") != identity:
            raise OpportunityError("immutable ledger collision")
        for relative, expected in record.get("artifact_hashes", {}).items():
            path = development_path(root, relative)
            if not path.is_file() or sha256(path.read_bytes()) != expected:
                raise OpportunityError("completed artifact collision")
        return record
    monthly = entry["monthly"]
    outcome, rows = _read_object(root, monthly, fetcher, retrieved_ms=retrieved_ms) if monthly else (dict(state="MISSING_ARCHIVE"), ())
    attempts = [dict(object_key=monthly["key"] if monthly else None, **outcome)]
    if outcome["state"] != "MONTHLY_SUCCESS" and allow_daily_fallback:
        daily_rows, daily_success = [], True
        first = date.fromisoformat(entry["month"] + "-01")
        last = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        dates = {(x["period"]): x for x in entry["daily"]}
        current = first
        while current < last:
            item = dates.get(current.isoformat())
            if item:
                result, part = _read_object(root, item, fetcher, retrieved_ms=retrieved_ms)
            else:
                result, part = dict(state="MISSING_ARCHIVE"), ()
            attempts.append(dict(object_key=item["key"] if item else None, period=current.isoformat(), **result))
            if result["state"] != "DAILY_FALLBACK_SUCCESS":
                daily_success = False
            daily_rows.extend(part)
            current += timedelta(days=1)
        if daily_success:
            rows = tuple(daily_rows)
            if gap_map(rows, entry["symbol"], "15m", "AF-01C/object").gap_count:
                outcome = dict(state="SOURCE_GAP", anomaly="daily fallback has missing bars")
                rows = ()
            else:
                outcome = dict(state="DAILY_FALLBACK_SUCCESS")
        else:
            outcome = dict(state="SOURCE_GAP")
    if rows:
        ordered = sorted(rows, key=lambda r: r.open_time_ms)
        if len({r.open_time_ms for r in ordered}) != len(ordered):
            outcome = dict(state="UNRECOVERABLE", anomaly="conflicting/duplicate bars")
            rows = ()
        else:
            rows = tuple(ordered)
            content = _canonical_csv(rows)
            relative = f"objects/canonical-{sha256(content)}.csv"
            save_artifact(root, relative, content)
    else:
        relative = None
    beginning, ending = object_bounds(dict(cadence="monthly", period=entry["month"]))
    gap_count = gap_map(rows, entry["symbol"], "15m", "AF-01C/object").gap_count if rows else 0
    # A monthly archive may legitimately start late/end early for a new/delisted pair;
    # preserve its observed coverage and gaps rather than inventing empty candles.
    hashes = {}
    for attempt in attempts:
        for label, ref in attempt.get("artifact_refs", {}).items():
            expected = {"checksum": sha256(development_path(root, ref).read_bytes()),
                        "zip": attempt.get("downloaded_sha256"),
                        "extracted": attempt.get("extracted_csv_sha256"),
                        "canonical": attempt.get("canonical_sha256")}[label]
            if sha256(development_path(root, ref).read_bytes()) != expected:
                raise OpportunityError("artifact hash mismatch during finalization")
            hashes[ref] = expected
    if relative:
        hashes[relative] = sha256(_canonical_csv(rows))
    base = dict(identity=identity, inventory_object_key=monthly["key"] if monthly else None,
                symbol=entry["symbol"], period=entry["month"], interval="15m",
                requested_start_ms=beginning, requested_end_ms=ending,
                state=outcome["state"], fallback_state="EXPLICIT" if allow_daily_fallback and len(attempts) > 1 else "NOT_REQUESTED",
                admission_state="PENDING_SYMBOL_RECONCILIATION" if rows else "BLOCKED",
                attempts=attempts, row_count=len(rows), gap_count=gap_count,
                canonical_sha256=sha256(_canonical_csv(rows)) if rows else None,
                canonical_ref=relative, artifact_hashes=hashes,
                classification=classify(entry["symbol"]))
    record = base | {"record_sha256": digest(base)}
    save_artifact(root, f"ledger/{identity}.json", canonical(record))
    return record


def reconcile(root: Path, p: dict) -> dict:
    records = []
    for entry in p["periods"]:
        path = root / "ledger" / f"{entry['symbol']}-{entry['month']}.json"
        if not path.is_file():
            raise OpportunityError("unfinished planned object")
        record = json.loads(path.read_bytes())
        if digest({k: v for k, v in record.items() if k != "record_sha256"}) != record.get("record_sha256"):
            raise OpportunityError("ledger record digest mismatch")
        if record["state"] not in STATES or record["identity"] != f"{entry['symbol']}-{entry['month']}":
            raise OpportunityError("invalid final object state")
        for relative, expected in record.get("artifact_hashes", {}).items():
            path = development_path(root, relative)
            if not path.is_file() or sha256(path.read_bytes()) != expected:
                raise OpportunityError("immutable object artifact collision")
        if record.get("canonical_ref"):
            ref = development_path(root, record["canonical_ref"])
            if not ref.is_file() or sha256(ref.read_bytes()) != record["canonical_sha256"]:
                raise OpportunityError("canonical object collision")
        records.append(record)
    result = dict(state="AF01C_ENGINEERING_PILOT_NO_SELECTION", plan_sha256=p["plan_sha256"],
                  records=tuple(x["record_sha256"] for x in records),
                  final_count=len(records), source_gap_count=sum(x["state"] not in ("MONTHLY_SUCCESS", "DAILY_FALLBACK_SUCCESS") for x in records))
    return result | {"reconciliation_sha256": digest(result)}


def build_lifecycle(root: Path, p: dict, symbol: str, *, retrieved_ms: int,
                    ordinary_evidence_ref: str | None = None) -> dict:
    reconcile(root, p)
    records = [json.loads((root / "ledger" / f"{e['symbol']}-{e['month']}.json").read_bytes())
               for e in p["periods"] if e["symbol"] == symbol]
    if not records or any(x["state"] not in ("MONTHLY_SUCCESS", "DAILY_FALLBACK_SUCCESS") for x in records):
        raise OpportunityError("symbol objects not fully admitted")
    rows = []
    for rec in records:
        raw = development_path(root, rec["canonical_ref"]).read_bytes().decode()
        reader = csv.reader(io.StringIO(raw))
        next(reader)
        from research.crisis_lab.acquisition import CanonicalRow
        rows.extend(CanonicalRow(tuple(x)) for x in reader)
    rows.sort(key=lambda x: x.open_time_ms)
    seen = {}
    for row in rows:
        if row.open_time_ms in seen and seen[row.open_time_ms] != row:
            raise OpportunityError("conflicting duplicate bars")
        seen[row.open_time_ms] = row
    rows = tuple(seen[t] for t in sorted(seen))
    if len(rows) != sum(x["row_count"] for x in records):
        raise OpportunityError("duplicate bars between objects")
    evidence_sha = _ordinary_evidence(root, symbol, ordinary_evidence_ref)
    classification = classify(symbol, (symbol,) if evidence_sha else ())
    refs = tuple(x["record_sha256"] for x in records)
    dataset, gaps, quality = admit(dataset_id=f"AF-01C/{symbol}-15m", symbol=symbol, interval="15m", rows=rows,
                                   source="BINANCE_PUBLIC_SPOT_ARCHIVE", requested_start_ms=START,
                                   requested_end_ms=END, retrieved_at_ms=retrieved_ms,
                                   source_refs=refs, allow_gaps=True)
    data_ref = f"symbols/{symbol}/canonical-{dataset.content_sha256}.csv"
    quality_ref = f"symbols/{symbol}/quality-{dataset.quality_sha256}.json"
    gap_ref = f"symbols/{symbol}/gaps-{gaps.gap_sha256}.json"
    save_artifact(root, data_ref, _canonical_csv(rows))
    save_artifact(root, quality_ref, canonical(quality))
    save_artifact(root, gap_ref, canonical(gaps.payload()))
    output = dict(classification=classification, production_eligible=False,
                  canonical_ref=data_ref, quality_ref=quality_ref, gap_ref=gap_ref,
                  quality_sha256=dataset.quality_sha256, gap_sha256=gaps.gap_sha256,
                  gap_count=gaps.gap_count, first_admitted_data_ms=rows[0].open_time_ms,
                  last_admitted_data_ms=rows[-1].open_time_ms,
                  listing_time_ms=None, delisting_time_ms=None,
                  provisional_lifecycle=dict(symbol=symbol, first_admitted_data_ms=rows[0].open_time_ms,
                                             last_admitted_data_ms=rows[-1].open_time_ms,
                                             listing_time_ms=None, delisting_time_ms=None,
                                             classification=classification, source_refs=refs))
    if classification == "ORDINARY_SPOT_CONFIRMED":
        lifecycle = Lifecycle(symbol, symbol[:-4], "USDT", "BINANCE_SPOT", "SPOT", True, False,
                              rows[0].open_time_ms, rows[-1].open_time_ms, None, None,
                              "UNKNOWN", refs + (evidence_sha,)).frozen()
        index = build_index((lifecycle,), ((dataset, gaps, quality),))
        output.update(product_classification_eligible=True, lifecycle=lifecycle.payload() | {"record_sha256": lifecycle.record_sha256},
                      index_sha256=index.index_sha256)
        save_artifact(root, f"symbols/{symbol}/index-{index.index_sha256}.json", canonical(index.payload()))
    save_artifact(root, f"symbols/{symbol}/lifecycle-{digest(output)}.json", canonical(output))
    return output
