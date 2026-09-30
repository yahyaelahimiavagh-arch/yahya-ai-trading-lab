"""Materialize reviewed historical product-classification evidence.

Pre-performance data governance only. The tool accepts either one canonical
acquisition ledger or a directory of canonical source shards, validates exact
wave accounting, then emits content-addressed evidence and a classification
map. Later waves may extend one immutable prior classification map without
replacing accepted evidence. It never reads strategy outcomes, Fresh OOS,
recent reserve, P10, or Live.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .classification_wave import EXPECTED_SAFETY, load_wave
from .models import MCFError, canonical, guard_root, safe_path, write_once

ACQUISITION_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_ACQUISITION/1.0.0"
SHARD_SCHEMA = "MCF_HISTORICAL_PRODUCT_CLASSIFICATION_SOURCE_SHARD/1.0.0"
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
_REQUIRED_SHARD_KEYS = {
    "entries",
    "schema",
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


def _validate_entries(entries: object) -> dict[str, dict]:
    if not isinstance(entries, dict):
        raise MCFError("classification entries must be an object")
    out: dict[str, dict] = {}
    for symbol, entry in entries.items():
        if not isinstance(symbol, str) or not symbol:
            raise MCFError("invalid classification symbol")
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
        out[symbol] = dict(entry)
    return out


def _validate_complete(doc: dict, wave: dict, wave_sha: str) -> None:
    entries = _validate_entries(doc.get("entries"))
    unresolved = doc.get("unresolved")
    if not isinstance(unresolved, dict):
        raise MCFError("classification unresolved must be an object")

    frontier = set(wave["frontier_symbols"])
    resolved = set(entries)
    blocked = set(unresolved)
    if resolved & blocked:
        raise MCFError("classification symbol both resolved and unresolved")
    if resolved | blocked != frontier:
        raise MCFError("classification acquisition does not account for exact wave frontier")
    for symbol, reason in unresolved.items():
        if not isinstance(reason, str) or not reason.strip():
            raise MCFError(f"missing unresolved reason: {symbol}")

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
    if set(doc) != _REQUIRED_LEDGER_KEYS or doc.get("schema") != ACQUISITION_SCHEMA:
        raise MCFError("invalid classification acquisition schema")
    _validate_complete(doc, wave, wave_sha)
    return doc, wave, _sha(raw), wave_sha


def load_acquisition_shards(shard_dir: Path, wave_path: Path) -> tuple[dict, dict, str, str]:
    wave, wave_sha = load_wave(wave_path)
    if not shard_dir.is_dir() or shard_dir.is_symlink():
        raise MCFError("missing classification source-shard directory")

    entries: dict[str, dict] = {}
    shard_ids: list[tuple[str, str]] = []
    paths = sorted(shard_dir.glob("source-shard-*.json"))
    if not paths:
        raise MCFError("classification source shards not found")

    for path in paths:
        if path.is_symlink():
            raise MCFError("symlink classification source shard")
        raw = path.read_bytes()
        try:
            shard = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise MCFError("invalid classification source shard JSON") from exc
        if (
            not isinstance(shard, dict)
            or canonical(shard) != raw
            or set(shard) != _REQUIRED_SHARD_KEYS
            or shard.get("schema") != SHARD_SCHEMA
            or shard.get("wave_id") != wave["wave_id"]
            or shard.get("wave_manifest_sha256") != wave_sha
        ):
            raise MCFError(f"invalid classification source shard: {path.name}")
        part = _validate_entries(shard.get("entries"))
        overlap = set(entries) & set(part)
        if overlap:
            raise MCFError(f"duplicate classification source symbol: {sorted(overlap)[0]}")
        entries.update(part)
        shard_ids.append((path.name, _sha(raw)))

    doc = {
        "entries": entries,
        "generation_id": "MCF-PROD-001",
        "safety": EXPECTED_SAFETY,
        "schema": ACQUISITION_SCHEMA,
        "source_preflight_sha256": wave["source_preflight_sha256"],
        "state": "REVIEWED_BEFORE_PERFORMANCE",
        "unresolved": {},
        "wave_id": wave["wave_id"],
        "wave_manifest_sha256": wave_sha,
    }
    _validate_complete(doc, wave, wave_sha)
    ledger_identity = _sha(canonical({
        "acquisition": doc,
        "source_shards": tuple(shard_ids),
    }))
    return doc, wave, ledger_identity, wave_sha


def _load_base_classification_map(
    output_root: Path, relative: str | None
) -> tuple[dict[str, str], str | None]:
    if relative is None:
        return {}, None
    path = safe_path(output_root, relative)
    if not path.is_file() or path.is_symlink():
        raise MCFError("missing base classification map")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise MCFError("invalid base classification map JSON") from exc
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if (
        not isinstance(doc, dict)
        or canonical(doc) != raw
        or set(doc) != {"entries", "generation_id", "schema", "state"}
        or doc.get("schema") != MAP_SCHEMA
        or doc.get("generation_id") != "MCF-PROD-001"
        or doc.get("state") != "FROZEN_BEFORE_PERFORMANCE"
        or not isinstance(entries, dict)
    ):
        raise MCFError("invalid base classification map")

    out: dict[str, str] = {}
    for symbol, evidence_relative in entries.items():
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(evidence_relative, str)
            or not evidence_relative
        ):
            raise MCFError("invalid base classification map entry")
        evidence_path = safe_path(output_root, evidence_relative)
        if not evidence_path.is_file() or evidence_path.is_symlink():
            raise MCFError(f"missing base classification evidence: {symbol}")
        evidence_raw = evidence_path.read_bytes()
        try:
            evidence = json.loads(evidence_raw)
        except (UnicodeError, ValueError) as exc:
            raise MCFError(
                f"invalid base classification evidence JSON: {symbol}"
            ) from exc
        identity = _sha(evidence_raw)
        if (
            not isinstance(evidence, dict)
            or canonical(evidence) != evidence_raw
            or evidence.get("schema") != EVIDENCE_SCHEMA
            or evidence.get("symbol") != symbol
            or evidence.get("classification") not in _ALLOWED_CLASSIFICATIONS
            or evidence.get("reviewed") is not True
            or evidence.get("source_type")
            != "INDEPENDENT_HISTORICAL_PRODUCT_RECORD"
            or not isinstance(evidence.get("source_reference"), str)
            or not evidence["source_reference"].strip()
            or "exchangeinfo" in evidence["source_reference"].lower()
            or not evidence_relative.endswith(f"{identity}.json")
        ):
            raise MCFError(f"invalid base classification evidence: {symbol}")
        out[symbol] = evidence_relative
    return out, _sha(raw)


def materialize(*, wave_path: Path, output_root: Path,
                acquisition_path: Path | None = None,
                source_shards_dir: Path | None = None,
                base_classification_map: str | None = None) -> dict:
    output_root = guard_root(output_root)
    if not output_root.is_dir():
        raise MCFError("classification output root must already exist")
    if (acquisition_path is None) == (source_shards_dir is None):
        raise MCFError("provide exactly one acquisition source")

    if source_shards_dir is not None:
        doc, wave, ledger_sha, wave_sha = load_acquisition_shards(source_shards_dir, wave_path)
    else:
        assert acquisition_path is not None
        doc, wave, ledger_sha, wave_sha = load_acquisition(acquisition_path, wave_path)

    base_entries, base_map_sha = _load_base_classification_map(
        output_root, base_classification_map
    )
    wave_map_entries: dict[str, str] = {}
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
        wave_map_entries[symbol] = relative

    overlap = set(base_entries) & set(wave_map_entries)
    if overlap:
        raise MCFError(
            "classification wave attempts to replace accepted evidence: "
            + sorted(overlap)[0]
        )
    map_entries = {**base_entries, **wave_map_entries}

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
    if base_map_sha is not None:
        result["base_classification_map_sha256"] = base_map_sha
        result["cumulative_resolved_count"] = len(map_entries)

    result_payload = canonical(result)
    result_sha = _sha(result_payload)
    result_relative = f"materialization/materialization-{result_sha}.json"
    write_once(safe_path(output_root, result_relative), result_payload)
    return {**result, "artifact": result_relative, "materialization_sha256": result_sha}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--acquisition-ledger", type=Path)
    group.add_argument("--source-shards-dir", type=Path)
    parser.add_argument("--wave-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--base-classification-map",
        help="immutable prior map path relative to --output-root",
    )
    args = parser.parse_args(argv)
    try:
        result = materialize(
            acquisition_path=args.acquisition_ledger,
            source_shards_dir=args.source_shards_dir,
            wave_path=args.wave_manifest,
            output_root=args.output_root,
            base_classification_map=args.base_classification_map,
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
