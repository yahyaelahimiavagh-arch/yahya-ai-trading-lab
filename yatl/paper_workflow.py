"""Deterministic, local-only P0 paper workflow validation.

This module performs arithmetic and policy validation only. It has no network
transport and cannot submit an exchange order.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
TOP_LEVEL_FIELDS = frozenset({
    "schema_version", "mode", "live_master_lock", "exchange_order_submission",
    "policy", "workflows",
})
POLICY_FIELDS = frozenset({
    "market", "direction", "primary_analysis_timeframe",
    "higher_timeframe_regime", "entry_context_timeframe",
    "execution_timeframe",
})
WORKFLOW_FIELDS = frozenset({
    "workflow_id", "symbol", "entry", "stop", "target", "position_size",
    "account_equity", "risk_percent", "max_loss", "potential_reward",
    "risk_reward_ratio", "status", "notes",
})


class PaperWorkflowError(Exception):
    """A concise validation error with no secret or payload echoing."""


def _decimal(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,18}(\.[0-9]{1,18})?", value):
        raise PaperWorkflowError(f"{field} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise PaperWorkflowError(f"{field} is invalid") from None
    if not number.is_finite() or number <= 0:
        raise PaperWorkflowError(f"{field} must be positive and finite")
    return number


def _exact_fields(value, expected, name):
    if not isinstance(value, dict) or set(value) != expected:
        raise PaperWorkflowError(f"{name} fields do not match the schema")


def validate_paper_workflow(payload):
    """Validate a fixed Spot paper plan and return a safe summary."""
    _exact_fields(payload, TOP_LEVEL_FIELDS, "Top-level")
    if payload["schema_version"] != 1:
        raise PaperWorkflowError("Unsupported paper workflow schema")
    if payload["mode"] != "PAPER_ONLY" or payload["live_master_lock"] != "OFF":
        raise PaperWorkflowError("Paper mode and LIVE_MASTER_LOCK=OFF are required")
    if payload["exchange_order_submission"] is not False:
        raise PaperWorkflowError("Exchange order submission must be disabled")

    policy = payload["policy"]
    _exact_fields(policy, POLICY_FIELDS, "Policy")
    expected_policy = {
        "market": "SPOT",
        "direction": "LONG_ONLY",
        "primary_analysis_timeframe": "1h",
        "higher_timeframe_regime": "4h",
        "entry_context_timeframe": "15m",
        "execution_timeframe": "NOT_ENABLED",
    }
    if policy != expected_policy:
        raise PaperWorkflowError("Paper workflow policy is outside the P0 allowlist")

    workflows = payload["workflows"]
    if not isinstance(workflows, list) or len(workflows) != 2:
        raise PaperWorkflowError("Exactly two paper workflows are required")
    seen_symbols = set()
    seen_ids = set()
    summaries = []
    for item in workflows:
        _exact_fields(item, WORKFLOW_FIELDS, "Workflow")
        workflow_id = item["workflow_id"]
        symbol = item["symbol"]
        if not isinstance(workflow_id, str) or not workflow_id or workflow_id in seen_ids:
            raise PaperWorkflowError("Workflow IDs must be unique non-empty strings")
        if symbol not in ALLOWED_SYMBOLS or symbol in seen_symbols:
            raise PaperWorkflowError("Workflow symbols must be unique BTCUSDT and ETHUSDT")
        if item["status"] != "MANUAL_PAPER_FIXTURE":
            raise PaperWorkflowError("Workflow status must remain a manual paper fixture")
        if not isinstance(item["notes"], str) or not item["notes"].strip():
            raise PaperWorkflowError("Workflow notes are required")

        entry = _decimal(item["entry"], "entry")
        stop = _decimal(item["stop"], "stop")
        target = _decimal(item["target"], "target")
        size = _decimal(item["position_size"], "position_size")
        equity = _decimal(item["account_equity"], "account_equity")
        risk_percent = _decimal(item["risk_percent"], "risk_percent")
        max_loss = _decimal(item["max_loss"], "max_loss")
        reward = _decimal(item["potential_reward"], "potential_reward")
        ratio = _decimal(item["risk_reward_ratio"], "risk_reward_ratio")
        if not stop < entry < target:
            raise PaperWorkflowError("Required price order is stop < entry < target")
        if risk_percent > Decimal("1"):
            raise PaperWorkflowError("Paper risk may not exceed 1 percent")
        if size * entry > equity:
            raise PaperWorkflowError("Position notional exceeds equity; leverage is forbidden")
        calculated_loss = size * (entry - stop)
        calculated_reward = size * (target - entry)
        risk_budget = equity * risk_percent / Decimal("100")
        if max_loss != calculated_loss or max_loss > risk_budget:
            raise PaperWorkflowError("Max loss is inconsistent or exceeds the risk budget")
        if reward != calculated_reward or ratio != reward / max_loss or ratio < Decimal("2"):
            raise PaperWorkflowError("Reward or risk/reward ratio is inconsistent")
        seen_ids.add(workflow_id)
        seen_symbols.add(symbol)
        summaries.append({
            "symbol": symbol,
            "entry": str(entry),
            "stop": str(stop),
            "target": str(target),
            "position_size": str(size),
            "max_loss": str(max_loss),
            "risk_reward_ratio": str(ratio),
        })
    if seen_symbols != ALLOWED_SYMBOLS:
        raise PaperWorkflowError("Both BTCUSDT and ETHUSDT workflows are required")
    return summaries


def load_and_validate(path=Path("fixtures/p0-paper-workflows.json")):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(65_537)
        if len(raw) > 65_536:
            raise PaperWorkflowError("Paper workflow fixture exceeds size limit")
        payload = json.loads(raw)
    except (OSError, UnicodeError, ValueError):
        raise PaperWorkflowError("Cannot read a valid paper workflow fixture") from None
    return validate_paper_workflow(payload)
