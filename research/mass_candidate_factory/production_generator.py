"""MCF-PROD-001 pre-outcome candidate compiler.

The compiler reads only frozen governance/domain JSON.  It never reads market
performance.  Candidate identity, structural filtering, family concentration
and the one-step parameter-neighbor graph are frozen before Development.
"""
from __future__ import annotations

import ast
import hashlib
import itertools
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

from .models import MCFError, digest

VERSION = "MCF_PRODUCTION_GENERATOR/1.0.0"
ROOT = Path(__file__).resolve().parents[2]
DOMAIN_PLAN_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-FAMILY-DOMAIN-PLAN-v1.0.json"
SEARCH_BUDGET_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-SEARCH-BUDGET-v1.0.json"
UNIVERSE_POLICY_PATH = ROOT / "docs/research/alpha-factory/MCF-PROD-001-UNIVERSE-EVIDENCE-POLICY-v1.0.json"


def _load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


DOMAIN_PLAN, DOMAIN_PLAN_SHA256 = _load(DOMAIN_PLAN_PATH)
SEARCH_BUDGET, SEARCH_BUDGET_SHA256 = _load(SEARCH_BUDGET_PATH)
UNIVERSE_POLICY, UNIVERSE_POLICY_SHA256 = _load(UNIVERSE_POLICY_PATH)


