"""Export a sanitised, STATIC Hostinger dashboard; no external network calls.

Read original YATL research data, but never mutate it. Intended to be run
in a separate checkout on the VPS and uploaded only to a password-protected
directory via SFTP. This exporter has no remote networking or wallet abilities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .live_monitor import _read_json, build_status


def make_static_html(template: str) -> str:
    old = 'fetch("/api/status"'
    new = 'fetch("./status.json"'
    if template.count(old) != 1:
        raise ValueError("dashboard API fetch marker missing or repeated")
    return template.replace(old, new)


def export(*, data_dir: Path, output_dir: Path, include_html: bool = False,
           budget_file: Path | None = None) -> dict:
    # The publish directory must never be the raw observer data directory.
    if output_dir.resolve() == data_dir.resolve():
        raise ValueError("refusing to publish into source data directory")
    report = _read_json(data_dir / "report.json")
    # V2 reuses the V1 Helius quota file, outside V2 report directory.
    # Read-only explicit override; NEVER restart or reset provider counters.
    budget = _read_json(budget_file if budget_file is not None else
                        data_dir / "helius_budget.json")
    status = build_status(report, budget)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(status, separators=(",", ":"), ensure_ascii=False)
    tmp = output_dir / "status.json.tmp"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(output_dir / "status.json")
    if include_html:
        source = Path(__file__).with_name("live_monitor.html")
        html = make_static_html(source.read_text(encoding="utf-8"))
        html_tmp = output_dir / "index.html.tmp"
        html_tmp.write_text(html, encoding="utf-8")
        html_tmp.replace(output_dir / "index.html")
    return status


def main():
    parser = argparse.ArgumentParser(
        description="Produce redacted status.json for a Hostinger static site; no network")
    parser.add_argument("--data-dir", type=Path,
                        default=Path("data/smart_money"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--include-html", action="store_true")
    parser.add_argument("--budget-file", type=Path,
                        help="Read-only existing shared Helius quota ledger")
    args = parser.parse_args()
    result = export(data_dir=args.data_dir, output_dir=args.output_dir,
                    include_html=args.include_html, budget_file=args.budget_file)
    # A minimal success log with no addresses or secrets.
    print(json.dumps({"status": result["status"],
                      "updated_at": result["updated_at"],
                      "polls": result["polls"],
                      "paper_fills": result["paper_fills"],
                      "hostinger_export_ready": True}, sort_keys=True))


if __name__ == "__main__":
    main()
