"""CRL-005 deterministic ordinary-market control replay.

Research-only. This module consumes a CRL-003-admitted continuous Development
corpus, slices only pre-registered ordinary windows, reuses the frozen CRL-004
YATL replay path, and emits matched CASH / BUY-AND-HOLD research baselines.

It has no network, account, credential, order, notification, AI, or P10 write
capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from yatl.data import Candle, INTERVAL_MILLISECONDS
from yatl.validation.paper_runner import RUNNER_QUANTITY
from yatl.validation.registration import CandidateFreeze

from . import acquisition as acq
from . import replay


CONTROL_IMPLEMENTATION_ID = "CRL-005/0.1.1"
CONTROL_SCHEMA_VERSION = "0.1.0"
CONTROL_CORPUS_ID = "CRL-CONTROL-DEV-POOL-001"
DEFAULT_PROTOCOL_PATH = Path(
    "docs/research/crisis-lab/CONTROL-WINDOW-PROTOCOL-v0.1.0.json"
)
MAX_PROTOCOL_BYTES = 2 * 1024 * 1024
MAX_CONTROL_MANIFEST_BYTES = 8 * 1024 * 1024


class ControlError(RuntimeError):
    """CRL-005 control replay failed closed."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (_json(value) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _plain(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ControlError("control arithmetic is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True, slots=True)
class AdmittedControlCorpus:
    event_id: str
    designation: str
    quality_manifest_relative_path: str
    quality_manifest_file_sha256: str
    event_acquisition_manifest_relative_path: str
    event_acquisition_manifest_sha256: str
    retrieved_at_ms: int
    datasets: dict[tuple[str, str], tuple[Candle, ...]]


