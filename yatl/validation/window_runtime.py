"""Deterministic P10-003 sealed-window runtime."""

import json

from .window import (
    ACCEPTED_SOURCE_ID,
    FORWARD_WINDOW_START_MS,
    INTERVAL_MILLISECONDS,
    ForwardObservationIdentity,
    ForwardWindowSeal,
    observation_identity_from_record,
    window_from_record,
)


def main():
    window = ForwardWindowSeal()
    replay = window_from_record(window.as_record())
    if replay != window or replay.window_sha256 != window.window_sha256:
        raise RuntimeError("P10-003 window replay diverged")

    first_identity = ForwardObservationIdentity(
        source_id=ACCEPTED_SOURCE_ID,
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=FORWARD_WINDOW_START_MS,
        close_time_ms=(
            FORWARD_WINDOW_START_MS + INTERVAL_MILLISECONDS["1h"] - 1
        ),
        is_closed=True,
        window_sha256=window.window_sha256,
    )
    if observation_identity_from_record(
        first_identity.as_record()
    ) != first_identity:
        raise RuntimeError("P10-003 admission identity replay diverged")

    output = {
        "window_id": window.window_id,
        "window_sha256": window.window_sha256,
        "p10_002_checkpoint": window.p10_002_checkpoint,
        "p10_002_registration_sha256":
            window.p10_002_registration_sha256,
        "candidate_sha256": window.candidate_sha256,
        "gate_registry_sha256": window.gate_registry_sha256,
        "accepted_source_id": window.accepted_source_id,
        "accepted_source_manifest_git_blob_sha1":
            window.accepted_source_manifest_git_blob_sha1,
        "p3_development_evidence_end_ms":
            window.p3_development_evidence_end_ms,
        "accepted_historical_source_end_ms":
            window.accepted_historical_source_end_ms,
        "sealed_at_ms": window.sealed_at_ms,
        "forward_window_start_ms": window.forward_window_start_ms,
        "minimum_evaluation_not_before_ms":
            window.minimum_evaluation_not_before_ms,
        "minimum_validation_days": window.minimum_validation_days,
        "symbols": list(window.symbols),
        "intervals": list(window.intervals),
        "time_basis": window.time_basis,
        "range_semantics": window.range_semantics,
        "window_state": window.window_state.value,
        "forward_collection_state":
            window.forward_collection_state.value,
        "economic_evaluation_state":
            window.economic_evaluation_state.value,
        "strategy_evidence": window.strategy_evidence.value,
        "future_only": window.future_only,
        "reject_pre_window_data": window.reject_pre_window_data,
        "candidate_mutation_allowed": window.candidate_mutation_allowed,
        "gate_mutation_allowed": window.gate_mutation_allowed,
        "source_substitution_allowed": window.source_substitution_allowed,
        "lookahead_allowed": window.lookahead_allowed,
        "forward_data_admission_authorized":
            window.forward_data_admission_authorized,
        "economic_evaluation_allowed":
            window.economic_evaluation_allowed,
        "evaluation_may_extend_for_sample_gate":
            window.evaluation_may_extend_for_sample_gate,
        "paper_only": window.paper_only,
        "live_master_lock": window.live_master_lock,
        "p11_locked": window.p11_locked,
        "live_candidate": window.live_candidate,
        "trade_permission": window.trade_permission,
        "order_endpoint": window.order_endpoint,
        "ai_direct_execution": window.ai_direct_execution,
        "identity_probe_only": True,
        "identity_probe_sha256": first_identity.identity_sha256,
        "real_forward_data_loaded": False,
        "economic_result_computed": False,
        "system_clock_read": False,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
