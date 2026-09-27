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
PREFIXES = ("data/spot/monthly/klines/", "data/spot/daily/klines/")
KEY = re.compile(r"^data/spot/(monthly|daily)/klines/([A-Z0-9]+USDT)/15m/\2-15m-(20\d\d-\d\d(?:-\d\d)?)\.zip$")
START, END = date(2020, 1, 1), date(2023, 1, 1)
MAX_PAGE_BYTES = 2_000_000


class InventoryUnproven(ValueError):
    def __init__(self, reason: str):
        super().__init__(f"HISTORICAL_SYMBOL_INVENTORY_UNPROVEN: {reason}")


def parse_key(key: str) -> dict | None:
    """Return a registered object, or None for unrelated archive objects."""
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


def _page(payload: bytes) -> tuple[list[str], bool, str | None]:
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
        truncated = value("IsTruncated")
        if truncated not in ("true", "false"):
            raise ValueError("missing truncation status")
        token = value("NextContinuationToken") or None
        if truncated == "true" and not token:
            raise ValueError("missing continuation token")
        if truncated == "false" and token:
            raise ValueError("unexpected continuation token")
        return keys, truncated == "true", token
    except (ET.ParseError, ValueError, IndexError, AttributeError) as exc:
        raise InventoryUnproven("invalid/non-auditable listing page") from exc


def discover(root: Path, *, fetched_at: str, fetcher=None, max_pages: int = 20000) -> dict:
    """List both prefixes to exhaustion; partial runs never freeze an inventory."""
    if max_pages < 1 or not fetched_at.endswith("Z"):
        raise InventoryUnproven("invalid retrieval bound/timestamp")
    fetcher = fetcher or HttpsFetcher((LIST_HOST,))
    try:
        guard_root(root)
    except ValueError as exc:
        raise InventoryUnproven("unsafe runtime root") from exc
    root.mkdir(parents=True, exist_ok=True)
    raw_pages, observed, pages, endpoints = [], set(), 0, []
    for prefix in PREFIXES:
        token, seen_tokens = None, set()
        while True:
            if pages >= max_pages:
                raise InventoryUnproven("listing pagination bound exceeded")
            query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
            if token:
                query["continuation-token"] = token
            url = f"{LIST_BASE}?{urlencode(query)}"
            try:
                payload = fetcher.fetch(url, max_bytes=MAX_PAGE_BYTES)
                keys, more, next_token = _page(payload)
            except InventoryUnproven:
                raise
            except Exception as exc:
                raise InventoryUnproven("listing transport unavailable") from exc
            if not keys and more:
                raise InventoryUnproven("empty truncated page")
            for key in keys:
                if not key.startswith(prefix) or key in observed:
                    raise InventoryUnproven("out-of-prefix/duplicate object key")
                observed.add(key)
                if key.endswith(".zip") and "/15m/" in key and "USDT/" in key and parse_key(key) is None:
                    raise InventoryUnproven("malformed registered object key")
            raw_pages.append(sha256(payload))
            save_artifact(root, f"inventory/raw/{sha256(payload)}.xml", payload)
            endpoints.append(url)
            pages += 1
            if not more:
                break
            if next_token in seen_tokens or next_token == token:
                raise InventoryUnproven("pagination cycle")
            seen_tokens.add(next_token)
            token = next_token
    objects = sorted((item for key in observed if (item := parse_key(key))), key=lambda x: x["key"])
    if not objects:
        raise InventoryUnproven("no registered historical objects")
    normalized = dict(schema="AF-01C-INVENTORY/1", objects=objects)
    snapshot = dict(schema="AF-01C-INVENTORY-SNAPSHOT/1", retrieved_at=fetched_at,
                    source_endpoint=f"{LIST_BASE}?list-type=2", listing_urls=endpoints,
                    raw_page_sha256=raw_pages, raw_inventory_sha256=sha256(canonical(raw_pages)),
                    normalized_inventory_sha256=digest(normalized), objects=objects,
                    state="COMPLETE")
    save_artifact(root, f"inventory/snapshot-{digest(snapshot)}.json", canonical(snapshot))
    return snapshot


def verify(snapshot: dict) -> None:
    objects = snapshot.get("objects")
    if (snapshot.get("state") != "COMPLETE" or not isinstance(objects, list) or not objects
            or objects != sorted(objects, key=lambda x: x["key"])
            or len({x["key"] for x in objects}) != len(objects)
            or any(parse_key(x["key"]) != x for x in objects)
            or snapshot.get("normalized_inventory_sha256") != digest(dict(schema="AF-01C-INVENTORY/1", objects=objects))):
        raise InventoryUnproven("snapshot identity/contents invalid")
