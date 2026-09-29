"""Strict MCF-03 production result ledger and reconciliation."""
from __future__ import annotations

import collections
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from .models import MCFError, canonical, digest, guard_root, write_once

VERSION = "MCF_PRODUCTION_LEDGER/1.0.0"
FINAL_STATES = {
    "STRUCTURALLY_INVALID",
    "BLOCKED_IMPLEMENTATION",
    "DEVELOPMENT_FAIL",
    "F0_F3_PASS",
}
SAFETY = {
    "paper_research_only": True,
    "fresh_oos_read": False,
    "recent_reserve_read": False,
    "p10_read": False,
    "p10_write": False,
    "futures": False,
    "leverage": False,
    "short": False,
    "live": False,
    "order_endpoint": False,
    "ai_direct_execution": False,
    "p11_locked": True,
}


def _valid_result_sha(result: Mapping[str, object]) -> bool:
    if "result_sha256" not in result:
        return False
    body = {k: v for k, v in result.items() if k != "result_sha256"}
    return result["result_sha256"] == digest(body)


def make_record(candidate: Mapping[str, object], *, state: str,
                result: Mapping[str, object] | None = None,
                blocker_reason: str | None = None) -> dict:
    if state not in FINAL_STATES:
        raise MCFError("invalid production result state")
    required = {"candidate_id", "candidate_spec_sha256", "family", "family_id"}
    if not required <= set(candidate):
        raise MCFError("incomplete production candidate identity")
    cid = str(candidate["candidate_id"])
    spec = str(candidate["candidate_spec_sha256"])

    result_sha = None
    daily_sha = None
    per_symbol_daily_sha = None
    failures: tuple[str, ...] = ()

    if state in {"DEVELOPMENT_FAIL", "F0_F3_PASS"}:
        if result is None or not _valid_result_sha(result):
            raise MCFError("performance state requires canonical MCF-03 result")
        if result.get("candidate_id") != cid or result.get("candidate_spec_sha256") != spec:
            raise MCFError("result/candidate identity mismatch")
        if result.get("evidence_partition") != "DEVELOPMENT":
            raise MCFError("non-Development production result")
        expected = "F0_F3_PASS" if state == "F0_F3_PASS" else "DEVELOPMENT_FAIL"
        if result.get("f0_f3_state") != expected:
            raise MCFError("ledger/result state mismatch")
        if result.get("safety") != SAFETY:
            raise MCFError("production result safety mismatch")
        result_sha = str(result["result_sha256"])
        daily_sha = digest(result["daily_return_series"])
        per_symbol_daily_sha = digest(result["per_symbol_daily_return_series"])
        failures = tuple(result.get("failure_reasons", ()))
    elif result is not None:
        raise MCFError("non-performance state cannot attach performance result")

    if state == "BLOCKED_IMPLEMENTATION":
        if not isinstance(blocker_reason, str) or not blocker_reason.strip():
            raise MCFError("implementation blocker requires reason")
        failures = ("BLOCKED_IMPLEMENTATION",)
    elif blocker_reason is not None:
        raise MCFError("unexpected blocker reason")
    elif state == "STRUCTURALLY_INVALID":
        failures = tuple(candidate.get("failure_reasons", ("STRUCTURALLY_INVALID",)))

    row = {
        "schema": VERSION,
        "ordinal": int(candidate["ordinal"]),
        "candidate_id": cid,
        "candidate_spec_sha256": spec,
        "family": str(candidate["family"]),
        "family_id": str(candidate["family_id"]),
        "state": state,
        "failure_reasons": tuple(sorted(set(failures))),
        "implementation_blocker": blocker_reason,
        "result_sha256": result_sha,
        "daily_return_sha256": daily_sha,
        "per_symbol_daily_return_sha256": per_symbol_daily_sha,
        "evidence_partition": "DEVELOPMENT",
        "safety": dict(SAFETY),
    }
    return {**row, "record_sha256": digest(row)}


