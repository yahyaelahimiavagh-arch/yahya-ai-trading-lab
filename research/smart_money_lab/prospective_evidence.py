"""Prospective, append-only V3 evidence journal (no network requests or orders).

Capture only already-observed parsed swaps and already-fetched indicative quotes.
Never synthesize backdated market quotes. The hash chain detects accidental
local edits but is not independent attestation of API truth or execution price.
Raw journal data contain wallet identifiers: keep on a private VPS path only.
"""
from __future__ import annotations

from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from .wallet_intelligence import quote_coverage

KIND = "YATL_V3_EVIDENCE_JOURNAL_V1"
GENESIS = "0" * 64
MAX_BYTES = 32_000_000


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash(data: dict) -> str:
    return hashlib.sha256(_json(data).encode("utf-8")).hexdigest()


def _positive_int(value):
    return type(value) is int and value > 0


def _valid_payload(kind: str, p: dict) -> bool:
    if not isinstance(p, dict):
        return False
    if kind == "signal":
        return (set(p) == {"source", "wallet", "mint", "signature", "side",
                           "chain_time", "observed_at"}
                and p["source"] == "live_observed"
                and p["side"] in ("BUY", "SELL")
                and all(isinstance(p[k], str) and p[k] for k in
                        ("wallet", "mint", "signature"))
                and _positive_int(p["chain_time"])
                and _positive_int(p["observed_at"])
                and p["chain_time"] <= p["observed_at"])
    if kind == "quote":
        from decimal import Decimal, InvalidOperation
        if (set(p) != {"source", "mint", "captured_at", "price_usd",
                       "liquidity_usd", "provider"}
                or p["source"] != "live_recorded"
                or p["provider"] != "dexscreener"
                or not isinstance(p["mint"], str) or not p["mint"]
                or not _positive_int(p["captured_at"])):
            return False
        try:
            price = Decimal(p["price_usd"])
            liquidity = Decimal(p["liquidity_usd"])
            return (price.is_finite() and price > 0
                    and liquidity.is_finite() and liquidity > 0)
        except (TypeError, ValueError, InvalidOperation):
            return False
    return False


def _decode(raw: bytes) -> tuple[list[dict], str]:
    if not raw:
        return [], GENESIS
    if not raw.endswith(b"\n"):
        raise ValueError("incomplete journal entry: refusing partial evidence")
    records = []
    last_hash = GENESIS
    last_time = 0
    for line in raw.splitlines():
        try:
            obj = json.loads(line)
        except (ValueError, UnicodeError):
            raise ValueError("invalid evidence journal record") from None
        if not isinstance(obj, dict) or set(obj) != {
                "schema", "sequence", "previous_sha256", "record_sha256",
                "kind", "payload", "written_at"}:
            raise ValueError("invalid evidence journal schema")
        digest = obj.pop("record_sha256")
        if (obj["schema"] != KIND or type(obj["sequence"]) is not int
                or obj["sequence"] != len(records) + 1
                or obj["previous_sha256"] != last_hash
                or not _positive_int(obj["written_at"])
                or obj["written_at"] < last_time
                or not _valid_payload(obj["kind"], obj["payload"])
                or not isinstance(digest, str) or _hash(obj) != digest):
            raise ValueError("evidence hash chain or provenance invalid")
        ts_field = "observed_at" if obj["kind"] == "signal" else "captured_at"
        if obj["payload"][ts_field] > obj["written_at"] + 2:
            raise ValueError("evidence timestamp is in the future")
        last_hash = digest
        last_time = obj["written_at"]
        obj["record_sha256"] = digest
        records.append(obj)
    return records, last_hash


