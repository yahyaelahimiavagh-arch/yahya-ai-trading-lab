"""Fail-closed local Paper execution contracts for P5."""

from .contracts import (
    EXECUTION_POLICY_ID,
    ExecutionContractError,
    ExecutionDisposition,
    ExecutionReason,
    LocalPaperExecutionDecision,
    LocalPaperExecutionPolicy,
    RecoveryReadiness,
    RecoveryReason,
    RecoveryStatus,
    assess_local_paper_authorization,
)
from .journal import (
    ExecutionIntentJournal,
    ExecutionJournalError,
    IntentConflict,
    LocalPaperIntentRecord,
)
from .state import (
    LocalOrderError,
    LocalOrderEventType,
    LocalOrderReason,
    LocalOrderStatus,
    LocalOrderTransitionError,
    LocalPaperOrderEvent,
    LocalPaperOrderState,
    LocalPaperOrderStore,
    LocalPaperOrderTransition,
    apply_local_order_event,
    build_local_order_event,
)
from .fills import (
    LocalPaperFillCostAdapter,
    LocalPaperFillError,
    LocalPaperFillStep,
)

__all__ = [
    "EXECUTION_POLICY_ID",
    "ExecutionContractError",
    "ExecutionDisposition",
    "ExecutionReason",
    "LocalPaperExecutionDecision",
    "LocalPaperExecutionPolicy",
    "RecoveryReadiness",
    "RecoveryReason",
    "RecoveryStatus",
    "assess_local_paper_authorization",
    "ExecutionIntentJournal",
    "ExecutionJournalError",
    "IntentConflict",
    "LocalPaperIntentRecord",
    "LocalOrderError",
    "LocalOrderEventType",
    "LocalOrderReason",
    "LocalOrderStatus",
    "LocalOrderTransitionError",
    "LocalPaperOrderEvent",
    "LocalPaperOrderState",
    "LocalPaperOrderStore",
    "LocalPaperOrderTransition",
    "apply_local_order_event",
    "build_local_order_event",
    "LocalPaperFillCostAdapter",
    "LocalPaperFillError",
    "LocalPaperFillStep",
]