def reconcile(raw_candidates: Sequence[Mapping[str, object]],
              executable_freeze: Mapping[str, object],
              records: Sequence[Mapping[str, object]]) -> dict:
    """Require one final row for every pre-outcome raw identity."""
    try:
        expected = {str(c["candidate_id"]): c for c in raw_candidates}
        if len(expected) != len(raw_candidates):
            raise MCFError("duplicate raw production candidate")
        frozen_exec = {
            str(cid): str(spec)
            for cid, spec in executable_freeze["registered_candidates"]
        }
        blocked = {
            str(c["candidate_id"]): c
            for c in executable_freeze["blocked"]
        }
        if set(frozen_exec) & set(blocked):
            raise MCFError("candidate both executable and blocked")

        found = {}
        for row in records:
            cid = str(row.get("candidate_id", ""))
            if cid not in expected or cid in found:
                raise MCFError("unknown/duplicate production result")
            if row.get("schema") != VERSION:
                raise MCFError("wrong production ledger schema")
            body = {k: v for k, v in row.items() if k != "record_sha256"}
            if row.get("record_sha256") != digest(body):
                raise MCFError("production record digest mismatch")
            candidate = expected[cid]
            if row.get("candidate_spec_sha256") != candidate["candidate_spec_sha256"]:
                raise MCFError("production record spec mismatch")
            if row.get("ordinal") != candidate["ordinal"]:
                raise MCFError("production record ordinal mismatch")
            if row.get("evidence_partition") != "DEVELOPMENT" or row.get("safety") != SAFETY:
                raise MCFError("production record evidence/safety mismatch")

            if candidate.get("state") == "STRUCTURALLY_INVALID":
                if row.get("state") != "STRUCTURALLY_INVALID":
                    raise MCFError("structural invalid candidate changed state")
            elif cid in blocked:
                if row.get("state") != "BLOCKED_IMPLEMENTATION":
                    raise MCFError("implementation blocker changed state")
            elif cid in frozen_exec:
                if row.get("state") not in {"DEVELOPMENT_FAIL", "F0_F3_PASS"}:
                    raise MCFError("executable candidate missing final Development state")
                if row.get("candidate_spec_sha256") != frozen_exec[cid]:
                    raise MCFError("executable freeze spec mismatch")
            else:
                raise MCFError("valid candidate missing from executable/blocker freeze")
            found[cid] = row

        if set(found) != set(expected):
            raise MCFError("incomplete production result ledger")
        ordered = [found[cid] for cid in sorted(found, key=lambda x: expected[x]["ordinal"])]
        counts = collections.Counter(row["state"] for row in ordered)
        family_failures: dict[str, collections.Counter] = {}
        for row in ordered:
            counter = family_failures.setdefault(row["family"], collections.Counter())
            for reason in row["failure_reasons"]:
                counter[reason] += 1
        return {
            "schema": "MCF_PRODUCTION_RECONCILIATION/1.0.0",
            "status": "BATCH_COMPLETE",
            "raw_candidate_count": len(expected),
            "state_counts": dict(sorted(counts.items())),
            "f0_f3_passer_count": counts.get("F0_F3_PASS", 0),
            "family_failure_summary": {
                family: dict(sorted(counter.items()))
                for family, counter in sorted(family_failures.items())
            },
            "ledger_sha256": digest(ordered),
            "safety": dict(SAFETY),
        }
    except (KeyError, TypeError, ValueError, MCFError) as exc:
        return {
            "schema": "MCF_PRODUCTION_RECONCILIATION/1.0.0",
            "status": "BATCH_INVALID",
            "reason": str(exc),
            "safety": dict(SAFETY),
        }


def write_ledger(root: Path, records: Sequence[Mapping[str, object]]) -> tuple[Path, str]:
    guard_root(root)
    ordered = sorted(records, key=lambda row: int(row["ordinal"]))
    payload = b"".join(canonical(row) for row in ordered)
    sha = hashlib.sha256(payload).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"MCF-PROD-001-results-{sha}.jsonl"
    write_once(target, payload)
    return target, sha
