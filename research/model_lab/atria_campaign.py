"""Bounded, resumable Atria research campaigns for YATL.

Campaigns orchestrate the already-isolated Atria worker. They do not add any
trade, order, quantity, risk, P10, or P11 authority.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import atria_worker as worker


CAMPAIGN_ID = "YATL_ATRIA_RESEARCH_CAMPAIGN_V1"
SCHEMA_VERSION = "0.1.0"
MAX_CAMPAIGN_BYTES = 128 * 1024
MAX_TASKS = 24
MAX_CAMPAIGN_OUTPUT_TOKENS = 131_072
TASK_ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
OBJECTIVES = frozenset(
    {
        "COMPARE_EVIDENCE",
        "FIND_ANOMALIES",
        "PROPOSE_FALSIFIABLE_TESTS",
    }
)


class AtriaCampaignError(RuntimeError):
    """A campaign violated its bounded research-only contract."""


def _load_campaign(path: Path) -> tuple[dict[str, object], str]:
    if not isinstance(path, Path):
        raise AtriaCampaignError("campaign path must be a Path")
    target = path.expanduser()
    if target.exists() and target.is_symlink():
        raise AtriaCampaignError("symlink campaign manifest is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise AtriaCampaignError("cannot read campaign manifest") from None
    if not payload or len(payload) > MAX_CAMPAIGN_BYTES:
        raise AtriaCampaignError("campaign manifest size is invalid")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AtriaCampaignError("campaign manifest is not UTF-8 JSON") from None
    if not isinstance(record, dict):
        raise AtriaCampaignError("campaign manifest must be an object")
    if (
        record.get("schema") != "YATL_ATRIA_RESEARCH_CAMPAIGN"
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("research_only") is not True
        or record.get("p10_write_allowed") is not False
        or record.get("p11_locked") is not True
    ):
        raise AtriaCampaignError("campaign safety invariants are invalid")
    campaign_id = record.get("campaign_id")
    tasks = record.get("tasks")
    if (
        not isinstance(campaign_id, str)
        or TASK_ID_RE.fullmatch(campaign_id) is None
        or not isinstance(tasks, list)
        or not 1 <= len(tasks) <= MAX_TASKS
    ):
        raise AtriaCampaignError("campaign identity or task count is invalid")

    task_ids = []
    total_budget = 0
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {
            "task_id",
            "objective",
            "artifacts",
            "max_output_tokens",
        }:
            raise AtriaCampaignError("campaign task schema is invalid")
        task_id = task["task_id"]
        objective = task["objective"]
        artifacts = task["artifacts"]
        max_tokens = task["max_output_tokens"]
        if (
            not isinstance(task_id, str)
            or TASK_ID_RE.fullmatch(task_id) is None
            or objective not in OBJECTIVES
            or not isinstance(artifacts, list)
            or not 1 <= len(artifacts) <= worker.MAX_INPUT_FILES
            or any(not isinstance(item, str) or not item for item in artifacts)
            or len(set(artifacts)) != len(artifacts)
            or type(max_tokens) is not int
            or not 1 <= max_tokens <= worker.MAX_OUTPUT_TOKENS
        ):
            raise AtriaCampaignError("campaign task values are invalid")
        task_ids.append(task_id)
        total_budget += max_tokens

    if (
        len(set(task_ids)) != len(task_ids)
        or task_ids != sorted(task_ids)
    ):
        raise AtriaCampaignError(
            "campaign task ids must be unique and sorted"
        )
    if total_budget > MAX_CAMPAIGN_OUTPUT_TOKENS:
        raise AtriaCampaignError(
            "campaign output-token budget exceeds fixed ceiling"
        )
    return record, worker._sha256(payload)


def _task_plan(
    *,
    runtime_root: Path,
    task: Mapping[str, object],
) -> dict[str, object]:
    try:
        packet = worker.build_packet(
            runtime_root=runtime_root,
            artifact_paths=task["artifacts"],
            objective=task["objective"],
        )
        request = worker.build_provider_request(
            packet,
            max_output_tokens=task["max_output_tokens"],
        )
    except worker.AtriaResearchError as exc:
        raise AtriaCampaignError(str(exc)) from None
    return {
        "task_id": task["task_id"],
        "objective": task["objective"],
        "artifact_count": len(task["artifacts"]),
        "packet_sha256": packet["packet_sha256"],
        "packet_bytes": len(worker._canonical_json(packet)),
        "max_output_tokens": request["max_output_tokens"],
    }


def plan_campaign(
    *,
    runtime_root: Path,
    campaign_path: Path,
) -> dict[str, object]:
    campaign, campaign_file_sha = _load_campaign(campaign_path)
    plans = [
        _task_plan(runtime_root=runtime_root, task=task)
        for task in campaign["tasks"]
    ]
    return {
        "campaign_runner_id": CAMPAIGN_ID,
        "campaign_id": campaign["campaign_id"],
        "campaign_file_sha256": campaign_file_sha,
        "task_count": len(plans),
        "total_packet_bytes": sum(
            int(item["packet_bytes"]) for item in plans
        ),
        "max_output_tokens_budget": sum(
            int(item["max_output_tokens"]) for item in plans
        ),
        "tasks": plans,
        "network_used": False,
        "credential_read": False,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def _receipt_relative_path(
    campaign_id: str,
    task_id: str,
    packet_sha256: str,
) -> Path:
    return (
        Path("model-lab")
        / "atria"
        / "campaigns"
        / campaign_id
        / f"{task_id}-{packet_sha256[:24]}.json"
    )


def _read_receipt(
    *,
    runtime_root: Path,
    relative: Path,
    campaign_id: str,
    task_id: str,
    packet_sha256: str,
) -> dict[str, object] | None:
    try:
        root = worker._safe_root(runtime_root)
    except worker.AtriaResearchError as exc:
        raise AtriaCampaignError(str(exc)) from None
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        raise AtriaCampaignError("campaign receipt escaped runtime root") from None
    if not target.exists():
        return None
    if target.is_symlink():
        raise AtriaCampaignError("symlink campaign receipt is forbidden")
    try:
        payload = target.read_bytes()
        record = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise AtriaCampaignError("campaign receipt is unreadable") from None
    if (
        not isinstance(record, dict)
        or record.get("schema") != "YATL_ATRIA_CAMPAIGN_TASK_RECEIPT"
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("campaign_id") != campaign_id
        or record.get("task_id") != task_id
        or record.get("packet_sha256") != packet_sha256
        or record.get("research_only") is not True
        or record.get("p10_write_allowed") is not False
        or record.get("p11_locked") is not True
    ):
        raise AtriaCampaignError("campaign receipt binding is invalid")
    rebound = dict(record)
    supplied = rebound.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or supplied != worker._sha256(worker._canonical_json(rebound))
    ):
        raise AtriaCampaignError("campaign receipt digest binding changed")
    return record


def _write_receipt(
    *,
    runtime_root: Path,
    campaign_id: str,
    task_plan: Mapping[str, object],
    worker_result: Mapping[str, object],
) -> dict[str, object]:
    required = {
        "manifest_relative_path",
        "manifest_file_sha256",
        "result_sha256",
        "analysis_sha256",
        "usage",
        "research_only",
        "p10_write_allowed",
        "p11_locked",
    }
    if (
        not isinstance(worker_result, Mapping)
        or not required.issubset(worker_result)
        or worker_result["research_only"] is not True
        or worker_result["p10_write_allowed"] is not False
        or worker_result["p11_locked"] is not True
    ):
        raise AtriaCampaignError("worker result is not an isolated research result")

    receipt: dict[str, object] = {
        "schema": "YATL_ATRIA_CAMPAIGN_TASK_RECEIPT",
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "task_id": task_plan["task_id"],
        "objective": task_plan["objective"],
        "packet_sha256": task_plan["packet_sha256"],
        "worker_manifest_relative_path": worker_result[
            "manifest_relative_path"
        ],
        "worker_manifest_file_sha256": worker_result[
            "manifest_file_sha256"
        ],
        "worker_result_sha256": worker_result["result_sha256"],
        "analysis_sha256": worker_result["analysis_sha256"],
        "usage": worker_result["usage"],
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    receipt["receipt_sha256"] = worker._sha256(
        worker._canonical_json(receipt)
    )
    relative = _receipt_relative_path(
        campaign_id,
        str(task_plan["task_id"]),
        str(task_plan["packet_sha256"]),
    )
    try:
        path = worker._write_immutable(
            runtime_root,
            relative,
            worker._canonical_json(receipt),
        )
    except worker.AtriaResearchError as exc:
        raise AtriaCampaignError(str(exc)) from None
    return {
        "task_id": task_plan["task_id"],
        "status": "EXECUTED",
        "receipt_relative_path": path,
        "receipt_sha256": receipt["receipt_sha256"],
        "usage": worker_result["usage"],
    }


def run_campaign(
    *,
    runtime_root: Path,
    campaign_path: Path,
    bearer_secret: str,
    transport=None,
    task_runner: Callable[..., Mapping[str, object]] = worker.run_worker,
) -> dict[str, object]:
    campaign, campaign_file_sha = _load_campaign(campaign_path)
    plans = [
        _task_plan(runtime_root=runtime_root, task=task)
        for task in campaign["tasks"]
    ]
    task_by_id = {
        task["task_id"]: task for task in campaign["tasks"]
    }
    outcomes = []
    for plan in plans:
        relative = _receipt_relative_path(
            campaign["campaign_id"],
            str(plan["task_id"]),
            str(plan["packet_sha256"]),
        )
        existing = _read_receipt(
            runtime_root=runtime_root,
            relative=relative,
            campaign_id=campaign["campaign_id"],
            task_id=str(plan["task_id"]),
            packet_sha256=str(plan["packet_sha256"]),
        )
        if existing is not None:
            outcomes.append(
                {
                    "task_id": plan["task_id"],
                    "status": "RECEIPT_REUSED",
                    "receipt_relative_path": relative.as_posix(),
                    "receipt_sha256": existing["receipt_sha256"],
                    "usage": existing["usage"],
                }
            )
            continue

        task = task_by_id[plan["task_id"]]
        try:
            result = task_runner(
                runtime_root=runtime_root,
                artifact_paths=task["artifacts"],
                objective=task["objective"],
                bearer_secret=bearer_secret,
                max_output_tokens=task["max_output_tokens"],
                transport=transport,
            )
        except worker.AtriaResearchError as exc:
            raise AtriaCampaignError(str(exc)) from None
        outcomes.append(
            _write_receipt(
                runtime_root=runtime_root,
                campaign_id=campaign["campaign_id"],
                task_plan=plan,
                worker_result=result,
            )
        )

    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for item in outcomes:
        usage = item.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for key in total_usage:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                total_usage[key] += value

    return {
        "campaign_runner_id": CAMPAIGN_ID,
        "campaign_id": campaign["campaign_id"],
        "campaign_file_sha256": campaign_file_sha,
        "task_count": len(outcomes),
        "executed_count": sum(
            item["status"] == "EXECUTED" for item in outcomes
        ),
        "receipt_reused_count": sum(
            item["status"] == "RECEIPT_REUSED" for item in outcomes
        ),
        "tasks": outcomes,
        "usage": total_usage,
        "external_transport_may_have_been_used": any(
            item["status"] == "EXECUTED" for item in outcomes
        ),
        "provider_output_trusted": False,
        "strategy_evidence_effect": "NONE",
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "trade_permission": False,
        "order_endpoint": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.model_lab.atria_campaign",
        description="Bounded resumable YATL Atria research campaigns",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        child = sub.add_parser(name)
        child.add_argument("--runtime-root", type=Path, required=True)
        child.add_argument("--campaign", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan":
        result = plan_campaign(
            runtime_root=args.runtime_root,
            campaign_path=args.campaign,
        )
    elif args.command == "run":
        secret = os.environ.get(worker.ENV_KEY)
        if not secret:
            raise AtriaCampaignError(
                f"{worker.ENV_KEY} environment variable is required"
            )
        result = run_campaign(
            runtime_root=args.runtime_root,
            campaign_path=args.campaign,
            bearer_secret=secret,
        )
    else:
        raise AtriaCampaignError("unsupported campaign command")
    print(worker._json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AtriaCampaignError as exc:
        print(
            worker._json(
                {
                    "code": "ATRIA_RESEARCH_CAMPAIGN_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                }
            )
        )
        raise SystemExit(2)
