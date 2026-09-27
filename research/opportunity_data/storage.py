"""Bounded immutable Development artifacts; no sealed evidence API."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from research.crisis_lab.acquisition import CANONICAL_COLUMNS, CanonicalRow, _canonical_csv
from research.mass_candidate_factory.models import write_once

from .models import OpportunityError, development_path, sha256, canonical


def read_canonical(root: Path, relative: str, expected_sha256: str,
                   *, partition: str = "DEVELOPMENT") -> tuple[CanonicalRow, ...]:
    path = development_path(root, relative, partition)
    if len(expected_sha256) != 64 or not path.is_file():
        raise OpportunityError("unbound canonical file")
    raw = path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise OpportunityError("canonical file digest mismatch")
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8")))
        if tuple(next(reader)) != CANONICAL_COLUMNS:
            raise OpportunityError("canonical header mismatch")
        rows = tuple(CanonicalRow(tuple(row)) for row in reader)
    except (UnicodeError, StopIteration, csv.Error) as exc:
        raise OpportunityError("invalid canonical CSV") from exc
    if _canonical_csv(rows) != raw:
        raise OpportunityError("noncanonical CSV bytes")
    return rows


def read_quality(root: Path, relative: str, expected_sha256: str,
                 *, partition: str = "DEVELOPMENT") -> dict:
    path = development_path(root, relative, partition)
    if len(expected_sha256) != 64 or not path.is_file():
        raise OpportunityError("unbound quality file")
    raw = path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise OpportunityError("quality file digest mismatch")
    try:
        document = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise OpportunityError("invalid quality JSON") from exc
    if (not isinstance(document, dict) or canonical(document) != raw
            or document.get("evidence_partition") != "DEVELOPMENT"
            or document.get("version") != "AF-01B/1.0.0"
            or document.get("quality_verdict") not in {"PASS_CONTIGUOUS", "PASS_WITH_GAPS"}
            or not document.get("dataset_id") or not document.get("content_sha256")):
        raise OpportunityError("invalid quality binding")
    return document


def save_artifact(root: Path, relative: str, payload: bytes) -> str:
    target = development_path(root, relative)
    try:
        write_once(target, payload)
    except (ValueError, OSError) as exc:
        raise OpportunityError("immutable artifact collision") from exc
    return sha256(payload)
