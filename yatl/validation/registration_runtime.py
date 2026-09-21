"""Deterministic P10-002 candidate/gate registration runtime."""

import json

from .registration import (
    CandidateFreeze,
    CandidateGateRegistration,
    EconomicGateRegistry,
    candidate_from_record,
    gate_registry_from_record,
    registration_from_record,
)


def main():
    candidate = CandidateFreeze()
    gates = EconomicGateRegistry()
    registration = CandidateGateRegistration(candidate=candidate, gates=gates)

    if (
        candidate_from_record(candidate.as_record()) != candidate
        or gate_registry_from_record(gates.as_record()) != gates
        or registration_from_record(registration.as_record()) != registration
    ):
        raise RuntimeError("P10-002 registration replay diverged")

    output = {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "strategy_version": candidate.strategy_version,
        "configuration_sha256": candidate.configuration_sha256,
        "candidate_sha256": candidate.candidate_sha256,
        "gate_registry_sha256": gates.registry_sha256,
        "registration_sha256": registration.registration_sha256,
        "policy_sha256": registration.p10_001_policy_sha256,
        "selection_basis": candidate.selection_basis,
        "selection_uses_historical_return":
            candidate.selection_uses_historical_return,
        "accepted_p3_evidence": candidate.accepted_p3_evidence,
        "minimum_validation_days": gates.minimum_validation_days,
        "minimum_total_completed_trades":
            gates.minimum_total_completed_trades,
        "minimum_completed_trades_per_symbol":
            gates.minimum_completed_trades_per_symbol,
        "minimum_net_return_after_costs":
            gates.minimum_net_return_after_costs,
        "minimum_profit_factor_after_costs":
            gates.minimum_profit_factor_after_costs,
        "maximum_validation_drawdown_fraction":
            gates.maximum_validation_drawdown_fraction,
        "minimum_positive_segments": gates.minimum_positive_segments,
        "segment_count": gates.segment_count,
        "maximum_segment_loss_fraction":
            gates.maximum_segment_loss_fraction,
        "positive_net_pnl_each_symbol_required":
            gates.positive_net_pnl_each_symbol_required,
        "minimum_distinct_regimes_observed":
            gates.minimum_distinct_regimes_observed,
        "allowed_entry_regimes": list(gates.allowed_entry_regimes),
        "candidate_state": registration.candidate_state.value,
        "gate_state": registration.gate_state.value,
        "window_state": registration.window_state.value,
        "forward_data_state": registration.forward_data_state.value,
        "economic_evaluation_state":
            registration.economic_evaluation_state.value,
        "strategy_evidence": registration.strategy_evidence.value,
        "paper_only": registration.paper_only,
        "live_master_lock": registration.live_master_lock,
        "p11_locked": registration.p11_locked,
        "live_candidate": registration.live_candidate,
        "trade_permission": registration.trade_permission,
        "order_endpoint": registration.order_endpoint,
        "ai_direct_execution": registration.ai_direct_execution,
        "real_forward_data_loaded": False,
        "economic_result_computed": False,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
