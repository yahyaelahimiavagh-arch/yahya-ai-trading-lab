"""Offline fail-closed file-scope gate for YATL autonomy bootstrap.

Stdlib only. No provider requests, subprocess execution, git mutation or VPS access.
This is a *repository policy check*, not a runtime sandbox or branch protection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

EXACT_PATHS = frozenset({
    "AGENTS.md",
    "docs/YATL-AUTONOMY-V1.md",
    ".github/workflows/yatl-autonomy-safety.yml",
    ".github/ISSUE_TEMPLATE/yatl-autonomy-task.yml",
})
PATH_PREFIXES = ("infra/autonomy/", "tests/test_yatl_autonomy_")
ROLES = ["orchestrator", "research", "developer", "qa", "ops"]
FLAGS = {
    "schema_version": 1,
    "phase": "github_only",
    "status": "dry_run",
    "paper_only": True,
    "vps_access_allowed": False,
    "deployment_allowed": False,
    "agent_external_network_allowed": False,
    "secrets_access_allowed": False,
    "real_orders_allowed": False,
    "paid_api_calls_allowed": False,
    "quota_reset_allowed": False,
    "agent_spend_limit_usd": 0,
}
APPROVALS = frozenset({
    "vps_access", "deployment", "production_changes", "paid_api_calls",
    "risk_or_order_control_changes", "quota_or_budget_change",
    "experiment_state_mutation", "merge", "new_secrets",
})


def validate_policy(policy: object) -> list[str]:
    """Reject missing/weakened policies; no writes or external effects."""
    if not isinstance(policy, dict):
        return ["policy must be a JSON object"]
    errors = []
    for key, expected in FLAGS.items():
        got = policy.get(key)
        if type(got) is not type(expected) or got != expected:
            errors.append(f"unsafe/missing {key}: expected {expected!r}")
    if policy.get("roles") != ROLES:
        errors.append("roles must match the audited V1 role set")
    if set(policy.get("allowed_exact_paths", [])) != EXACT_PATHS:
        errors.append("allowed_exact_paths cannot be expanded or reduced in V1")
    if set(policy.get("allowed_path_prefixes", [])) != set(PATH_PREFIXES):
        errors.append("allowed_path_prefixes cannot be changed in V1")
    if not APPROVALS.issubset(set(policy.get("human_approval_required_for", []))):
        errors.append("required human approvals are missing")
    return errors


def validate_changed_paths(paths: list[str], policy: dict) -> list[str]:
    """Deny unexpected changes to research, trading or existing operations."""
    errors = []
    exact = set(policy.get("allowed_exact_paths", []))
    prefixes = tuple(policy.get("allowed_path_prefixes", []))
    for raw in paths:
        path = raw.strip()
        if not path:
            continue
        parts = PurePosixPath(path).parts
        if (path.startswith("/") or "\\" in path or
                "." in parts or ".." in parts or
                any(ord(ch) < 32 for ch in path)):
            errors.append(f"invalid relative path: {raw!r}")
        elif path not in exact and not any(path.startswith(p) for p in prefixes):
            errors.append(f"path outside autonomy V1 scope: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--paths-file", type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        errors = validate_policy(policy)
        if args.paths_file:
            paths = args.paths_file.read_text(encoding="utf-8").splitlines()
            errors.extend(validate_changed_paths(paths, policy))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors = [f"cannot verify policy or paths: {type(exc).__name__}: {exc}"]
    if errors:
        for error in errors:
            print("DENY:", error)
        return 1
    print("PASS: GitHub-only, dry-run, paper-only autonomy V1; scoped files only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
