"""Versioned production family manifests compiled from frozen MCF-PROD-001 JSON."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import MCFError, digest

VERSION = "MCF_PRODUCTION_FAMILY_MANIFEST/1.0.0"
ROOT = Path(__file__).resolve().parents[2]
DOMAIN_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-FAMILY-DOMAIN-PLAN-v1.0.json"
BUDGET_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-SEARCH-BUDGET-v1.0.json"
UNIVERSE_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-UNIVERSE-EVIDENCE-POLICY-v1.0.json"


def _read(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


DOMAIN, DOMAIN_SHA256 = _read(DOMAIN_PATH)
BUDGET, BUDGET_SHA256 = _read(BUDGET_PATH)
UNIVERSE, UNIVERSE_SHA256 = _read(UNIVERSE_PATH)

_DEPENDENCIES = {
    "TREND_CROSSOVER": ("PRICE_OHLC",),
    "BREAKOUT_CHANNEL": ("PRICE_OHLC",),
    "SHORT_HORIZON_MEAN_REVERSION": ("PRICE_OHLC",),
    "CRASH_REBOUND": ("PRICE_OHLC",),
    "VOLUME_CONFIRMED_DIRECTION": ("PRICE_OHLC", "VOLUME"),
    "SESSION_TIME_EFFECT": ("PRICE_OHLC",),
    "LIQUIDITY_CONDITIONED_ENTRY": ("PRICE_OHLC", "VOLUME"),
    "LEAD_LAG": ("PRICE_OHLC", "MULTI_ASSET"),
    "PRICE_VOLUME_INTERACTION": ("PRICE_OHLC", "VOLUME"),
    "SIMPLE_STATISTICAL_DEVIATION": ("PRICE_OHLC",),
    "TRADE_COUNT_CONFIRMED_DIRECTION": ("PRICE_OHLC", "TRADE_COUNT"),
    "RANGE_COMPRESSION_BREAKOUT": ("PRICE_OHLC",),
}


def validate_manifest(record: dict) -> str:
    required = {
        "schema", "generation_id", "family_id", "family", "attribution",
        "tested_object_type", "timeframes", "parameter_domains",
        "structural_constraints", "rule_definition", "data_dependencies",
        "cost_policy_ref", "universe_policy_id", "universe_policy_sha256",
        "domain_plan_sha256", "search_budget_sha256", "evidence_partition",
        "research_only", "safety",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise MCFError("production family manifest fields mismatch")
    if record["schema"] != VERSION or record["generation_id"] != "MCF-PROD-001":
        raise MCFError("production family manifest identity mismatch")
    if record["tested_object_type"] != "PER_SYMBOL_RULE_ACROSS_DYNAMIC_UNIVERSE":
        raise MCFError("wrong production tested object")
    if record["cost_policy_ref"] != "MCF-SPOT-COST/v1":
        raise MCFError("wrong production cost policy")
    if record["universe_policy_id"] != "MCF-PROD-001-UNIVERSE-EVIDENCE":
        raise MCFError("wrong production universe policy")
    if record["universe_policy_sha256"] != UNIVERSE_SHA256:
        raise MCFError("production universe policy SHA mismatch")
    if record["domain_plan_sha256"] != DOMAIN_SHA256 or record["search_budget_sha256"] != BUDGET_SHA256:
        raise MCFError("production frozen-document SHA mismatch")
    if record["evidence_partition"] != "DEVELOPMENT" or record["research_only"] is not True:
        raise MCFError("production evidence boundary mismatch")
    if not isinstance(record["timeframes"], tuple) or not record["timeframes"]:
        raise MCFError("empty production timeframes")
    if any(x not in {"15m", "1h", "4h"} for x in record["timeframes"]):
        raise MCFError("unadmitted production timeframe")
    if not isinstance(record["parameter_domains"], tuple) or not record["parameter_domains"]:
        raise MCFError("empty production parameter domains")
    for name, values in record["parameter_domains"]:
        if not isinstance(name, str) or not name or not isinstance(values, tuple) or not values:
            raise MCFError("invalid production parameter domain")
    if record["family"] not in _DEPENDENCIES or tuple(record["data_dependencies"]) != _DEPENDENCIES[record["family"]]:
        raise MCFError("production dependency mismatch")
    if not isinstance(record["rule_definition"], str) or not record["rule_definition"].strip():
        raise MCFError("empty frozen production rule definition")
    if record["safety"] != {
        "paper_research_only": True,
        "fresh_oos_read": False,
        "recent_reserve_read": False,
        "p10_read": False,
        "p10_write": False,
        "p11_locked": True,
        "live_master_lock": "OFF",
    }:
        raise MCFError("production manifest safety mismatch")
    return digest(record)


def compile_manifests() -> tuple[dict, ...]:
    if DOMAIN.get("generation_id") != "MCF-PROD-001" or DOMAIN.get("state") != "FROZEN_BEFORE_PERFORMANCE":
        raise MCFError("production domain plan not frozen")
    allowed = tuple(BUDGET.get("allowed_initial_families", ()))
    families = DOMAIN.get("families")
    if not isinstance(families, list) or set(f["family"] for f in families) != set(allowed):
        raise MCFError("production family catalog mismatch")

    records = []
    for family in families:
        record = {
            "schema": VERSION,
            "generation_id": "MCF-PROD-001",
            "family_id": family["id"],
            "family": family["family"],
            "attribution": family["attribution"],
            "tested_object_type": "PER_SYMBOL_RULE_ACROSS_DYNAMIC_UNIVERSE",
            "timeframes": tuple(family["timeframes"]),
            "parameter_domains": tuple(
                (name, tuple(values))
                for name, values in family["domains"].items()
            ),
            "structural_constraints": tuple(family.get("constraints", ())),
            "rule_definition": family["rule_definition"],
            "data_dependencies": _DEPENDENCIES[family["family"]],
            "cost_policy_ref": "MCF-SPOT-COST/v1",
            "universe_policy_id": "MCF-PROD-001-UNIVERSE-EVIDENCE",
            "universe_policy_sha256": UNIVERSE_SHA256,
            "domain_plan_sha256": DOMAIN_SHA256,
            "search_budget_sha256": BUDGET_SHA256,
            "evidence_partition": "DEVELOPMENT",
            "research_only": True,
            "safety": {
                "paper_research_only": True,
                "fresh_oos_read": False,
                "recent_reserve_read": False,
                "p10_read": False,
                "p10_write": False,
                "p11_locked": True,
                "live_master_lock": "OFF",
            },
        }
        sha = validate_manifest(record)
        records.append({**record, "family_spec_sha256": sha})
    return tuple(sorted(records, key=lambda x: x["family_id"]))


def manifest_index() -> dict[str, dict]:
    records = compile_manifests()
    return {record["family"]: record for record in records}
