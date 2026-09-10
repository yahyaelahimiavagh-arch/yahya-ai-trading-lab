"""Canonical, atomic and secret-free manifests for deterministic P2 runs."""

import hashlib
import json
from dataclasses import fields
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import uuid4

from yatl.data import Candle

from .config import BacktestSpec
from .costs import DECIMAL_PRECISION, CostedFill
from .fills import IntentAction
from .loader import AcceptedBacktestDataset
from .metrics import PerformanceReport


ARTIFACT_KIND = "YATL_SPOT_PAPER_BACKTEST"
ENGINE_VERSION = "P2.1"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


class ArtifactError(Exception):
    """A run artifact is inconsistent or cannot be published atomically."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _spec(spec):
    if not isinstance(spec, BacktestSpec):
        raise ArtifactError("Artifact requires a valid backtest specification")
    return {
        "symbol": spec.symbol,
        "start_time_ms": spec.start_time_ms,
        "end_time_ms": spec.end_time_ms,
        "initial_cash": spec.initial_cash,
        "fee_bps": spec.fee_bps,
        "slippage_bps": spec.slippage_bps,
        "seed": spec.seed,
        "paper_only": spec.paper_only,
        "live_master_lock": spec.live_master_lock,
        "spot_only": spec.spot_only,
        "allow_short": spec.allow_short,
        "allow_leverage": spec.allow_leverage,
        "execution_price_policy": spec.execution_price_policy,
    }


def _data(dataset):
    if not isinstance(dataset, AcceptedBacktestDataset):
        raise ArtifactError("Artifact requires an accepted dataset")
    if (type(dataset.manifest_generated_at_ms) is not int
            or dataset.manifest_generated_at_ms <= 0):
        raise ArtifactError("Accepted dataset timestamp is invalid")
    result = {
        "source": "BINANCE_SPOT_PUBLIC_CLOSED_OHLCV",
        "symbol": dataset.spec.symbol,
        "manifest_generated_at_ms": dataset.manifest_generated_at_ms,
        "intervals": {},
    }
    for name, candles in (("1h", dataset.primary), ("15m", dataset.context),
                          ("4h", dataset.regime)):
        if (not isinstance(candles, tuple) or not candles
                or any(not isinstance(item, Candle)
                       or item.symbol != dataset.spec.symbol or item.interval != name
                       or not item.is_closed for item in candles)
                or tuple(item.open_time_ms for item in candles)
                != tuple(sorted(item.open_time_ms for item in candles))
                or len({item.open_time_ms for item in candles}) != len(candles)):
            raise ArtifactError("Accepted dataset identity is inconsistent")
        records = [item.as_record() for item in candles]
        result["intervals"][name] = {
            "rows": len(records),
            "first_open_time_ms": candles[0].open_time_ms,
            "last_open_time_ms": candles[-1].open_time_ms,
            "sha256": _digest(records),
        }
    return result


def _fill_input(fill):
    reference = fill.reference
    return {
        "action": reference.action.value,
        "decision_time_ms": reference.decision_time_ms,
        "fill_time_ms": reference.fill_time_ms,
        "quantity": reference.quantity,
        "reference_price": reference.reference_price,
        "reason": reference.reason.value,
    }


def _trades(fills, report):
    if (not isinstance(fills, tuple)
            or any(not isinstance(fill, CostedFill) for fill in fills)):
        raise ArtifactError("Artifact fills must be a tuple of costed fills")
    trades = []
    entry = None
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for fill in fills:
            if fill.reference.symbol != report.points[0].portfolio.symbol:
                raise ArtifactError("Artifact fill symbol is inconsistent")
            if fill.reference.action is IntentAction.ENTER_LONG:
                if entry is not None:
                    raise ArtifactError("Artifact contains overlapping entries")
                entry = fill
                continue
            if (entry is None
                    or entry.reference.quantity != fill.reference.quantity
                    or fill.reference.fill_time_ms < entry.reference.fill_time_ms):
                raise ArtifactError("Artifact trade lifecycle is inconsistent")
            gross_pnl = ((Decimal(fill.reference.reference_price)
                          - Decimal(entry.reference.reference_price))
                         * Decimal(entry.reference.quantity))
            net_pnl = entry.cash_delta + fill.cash_delta
            trades.append({
                "entry_time_ms": entry.reference.fill_time_ms,
                "exit_time_ms": fill.reference.fill_time_ms,
                "quantity": entry.reference.quantity,
                "entry_reference_price": entry.reference.reference_price,
                "entry_execution_price": str(entry.execution_price),
                "exit_reference_price": fill.reference.reference_price,
                "exit_execution_price": str(fill.execution_price),
                "exit_reason": fill.reference.reason.value,
                "gross_pnl_quote": str(gross_pnl),
                "net_pnl_quote": str(net_pnl),
                "fee_quote": str(entry.fee_quote + fill.fee_quote),
                "slippage_quote": str(entry.slippage_quote + fill.slippage_quote),
            })
            entry = None
    if entry is not None or len(trades) != report.trade_count:
        raise ArtifactError("Artifact must contain only completed reported trades")
    if (sum((Decimal(item["gross_pnl_quote"]) for item in trades), Decimal(0))
            != report.gross_pnl_quote
            or sum((Decimal(item["net_pnl_quote"]) for item in trades), Decimal(0))
            != report.net_pnl_quote
            or sum((Decimal(item["fee_quote"]) for item in trades), Decimal(0))
            != report.total_fee_quote
            or sum((Decimal(item["slippage_quote"]) for item in trades), Decimal(0))
            != report.total_slippage_quote):
        raise ArtifactError("Artifact trades do not reconcile with performance metrics")
    return trades


def _metrics(report):
    result = {}
    for item in fields(report):
        if item.name == "points":
            continue
        value = getattr(report, item.name)
        result[item.name] = str(value) if isinstance(value, Decimal) else value
    return result


def build_run_manifest(dataset, fills, report):
    if (not isinstance(report, PerformanceReport)
            or not isinstance(dataset, AcceptedBacktestDataset)
            or not isinstance(fills, tuple)
            or any(not isinstance(fill, CostedFill) for fill in fills)
            or dataset.spec.symbol != report.points[0].portfolio.symbol):
        raise ArtifactError("Artifact inputs are inconsistent")
    if (report.points[0].time_ms < dataset.spec.start_time_ms
            or report.points[-1].time_ms >= dataset.spec.end_time_ms
            or any(not dataset.spec.start_time_ms <= fill.reference.fill_time_ms
                   < dataset.spec.end_time_ms for fill in fills)):
        raise ArtifactError("Artifact lifecycle is outside the configured range")
    config = _spec(dataset.spec)
    data = _data(dataset)
    trades = _trades(fills, report)
    input_material = {
        "configuration": config,
        "data": data,
        "fill_inputs": [_fill_input(fill) for fill in fills],
    }
    equities = [point.portfolio.equity_quote for point in report.points]
    manifest = {
        "schema_version": 1,
        "artifact_kind": ARTIFACT_KIND,
        "engine_version": ENGINE_VERSION,
        "input_sha256": _digest(input_material),
        "configuration": config,
        "data": data,
        "trades": trades,
        "equity_curve": {
            "points": len(report.points),
            "start_time_ms": report.points[0].time_ms,
            "end_time_ms": report.points[-1].time_ms,
            "initial_equity_quote": str(report.initial_equity_quote),
            "final_equity_quote": str(report.final_equity_quote),
            "minimum_equity_quote": str(min(equities)),
            "maximum_equity_quote": str(max(equities)),
        },
        "metrics": _metrics(report),
    }
    return manifest


def artifact_json(manifest):
    expected_keys = {"schema_version", "artifact_kind", "engine_version",
                     "input_sha256", "configuration", "data", "trades",
                     "equity_curve", "metrics"}
    if (not isinstance(manifest, dict) or set(manifest) != expected_keys
            or manifest.get("schema_version") != 1
            or manifest.get("artifact_kind") != ARTIFACT_KIND
            or manifest.get("engine_version") != ENGINE_VERSION):
        raise ArtifactError("Run manifest identity is invalid")
    try:
        encoded = _json(manifest) + "\n"
    except (TypeError, ValueError):
        raise ArtifactError("Run manifest JSON values are invalid") from None
    lowered = encoded.lower()
    forbidden = ('"api_key"', '"api_secret"', '"password"', '"credential"',
                 '"database_path"', '"manifest_path"', "\\\\users\\\\", "/users/")
    if any(item in lowered for item in forbidden):
        raise ArtifactError("Run manifest contains forbidden sensitive material")
    if len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ArtifactError("Run manifest is too large")
    return encoded


def write_run_manifest(manifest, path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise ArtifactError("Run manifest path is required")
    target = Path(path)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(artifact_json(manifest), encoding="utf-8", newline="\n")
        temporary.replace(target)
    except (OSError, ArtifactError):
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ArtifactError("Cannot write the run manifest") from None
    return target
