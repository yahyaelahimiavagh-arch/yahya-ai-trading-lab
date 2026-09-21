"""Deterministic runtime gate for P10-001 preregistration contracts."""

import json

from .contracts import (
    ValidationCharter,
    ValidationPolicy,
    validation_charter_from_record,
    validation_policy_from_record,
)


REGISTERED_AT_MS = 1_800_000_000_000


def main():
    policy = ValidationPolicy()
    charter = ValidationCharter(
        "P10-REG-BASELINE-001",
        REGISTERED_AT_MS,
        policy,
    )

    restored_policy = validation_policy_from_record(policy.as_record())
    restored_charter = validation_charter_from_record(charter.as_record())

    if (
        restored_policy != policy
        or restored_charter != charter
        or restored_policy.policy_sha256 != policy.policy_sha256
        or restored_charter.charter_sha256 != charter.charter_sha256
    ):
        raise RuntimeError("P10-001 preregistration replay diverged")

    output = {
        "policy_id": policy.policy_id,
        "policy_sha256": policy.policy_sha256,
        "charter_sha256": charter.charter_sha256,
        "criteria": [item.value for item in policy.criteria],
        "criteria_count": len(policy.criteria),
        "mode": policy.mode,
        "forward_only": policy.forward_only,
        "new_data_only": policy.new_data_only,
        "paper_only": policy.paper_only,
        "live_master_lock": policy.live_master_lock,
        "net_pnl_after_fee_slippage_required":
            policy.net_pnl_after_fee_slippage_required,
        "risk_adjusted_persistence_required":
            policy.risk_adjusted_persistence_required,
        "thresholds_registered": policy.thresholds_registered,
        "candidate_frozen": policy.candidate_frozen,
        "validation_window_open": policy.validation_window_open,
        "forward_data_collection_allowed":
            policy.forward_data_collection_allowed,
        "economic_evaluation_allowed": policy.economic_evaluation_allowed,
        "strategy_evidence": charter.strategy_evidence.value,
        "candidate_state": charter.candidate_state.value,
        "threshold_state": charter.threshold_state.value,
        "window_state": charter.window_state.value,
        "forward_data_state": charter.forward_data_state.value,
        "economic_evaluation_state": charter.economic_evaluation_state.value,
        "inherited_risk_per_trade_fraction":
            policy.inherited_risk_per_trade_fraction,
        "inherited_max_session_loss_fraction":
            policy.inherited_max_session_loss_fraction,
        "inherited_max_drawdown_fraction":
            policy.inherited_max_drawdown_fraction,
        "inherited_max_consecutive_losses":
            policy.inherited_max_consecutive_losses,
        "trade_permission": policy.allow_trade_permission,
        "order_endpoint": policy.allow_order_endpoint,
        "ai_direct_execution": policy.allow_ai_direct_execution,
        "live_candidate": policy.allow_live_candidate,
        "real_forward_data_loaded": False,
        "economic_result_computed": False,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
