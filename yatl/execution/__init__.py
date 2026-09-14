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
]
