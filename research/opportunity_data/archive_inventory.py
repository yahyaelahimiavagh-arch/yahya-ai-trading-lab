"""AF-01C: auditable public archive object listing, independent of exchangeInfo."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from research.crisis_lab.acquisition import HttpsFetcher
from .models import canonical, digest, sha256
from .storage import save_artifact
from research.mass_candidate_factory.models import guard_root

HOST = "data.binance.vision"
LIST_HOST = "s3-ap-northeast-1.amazonaws.com"
LIST_BASE = f"https://{LIST_HOST}/data.binance.vision"
PREFIXES = (
    ("monthly", "data/spot/monthly/klines/"),
    ("daily", "data/spot/daily/klines/"),
)
SYMBOL = re.compile(r"^[A-Z0-9]+USDT$")
KEY = re.compile(
    r"^data/spot/(monthly|daily)/klines/([A-Z0-9]+USDT)/15m/\2-15m-"
    r"(20\d\d-\d\d(?:-\d\d)?)\.zip$"
)
START, END = date(2020, 1, 1), date(2023, 1, 1)
MAX_PAGE_BYTES = 2_000_000
INVENTORY_STRATEGY = "HIERARCHICAL_COMMON_PREFIXES_RANGE_BOUNDED/2"


class InventoryUnproven(ValueError):
    def __init__(self, reason: str):
        super().__init__(f"HISTORICAL_SYMBOL_INVENTORY_UNPROVEN: {reason}")


def parse_key(key: str) -> dict | None:
    """Return a registered Development object, or None for unrelated/out-of-window objects."""
    match = KEY.fullmatch(key)
    if not match:
        return None
    cadence, symbol, period = match.groups()
    try:
        first = date.fromisoformat(period + "-01" if cadence == "monthly" else period)
        if cadence == "monthly":
            last = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        else:
            from datetime import timedelta
            last = first + timedelta(days=1)
    except ValueError as exc:
        raise InventoryUnproven("malformed registered archive period") from exc
    if first >= END or last <= START:
        return None
    return dict(key=key, cadence=cadence, symbol=symbol, interval="15m", period=period)


def _listing_page(payload: bytes) -> tuple[list[str], list[str], bool, str | None]:
    if len(payload) > MAX_PAGE_BYTES or b"<!DOCTYPE" in payload.upper():
        raise InventoryUnproven("invalid/oversized listing response")
    try:
        root = ET.fromstring(payload)
        name = lambda element: element.tag.rsplit("}", 1)[-1]
        if name(root) != "ListBucketResult":
            raise ValueError("not an S3 listing")
        children = lambda e, n: [c for c in e if name(c) == n]
        value = lambda n: (children(root, n)[0].text or "") if children(root, n) else ""
        keys = [(children(e, "Key")[0].text or "") for e in children(root, "Contents")]
        prefixes = [(children(e, "Prefix")[0].text or "") for e in children(root, "CommonPrefixes")]
        truncated = value("IsTruncated")
        if truncated not in ("true", "false"):
            raise ValueError("missing truncation status")
        token = value("NextContinuationToken") or None
        if truncated == "true" and not token:
            raise ValueError("missing continuation token")
        if truncated == "false" and token:
            raise ValueError("unexpected continuation token")
        key_count = value("KeyCount")
        if key_count and int(key_count) != len(keys) + len(prefixes):
            raise ValueError("S3 KeyCount mismatch")
        return keys, prefixes, truncated == "true", token
    except (ET.ParseError, ValueError, IndexError, AttributeError) as exc:
        raise InventoryUnproven("invalid/non-auditable listing page") from exc


def _page(payload: bytes) -> tuple[list[str], bool, str | None]:
    """Compatibility parser for object-only listing tests/callers."""
    keys, _, more, token = _listing_page(payload)
    return keys, more, token


def discover(root: Path, *, fetched_at: str, fetcher=None, max_pages: int = 20000) -> dict:
    """Hierarchically enumerate symbol directories, then exact SYMBOL/15m object metadata."""
    if max_pages < 1 or not fetched_at.endswith("Z"):
        raise InventoryUnproven("invalid retrieval bound/timestamp")
    fetcher = fetcher or HttpsFetcher((LIST_HOST,))
    try:
        guard_root(root)
    except ValueError as exc:
        raise InventoryUnproven("unsafe runtime root") from exc
    root.mkdir(parents=True, exist_ok=True)

    raw_pages: list[str] = []
    endpoints: list[str] = []
    pages = 0

    def fetch_page(
        prefix: str,
        *,
        delimiter: str | None = None,
        token: str | None = None,
        start_after: str | None = None,
    ):
        nonlocal pages
        if pages >= max_pages:
            raise InventoryUnproven("listing pagination bound exceeded")
        query = {"list-type": "2", "prefix": prefix}
        if delimiter is not None:
            query["delimiter"] = delimiter
        query["max-keys"] = "1000"
        if token:
            query["continuation-token"] = token
        elif start_after:
            query["start-after"] = start_after
        url = f"{LIST_BASE}?{urlencode(query)}"
        try:
            payload = fetcher.fetch(url, max_bytes=MAX_PAGE_BYTES)
            result = _listing_page(payload)
        except InventoryUnproven:
            raise
        except Exception as exc:
            raise InventoryUnproven("listing transport unavailable") from exc
        raw_sha = sha256(payload)
        raw_pages.append(raw_sha)
        save_artifact(root, f"inventory/raw/{raw_sha}.xml", payload)
        endpoints.append(url)
        pages += 1
        return result

    cadence_symbols: dict[str, list[str]] = {}
    for cadence, root_prefix in PREFIXES:
        token = None
        seen_tokens: set[str] = set()
        seen_prefixes: set[str] = set()
        symbols: set[str] = set()
        while True:
            keys, prefixes, more, next_token = fetch_page(root_prefix, delimiter="/", token=token)
            if not keys and not prefixes and more:
                raise InventoryUnproven("empty truncated symbol page")
            for common_prefix in prefixes:
                if not common_prefix.startswith(root_prefix) or not common_prefix.endswith("/"):
                    raise InventoryUnproven("out-of-prefix symbol directory")
                symbol = common_prefix[len(root_prefix):-1]
                if not symbol or "/" in symbol or common_prefix in seen_prefixes:
                    raise InventoryUnproven("malformed/duplicate symbol directory")
                seen_prefixes.add(common_prefix)
                if symbol.endswith("USDT") and not SYMBOL.fullmatch(symbol):
                    raise InventoryUnproven("malformed USDT symbol directory")
                if SYMBOL.fullmatch(symbol):
                    symbols.add(symbol)
            if not more:
                break
            if next_token in seen_tokens or next_token == token:
                raise InventoryUnproven("pagination cycle")
            seen_tokens.add(next_token)
            token = next_token
        cadence_symbols[cadence] = sorted(symbols)

    observed: set[str] = set()
    range_bounds: dict[str, dict[str, str]] = {}
    for cadence, root_prefix in PREFIXES:
        for symbol in cadence_symbols[cadence]:
            object_prefix = f"{root_prefix}{symbol}/15m/"
            start_after = f"{object_prefix}{symbol}-15m-2019-99"
            range_bounds[f"{cadence}:{symbol}"] = {
                "start_after": start_after,
                "end_exclusive": f"{object_prefix}{symbol}-15m-2023-01",
            }
            token = None
            seen_tokens: set[str] = set()
            seen_listing_keys: set[str] = set()
            reached_end = False
            while True:
                keys, prefixes, more, next_token = fetch_page(
                    object_prefix,
                    token=token,
                    start_after=start_after if token is None else None,
                )
                if prefixes:
                    raise InventoryUnproven("unexpected nested prefix in exact 15m listing")
                if not keys and more:
                    raise InventoryUnproven("empty truncated object page")
                for key in keys:
                    if not key.startswith(object_prefix) or key in seen_listing_keys:
                        raise InventoryUnproven("out-of-prefix/duplicate object key")
                    seen_listing_keys.add(key)
                    if not key.endswith(".zip"):
                        continue
                    match = KEY.fullmatch(key)
                    if match is None:
                        raise InventoryUnproven("malformed registered object key")
                    item = parse_key(key)  # validates period
                    if item is None:
                        _, _, period = match.groups()
                        first = date.fromisoformat(period + "-01" if cadence == "monthly" else period)
                        if first >= END:
                            reached_end = True
                            break
                        continue
                    if key in observed:
                        raise InventoryUnproven("duplicate archive object key")
                    observed.add(key)
                if reached_end or not more:
                    break
                if next_token in seen_tokens or next_token == token:
                    raise InventoryUnproven("pagination cycle")
                seen_tokens.add(next_token)
                token = next_token

    objects = sorted((item for key in observed if (item := parse_key(key))), key=lambda x: x["key"])
    if not objects:
        raise InventoryUnproven("no registered historical objects")
    normalized = dict(schema="AF-01C-INVENTORY/1", objects=objects)
    snapshot = dict(
        schema="AF-01C-INVENTORY-SNAPSHOT/1",
        inventory_strategy=INVENTORY_STRATEGY,
        retrieved_at=fetched_at,
        source_endpoint=f"{LIST_BASE}?list-type=2",
        discovered_symbols=cadence_symbols,
        object_range_bounds=range_bounds,
        listing_urls=endpoints,
        raw_page_sha256=raw_pages,
        raw_inventory_sha256=sha256(canonical(raw_pages)),
        normalized_inventory_sha256=digest(normalized),
        objects=objects,
        state="COMPLETE",
    )
    save_artifact(root, f"inventory/snapshot-{digest(snapshot)}.json", canonical(snapshot))
    return snapshot


def verify(snapshot: dict) -> None:
    objects = snapshot.get("objects")
    symbols = snapshot.get("discovered_symbols")
    if (
        snapshot.get("state") != "COMPLETE"
        or snapshot.get("inventory_strategy") != INVENTORY_STRATEGY
        or not isinstance(snapshot.get("object_range_bounds"), dict)
        or not isinstance(symbols, dict)
        or sorted(symbols) != ["daily", "monthly"]
        or any(
            not isinstance(symbols.get(cadence), list)
            or symbols[cadence] != sorted(set(symbols[cadence]))
            or any(not SYMBOL.fullmatch(symbol) for symbol in symbols[cadence])
            for cadence in ("monthly", "daily")
        )
        or not isinstance(objects, list)
        or not objects
        or objects != sorted(objects, key=lambda x: x["key"])
        or len({x["key"] for x in objects}) != len(objects)
        or any(parse_key(x["key"]) != x for x in objects)
        or snapshot.get("normalized_inventory_sha256")
        != digest(dict(schema="AF-01C-INVENTORY/1", objects=objects))
    ):
        raise InventoryUnproven("snapshot identity/contents invalid")
