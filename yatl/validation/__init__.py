"""P10 Forward/Paper validation package."""

from .contracts import (
    P4_MAX_CONSECUTIVE_LOSSES,
    P4_MAX_DRAWDOWN_FRACTION,
    P4_MAX_SESSION_LOSS_FRACTION,
    P4_RISK_PER_TRADE_FRACTION,
    VALIDATION_CRITERIA,
    VALIDATION_POLICY_ID,
    VALIDATION_SCHEMA_VERSION,
    CandidateState,
    EconomicEvaluationState,
    ForwardDataState,
    RegistrationState,
    ThresholdState,
    ValidationCharter,
    ValidationContractError,
    ValidationCriterion,
    ValidationEvidenceState,
    ValidationPolicy,
    WindowState,
    validation_charter_from_record,
    validation_policy_from_record,
)

__all__ = [
    "P4_MAX_CONSECUTIVE_LOSSES",
    "P4_MAX_DRAWDOWN_FRACTION",
    "P4_MAX_SESSION_LOSS_FRACTION",
    "P4_RISK_PER_TRADE_FRACTION",
    "VALIDATION_CRITERIA",
    "VALIDATION_POLICY_ID",
    "VALIDATION_SCHEMA_VERSION",
    "CandidateState",
    "EconomicEvaluationState",
    "ForwardDataState",
    "RegistrationState",
    "ThresholdState",
    "ValidationCharter",
    "ValidationContractError",
    "ValidationCriterion",
    "ValidationEvidenceState",
    "ValidationPolicy",
    "WindowState",
    "validation_charter_from_record",
    "validation_policy_from_record",
]


from .registration import (
    CANDIDATE_ID,
    CANDIDATE_SOURCE_BLOBS,
    GATE_REGISTRY_ID,
    P10_001_POLICY_SHA256,
    REGISTRATION_ID,
    TREND_CONFIGURATION_SHA256,
    CandidateFreeze,
    CandidateFreezeState,
    CandidateGateRegistration,
    EconomicEvaluationState as RegisteredEconomicEvaluationState,
    EconomicGateRegistry,
    ForwardDataState as RegisteredForwardDataState,
    GateRegistrationState,
    RegistrationError,
    SourceBlobIdentity,
    ValidationWindowState,
    candidate_from_record,
    gate_registry_from_record,
    registration_from_record,
)

__all__ += [
    "CANDIDATE_ID",
    "CANDIDATE_SOURCE_BLOBS",
    "GATE_REGISTRY_ID",
    "P10_001_POLICY_SHA256",
    "REGISTRATION_ID",
    "TREND_CONFIGURATION_SHA256",
    "CandidateFreeze",
    "CandidateFreezeState",
    "CandidateGateRegistration",
    "RegisteredEconomicEvaluationState",
    "EconomicGateRegistry",
    "RegisteredForwardDataState",
    "GateRegistrationState",
    "RegistrationError",
    "SourceBlobIdentity",
    "ValidationWindowState",
    "candidate_from_record",
    "gate_registry_from_record",
    "registration_from_record",
]


from .window import (
    ACCEPTED_HISTORICAL_SOURCE_END_MS,
    ACCEPTED_SOURCE_ID,
    ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS,
    ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1,
    ACCEPTED_SOURCE_MANIFEST_PATH,
    FORWARD_WINDOW_START_MS,
    INTERVALS,
    MINIMUM_EVALUATION_NOT_BEFORE_MS,
    MINIMUM_VALIDATION_DAYS,
    P10_002_CHECKPOINT,
    P3_DEVELOPMENT_EVIDENCE_END_MS,
    SEALED_AT_MS,
    ForwardCollectionState,
    ForwardObservationIdentity,
    ForwardWindowSeal,
    WindowEvidenceState,
    WindowSealError,
    WindowSealState,
    EconomicEvaluationState as WindowEconomicEvaluationState,
    observation_identity_from_record,
    window_from_record,
)

__all__ += [
    "ACCEPTED_HISTORICAL_SOURCE_END_MS",
    "ACCEPTED_SOURCE_ID",
    "ACCEPTED_SOURCE_MANIFEST_GENERATED_AT_MS",
    "ACCEPTED_SOURCE_MANIFEST_GIT_BLOB_SHA1",
    "ACCEPTED_SOURCE_MANIFEST_PATH",
    "FORWARD_WINDOW_START_MS",
    "INTERVALS",
    "MINIMUM_EVALUATION_NOT_BEFORE_MS",
    "MINIMUM_VALIDATION_DAYS",
    "P10_002_CHECKPOINT",
    "P3_DEVELOPMENT_EVIDENCE_END_MS",
    "SEALED_AT_MS",
    "ForwardCollectionState",
    "ForwardObservationIdentity",
    "ForwardWindowSeal",
    "WindowEvidenceState",
    "WindowSealError",
    "WindowSealState",
    "WindowEconomicEvaluationState",
    "observation_identity_from_record",
    "window_from_record",
]


