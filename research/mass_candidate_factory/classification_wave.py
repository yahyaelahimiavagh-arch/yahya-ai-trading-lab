"""Validate frozen historical product-classification acquisition waves.

Pre-performance governance only: no source acquisition, product classification,
strategy outcome, Fresh OOS, recent reserve, P10, or Live access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .models import MCFError, canonical

WAVE_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_WAVE/1.0.0"
EXPECTED_SAFETY = {
    "fresh_oos_read": False,
    "live": False,
    "p10_read": False,
    "p10_write": False,
    "p11_locked": True,
    "performance_read": False,
    "recent_reserve_read": False,
}
_REQUIRED_KEYS = {
    "frontier_symbol_count",
    "frontier_symbols",
    "generation_id",
    "safety",
    "schema",
    "source_preflight_sha256",
    "state",
    "wave_id",
}


def validate_wave(doc: object) -> dict:
    if not isinstance(doc, dict) or set(doc) != _REQUIRED_KEYS:
        raise MCFError("invalid classification-wave schema keys")
    if doc.get("schema") != WAVE_SCHEMA:
        raise MCFError("invalid classification-wave schema")
    if doc.get("generation_id") != "MCF-PROD-001":
        raise MCFError("classification wave generation mismatch")
    if doc.get("state") != "FROZEN_BEFORE_SOURCE_ACQUISITION":
        raise MCFError("classification wave not frozen before acquisition")
    wave_id = doc.get("wave_id")
    if not isinstance(wave_id, str) or not wave_id.startswith("MCF-PROD-001-CLASSIFICATION-WAVE-"):
        raise MCFError("invalid classification wave id")
    source_sha = doc.get("source_preflight_sha256")
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 64
        or any(ch not in "0123456789abcdef" for ch in source_sha)
    ):
        raise MCFError("invalid source preflight identity")
    symbols = doc.get("frontier_symbols")
    count = doc.get("frontier_symbol_count")
    if (
        not isinstance(symbols, list)
        or not isinstance(count, int)
        or count <= 0
        or len(symbols) != count
        or len(set(symbols)) != count
        or symbols != sorted(symbols)
    ):
        raise MCFError("classification-wave frontier is not unique and sorted")
    if any(
        not isinstance(symbol, str)
        or not symbol
        or symbol != symbol.upper()
        or not symbol.endswith("USDT")
        for symbol in symbols
    ):
        raise MCFError("invalid frontier symbol")
    if doc.get("safety") != EXPECTED_SAFETY:
        raise MCFError("classification-wave safety boundary mismatch")
    return doc


def load_wave(path: Path) -> tuple[dict, str]:
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing classification-wave manifest")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid classification-wave JSON") from exc
    if canonical(doc) != raw:
        raise MCFError("noncanonical classification-wave manifest")
    return validate_wave(doc), hashlib.sha256(raw).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave-manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        doc, identity = load_wave(args.wave_manifest)
        print(json.dumps({
            "frontier_symbol_count": doc["frontier_symbol_count"],
            "source_preflight_sha256": doc["source_preflight_sha256"],
            "status": "VALID",
            "wave_id": doc["wave_id"],
            "wave_manifest_sha256": identity,
        }, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError) as exc:
        print(json.dumps({
            "reason": str(exc),
            "status": "CLASSIFICATION_WAVE_INVALID",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
