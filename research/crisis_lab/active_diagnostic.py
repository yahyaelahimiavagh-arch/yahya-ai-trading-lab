"""CRL-005 strategy-active ordinary-market diagnostic.

Research-only. The scanner evolves the frozen YATL strategy/risk/Paper state
through the continuous Development control corpus, but selection observes only
confirmed entry occurrence and pre-registered timing/exclusion rules. It never
uses later PnL, drawdown, exit quality, recovery, or future price path to select
an episode.

Selected entry states are intended to become immutable source states for the
separate CRL-006 synthetic open-position shock track.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from yatl.backtest import (
    BacktestClock,
    IntentAction,
    PaperFillEngine,
    PaperIntent,
    PortfolioLedger,
    apply_costs,
)
from yatl.data import INTERVAL_MILLISECONDS
from yatl.strategy import (
    StrategyAction,
    StrategyContext,
    TREND_PULLBACK_IDENTITY,
    evaluate_trend_pullback,
)
from yatl.strategy.regime import classify_regime
from yatl.validation.paper_runner import (
    RUNNER_QUANTITY,
    _RiskTracker,
    _fill_record,
    _portfolio_record,
    assess_fixed_quantity_entry,
)
from yatl.validation.registration import CandidateFreeze

from . import acquisition as acq
from . import controls
from . import replay


DIAGNOSTIC_IMPLEMENTATION_ID = "CRL-005-STRATEGY-ACTIVE/0.1.0"
DIAGNOSTIC_SCHEMA_VERSION = "0.1.0"
DEFAULT_EVENT_CATALOG_PATH = Path(
    "docs/research/crisis-lab/EVENT-CATALOG-v0.1.0.json"
)
MAX_EVENT_CATALOG_BYTES = 4 * 1024 * 1024
MAX_DIAGNOSTIC_MANIFEST_BYTES = 4 * 1024 * 1024


class DiagnosticError(RuntimeError):
    """Strategy-active diagnostic violated a frozen research boundary."""


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


def _setup_record(setup) -> dict[str, str]:
    return {
        "reference_price": setup.reference_price,
        "invalidation_price": setup.invalidation_price,
        "target_price": setup.target_price,
    }


def _load_crisis_exclusions(
    *,
    event_catalog_path: Path,
    guard_days: int,
) -> tuple[tuple[int, int, str], ...]:
    if type(guard_days) is not int or guard_days < 0:
        raise DiagnosticError("crisis exclusion guard is invalid")
    try:
        target = acq.assert_safe_runtime_path(event_catalog_path)
    except acq.AcquisitionError as exc:
        raise DiagnosticError(str(exc)) from None
    if target.is_symlink():
        raise DiagnosticError("symlink event catalog is forbidden")
    try:
        payload = target.read_bytes()
    except OSError:
        raise DiagnosticError("cannot read registered event catalog") from None
    if not payload or len(payload) > MAX_EVENT_CATALOG_BYTES:
        raise DiagnosticError("registered event catalog size is invalid")
    try:
        catalog = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DiagnosticError("event catalog is not UTF-8 JSON") from None
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema") != "YATL_CRL_EVENT_CATALOG"
        or catalog.get("catalog_version") != acq.CATALOG_VERSION
        or catalog.get("research_only") is not True
        or catalog.get("p10_untouched") is not True
        or catalog.get("p11_locked") is not True
    ):
        raise DiagnosticError("event catalog invariants are invalid")
    events = catalog.get("events")
    if not isinstance(events, list) or not events:
        raise DiagnosticError("event catalog events are invalid")

    guard_ms = guard_days * 86_400_000
    ranges: list[tuple[int, int, str]] = []
    for event in events:
        if not isinstance(event, dict):
            raise DiagnosticError("event catalog record is invalid")
        event_id = event.get("event_id")
        windows = event.get("windows")
        if not isinstance(event_id, str) or not isinstance(windows, dict):
            raise DiagnosticError("event catalog record is incomplete")
        try:
            pre = windows["pre_event"]
            aftermath = windows["aftermath_recovery"]
            if not isinstance(pre, dict) or not isinstance(aftermath, dict):
                raise DiagnosticError("event window shape is invalid")
            start = acq._iso_to_ms(pre["start_utc"]) - guard_ms
            end = acq._iso_to_ms(aftermath["end_utc"]) + guard_ms
        except (KeyError, TypeError, acq.AcquisitionError):
            raise DiagnosticError(
                "event exclusion timestamp is invalid"
            ) from None
        if start >= end:
            raise DiagnosticError("event exclusion interval is empty")
        ranges.append((start, end, event_id))
    return tuple(sorted(ranges, key=lambda item: (item[0], item[1], item[2])))


def _excluded(
    decision_time_ms: int,
    exclusions: Sequence[tuple[int, int, str]],
) -> bool:
    return any(
        start <= decision_time_ms < end
        for start, end, _ in exclusions
    )


def _pool_event(
    *,
    corpus: controls.AdmittedControlCorpus,
    protocol_sha256: str,
    pool_start_ms: int,
    pool_end_ms: int,
):
    if pool_start_ms >= pool_end_ms:
        raise DiagnosticError("strategy-active pool is empty")
    return replay.AdmittedEvent(
        event_id=corpus.event_id,
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
        replay_window_start_ms=pool_start_ms,
        replay_window_end_ms=pool_end_ms,
        replay_start_ms=pool_start_ms,
        replay_end_ms=pool_end_ms,
        event_anchor_ms=pool_start_ms,
        datasets=corpus.datasets,
    )


def _scan_symbol(
    *,
    event: replay.AdmittedEvent,
    symbol: str,
    exclusions: Sequence[tuple[int, int, str]],
) -> dict[str, object]:
    try:
        dataset, input_sha = replay._dataset_for_symbol(event, symbol)
    except replay.ReplayError as exc:
        raise DiagnosticError(str(exc)) from None
    events = tuple(BacktestClock(dataset).events())
    if not events:
        raise DiagnosticError("strategy-active scan has no legal decisions")
    by_open = {item.open_time_ms: item for item in dataset.primary}
    if len(by_open) != len(dataset.primary):
        raise DiagnosticError("strategy-active primary candles are duplicated")

    fill_engine = PaperFillEngine(symbol)
    ledger = PortfolioLedger(dataset.spec)
    risk_tracker = _RiskTracker(
        symbol, CandidateFreeze().initial_equity_quote
    )
    active_setup = None
    candidates: list[dict[str, object]] = []
    entry_signal_count = 0
    risk_allowed_entry_count = 0
    confirmed_open_entry_count = 0
    excluded_confirmed_open_entry_count = 0

    for decision_event in events:
        fill_candle = by_open.get(
            decision_event.eligible_fill_open_time_ms
        )
        if fill_candle is None or not fill_candle.is_closed:
            raise DiagnosticError(
                "strategy-active next-open candle is missing"
            )
        if any(
            candle.close_time_ms >= decision_event.decision_time_ms
            for series in (
                decision_event.snapshot.primary,
                decision_event.snapshot.context,
                decision_event.snapshot.regime,
            )
            for candle in series
        ):
            raise DiagnosticError(
                "strategy-active decision contains future data"
            )

        pre = ledger.snapshot(
            decision_event.snapshot.latest_primary.close
        )
        risk_state = risk_tracker.observe(
            decision_event.decision_time_ms,
            pre,
            decision_event.snapshot.latest_primary.close,
        )
        context = StrategyContext(
            TREND_PULLBACK_IDENTITY, decision_event.snapshot
        )
        regime = classify_regime(context)
        decision = evaluate_trend_pullback(
            context,
            in_position=fill_engine.has_position,
            active_setup=active_setup,
        )

        veto = None
        if decision.action is StrategyAction.ENTER_LONG:
            entry_signal_count += 1
            veto = assess_fixed_quantity_entry(decision, risk_state)
            if veto.allowed:
                risk_allowed_entry_count += 1
                intent = PaperIntent(
                    IntentAction.ENTER_LONG,
                    decision_event.decision_time_ms,
                    RUNNER_QUANTITY,
                    decision.setup.invalidation_price,
                    decision.setup.target_price,
                )
            else:
                intent = PaperIntent(
                    IntentAction.HOLD,
                    decision_event.decision_time_ms,
                )
        elif decision.action is StrategyAction.EXIT_LONG:
            intent = PaperIntent(
                IntentAction.EXIT_LONG,
                decision_event.decision_time_ms,
            )
        else:
            intent = PaperIntent(
                IntentAction.HOLD,
                decision_event.decision_time_ms,
            )

        references = fill_engine.process(
            decision_event, intent, fill_candle
        )
        costed = tuple(
            apply_costs(item, dataset.spec) for item in references
        )
        if costed:
            ledger.apply_many(costed)

        entry_fill = next(
            (
                item
                for item in costed
                if item.reference.action is IntentAction.ENTER_LONG
            ),
            None,
        )

        if fill_engine.has_position:
            if intent.action is IntentAction.ENTER_LONG:
                active_setup = decision.setup
            elif active_setup is None:
                raise DiagnosticError(
                    "strategy-active Paper position lost setup state"
                )
        else:
            active_setup = None

        if (
            intent.action is IntentAction.ENTER_LONG
            and veto is not None
            and veto.allowed
            and entry_fill is not None
            and fill_engine.has_position
        ):
            confirmed_open_entry_count += 1
            if _excluded(
                decision_event.decision_time_ms, exclusions
            ):
                excluded_confirmed_open_entry_count += 1
            else:
                if decision.setup is None or active_setup is None:
                    raise DiagnosticError(
                        "confirmed entry has no active setup"
                    )
                post = ledger.snapshot(fill_candle.open)
                candidates.append(
                    {
                        "decision_time_ms": (
                            decision_event.decision_time_ms
                        ),
                        "fill_time_ms": (
                            entry_fill.reference.fill_time_ms
                        ),
                        "symbol": symbol,
                        "context_sha256": decision.context_sha256,
                        "regime": regime.regime.value,
                        "strategy_reason": decision.reason.value,
                        "active_setup": _setup_record(active_setup),
                        "risk_state_before_entry": (
                            risk_state.as_record()
                        ),
                        "portfolio_before_entry": (
                            _portfolio_record(pre)
                        ),
                        "portfolio_after_entry": (
                            _portfolio_record(post)
                        ),
                        "entry_fill": _fill_record(entry_fill),
                        "entry_candle": fill_candle.as_record(),
                        "source_state_confirmed_at_ms": (
                            fill_candle.close_time_ms
                        ),
                    }
                )

    return {
        "symbol": symbol,
        "input_dataset_sha256": input_sha,
        "decision_count": len(events),
        "entry_signal_count": entry_signal_count,
        "risk_allowed_entry_count": risk_allowed_entry_count,
        "confirmed_open_entry_count": confirmed_open_entry_count,
        "excluded_confirmed_open_entry_count": (
            excluded_confirmed_open_entry_count
        ),
        "eligible_candidate_count": len(candidates),
        "candidates": candidates,
        "point_in_time_verified": True,
    }


def _select_episodes(
    candidates: Sequence[Mapping[str, object]],
    *,
    maximum_episodes: int,
    minimum_separation_ms: int,
) -> tuple[dict[str, object], ...]:
    if (
        type(maximum_episodes) is not int
        or maximum_episodes < 1
        or type(minimum_separation_ms) is not int
        or minimum_separation_ms < 0
    ):
        raise DiagnosticError("entry selection limits are invalid")

    normalized: list[dict[str, object]] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            raise DiagnosticError("entry candidate is invalid")
        decision_time = item.get("decision_time_ms")
        symbol = item.get("symbol")
        if (
            type(decision_time) is not int
            or symbol not in acq.ALLOWED_SYMBOLS
        ):
            raise DiagnosticError("entry candidate identity is invalid")
        forbidden = {
            "pnl",
            "net_pnl",
            "drawdown",
            "maximum_excursion",
            "exit_quality",
            "recovery",
            "future_price_path",
        }
        if forbidden.intersection(item):
            raise DiagnosticError(
                "entry candidate contains forbidden selection outcome"
            )
        normalized.append(dict(item))

    normalized.sort(
        key=lambda item: (
            item["decision_time_ms"],
            item["symbol"],
        )
    )
    selected: list[dict[str, object]] = []
    last_time: int | None = None
    for item in normalized:
        current = int(item["decision_time_ms"])
        if (
            last_time is not None
            and current - last_time < minimum_separation_ms
        ):
            continue
        selected.append(item)
        last_time = current
        if len(selected) == maximum_episodes:
            break
    return tuple(selected)


def run_strategy_active_diagnostic(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = controls.DEFAULT_PROTOCOL_PATH,
    event_catalog_path: Path = DEFAULT_EVENT_CATALOG_PATH,
) -> dict[str, object]:
    protocol, protocol_sha = controls.load_protocol(protocol_path)
    active = protocol.get("strategy_active_diagnostic")
    development = protocol.get("development_corpus")
    if not isinstance(active, dict) or not isinstance(development, dict):
        raise DiagnosticError("strategy-active protocol is missing")
    if (
        active.get("selection_scope")
        != "BTCUSDT_AND_ETHUSDT_COMBINED"
        or active.get("confirmed_open_position_required") is not True
        or active.get("deterministic_tie_break") is not True
        or active.get("unbiased_performance_evidence") is not False
        or active.get("diagnostic_only") is not True
    ):
        raise DiagnosticError(
            "strategy-active selection semantics are not frozen"
        )
    try:
        pool_start = acq._iso_to_ms(
            development["analysis_pool_start_utc"]
        )
        pool_end = acq._iso_to_ms(
            development["analysis_pool_end_utc"]
        )
        guard_days = int(active["crisis_exclusion_guard_days"])
        maximum = int(active["maximum_episodes"])
        separation = int(active["minimum_separation_ms"])
    except (KeyError, TypeError, ValueError, acq.AcquisitionError):
        raise DiagnosticError(
            "strategy-active protocol values are invalid"
        ) from None

    try:
        corpus = controls._load_control_corpus(
            runtime_root=runtime_root,
            quality_manifest_relative_path=(
                quality_manifest_relative_path
            ),
            quality_manifest_file_sha256=(
                quality_manifest_file_sha256
            ),
        )
    except controls.ControlError as exc:
        raise DiagnosticError(str(exc)) from None

    exclusions = _load_crisis_exclusions(
        event_catalog_path=event_catalog_path,
        guard_days=guard_days,
    )
    try:
        event_catalog_payload = acq.assert_safe_runtime_path(
            event_catalog_path
        ).read_bytes()
    except (OSError, acq.AcquisitionError) as exc:
        raise DiagnosticError(
            "cannot bind strategy-active event catalog"
        ) from exc
    event_catalog_sha = _sha256(event_catalog_payload)

    event = _pool_event(
        corpus=corpus,
        protocol_sha256=protocol_sha,
        pool_start_ms=pool_start,
        pool_end_ms=pool_end,
    )
    scans = [
        _scan_symbol(
            event=event,
            symbol=symbol,
            exclusions=exclusions,
        )
        for symbol in acq.ALLOWED_SYMBOLS
    ]
    all_candidates = [
        item
        for scan in scans
        for item in scan["candidates"]
    ]
    selected = _select_episodes(
        all_candidates,
        maximum_episodes=maximum,
        minimum_separation_ms=separation,
    )

    candidate = CandidateFreeze()
    result: dict[str, object] = {
        "schema": "YATL_CRL_STRATEGY_ACTIVE_DIAGNOSTIC",
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "implementation_id": DIAGNOSTIC_IMPLEMENTATION_ID,
        "cohort_id": active["cohort_id"],
        "source_corpus_id": corpus.event_id,
        "protocol_sha256": protocol_sha,
        "event_catalog_sha256": event_catalog_sha,
        "input_quality_manifest_relative_path": (
            corpus.quality_manifest_relative_path
        ),
        "input_quality_manifest_file_sha256": (
            corpus.quality_manifest_file_sha256
        ),
        "analysis_pool": {
            "start_ms": pool_start,
            "end_exclusive_ms": pool_end,
            "crisis_exclusion_guard_days": guard_days,
        },
        "selection": {
            "selection_scope": active["selection_scope"],
            "entry_definition": active["entry_definition"],
            "ordering": active["ordering"],
            "maximum_episodes": maximum,
            "minimum_separation_ms": separation,
            "selected_count": len(selected),
            "outcome_selected": False,
            "future_path_selected": False,
            "confirmed_open_position_required": True,
        },
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "candidate_sha256": candidate.candidate_sha256,
            "strategy_id": candidate.strategy_id,
            "strategy_version": candidate.strategy_version,
            "configuration_sha256": candidate.configuration_sha256,
            "fixed_research_quantity": RUNNER_QUANTITY,
            "fee_bps": candidate.fee_bps,
            "slippage_bps": candidate.slippage_bps,
        },
        "scan_summary": [
            {
                key: value
                for key, value in scan.items()
                if key != "candidates"
            }
            for scan in scans
        ],
        "selected_episodes": list(selected),
        "forbidden_selection_fields": active[
            "forbidden_selection_fields"
        ],
        "future_outcomes_used_for_selection": False,
        "historical_pnl_used_for_selection": False,
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
    result["result_sha256"] = _sha256(_canonical_json(result))
    return result


def _relative_path(digest: str) -> Path:
    return (
        Path("active-diagnostic")
        / f"control-protocol-v{DIAGNOSTIC_SCHEMA_VERSION}"
        / f"strategy-active-{digest[:24]}.json"
    )


def write_diagnostic(
    *,
    runtime_root: Path,
    result: Mapping[str, object],
) -> dict[str, object]:
    payload = _canonical_json(result)
    if len(payload) > MAX_DIAGNOSTIC_MANIFEST_BYTES:
        raise DiagnosticError(
            "strategy-active diagnostic manifest exceeds bounded size"
        )
    digest = _sha256(payload)
    relative = _relative_path(digest)
    try:
        path = acq._write_immutable(
            runtime_root, relative, payload
        )
    except acq.AcquisitionError as exc:
        raise DiagnosticError(str(exc)) from None
    return {
        "manifest_relative_path": path,
        "manifest_file_sha256": digest,
        "selected_count": result["selection"]["selected_count"],
        "result_sha256": result["result_sha256"],
        "research_only": True,
        "p10_write_allowed": False,
        "p11_locked": True,
    }


def run_and_write(
    *,
    runtime_root: Path,
    quality_manifest_relative_path: str,
    quality_manifest_file_sha256: str,
    protocol_path: Path = controls.DEFAULT_PROTOCOL_PATH,
    event_catalog_path: Path = DEFAULT_EVENT_CATALOG_PATH,
) -> dict[str, object]:
    result = run_strategy_active_diagnostic(
        runtime_root=runtime_root,
        quality_manifest_relative_path=quality_manifest_relative_path,
        quality_manifest_file_sha256=quality_manifest_file_sha256,
        protocol_path=protocol_path,
        event_catalog_path=event_catalog_path,
    )
    return write_diagnostic(
        runtime_root=runtime_root,
        result=result,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m research.crisis_lab.active_diagnostic",
        description=(
            "YATL CRL-005 strategy-active ordinary-market diagnostic"
        ),
    )
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--quality-manifest", required=True)
    parser.add_argument("--quality-manifest-sha256", required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=controls.DEFAULT_PROTOCOL_PATH,
    )
    parser.add_argument(
        "--event-catalog",
        type=Path,
        default=DEFAULT_EVENT_CATALOG_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_and_write(
        runtime_root=args.runtime_root,
        quality_manifest_relative_path=args.quality_manifest,
        quality_manifest_file_sha256=args.quality_manifest_sha256,
        protocol_path=args.protocol,
        event_catalog_path=args.event_catalog,
    )
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as exc:
        print(
            json.dumps(
                {
                    "code": "CRL005_STRATEGY_ACTIVE_ERROR",
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