from .forward_store import (
    FORWARD_STORE_KIND,
    FORWARD_STORE_SCHEMA_VERSION,
    ForwardCandleStore,
    ForwardStoreError,
)
from .ingestion import (
    FORWARD_DATASET_KIND,
    FORWARD_INGESTION_ID,
    ForwardDatasetEvidence,
    ForwardIngestionError,
    ForwardIngestionSnapshot,
    collect_forward_snapshot,
    snapshot_from_record,
)

__all__ += [
    "FORWARD_STORE_KIND",
    "FORWARD_STORE_SCHEMA_VERSION",
    "ForwardCandleStore",
    "ForwardStoreError",
    "FORWARD_DATASET_KIND",
    "FORWARD_INGESTION_ID",
    "ForwardDatasetEvidence",
    "ForwardIngestionError",
    "ForwardIngestionSnapshot",
    "collect_forward_snapshot",
    "snapshot_from_record",
]


from .paper_runner import (
    FORWARD_PAPER_RUNNER_ID,
    P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1,
    REGIME_WARMUP_BARS,
    RUNNER_QUANTITY,
    EntrySafetyVeto,
    EntryVetoReason,
    ForwardPaperRunResult,
    ForwardPaperRunnerError,
    ForwardPaperSymbolResult,
    ValidationRiskState,
    assess_fixed_quantity_entry,
    run_forward_paper,
)

__all__ += [
    "FORWARD_PAPER_RUNNER_ID",
    "P3_RESEARCH_ADAPTER_GIT_BLOB_SHA1",
    "REGIME_WARMUP_BARS",
    "RUNNER_QUANTITY",
    "EntrySafetyVeto",
    "EntryVetoReason",
    "ForwardPaperRunResult",
    "ForwardPaperRunnerError",
    "ForwardPaperSymbolResult",
    "ValidationRiskState",
    "assess_fixed_quantity_entry",
    "run_forward_paper",
]

from .economics import (
    FORWARD_ECONOMICS_ID,
    ForwardEconomicsError,
    ForwardEconomicsReport,
    calculate_forward_economics,
)

__all__ += [
    "FORWARD_ECONOMICS_ID",
    "ForwardEconomicsError",
    "ForwardEconomicsReport",
    "calculate_forward_economics",
]


from .gate import (
    FORWARD_GATE_ID,
    CriterionStatus,
    ForwardGateError,
    ForwardGateReport,
    GateDisposition,
    evaluate_forward_gate,
)

__all__ += [
    "FORWARD_GATE_ID",
    "CriterionStatus",
    "ForwardGateError",
    "ForwardGateReport",
    "GateDisposition",
    "evaluate_forward_gate",
]


from .cli import (
    VALIDATION_CLI_SCHEMA_VERSION,
    VALIDATION_EXPORT_SCHEMA_VERSION,
    ValidationCliCode,
    ValidationCliError,
    ValidationEvidenceBundle,
    snapshot_json,
    validation_export,
    validation_status,
    validation_summary,
)

__all__ += [
    "VALIDATION_CLI_SCHEMA_VERSION",
    "VALIDATION_EXPORT_SCHEMA_VERSION",
    "ValidationCliCode",
    "ValidationCliError",
    "ValidationEvidenceBundle",
    "snapshot_json",
    "validation_export",
    "validation_status",
    "validation_summary",
]


from .scenarios import (
    ARTIFACT_KIND as VALIDATION_SCENARIO_ARTIFACT_KIND,
    MATRIX_KIND as VALIDATION_SCENARIO_MATRIX_KIND,
    SCENARIOS as VALIDATION_SCENARIOS,
    SYMBOLS as VALIDATION_SCENARIO_SYMBOLS,
    ValidationAcceptedFixture,
    ValidationScenarioError,
    ValidationScenarioMatrixResult,
    ValidationScenarioResult,
    accepted_validation_fixture,
    run_adversarial_validation_matrix,
    scenario_artifact_json,
    validation_matrix_sha256,
    write_adversarial_validation_matrix,
)

__all__ += [
    "VALIDATION_SCENARIO_ARTIFACT_KIND",
    "VALIDATION_SCENARIO_MATRIX_KIND",
    "VALIDATION_SCENARIOS",
    "VALIDATION_SCENARIO_SYMBOLS",
    "ValidationAcceptedFixture",
    "ValidationScenarioError",
    "ValidationScenarioMatrixResult",
    "ValidationScenarioResult",
    "accepted_validation_fixture",
    "run_adversarial_validation_matrix",
    "scenario_artifact_json",
    "validation_matrix_sha256",
    "write_adversarial_validation_matrix",
]
