"""Lossless-for-adjudication projection of heavy MCF-03 candidate results.

The canonical production simulator returns large per-symbol mark arrays needed
while computing summaries. MCF-04 adjudication does not consume those arrays.
This module validates the full result, drops only preregistered heavy fields,
and re-hashes the projected result so downstream integrity checks remain exact.
"""
from __future__ import annotations

from typing import Mapping

from .models import MCFError, digest

SCHEMA = "MCF_PRODUCTION_RESULT_PROJECTION/1.0.0"
OMITTED_FIELDS = (
    "per_symbol_base",
    "per_symbol_stress",
    "per_symbol_daily_return_series",
)

REQUIRED_ADJUDICATION_FIELDS = (
    "candidate_id",
    "candidate_spec_sha256",
    "family_id",
    "economic_mechanism_id",
    "family_spec_sha256",
    "neighbor_graph_sha256",
    "evidence_partition",
    "f0_f3_state",
    "aggregate_stress_net_return",
    "median_symbol_stress_net_return",
    "fold_stress_returns",
    "maximum_normalized_drawdown",
    "mean_turnover",
    "exact_accounting",
    "daily_return_series",
)


def valid_result(result: Mapping[str, object]) -> bool:
    if not isinstance(result, Mapping) or "result_sha256" not in result:
        return False
    body = {k: v for k, v in result.items() if k != "result_sha256"}
    return result.get("result_sha256") == digest(body)


def project_result(result: Mapping[str, object]) -> dict:
    """Drop only MCF-04-unused heavy arrays after validating the full result."""
    if not valid_result(result):
        raise MCFError("cannot project invalid MCF-03 result")
    missing = [name for name in REQUIRED_ADJUDICATION_FIELDS if name not in result]
    if missing:
        raise MCFError("cannot project incomplete MCF-03 adjudication surface")
    source_sha = str(result["result_sha256"])
    body = {
        k: v
        for k, v in result.items()
        if k != "result_sha256" and k not in OMITTED_FIELDS
    }
    body["projection_schema"] = SCHEMA
    body["source_full_result_sha256"] = source_sha
    body["projection_omitted_fields"] = OMITTED_FIELDS
    projected = {**body, "result_sha256": digest(body)}
    validate_projection(projected)
    return projected


def validate_projection(result: Mapping[str, object]) -> None:
    if not valid_result(result):
        raise MCFError("invalid projected result digest")
    if result.get("projection_schema") != SCHEMA:
        raise MCFError("wrong projected result schema")
    if tuple(result.get("projection_omitted_fields", ())) != OMITTED_FIELDS:
        raise MCFError("projected result omitted-field contract changed")
    if any(name in result for name in OMITTED_FIELDS):
        raise MCFError("projected result retained prohibited heavy field")
    source = result.get("source_full_result_sha256")
    if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
        raise MCFError("projected result missing source full-result identity")
    missing = [name for name in REQUIRED_ADJUDICATION_FIELDS if name not in result]
    if missing:
        raise MCFError("projected result missing adjudication field")
    daily = result.get("daily_return_series")
    if not isinstance(daily, Mapping):
        raise MCFError("projected result missing daily return evidence")
    n = len(daily.get("calendar_days", ()))
    if n < 2 or len(daily.get("returns", ())) != n or len(daily.get("valid_mask", ())) != n:
        raise MCFError("projected daily return evidence length mismatch")


def storage_result(result: Mapping[str, object]) -> dict:
    """Return one validated compact result suitable for durable transfer."""
    if result.get("projection_schema") == SCHEMA:
        validate_projection(result)
        return dict(result)
    return project_result(result)
