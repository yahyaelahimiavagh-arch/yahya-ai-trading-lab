"""Materialize reviewed historical product-classification evidence.

This is a pre-performance data-governance tool. It consumes a frozen wave
manifest plus a reviewed source ledger, writes content-addressed per-symbol
classification evidence and a partial/full classification map, and preserves
unresolved symbols explicitly.

It never reads strategy outcomes, Fresh OOS, recent reserve, P10, or Live data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .classification_wave import EXPECTED_SAFETY, load_wave
from .models import MCFError, canonical, guard_root, safe_path, write_once

ACQUISITION_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_ACQUISITION/1.0.0"
EVIDENCE_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION/1.0.0"
MAP_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_MAP/1.0.0"

_REQUIRED_LEDGER_KEYS = {
    "entries",
    "generation_id",
    "safety",
    "schema",
    "source_preflight_sha256",
    "state",
    "unresolved",
    "wave_id",
    "wave_manifest_sha256",
}
_REQUIRED_ENTRY_KEYS = {
    "classification",
    "evidence_basis",
    "reviewed",
    "source_published_at",
    "source_reference",
    "source_title",
}
_ALLOWED_CLASSIFICATIONS = {
    "ORDINARY_SPOT_CONFIRMED",
    "NONORDINARY_CONFIRMED",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_acquisition(path: Path, wave_path: Path) -> tuple[dict, dict, str, str]:
    wave, wave_sha = load_wave(wave_path)
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing classification acquisition ledger")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid classification acquisition JSON") from exc
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise MCFError("noncanonical classification acquisition ledger")
    if set(doc) != _REQUIRED_LEDGER_KEYS:
        raise MCFError("invalid classification acquisition schema keys")
    if doc.get("schema") != ACQUISITION_SCHEMA:
        raise MCFError("invalid classification acquisition schema")
    if doc.get("generation_id") != "MCF-PROD-001":
        raise MCFError("classification acquisition generation mismatch")
    if doc.get("state") != "REVIEWED_BEFORE_PERFORMANCE":
        raise MCFError("classification acquisition not reviewed before performance")
    if doc.get("wave_id") != wave["wave_id"]:
        raise MCFError("classification acquisition wave mismatch")
    if doc.get("wave_manifest_sha256") != wave_sha:
        raise MCFError("classification acquisition wave identity mismatch")
    if doc.get("source_preflight_sha256") != wave["source_preflight_sha256"]:
        raise MCFError("classification acquisition source preflight mismatch")
    if doc.get("safety") != EXPECTED_SAFETY:
        raise MCFError("classification acquisition safety boundary mismatch")

    entries = doc.get("entries")
    unresolved = doc.get("unresolved")
    if not isinstance(entries, dict) or not isinstance(unresolved, dict):
        raise MCFError("classification acquisition entries/unresolved must be objects")

    frontier = set(wave["frontier_symbols"])
    resolved = set(entries)
    blocked = set(unresolved)
    if resolved & blocked:
        raise MCFError("classification symbol both resolved and unresolved")
    if resolved | blocked != frontier:
        raise MCFError("classification acquisition does not account for exact wave frontier")

    for symbol, entry in entries.items():
        if not isinstance(entry, dict) or set(entry) != _REQUIRED_ENTRY_KEYS:
            raise MCFError(f"invalid classification acquisition entry: {symbol}")
        if entry.get("classification") not in _ALLOWED_CLASSIFICATIONS:
            raise MCFError(f"invalid product classification: {symbol}")
        if entry.get("reviewed") is not True:
            raise MCFError(f"unreviewed product classification: {symbol}")
        for key in ("evidence_basis", "source_published_at", "source_reference", "source_title"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise MCFError(f"missing {key}: {symbol}")
        if "exchangeinfo" in entry["source_reference"].lower():
            raise MCFError(f"current exchangeInfo prohibited: {symbol}")

    for symbol, reason in unresolved.items():
        if not isinstance(reason, str) or not reason.strip():
            raise MCFError(f"missing unresolved reason: {symbol}")

    return doc, wave, _sha(raw), wave_sha


def materialize(*, acquisition_path: Path, wave_path: Path, output_root: Path) -> dict:
    output_root = guard_root(output_root)
    if not output_root.is_dir():
        raise MCFError("classification output root must already exist")

    doc, wave, ledger_sha, wave_sha = load_acquisition(acquisition_path, wave_path)
    map_entries: dict[str, str] = {}

    for symbol in sorted(doc["entries"]):
        source = doc["entries"][symbol]
        evidence = {
            "acquisition_ledger_sha256": ledger_sha,
            "classification": source["classification"],
            "evidence_basis": source["evidence_basis"],
            "reviewed": True,
            "schema": EVIDENCE_SCHEMA,
            "source_published_at": source["source_published_at"],
            "source_reference": source["source_reference"],
            "source_title": source["source_title"],
            "source_type": "INDEPENDENT_HISTORICAL_PRODUCT_RECORD",
            "symbol": symbol,
            "wave_id": wave["wave_id"],
            "wave_manifest_sha256": wave_sha,
        }
        payload = canonical(evidence)
        identity = _sha(payload)
        relative = f"evidence/{symbol}-{identity}.json"
        write_once(safe_path(output_root, relative), payload)
        map_entries[symbol] = relative

    cmap = {
        "entries": map_entries,
        "generation_id": "MCF-PROD-001",
        "schema": MAP_SCHEMA,
        "state": "FROZEN_BEFORE_PERFORMANCE",
    }
    map_payload = canonical(cmap)
    map_sha = _sha(map_payload)
    map_relative = f"classification-map-{map_sha}.json"
    write_once(safe_path(output_root, map_relative), map_payload)

    result = {
        "acquisition_ledger_sha256": ledger_sha,
        "classification_map": map_relative,
        "classification_map_sha256": map_sha,
        "generation_id": "MCF-PROD-001",
        "resolved_count": len(doc["entries"]),
        "safety": EXPECTED_SAFETY,
        "schema": "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_MATERIALIZATION/1.0.0",
        "status": "CLASSIFICATION_WAVE_MATERIALIZED",
        "unresolved_count": len(doc["unresolved"]),
        "wave_id": wave["wave_id"],
        "wave_manifest_sha256": wave_sha,
    }
    result_payload = canonical(result)
    result_sha = _sha(result_payload)
    result_relative = f"materialization/materialization-{result_sha}.json"
    write_once(safe_path(output_root, result_relative), result_payload)
    return {**result, "artifact": result_relative, "materialization_sha256": result_sha}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-ledger", required=True, type=Path)
    parser.add_argument("--wave-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = materialize(
            acquisition_path=args.acquisition_ledger,
            wave_path=args.wave_manifest,
            output_root=args.output_root,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError) as exc:
        print(json.dumps({
            "reason": str(exc),
            "status": "CLASSIFICATION_ACQUISITION_BLOCKED",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