def _number(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return value
    return value


def _eval_node(node: ast.AST, values: Mapping[str, object]):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, values)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise MCFError("constraint references unknown parameter")
        return _number(values[node.id])
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str)):
            raise MCFError("unsupported constraint constant")
        return _number(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left, right = _eval_node(node.left, values), _eval_node(node.right, values)
        if not isinstance(left, Decimal) or not isinstance(right, Decimal):
            raise MCFError("nonnumeric structural arithmetic")
        return left + right if isinstance(node.op, ast.Add) else left - right
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, right = _eval_node(node.left, values), _eval_node(node.comparators[0], values)
        op = node.ops[0]
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
    raise MCFError("unsupported structural constraint syntax")


def structural_pass(expression: str, values: Mapping[str, object]) -> bool:
    if not isinstance(expression, str) or not expression or len(expression) > 200:
        raise MCFError("invalid structural constraint")
    tree = ast.parse(expression, mode="eval")
    allowed = (
        ast.Expression, ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.Add,
        ast.Sub, ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    )
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise MCFError("unsafe structural constraint")
    result = _eval_node(tree, values)
    if type(result) is not bool:
        raise MCFError("constraint did not produce boolean")
    return result


def validate_frozen_inputs() -> None:
    if DOMAIN_PLAN.get("schema") != "YATL_MCF_PRODUCTION_FAMILY_DOMAIN_PLAN":
        raise MCFError("wrong production domain plan")
    if DOMAIN_PLAN.get("generation_id") != "MCF-PROD-001" or DOMAIN_PLAN.get("state") != "FROZEN_BEFORE_PERFORMANCE":
        raise MCFError("production domain plan is not frozen")
    if SEARCH_BUDGET.get("generation_id") != "MCF-PROD-001" or SEARCH_BUDGET.get("state") != "FROZEN_BEFORE_STRATEGY_OUTCOME":
        raise MCFError("production search budget is not frozen")
    if UNIVERSE_POLICY.get("policy_id") != "MCF-PROD-001-UNIVERSE-EVIDENCE":
        raise MCFError("wrong production universe policy")
    if UNIVERSE_POLICY["evidence"] != {
        "partition": "DEVELOPMENT",
        "population_start_utc": "2020-01-01T00:00:00Z",
        "scored_search_start_utc": "2020-03-01T00:00:00Z",
        "development_end_exclusive_utc": "2023-01-01T00:00:00Z",
        "fresh_oos_read_allowed": False,
        "recent_reserve_read_allowed": False,
        "p10_read_allowed": False,
        "p10_write_allowed": False,
    }:
        raise MCFError("production evidence boundary changed")
    safety = DOMAIN_PLAN.get("safety", {})
    required_false = ("fresh_oos_read", "recent_reserve_read", "p10_read", "p10_write")
    if safety.get("paper_research_only") is not True or any(safety.get(k) is not False for k in required_false):
        raise MCFError("production safety boundary changed")
    families = DOMAIN_PLAN.get("families")
    if not isinstance(families, list) or len({f["family"] for f in families}) != len(families):
        raise MCFError("invalid production family catalog")
    if set(f["family"] for f in families) != set(SEARCH_BUDGET["allowed_initial_families"]):
        raise MCFError("domain/search-budget family mismatch")


def _candidate_identity(family: Mapping[str, object], timeframe: str,
                        vector: Mapping[str, object]) -> dict:
    return {
        "generator_version": VERSION,
        "generation_id": "MCF-PROD-001",
        "family_id": family["id"],
        "family": family["family"],
        "timeframe": timeframe,
        "parameter_vector": dict(vector),
        "domain_plan_sha256": DOMAIN_PLAN_SHA256,
        "search_budget_sha256": SEARCH_BUDGET_SHA256,
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "cost_policy_ref": "MCF-SPOT-COST/v1",
        "evidence_partition": "DEVELOPMENT",
        "tested_object_type": "PER_SYMBOL_RULE_ACROSS_DYNAMIC_UNIVERSE",
    }


def generate() -> dict:
    """Enumerate the complete frozen Cartesian domain without performance."""
    validate_frozen_inputs()
    raw = []
    valid = []
    invalid = []
    family_counts: dict[str, int] = {}
    ordinal = 0

    for family in DOMAIN_PLAN["families"]:
        domains = family["domains"]
        names = list(domains)
        if not names or any(not isinstance(domains[name], list) or not domains[name] for name in names):
            raise MCFError("empty production parameter domain")
        expected_raw = len(family["timeframes"])
        for name in names:
            expected_raw *= len(domains[name])
        if expected_raw != family["raw_max"]:
            raise MCFError("family raw domain arithmetic mismatch")

        for timeframe in family["timeframes"]:
            for values in itertools.product(*(domains[name] for name in names)):
                vector = dict(zip(names, values))
                identity = _candidate_identity(family, timeframe, vector)
                row = {
                    "ordinal": ordinal,
                    "candidate_id": f"MCF-PROD-001-{ordinal:06d}",
                    "candidate_spec_sha256": digest(identity),
                    "family_id": family["id"],
                    "family": family["family"],
                    "economic_mechanism_id": family["family"],
                    "timeframe": timeframe,
                    "parameter_vector": vector,
                    "free_parameter_dimensions": len(names),
                    "domain_plan_sha256": DOMAIN_PLAN_SHA256,
                    "search_budget_sha256": SEARCH_BUDGET_SHA256,
                    "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
                }
                reasons = [
                    expression for expression in family.get("constraints", [])
                    if not structural_pass(expression, vector)
                ]
                if reasons:
                    item = {**row, "state": "STRUCTURALLY_INVALID", "failure_reasons": tuple(reasons)}
                    invalid.append(item)
                else:
                    item = {**row, "state": "PRE_OUTCOME_REGISTERED", "failure_reasons": ()}
                    valid.append(item)
                    family_counts[family["family"]] = family_counts.get(family["family"], 0) + 1
                raw.append(item)
                ordinal += 1

    if len(raw) != DOMAIN_PLAN["raw_cartesian_upper_bound"]:
        raise MCFError("raw production count mismatch")
    if len(valid) != DOMAIN_PLAN["expected_structurally_valid_count"]:
        raise MCFError("structural production count mismatch")
    if len(valid) != SEARCH_BUDGET["expected_preperformance_structurally_valid_count"]:
        raise MCFError("search-budget expected count mismatch")
    if len(raw) > SEARCH_BUDGET["hard_maximum_raw_candidates"]:
        raise MCFError("production hard candidate cap exceeded")

    target_low, target_high = SEARCH_BUDGET["target_raw_candidate_range"]
    if not target_low <= len(raw) <= target_high:
        raise MCFError("raw production count outside frozen target range")
    if len(family_counts) < SEARCH_BUDGET["minimum_executable_mechanism_families"]:
        raise MCFError("insufficient production family breadth")

    total_valid = len(valid)
    max_family_fraction = Decimal(max(family_counts.values())) / Decimal(total_valid)
    if max_family_fraction > Decimal(SEARCH_BUDGET["maximum_single_family_fraction"]):
        raise MCFError("single-family concentration cap exceeded")
    trend_breakout = family_counts.get("TREND_CROSSOVER", 0) + family_counts.get("BREAKOUT_CHANNEL", 0)
    trend_breakout_fraction = Decimal(trend_breakout) / Decimal(total_valid)
    if trend_breakout_fraction > Decimal(SEARCH_BUDGET["maximum_combined_trend_breakout_fraction"]):
        raise MCFError("combined trend/breakout concentration cap exceeded")

    registered = tuple(
        (row["candidate_id"], row["candidate_spec_sha256"])
        for row in valid
    )
    family_count_rows = tuple(sorted(family_counts.items()))
    summary = {
        "schema": VERSION,
        "generation_id": "MCF-PROD-001",
        "domain_plan_sha256": DOMAIN_PLAN_SHA256,
        "search_budget_sha256": SEARCH_BUDGET_SHA256,
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "raw_candidate_count": len(raw),
        "structurally_valid_count": len(valid),
        "structurally_invalid_count": len(invalid),
        "family_valid_counts": family_count_rows,
        "maximum_single_family_fraction": str(max_family_fraction),
        "combined_trend_breakout_fraction": str(trend_breakout_fraction),
        "registered_candidate_ledger_sha256": digest([
            {"candidate_id": cid, "candidate_spec_sha256": spec}
            for cid, spec in registered
        ]),
        "state": "PRE_OUTCOME_GENERATION_FROZEN",
        "safety": {
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
        },
    }
    return {
        "summary": {**summary, "summary_sha256": digest(summary)},
        "valid": tuple(valid),
        "invalid": tuple(invalid),
        "registered_candidates": registered,
    }


def build_neighbor_graph(valid_candidates: Sequence[Mapping[str, object]]) -> dict:
    """One-step parameter neighbors within the same family and timeframe."""
    if not valid_candidates:
        raise MCFError("empty production candidate set")
    family_plan = {f["family"]: f for f in DOMAIN_PLAN["families"]}
    graph: dict[str, set[str]] = {str(row["candidate_id"]): set() for row in valid_candidates}

    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in valid_candidates:
        grouped.setdefault((str(row["family"]), str(row["timeframe"])), []).append(row)

    for (family_name, _timeframe), rows in grouped.items():
        family = family_plan.get(family_name)
        if family is None:
            raise MCFError("candidate has unknown production family")
        domains = family["domains"]
        names = list(domains)

        def key(vector: Mapping[str, object]) -> tuple[str, ...]:
            return tuple(json.dumps(vector[name], sort_keys=True, separators=(",", ":")) for name in names)

        index = {key(row["parameter_vector"]): str(row["candidate_id"]) for row in rows}
        if len(index) != len(rows):
            raise MCFError("duplicate production parameter vector")

        for row in rows:
            cid = str(row["candidate_id"])
            vector = dict(row["parameter_vector"])
            for name in names:
                domain = domains[name]
                try:
                    position = domain.index(vector[name])
                except ValueError as exc:
                    raise MCFError("candidate outside frozen production domain") from exc
                for step in (-1, 1):
                    q = position + step
                    if 0 <= q < len(domain):
                        other = dict(vector)
                        other[name] = domain[q]
                        neighbor = index.get(key(other))
                        if neighbor is not None:
                            graph[cid].add(neighbor)

    canonical = {cid: tuple(sorted(neighbors)) for cid, neighbors in sorted(graph.items())}
    row = {"schema": "MCF_PRODUCTION_NEIGHBOR_GRAPH/1.0.0", "graph": canonical}
    return {**row, "neighbor_graph_sha256": digest(row)}


def freeze_executable_generation(blocked_families: Mapping[str, str]) -> dict:
    """Freeze exact executable identities after pre-performance blockers.

    The blocked-family mapping is an implementation audit result, never a
    performance result. Blocked trials remain recorded and are not transferred
    to another family or parameter grid.
    """
    generated = generate()
    known = {str(f["family"]) for f in DOMAIN_PLAN["families"]}
    if not isinstance(blocked_families, Mapping):
        raise MCFError("blocked-family audit must be a mapping")
    if set(blocked_families) - known:
        raise MCFError("unknown blocked production family")
    if any(not isinstance(reason, str) or not reason.strip() for reason in blocked_families.values()):
        raise MCFError("blocked production family requires reason")

    executable = tuple(
        row for row in generated["valid"]
        if row["family"] not in blocked_families
    )
    blocked = tuple(
        {
            **row,
            "state": "BLOCKED_IMPLEMENTATION",
            "failure_reasons": ("BLOCKED_IMPLEMENTATION",),
            "implementation_blocker": blocked_families[row["family"]],
        }
        for row in generated["valid"]
        if row["family"] in blocked_families
    )
    if not executable:
        raise MCFError("no executable production candidates after implementation audit")

    counts: dict[str, int] = {}
    for row in executable:
        counts[str(row["family"])] = counts.get(str(row["family"]), 0) + 1
    if len(counts) < SEARCH_BUDGET["minimum_executable_mechanism_families"]:
        raise MCFError("implementation blockers reduce mechanism breadth below minimum")

    total = len(executable)
    max_fraction = Decimal(max(counts.values())) / Decimal(total)
    trend = counts.get("TREND_CROSSOVER", 0) + counts.get("BREAKOUT_CHANNEL", 0)
    trend_fraction = Decimal(trend) / Decimal(total)
    if max_fraction > Decimal(SEARCH_BUDGET["maximum_single_family_fraction"]):
        raise MCFError("post-blocker single-family concentration cap exceeded")
    if trend_fraction > Decimal(SEARCH_BUDGET["maximum_combined_trend_breakout_fraction"]):
        raise MCFError("post-blocker trend/breakout concentration cap exceeded")

    neighbor = build_neighbor_graph(executable)
    registered = tuple(
        (str(row["candidate_id"]), str(row["candidate_spec_sha256"]))
        for row in executable
    )
    family_specs = {
        str(f["family"]): digest(f)
        for f in DOMAIN_PLAN["families"]
        if f["family"] in counts
    }
    ledger_payload = [
        {"candidate_id": cid, "candidate_spec_sha256": spec}
        for cid, spec in registered
    ]
    summary = {
        "schema": "MCF_PRODUCTION_EXECUTABLE_FREEZE/1.0.0",
        "generation_id": "MCF-PROD-001",
        "domain_plan_sha256": DOMAIN_PLAN_SHA256,
        "search_budget_sha256": SEARCH_BUDGET_SHA256,
        "universe_policy_sha256": UNIVERSE_POLICY_SHA256,
        "pre_block_structurally_valid_count": len(generated["valid"]),
        "blocked_implementation_count": len(blocked),
        "executable_candidate_count": len(executable),
        "blocked_families": tuple(sorted((str(k), str(v)) for k, v in blocked_families.items())),
        "executable_family_counts": tuple(sorted(counts.items())),
        "candidate_ledger_sha256": digest(ledger_payload),
        "neighbor_graph_sha256": neighbor["neighbor_graph_sha256"],
        "family_spec_sha256s": tuple(sorted(family_specs.values())),
        "family_spec_sha256_by_family": tuple(sorted(family_specs.items())),
        "maximum_single_family_fraction": str(max_fraction),
        "combined_trend_breakout_fraction": str(trend_fraction),
        "state": "PRE_OUTCOME_EXECUTABLE_SET_FROZEN",
        "safety": {
            "performance_read": False,
            "fresh_oos_read": False,
            "recent_reserve_read": False,
            "p10_read": False,
            "p10_write": False,
            "live": False,
        },
    }
    return {
        "summary": {**summary, "freeze_sha256": digest(summary)},
        "executable": executable,
        "blocked": blocked,
        "registered_candidates": registered,
        "neighbor_graph": neighbor,
    }
