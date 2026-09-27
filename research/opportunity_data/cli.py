"""Read-only Development validation CLI; no trading or bulk acquisition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import development_path
from .storage import read_canonical, read_quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AF-01B research data validation")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate-runtime-root")
    p.add_argument("root", type=Path)
    for command in ("validate-manifest", "validate-canonical"):
        p = sub.add_parser(command)
        p.add_argument("root", type=Path)
        p.add_argument("relative")
        p.add_argument("sha256")
    args = parser.parse_args(argv)
    if args.command == "validate-runtime-root":
        print(development_path(args.root, "manifests"))
    elif args.command == "validate-manifest":
        print(json.dumps(read_quality(args.root, args.relative, args.sha256), sort_keys=True))
    else:
        print(json.dumps({"rows": len(read_canonical(args.root, args.relative, args.sha256))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