def read_journal(path: Path) -> tuple[list[dict], str]:
    """Validate the whole file before using any evidence; reject symlinks."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("journal symlink forbidden")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        raise ValueError("journal must be a bounded regular file")
    if st.st_mode & 0o077:
        raise PermissionError("journal permissions must not allow other users")
    return _decode(path.read_bytes())


class EvidenceJournal:
    """Exclusive Linux writer; on-disk wallet data are mode 0600.

    When an experimental observer opts in, it writes only receipts it already
    obtained. It never performs its own provider/API requests.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        if (not self.path.is_absolute() or "public_html" in self.path.parts
                or self.path.name in ("report.json", "state.json",
                                      "helius_budget.json")):
            raise ValueError("journal must use an explicit private absolute path")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fd = None
        fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_size > MAX_BYTES:
                raise PermissionError("unsafe evidence journal file or permissions")
            os.lseek(fd, 0, os.SEEK_SET)
            existing = os.read(fd, MAX_BYTES + 1)
            records, last_hash = _decode(existing)
        except Exception:
            os.close(fd)
            raise
        self.fd = fd
        self.sequence = len(records)
        self.last_hash = last_hash

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _append(self, kind: str, payload: dict):
        if self.fd is None:
            raise ValueError("evidence journal is closed")
        if not _valid_payload(kind, payload):
            raise ValueError("invalid prospective evidence payload")
        now = int(time.time())
        sample_time = payload["observed_at"] if kind == "signal" else payload["captured_at"]
        if sample_time > now + 2:
            raise ValueError("cannot record a future observation")
        record = {
            "schema": KIND, "sequence": self.sequence + 1,
            "previous_sha256": self.last_hash, "kind": kind,
            "payload": payload, "written_at": now,
        }
        digest = _hash(record)
        line = (_json({**record, "record_sha256": digest}) + "\n").encode("utf-8")
        if os.fstat(self.fd).st_size + len(line) > MAX_BYTES:
            raise ValueError("evidence journal size cap reached")
        # One exclusive process holds the lock for the journal's lifetime.
        # Refuse partial writes; partial records are rejected on next open.
        written = os.write(self.fd, line)
        if written != len(line):
            raise OSError("incomplete evidence journal write")
        os.fsync(self.fd)
        self.sequence += 1
        self.last_hash = digest

    def signal(self, *, wallet: str, mint: str, signature: str,
               side: str, chain_time: int, observed_at: int):
        self._append("signal", {
            "source": "live_observed", "wallet": wallet, "mint": mint,
            "signature": signature, "side": side,
            "chain_time": chain_time, "observed_at": observed_at,
        })

    def quote(self, *, mint: str, captured_at: int,
              price_usd: str, liquidity_usd: str):
        self._append("quote", {
            "source": "live_recorded", "provider": "dexscreener",
            "mint": mint, "captured_at": captured_at,
            "price_usd": str(price_usd), "liquidity_usd": str(liquidity_usd),
        })


def audit_journal(path: Path, *, cutoff: int, latency_seconds: int = 134) -> dict:
    """Return a privacy-safe, aggregate-only audit of a private local journal."""
    records, digest = read_journal(path)
    events = [r["payload"] for r in records if r["kind"] == "signal"]
    quotes = [r["payload"] for r in records if r["kind"] == "quote"]
    coverage = quote_coverage(events, quotes, cutoff=cutoff,
                              latency_seconds=latency_seconds)
    return {
        "kind": "YATL_V3_PROSPECTIVE_EVIDENCE_AUDIT",
        "journal_records": len(records),
        "signal_receipt_rows": len(events),
        "indicative_quote_receipt_rows": len(quotes),
        "last_record_sha256": digest,
        "coverage": coverage,
        "caveat": ("Local hash chains detect unintended edits but cannot prove "
                   "independent source authenticity. DEX snapshots are indicative "
                   "and do not establish executable prices, fills, or profitability."),
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Offline V3 evidence journal audit; no network")
    p.add_argument("--journal", required=True, type=Path)
    p.add_argument("--cutoff", required=True, type=int)
    p.add_argument("--latency", type=int, default=134)
    args = p.parse_args(argv)
    print(json.dumps(audit_journal(args.journal, cutoff=args.cutoff,
                                  latency_seconds=args.latency),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
