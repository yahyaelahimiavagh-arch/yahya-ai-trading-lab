"""Portable node enrollment and hardware preflight utilities for YATL compute workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import sys
from pathlib import Path

from .models import MCFError
from .production_distributed import NODE_RE


def validate_node_id(node_id: str) -> str:
    if not isinstance(node_id, str) or not NODE_RE.fullmatch(node_id):
        raise MCFError("invalid distributed node id")
    return node_id


def token_sha256(token: str) -> str:
    if not isinstance(token, str) or len(token) < 32:
        raise MCFError("node token too short")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_enrollment(node_id: str, *, max_workers: int = 1) -> dict:
    validate_node_id(node_id)
    if type(max_workers) is not int or not 1 <= max_workers <= 32:
        raise MCFError("invalid node max_workers")
    token = secrets.token_urlsafe(32)
    digest = token_sha256(token)
    # node_id is strict-regex validated and digest is lowercase hex.
    sql = (
        "INSERT OR REPLACE INTO nodes"
        "(node_id,token_sha256,enabled,max_workers,created_at_ms,notes) "
        f"VALUES('{node_id}','{digest}',1,{max_workers},0,NULL);"
    )
    return {
        "status": "NODE_ENROLLMENT_GENERATED",
        "node_id": node_id,
        "node_token": token,
        "token_sha256": digest,
        "max_workers": max_workers,
        "d1_sql": sql,
        "warning": "PLAINTEXT_TOKEN_SHOWN_ONCE_DO_NOT_COMMIT",
    }


def _physical_memory_bytes() -> int | None:
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            if isinstance(page_size, int) and isinstance(pages, int) and page_size > 0 and pages > 0:
                return page_size * pages
    except (ValueError, OSError, AttributeError):
        pass
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except (AttributeError, OSError, ValueError):
            pass
    return None


def preflight(node_id: str, root: Path) -> dict:
    validate_node_id(node_id)
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    memory = _physical_memory_bytes()
    return {
        "status": "NODE_PREFLIGHT_COMPLETE_NO_PERFORMANCE",
        "node_id": node_id,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "cpu_logical_count": os.cpu_count(),
        "physical_memory_bytes": memory,
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
        "root": str(root),
        "performance_execution_authorized": False,
        "gpu_required": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("enroll")
    p.add_argument("--node-id", required=True)
    p.add_argument("--max-workers", type=int, default=1)

    p = sub.add_parser("preflight")
    p.add_argument("--node-id", required=True)
    p.add_argument("--root", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "enroll":
            result = generate_enrollment(args.node_id, max_workers=args.max_workers)
        else:
            result = preflight(args.node_id, args.root)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "NODE_TOOL_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
