"""AF-01B research-only identities and fail-closed Development paths."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from research.crisis_lab.acquisition import CanonicalRow
from research.mass_candidate_factory.models import guard_root, safe_path

VERSION = "AF-01B/1.0.0"
CADENCE_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
SUPPORTED = frozenset({"PRICE_OHLC", "VOLUME", "TRADE_COUNT", "MULTI_ASSET"})
BLOCKED = frozenset({"MULTI_VENUE", "EXTERNAL_CONTEXT", "ORDER_BOOK", "ON_CHAIN", "NEWS_SENTIMENT", "MACRO_RELEASE"})


class OpportunityError(ValueError):
    """Fail-closed data or policy violation."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def development_path(root: Path, relative: str, partition: str = "DEVELOPMENT") -> Path:
    if partition != "DEVELOPMENT":
        raise OpportunityError("unregistered evidence partition")
    try:
        guard_root(root)
        return safe_path(root, relative)
    except (ValueError, OSError) as exc:
        raise OpportunityError("unsafe Development path") from exc


@dataclass(frozen=True)
class AdmittedDataset:
    dataset_id: str
    symbol: str
    interval: str
    venue: str
    source: str
    requested_start_ms: int
    requested_end_ms: int
    retrieved_at_ms: int
    source_refs: tuple[str, ...]
    rows: tuple[CanonicalRow, ...]
    content_sha256: str
    quality_sha256: str
    gap_sha256: str
    quality_verdict: str
    evidence_partition: str = "DEVELOPMENT"

    def validate_binding(self) -> None:
        if self.evidence_partition != "DEVELOPMENT" or self.venue != "BINANCE_SPOT":
            raise OpportunityError("evidence/venue boundary")
        if self.interval not in CADENCE_MS or not self.dataset_id or not self.source or not self.source_refs:
            raise OpportunityError("unbound dataset identity")
        if not (0 <= self.requested_start_ms < self.requested_end_ms <= self.retrieved_at_ms):
            raise OpportunityError("invalid provenance interval")
        if any(len(x) != 64 or any(c not in '0123456789abcdef' for c in x)
               for x in (self.content_sha256, self.quality_sha256, self.gap_sha256)):
            raise OpportunityError("invalid digest")
        if self.quality_verdict not in {"PASS_CONTIGUOUS", "PASS_WITH_GAPS"}:
            raise OpportunityError("unadmitted quality")
