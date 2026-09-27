"""Deterministic ordinal shards and collision-proof final artifacts."""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
from .models import MCFError, canonical, digest, safe_path, guard_root

SCHEMA = "MCF_SHARD/1"

def layout(batch_id: str, count: int, size: int):
    if count < 0 or size <= 0 or not batch_id:
        raise MCFError("invalid shard layout")
    return [{"shard_id": digest({"batch_id": batch_id, "start": start, "end": min(start+size,count), "schema": SCHEMA})[:24], "start": start, "end": min(start+size,count)} for start in range(0,count,size)]

def finalize(root: Path, shard: dict, rows: list[dict]) -> tuple[Path, str]:
    guard_root(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise MCFError("symlink shard root")
    if len(rows) != shard["end"]-shard["start"] or [r["ordinal"] for r in rows] != list(range(shard["start"],shard["end"])):
        raise MCFError("incomplete/noncanonical shard")
    payload = b"".join(canonical(r) for r in rows)
    sha = hashlib.sha256(payload).hexdigest()
    name = f"{shard['shard_id']}-{sha}.jsonl"
    target = safe_path(root, name)
    other = list(root.glob(f"{shard['shard_id']}-*.jsonl"))
    if other and (len(other) != 1 or other[0] != target or other[0].read_bytes() != payload):
        raise MCFError("final shard identity collision")
    if target.exists():
        return target, sha
    fd, tmp = tempfile.mkstemp(prefix=".partial-", dir=root)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        if target.exists():
            if target.read_bytes() != payload:
                raise MCFError("concurrent shard collision")
        else:
            os.link(tmp, target)  # exclusive create; never overwrite final evidence
    finally:
        os.unlink(tmp)
    return target, sha
