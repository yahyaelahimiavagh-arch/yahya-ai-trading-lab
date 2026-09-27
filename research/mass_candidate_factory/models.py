"""Canonical records and narrow identity helpers."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

class MCFError(ValueError):
    """Fail-closed MCF contract violation."""

def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")

def digest(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()

def safe_path(root: Path, relative: str) -> Path:
    guard_root(root)
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise MCFError("invalid relative path")
    p = Path(relative)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts):
        raise MCFError("path traversal/absolute path")
    forbidden = ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve", "blind_oos", "blind-oos")
    if any(any(x in part.lower() for x in forbidden) for part in p.parts):
        raise MCFError("sealed evidence/P10 path")
    root = root.resolve(strict=True)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise MCFError("symlink path")
    target = current.resolve()
    if not target.is_relative_to(root):
        raise MCFError("path escape")
    return target

def guard_root(root: Path) -> Path:
    forbidden = ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve", "blind_oos", "blind-oos")
    if any(any(x in part.lower() for x in forbidden) for part in root.parts):
        raise MCFError("sealed evidence/P10 root")
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise MCFError("symlink root")
    resolved = root.resolve()
    if any(any(x in part.lower() for x in forbidden) for part in resolved.parts):
        raise MCFError("sealed resolved root")
    return resolved

def write_once(target: Path, payload: bytes) -> None:
    guard_root(target.parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != payload:
            raise MCFError("artifact collision")
        return
    fd, tmp = tempfile.mkstemp(prefix=".partial-", dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        try:
            os.link(tmp,target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes()!=payload:
                raise MCFError("concurrent artifact collision")
    finally:
        os.unlink(tmp)

@dataclass(frozen=True)
class EvidenceBinding:
    root: Path
    quality_manifest: str
    quality_sha256: str
    dataset_id: str
    partition: str = "DEVELOPMENT"

    def validate(self) -> Path:
        if self.partition != "DEVELOPMENT" or not self.dataset_id or len(self.quality_sha256) != 64:
            raise MCFError("evidence partition or identity invalid")
        p = safe_path(self.root, self.quality_manifest)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != self.quality_sha256:
            raise MCFError("unbound quality manifest")
        return p

@dataclass(frozen=True)
class CostPolicy:
    ref: str
    quantity: str
    initial_equity: str
    base_fee_bps: str
    base_slippage_bps: str
    stress_fee_bps: str
    stress_slippage_bps: str

    def validate(self) -> None:
        from decimal import Decimal
        if not self.ref or not self.ref.endswith("/v1"):
            raise MCFError("unversioned cost policy")
        vals = [Decimal(getattr(self, f)) for f in ("quantity", "initial_equity", "base_fee_bps", "base_slippage_bps", "stress_fee_bps", "stress_slippage_bps")]
        if not all(v.is_finite() for v in vals) or vals[0] <= 0 or vals[1] <= 0 or any(v < 0 for v in vals[2:]):
            raise MCFError("invalid cost policy")