def load_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
) -> tuple[dict[str, object], str]:
    try:
        target = acq.assert_safe_runtime_path(path)
    except acq.AcquisitionError as exc:
        raise ControlError(str(exc)) from None
    if target.is_symlink():
        raise ControlError("symlink control protocol is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise ControlError("cannot read registered control protocol") from None
    if not payload or len(payload) > MAX_PROTOCOL_BYTES:
        raise ControlError("registered control protocol size is invalid")
    try:
        protocol = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ControlError(
            "registered control protocol is not UTF-8 JSON"
        ) from None
    if not isinstance(protocol, dict):
        raise ControlError("registered control protocol must be an object")
    if (
        protocol.get("schema") != "YATL_CRL_CONTROL_WINDOW_PROTOCOL"
        or protocol.get("version") != CONTROL_SCHEMA_VERSION
        or protocol.get("research_only") is not True
        or protocol.get("p10_untouched") is not True
        or protocol.get("p11_locked") is not True
    ):
        raise ControlError("registered control protocol invariants are invalid")

    development = protocol.get("development_corpus")
    ordinary = protocol.get("unbiased_ordinary_windows")
    baseline_defs = protocol.get("baseline_definitions")
    if (
        not isinstance(development, dict)
        or development.get("corpus_id") != CONTROL_CORPUS_ID
        or not isinstance(ordinary, dict)
        or not isinstance(ordinary.get("windows"), list)
        or not ordinary["windows"]
        or not isinstance(baseline_defs, dict)
    ):
        raise ControlError("control protocol scope is incomplete")
    if set(baseline_defs) != {
        "NO_TRADE_CASH",
        "BUY_AND_HOLD_RESEARCH",
    }:
        raise ControlError("control baseline definitions are incomplete")

    seen: set[str] = set()
    hour = INTERVAL_MILLISECONDS["1h"]
    for item in ordinary["windows"]:
        if not isinstance(item, dict):
            raise ControlError("control window is invalid")
        control_id = item.get("control_id")
        if not isinstance(control_id, str) or control_id in seen:
            raise ControlError("control window identity is invalid")
        seen.add(control_id)
        try:
            acquisition_start = acq._iso_to_ms(
                item["acquisition_start_utc"]
            )
            analysis_start = acq._iso_to_ms(item["analysis_start_utc"])
            analysis_end = acq._iso_to_ms(item["analysis_end_utc"])
        except (KeyError, TypeError, acq.AcquisitionError):
            raise ControlError("control window timestamp is invalid") from None
        if not acquisition_start < analysis_start < analysis_end:
            raise ControlError("control window ordering is invalid")
        if (
            acquisition_start % hour
            or analysis_start % hour
            or analysis_end % hour
        ):
            raise ControlError("control window is not primary-grid aligned")
        warmup = analysis_start - acquisition_start
        if warmup < (
            replay.REGIME_WARMUP_BARS
            * INTERVAL_MILLISECONDS["4h"]
        ):
            raise ControlError("control window lacks frozen regime warmup")

    return protocol, _sha256(payload)


def _load_control_corpus(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
) -> AdmittedControlCorpus:
    try:
        root = replay._safe_root(runtime_root)
        quality_event = replay._read_bound_json(
            root,
            relative=quality_manifest_relative_path,
            sha256=quality_manifest_file_sha256,
            prefix="event-quality-",
            label="control corpus quality manifest",
        )
    except replay.ReplayError as exc:
        raise ControlError(str(exc)) from None
    if (
        quality_event.get("schema")
        != "YATL_CRL_EVENT_QUALITY_MANIFEST"
        or quality_event.get("schema_version")
        != replay.QUALITY_SCHEMA_VERSION
        or quality_event.get("event_id") != CONTROL_CORPUS_ID
        or quality_event.get("designation") != replay.ALLOWED_DESIGNATION
        or quality_event.get("overall_status") != "PASS"
        or quality_event.get("replay_admitted") is not True
        or quality_event.get("replay_eligible") is not True
        or quality_event.get("dataset_count") != 6
        or quality_event.get("pass_count") != 6
        or quality_event.get("fail_count") != 0
        or quality_event.get("market_outcomes_exposed") is not False
        or quality_event.get("research_only") is not True
        or quality_event.get("p10_write_allowed") is not False
        or quality_event.get("p11_locked") is not True
        or quality_event.get("trade_permission") is not False
        or quality_event.get("order_endpoint") is not False
        or quality_event.get("ai_direct_execution") is not False
    ):
        raise ControlError(
            "control corpus is not CRL-003-admitted Development evidence"
        )

    event_acq_rel = quality_event.get(
        "input_event_acquisition_manifest_relative_path"
    )
    event_acq_sha = quality_event.get(
        "input_event_acquisition_manifest_sha256"
    )
    if not isinstance(event_acq_rel, str):
        raise ControlError("control corpus acquisition identity is missing")
    try:
        event_acq_sha = replay._require_sha(
            event_acq_sha, "control corpus acquisition SHA-256"
        )
        event_acq = replay._read_bound_json(
            root,
            relative=event_acq_rel,
            sha256=event_acq_sha,
            prefix="event-acquisition-",
            label="control corpus acquisition manifest",
        )
    except replay.ReplayError as exc:
        raise ControlError(str(exc)) from None
    if (
        event_acq.get("schema")
        != "YATL_CRL_EVENT_ACQUISITION_PROVENANCE"
        or event_acq.get("schema_version") != "0.1.0"
        or event_acq.get("event_id") != CONTROL_CORPUS_ID
        or event_acq.get("designation") != replay.ALLOWED_DESIGNATION
        or event_acq.get("overall_status") != "COMPLETE"
        or event_acq.get("replay_eligible") is not True
        or event_acq.get("research_only") is not True
        or event_acq.get("p10_write_allowed") is not False
        or event_acq.get("p11_locked") is not True
    ):
        raise ControlError("control corpus acquisition provenance is invalid")
    retrieved = event_acq.get("retrieved_at_utc")
    if not isinstance(retrieved, str):
        raise ControlError("control corpus retrieval time is missing")
    try:
        retrieved_at_ms = acq._iso_to_ms(retrieved)
    except acq.AcquisitionError as exc:
        raise ControlError(str(exc)) from None

    refs = quality_event.get("datasets")
    if not isinstance(refs, list) or len(refs) != 6:
        raise ControlError("control corpus dataset scope is incomplete")
    expected_pairs = {
        (symbol, interval)
        for symbol in acq.ALLOWED_SYMBOLS
        for interval in acq.ALLOWED_INTERVALS
    }
    loaded: dict[tuple[str, str], tuple[Candle, ...]] = {}

    for item in refs:
        if not isinstance(item, dict):
            raise ControlError("control dataset quality reference is invalid")
        symbol = item.get("symbol")
        interval = item.get("interval")
        pair = (symbol, interval)
        if pair not in expected_pairs or pair in loaded:
            raise ControlError("control dataset identity set is invalid")
        if (
            item.get("quality_status") != "PASS"
            or item.get("replay_admitted") is not True
            or item.get("failure_codes") != []
        ):
            raise ControlError("control dataset is not quality-admitted")
        qrel = item.get("quality_manifest_relative_path")
        qsha = item.get("quality_manifest_file_sha256")
        if not isinstance(qrel, str):
            raise ControlError("control dataset quality path is missing")
        try:
            qsha = replay._require_sha(
                qsha, "control dataset quality SHA-256"
            )
            dataset_quality = replay._read_bound_json(
                root,
                relative=qrel,
                sha256=qsha,
                prefix="quality-",
                label="control dataset quality manifest",
            )
        except replay.ReplayError as exc:
            raise ControlError(str(exc)) from None
        if (
            dataset_quality.get("schema")
            != "YATL_CRL_DATASET_QUALITY_MANIFEST"
            or dataset_quality.get("schema_version")
            != replay.QUALITY_SCHEMA_VERSION
            or dataset_quality.get("event_id") != CONTROL_CORPUS_ID
            or dataset_quality.get("designation")
            != replay.ALLOWED_DESIGNATION
            or dataset_quality.get("symbol") != symbol
            or dataset_quality.get("interval") != interval
            or dataset_quality.get("quality_status") != "PASS"
            or dataset_quality.get("replay_admitted") is not True
            or dataset_quality.get("failure_codes") != []
            or dataset_quality.get("market_outcomes_exposed") is not False
            or dataset_quality.get("research_only") is not True
            or dataset_quality.get("p10_write_allowed") is not False
            or dataset_quality.get("p11_locked") is not True
        ):
            raise ControlError("control dataset quality provenance is invalid")

        arel = dataset_quality.get(
            "input_acquisition_manifest_relative_path"
        )
        asha = dataset_quality.get(
            "input_acquisition_manifest_sha256"
        )
        if not isinstance(arel, str):
            raise ControlError("control dataset acquisition path is missing")
        try:
            asha = replay._require_sha(
                asha, "control dataset acquisition SHA-256"
            )
            acquisition = replay._read_bound_json(
                root,
                relative=arel,
                sha256=asha,
                prefix="acquisition-",
                label="control dataset acquisition manifest",
            )
        except replay.ReplayError as exc:
            raise ControlError(str(exc)) from None
        if (
            acquisition.get("schema")
            != "YATL_CRL_DATASET_ACQUISITION_PROVENANCE"
            or acquisition.get("schema_version") != "0.1.0"
            or acquisition.get("event_id") != CONTROL_CORPUS_ID
            or acquisition.get("designation")
            != replay.ALLOWED_DESIGNATION
            or acquisition.get("symbol") != symbol
            or acquisition.get("interval") != interval
            or acquisition.get("replay_eligible") is not True
            or acquisition.get("research_only") is not True
            or acquisition.get("p10_write_allowed") is not False
            or acquisition.get("p11_locked") is not True
        ):
            raise ControlError(
                "control dataset acquisition provenance is invalid"
            )
        try:
            loaded[(str(symbol), str(interval))] = (
                replay._load_canonical_candles(
                    root,
                    symbol=str(symbol),
                    interval=str(interval),
                    acquisition=acquisition,
                    quality=dataset_quality,
                )
            )
        except replay.ReplayError as exc:
            raise ControlError(str(exc)) from None

    if set(loaded) != expected_pairs:
        raise ControlError("admitted control corpus scope is incomplete")
    return AdmittedControlCorpus(
        event_id=CONTROL_CORPUS_ID,
        designation=replay.ALLOWED_DESIGNATION,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        event_acquisition_manifest_relative_path=event_acq_rel,
        event_acquisition_manifest_sha256=event_acq_sha,
        retrieved_at_ms=retrieved_at_ms,
        datasets=loaded,
    )


def _window_times(
    window: Mapping[str, object],
) -> tuple[int, int, int]:
    try:
        acquisition_start = acq._iso_to_ms(
            window["acquisition_start_utc"]
        )
        analysis_start = acq._iso_to_ms(window["analysis_start_utc"])
        analysis_end = acq._iso_to_ms(window["analysis_end_utc"])
    except (KeyError, TypeError, acq.AcquisitionError):
        raise ControlError("control window timestamp is invalid") from None
    return acquisition_start, analysis_start, analysis_end


def _slice_window(
    corpus: AdmittedControlCorpus,
    window: Mapping[str, object],
) -> dict[tuple[str, str], tuple[Candle, ...]]:
    acquisition_start, _, analysis_end = _window_times(window)
    sliced: dict[tuple[str, str], tuple[Candle, ...]] = {}
    for symbol in acq.ALLOWED_SYMBOLS:
        for interval in acq.ALLOWED_INTERVALS:
            duration = INTERVAL_MILLISECONDS[interval]
            values = tuple(
                candle
                for candle in corpus.datasets[(symbol, interval)]
                if acquisition_start
                <= candle.open_time_ms
                < analysis_end
            )
            expected = set(
                range(acquisition_start, analysis_end, duration)
            )
            actual = tuple(item.open_time_ms for item in values)
            if (
                not values
                or len(set(actual)) != len(actual)
                or actual != tuple(sorted(actual))
                or not set(actual).issubset(expected)
            ):
                raise ControlError(
                    "admitted control corpus does not cover registered window"
                )
            full = corpus.datasets[(symbol, interval)]
            if (
                acquisition_start < full[0].open_time_ms
                or analysis_end
                > full[-1].open_time_ms + duration
            ):
                raise ControlError(
                    "registered control window exceeds admitted corpus coverage"
                )
            sliced[(symbol, interval)] = values
    return sliced


def _event_for_window(
    *,
    corpus: AdmittedControlCorpus,
    protocol_sha256: str,
    window: Mapping[str, object],
) -> replay.AdmittedEvent:
    _, analysis_start, analysis_end = _window_times(window)
    control_id = window.get("control_id")
    if not isinstance(control_id, str):
        raise ControlError("control window identity is missing")
    return replay.AdmittedEvent(
        event_id=control_id,
        designation=corpus.designation,
        quality_manifest_relative_path=(
            corpus.quality_manifest_relative_path
        ),
        quality_manifest_file_sha256=(
            corpus.quality_manifest_file_sha256
        ),
        event_acquisition_manifest_relative_path=(
            corpus.event_acquisition_manifest_relative_path
        ),
        event_acquisition_manifest_sha256=(
            corpus.event_acquisition_manifest_sha256
        ),
        retrieved_at_ms=corpus.retrieved_at_ms,
        event_catalog_sha256=protocol_sha256,
        replay_window_start_ms=analysis_start,
        replay_window_end_ms=analysis_end,
        replay_start_ms=analysis_start,
        replay_end_ms=analysis_end,
        event_anchor_ms=analysis_start,
        datasets=_slice_window(corpus, window),
    )


def _cash_baseline(initial_equity: Decimal) -> dict[str, object]:
    return {
        "baseline_id": "NO_TRADE_CASH",
        "initial_equity_quote": _plain(initial_equity),
        "final_equity_quote": _plain(initial_equity),
        "net_pnl_after_costs_quote": "0",
        "net_return_after_costs": "0",
        "executed_total_cost_quote": "0",
        "position_quantity": "0",
    }


def _buy_hold_baseline(
    primary: Sequence[Candle],
) -> dict[str, object]:
    if not primary:
        raise ControlError("buy-and-hold baseline has no primary candles")
    candidate = CandidateFreeze()
    initial = Decimal(candidate.initial_equity_quote)
    quantity = Decimal(str(RUNNER_QUANTITY))
    fee_rate = Decimal(str(candidate.fee_bps)) / Decimal("10000")
    slippage_rate = (
        Decimal(str(candidate.slippage_bps)) / Decimal("10000")
    )
    entry_reference = Decimal(primary[0].open)
    exit_reference = Decimal(primary[-1].close)
    entry_execution = entry_reference * (Decimal(1) + slippage_rate)
    exit_execution = exit_reference * (Decimal(1) - slippage_rate)
    entry_notional = quantity * entry_execution
    exit_notional = quantity * exit_execution
    entry_fee = entry_notional * fee_rate
    exit_fee = exit_notional * fee_rate
    debit = entry_notional + entry_fee
    if debit > initial:
        raise ControlError(
            "matched-quantity buy-and-hold exceeds initial equity"
        )
    final = initial - debit + exit_notional - exit_fee
    net = final - initial
    return {
        "baseline_id": "BUY_AND_HOLD_RESEARCH",
        "quantity_policy": "MATCH_FROZEN_YATL_RESEARCH_QUANTITY",
        "quantity": _plain(quantity),
        "entry_policy": "FIRST_ANALYSIS_PRIMARY_OPEN",
        "exit_policy": "LAST_ANALYSIS_PRIMARY_CLOSE_LIQUIDATION",
        "entry_reference_price": _plain(entry_reference),
        "exit_reference_price": _plain(exit_reference),
        "entry_execution_price": _plain(entry_execution),
        "exit_execution_price": _plain(exit_execution),
        "fee_bps_each_side": str(candidate.fee_bps),
        "slippage_bps_each_side": str(candidate.slippage_bps),
        "entry_fee_quote": _plain(entry_fee),
        "exit_fee_quote": _plain(exit_fee),
        "executed_total_cost_quote": _plain(entry_fee + exit_fee),
        "initial_equity_quote": _plain(initial),
        "final_equity_quote": _plain(final),
        "net_pnl_after_costs_quote": _plain(net),
        "net_return_after_costs": _plain(net / initial),
    }


def _analysis_primary(
    event: replay.AdmittedEvent,
    symbol: str,
) -> tuple[Candle, ...]:
    values = tuple(
        item
        for item in event.datasets[(symbol, "1h")]
        if event.replay_start_ms
        <= item.open_time_ms
        < event.replay_end_ms
    )
    expected = set(
        range(
            event.replay_start_ms,
            event.replay_end_ms,
            INTERVAL_MILLISECONDS["1h"],
        )
    )
    actual = tuple(item.open_time_ms for item in values)
    if (
        not values
        or len(set(actual)) != len(actual)
        or actual != tuple(sorted(actual))
        or not set(actual).issubset(expected)
    ):
        raise ControlError("analysis primary window is invalid")
    return values


def _run_window(
    *,
    corpus: AdmittedControlCorpus,
    protocol_sha256: str,
    window: Mapping[str, object],
) -> dict[str, object]:
    event = _event_for_window(
        corpus=corpus,
        protocol_sha256=protocol_sha256,
        window=window,
    )
    candidate = CandidateFreeze()
    symbols: list[dict[str, object]] = []
    for symbol in candidate.symbols:
        try:
            yatl_result = replay._run_symbol(event, symbol)
        except replay.ReplayError as exc:
            raise ControlError(str(exc)) from None
        primary = _analysis_primary(event, symbol)
        symbols.append(
            {
                "symbol": symbol,
                "yatl": yatl_result,
                "baselines": {
                    "NO_TRADE_CASH": _cash_baseline(
                        Decimal(candidate.initial_equity_quote)
                    ),
                    "BUY_AND_HOLD_RESEARCH": _buy_hold_baseline(primary),
                },
            }
        )
    control_id = window.get("control_id")
    acquisition_start, analysis_start, analysis_end = _window_times(window)
    return {
        "schema": "YATL_CRL_ORDINARY_CONTROL_REPLAY",
        "schema_version": CONTROL_SCHEMA_VERSION,
        "implementation_id": CONTROL_IMPLEMENTATION_ID,
        "control_id": control_id,
        "source_corpus_id": corpus.event_id,
        "protocol_sha256": protocol_sha256,
        "input_quality_manifest_relative_path": (
            corpus.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "registered_window": {
            "acquisition_start_ms": acquisition_start,
            "analysis_start_ms": analysis_start,
            "analysis_end_exclusive_ms": analysis_end,
            "warmup_excluded_from_economics": True,
        },
        "selection": {
            "outcome_selected": False,
            "strategy_result_selected": False,
            "must_retain_if_no_trade_or_unfavorable": True,
        },
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "candidate_sha256": candidate.candidate_sha256,
            "fixed_research_quantity": RUNNER_QUANTITY,
            "fee_bps": candidate.fee_bps,
            "slippage_bps": candidate.slippage_bps,
        },
        "symbols": symbols,
        "deterministic_replay_verified": True,
        "point_in_time_verified": True,
        "future_data_visible_to_strategy": False,
        "market_outcomes_exposed": True,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }


def _window_relative_path(control_id: str, digest: str) -> Path:
    return (
        Path("control-replay")
        / f"control-protocol-v{CONTROL_SCHEMA_VERSION}"
        / control_id
        / f"control-replay-{digest[:24]}.json"
    )


def _write_window(
    runtime_root: Path,
    record: Mapping[str, object],
) -> dict[str, object]:
    payload = _canonical_json(record)
    if len(payload) > MAX_CONTROL_MANIFEST_BYTES:
        raise ControlError("control replay manifest exceeds bounded size")
    digest = _sha256(payload)
    control_id = record.get("control_id")
    if not isinstance(control_id, str):
        raise ControlError("control replay identity is missing")
    relative = _window_relative_path(control_id, digest)
    try:
        path = acq._write_immutable(runtime_root, relative, payload)
    except acq.AcquisitionError as exc:
        raise ControlError(str(exc)) from None
    return {
        "control_id": control_id,
        "manifest_relative_path": path,
        "manifest_file_sha256": digest,
        "symbols": [
            {
                "symbol": item["symbol"],
                "yatl_net_return_after_costs": item["yatl"][
                    "economics"
                ]["net_return_after_costs"],
                "yatl_maximum_drawdown_fraction": item["yatl"][
                    "economics"
                ]["sampled_liquidation_drawdown"][
                    "maximum_drawdown_fraction"
                ],
                "yatl_completed_trades": item["yatl"]["economics"][
                    "completed_trades"
                ],
                "cash_net_return_after_costs": item["baselines"][
                    "NO_TRADE_CASH"
                ]["net_return_after_costs"],
                "buy_hold_net_return_after_costs": item["baselines"][
                    "BUY_AND_HOLD_RESEARCH"
                ]["net_return_after_costs"],
            }
            for item in record["symbols"]
        ],
    }


def replay_control_windows(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = DEFAULT_PROTOCOL_PATH,
    control_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    protocol, protocol_sha = load_protocol(protocol_path)
    corpus = _load_control_corpus(
        runtime_root=runtime_root,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
    )
    ordinary = protocol["unbiased_ordinary_windows"]
    windows = ordinary["windows"]
    available = {
        item["control_id"]: item
        for item in windows
    }
    if control_ids is None:
        selected = [item["control_id"] for item in windows]
    else:
        selected = list(control_ids)
        if not selected or len(selected) != len(set(selected)):
            raise ControlError("requested control identity list is invalid")
        unknown = [item for item in selected if item not in available]
        if unknown:
            raise ControlError("requested control window is not registered")

    reports = []
    for control_id in selected:
        record = _run_window(
            corpus=corpus,
            protocol_sha256=protocol_sha,
            window=available[control_id],
        )
        reports.append(_write_window(runtime_root, record))

    aggregate = {
        "schema": "YATL_CRL_ORDINARY_CONTROL_REPLAY_INDEX",
        "schema_version": CONTROL_SCHEMA_VERSION,
        "implementation_id": CONTROL_IMPLEMENTATION_ID,
        "source_corpus_id": corpus.event_id,
        "protocol_sha256": protocol_sha,
        "quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "control_count": len(reports),
        "controls": reports,
        "market_outcomes_exposed": True,
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "p11_locked": True,
    }
    aggregate["result_sha256"] = _sha256(_canonical_json(aggregate))
    return aggregate


def safe_summary(result: Mapping[str, object]) -> dict[str, object]:
    return {
        "source_corpus_id": result["source_corpus_id"],
        "protocol_sha256": result["protocol_sha256"],
        "control_count": result["control_count"],
        "controls": result["controls"],
        "result_sha256": result["result_sha256"],
        "research_only": True,
        "p10_read": False,
        "p10_write_allowed": False,
        "p10_evidence_effect": "NONE",
        "p11_locked": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab.controls",
        description=(
            "YATL CRL-005 deterministic ordinary-market control replay"
        ),
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument(
        "--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH
    )
    parser.add_argument(
        "--control",
        action="append",
        dest="controls",
        default=None,
        help="registered control id; repeat to run a subset",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = replay_control_windows(
        runtime_root=args.runtime_root,
        quality_manifest_relative_path=args.quality_manifest,
        quality_manifest_file_sha256=args.quality_manifest_sha256,
        protocol_path=args.protocol,
        control_ids=args.controls,
    )
    print(
        json.dumps(
            safe_summary(result),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ControlError as exc:
        print(
            json.dumps(
                {
                    "code": "CRL005_CONTROL_REPLAY_ERROR",
                    "reason": str(exc),
                    "research_only": True,
                    "p10_write_allowed": False,
                    "p11_locked": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise SystemExit(2)
