"""Exact MCF-01 outer schema, bounded domains and closed typed templates."""
from __future__ import annotations
import json
import re
from decimal import Decimal
from pathlib import Path
from .models import MCFError, digest, safe_path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "docs/research/alpha-factory/MCF-01-FAMILY-MANIFEST-SCHEMA-v1.0.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
SUPPORTED_DATA = {"PRICE_OHLC", "VOLUME", "TRADE_COUNT", "MULTI_ASSET"}
FEATURES = {"LAGGED_RETURN", "MOVING_AVERAGE", "ROLLING_MIN", "ROLLING_MAX", "ROLLING_MEAN", "ROLLING_STD", "OHLC_RANGE", "BASE_VOLUME_MEAN", "QUOTE_VOLUME_MEAN", "TRADE_COUNT_MEAN", "UTC_SESSION", "CROSS_ASSET_LAGGED_RETURN"}
RULES = {"GT", "LT", "CROSS_ABOVE", "CROSS_BELOW", "ZSCORE_GT", "ZSCORE_LT", "BREAKOUT", "REENTRY", "AND", "OR"}
DOMAIN_FIELDS = {"name", "type", "values", "start", "stop", "step", "ordering", "semantic_role", "mechanism_distinct"}
TEMPLATE_KEYS = {"feature", "operator", "left", "right", "threshold", "children", "window", "lag", "field", "symbol", "start_hour", "end_hour", "value", "scale", "quantity"}

def _positive_int(v):
    return type(v) is int and v > 0

