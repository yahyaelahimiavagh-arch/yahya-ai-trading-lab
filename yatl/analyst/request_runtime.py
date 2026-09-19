"""Offline deterministic runtime gate for P6-004 request materialization."""

from .contracts import EvidenceLayer, StrategyEvidenceState
from .evidence import build_evidence_bundle, build_layer_evidence
from .request import MODEL_REQUEST_INSTRUCTIONS, build_model_request


DECISION_TIME = 1_790_000_000_000
VALID_THROUGH = DECISION_TIME + 60_000


def _bundle():
    evidence = (
        build_layer_evidence(
            "E_P1_MARKET",
            EvidenceLayer.P1_PUBLIC_MARKET,
            "BTCUSDT",
            DECISION_TIME - 4_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "data_scope": "PUBLIC_SPOT_CLOSED_OHLCV",
                "latest_closed_at_ms": DECISION_TIME - 5_000,
                "manifest_sha256": "a" * 64,
            },
        ),
        build_layer_evidence(
            "E_P3_STRATEGY",
            EvidenceLayer.P3_STRATEGY_EVIDENCE,
            "BTCUSDT",
            DECISION_TIME - 3_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "candidate_matrix_sha256":
                    "59f0af64843baeb2ecf593142e3247be190bb24c8768de80dd971bc677d8e92a",
                "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            },
        ),
        build_layer_evidence(
            "E_P4_RISK",
            EvidenceLayer.P4_RISK_STATUS,
            "BTCUSDT",
            DECISION_TIME - 2_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "audit_sha256":
                    "56c945c38571af294bb44bfd7e788f314d9ee3e9fc76457c6bedb018daae0783",
                "policy_sha256":
                    "cb72fffad317e05638e60ad4a93b96bb78e356b52677330ecd6149095b65e2c7",
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "risk_status": "PASS",
            },
        ),
        build_layer_evidence(
            "E_P5_SAFETY",
            EvidenceLayer.P5_SAFETY_STATUS,
            "BTCUSDT",
            DECISION_TIME - 1_000,
            VALID_THROUGH,
            {
                "accepted": True,
                "ai_direct_execution": False,
                "audit_sha256":
                    "7e90d6d39fde707b1fc1f0504ec96d3d537863c9a1042d757d3437ccc41690fa",
                "credentials_present": False,
                "live_master_lock": "OFF",
                "order_endpoints": False,
                "paper_only": True,
                "policy_sha256":
                    "d3a7edcad7027c215093d6cc0e11d90d194fda8f918c1e27fdbdd4bba5b98b72",
                "private_payload_present": False,
                "safety_status": "PASS",
                "trade_permission": False,
            },
        ),
    )
    return build_evidence_bundle("BTCUSDT", DECISION_TIME, evidence)


def main():
    first = build_model_request(_bundle())
    second = build_model_request(_bundle())
    if (
        first != second
        or first.request_sha256 != second.request_sha256
        or first.material_sha256 != second.material_sha256
        or first.bundle.strategy_evidence
        is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        or first.as_record()["transport"] != "NONE"
        or tuple(first.as_record()["instructions"]) != MODEL_REQUEST_INSTRUCTIONS
    ):
        raise RuntimeError("P6-004 model request boundary failed")

    print(
        "OK: P6 model request boundary; "
        "strategy=INSUFFICIENT_EVIDENCE transport=NONE "
        "untrusted_data_only=true replay_equal=true "
        f"material_bytes={first.as_record()['material_bytes']} "
        f"material_sha256={first.material_sha256} "
        f"request_sha256={first.request_sha256}"
    )
    print(
        "PAPER ONLY | ANALYSIS_ONLY | LIVE_MASTER_LOCK=OFF | "
        "Provider-neutral | No transport | No environment access | "
        "No credentials | No private account payload | No executor import | "
        "No RiskAuthorization mutation | No quantity authority | "
        "No trade permission | No order endpoint | No AI direct execution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