def _ref(v):
    return isinstance(v, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", v)) and ".." not in v and not v.startswith("/") and not any(x in v.lower() for x in ("p10", "fresh_oos", "fresh-oos", "recent_reserve", "recent-reserve"))

def _template(t, depth=0):
    if t is None:
        return
    if not isinstance(t, dict) or set(t) - TEMPLATE_KEYS or depth > 3:
        raise MCFError("unbounded/unknown typed template")
    if "feature" in t and t["feature"] not in FEATURES:
        raise MCFError("unknown feature")
    if "operator" in t and t["operator"] not in RULES:
        raise MCFError("unknown operator")
    if "children" in t:
        if t.get("operator") not in {"AND", "OR"} or not isinstance(t["children"], list) or not 1 <= len(t["children"]) <= 4:
            raise MCFError("unbounded logical rule")
        for child in t["children"]:
            _template(child, depth + 1)
    for k in ("left", "right"):
        if isinstance(t.get(k), dict):
            _template(t[k], depth + 1)
    if "scale" in t and (not isinstance(t["scale"], (int, float, str)) or not 0 <= Decimal(str(t["scale"])) <= 1):
        raise MCFError("unsafe scale")
    if "quantity" in t and (not isinstance(t["quantity"], (int, float, str)) or not Decimal(str(t["quantity"])).is_finite() or Decimal(str(t["quantity"])) <= 0):
        raise MCFError("unsafe quantity")

def domain_values(d):
    if not isinstance(d, dict) or set(d) - DOMAIN_FIELDS or not {"name", "type", "ordering", "semantic_role", "mechanism_distinct"} <= set(d):
        raise MCFError("invalid domain fields")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", d["name"]):
        raise MCFError("invalid domain name")
    typ = d["type"]
    if typ not in SCHEMA["parameter_domain_types"]:
        raise MCFError("unknown domain type")
    if d["ordering"] != "ASCENDING" or type(d["mechanism_distinct"]) is not bool or not isinstance(d["semantic_role"], str) or not d["semantic_role"]:
        raise MCFError("domain ordering/role")
    if typ in {"ENUM", "FIXED", "BOOLEAN"}:
        if set(d) - ({"name", "type", "ordering", "semantic_role", "mechanism_distinct", "values"}):
            raise MCFError("extra domain bounds")
        vals = d.get("values")
        if not isinstance(vals, list) or not 1 <= len(vals) <= 10000 or (typ == "FIXED" and len(vals) != 1) or (typ == "BOOLEAN" and any(type(v) is not bool for v in vals)):
            raise MCFError("unbounded enum")
        if any(not isinstance(x, (str, int, float, bool)) or (isinstance(x, str) and not _ref(x)) for x in vals):
            raise MCFError("unsafe enum value")
        if vals != sorted(vals, key=lambda x: json.dumps(x, sort_keys=True)) or len({json.dumps(x, sort_keys=True) for x in vals}) != len(vals):
            raise MCFError("noncanonical enum")
        return vals
    if typ == "DERIVED_DETERMINISTIC":
        raise MCFError("derived domain requires a future versioned derivation operator")
    if set(d) != {"name", "type", "ordering", "semantic_role", "mechanism_distinct", "start", "stop", "step"}:
        raise MCFError("missing/extra range bounds")
    a, b, s = (Decimal(str(d[k])) for k in ("start", "stop", "step"))
    if not all(v.is_finite() for v in (a, b, s)) or s <= 0 or b < a or (b-a)/s > 9999:
        raise MCFError("unbounded range")
    if typ == "INTEGER_RANGE" and any(v != int(v) for v in (a,b,s)):
        raise MCFError("noninteger range")
    if typ == "LOG_RANGE":
        raise MCFError("log domain requires a frozen logarithm base/version")
    values = []
    x = a
    while x <= b:
        values.append(int(x) if typ == "INTEGER_RANGE" else format(x, "f"))
        x += s
    return values

def validate(record):
    if not isinstance(record, dict) or set(record) != set(SCHEMA["required_fields"]):
        raise MCFError("exact manifest fields mismatch")
    if record["manifest_schema"] != SCHEMA["schema"] or record["manifest_schema_version"] != SCHEMA["schema_version"]:
        raise MCFError("manifest schema identity mismatch")
    if record["origin_type"] not in SCHEMA["origin_types"] or record["research_only"] is not True:
        raise MCFError("origin or research mode")
    for name in ("family_manifest_id", "family_manifest_version", "alpha_family_id", "economic_mechanism_id", "common_factor_cluster_hint", "tested_object_type", "cost_policy_ref", "evidence_policy_ref"):
        if not _ref(record[name]):
            raise MCFError(f"unsafe {name}")
    if not isinstance(record["source_refs"], list) or not all(_ref(x) for x in record["source_refs"]):
        raise MCFError("unsafe source refs")
    scope = record["market_scope"]
    if not isinstance(scope, dict) or set(scope) != {"assets", "quote_assets", "venues", "timeframes", "spot_only", "directionality", "universe_policy_ref"} or scope["spot_only"] is not True or scope["directionality"] != "LONG_CASH":
        raise MCFError("unsafe market scope")
    for k in ("assets", "quote_assets", "venues", "timeframes"):
        if not isinstance(scope[k], list) or not scope[k] or not all(_ref(x) for x in scope[k]):
            raise MCFError("unsafe market assignment")
    if not _ref(scope["universe_policy_ref"]) or any(x not in ("BTCUSDT", "ETHUSDT") for x in scope["assets"]) or scope["quote_assets"] != ["USDT"] or scope["venues"] != ["BINANCE_SPOT"] or any(x not in ("15m", "1h", "4h", "1d") for x in scope["timeframes"]):
        raise MCFError("unadmitted scope")
    deps = record["data_dependencies"]
    if not isinstance(deps, list) or not deps or len(set(deps)) != len(deps) or not set(deps) <= SUPPORTED_DATA:
        raise MCFError("unsupported data dependency")
    if "MULTI_ASSET" in deps and len(scope["assets"]) != 2:
        raise MCFError("cross-asset dependency not admitted")
    for k in ("signal_template", "entry_template", "exit_template", "sizing_template", "eligibility_template"):
        _template(record[k])
    sizing=record["sizing_template"]
    if not isinstance(sizing,dict) or not set(sizing) <= {"quantity","scale"} or "quantity" not in sizing or ("scale" in sizing and ("SIZING" not in record["tested_object_type"] and "SIZING" not in record["economic_mechanism_id"])):
        raise MCFError("sizing scale requires explicit family authorization")
    for k in ("signal_template","entry_template","exit_template","eligibility_template"):
        if record[k] is not None and "operator" not in record[k]:
            raise MCFError("typed rule operator required")
    if not isinstance(record["parameter_domains"], list) or not record["parameter_domains"] or len(record["parameter_domains"]) > 20:
        raise MCFError("unbounded parameter domains")
    names = [d["name"] for d in record["parameter_domains"]]
    if len(set(names)) != len(names):
        raise MCFError("duplicate domains")
    total = 1
    for d in record["parameter_domains"]:
        total *= len(domain_values(d))
        if total > 1000000:
            raise MCFError("unbounded Cartesian product")
    constraints = record["structural_constraints"]
    if not isinstance(constraints, list) or len(constraints) > 30:
        raise MCFError("invalid constraints")
    for c in constraints:
        if not isinstance(c, dict) or set(c) != {"left", "operator", "right"} or c["operator"] not in ("LT", "LE", "GT", "GE", "EQ", "NE") or c["left"] not in names or (c["right"] not in names and not isinstance(c["right"], (int, float))):
            raise MCFError("invalid structural constraint")
    budget = record["generation_budget"]
    if not isinstance(budget, dict) or set(budget) != {"batch_generation_id", "maximum_raw_candidates", "maximum_valid_economic_trials", "parameter_neighbor_accounting", "hidden_trials_forbidden", "post_outcome_expansion_forbidden", "child_generation_requires_new_batch"} or not _ref(budget["batch_generation_id"]) or any(budget[x] is not True for x in ("hidden_trials_forbidden", "post_outcome_expansion_forbidden", "child_generation_requires_new_batch")) or not all(_positive_int(budget[x]) for x in ("maximum_raw_candidates", "maximum_valid_economic_trials")) or total > budget["maximum_raw_candidates"]:
        raise MCFError("unsafe generation budget")
    safety = record["safety"]
    if not isinstance(safety, dict) or set(safety) != set(SCHEMA["defaults"]) or any(safety[k] != v or type(safety[k]) is not type(v) for k,v in SCHEMA["defaults"].items()):
        raise MCFError("safety mismatch")
    for k in ("screening_policy", "exact_recompute_policy"):
        p = record[k]
        if not isinstance(p, dict) or set(p) != {"policy_ref", "thresholds"} or not _ref(p["policy_ref"]) or not isinstance(p["thresholds"], dict) or any(not _ref(t) or not isinstance(v, (int,float,str)) or not Decimal(str(v)).is_finite() for t,v in p["thresholds"].items()):
            raise MCFError("unbounded policy")
    if not isinstance(record["prohibited_adaptations"], list) or any(not _ref(x) for x in record["prohibited_adaptations"]):
        raise MCFError("unsafe adaptations")
    return digest(record)

def load(path: Path, root: Path):
    target = safe_path(root, str(path))
    if not target.is_file() or target.stat().st_size > 1_000_000:
        raise MCFError("manifest missing/oversized")
    record = json.loads(target.read_text(encoding="utf-8"))
    return record, validate(record)
