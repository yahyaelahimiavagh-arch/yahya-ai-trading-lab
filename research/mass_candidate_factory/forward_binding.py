"""Metadata-only prerequisite for candidate-specific forward evidence claims.

Expected lineage must come from independently resolved, current authoritative
artifacts, never from the submitted binding. No evidence loading or execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .models import MCFError, digest

VERSION = "MCF_FORWARD_EVIDENCE_BINDING/1.0.0"
HASH_FIELDS = (
    "candidate_spec_sha256", "freeze_sha256", "evidence_binding_sha256",
    "runner_input_sha256", "forward_registration_sha256", "window_sha256",
    "ingestion_snapshot_sha256", "gate_registry_sha256", "forward_report_sha256",
)
IDENTITY_FIELDS = frozenset(("candidate_id", "runtime_code_sha256", *HASH_FIELDS))


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True)
class ForwardIdentity:
    """Immutable canonical identity, with no mutable provenance members."""

    candidate_id: str
    hashes: tuple[tuple[str, str], ...]
    runtime_code_sha256: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if (not isinstance(self.candidate_id, str) or not self.candidate_id
                or self.candidate_id.strip() != self.candidate_id
                or any(ord(c) < 32 for c in self.candidate_id)):
            raise MCFError("invalid forward candidate identity")
        if type(self.hashes) is not tuple or len(self.hashes) != len(HASH_FIELDS):
            raise MCFError("incomplete forward hashes")
        if any(type(p) is not tuple or len(p) != 2 for p in self.hashes):
            raise MCFError("invalid forward hash pairs")
        if tuple(k for k, _ in self.hashes) != tuple(sorted(HASH_FIELDS)):
            raise MCFError("ambiguous/noncanonical forward hashes")
        if any(not _sha(v) for _, v in self.hashes):
            raise MCFError("invalid forward hash")
        code = self.runtime_code_sha256
        if type(code) is not tuple or not code:
            raise MCFError("missing runtime code identity")
        for pair in code:
            if type(pair) is not tuple or len(pair) != 2:
                raise MCFError("invalid runtime code pair")
            path, sha = pair
            if (not isinstance(path, str) or not path or path.startswith("/")
                    or "\\" in path or any(p in ("", ".", "..") for p in path.split("/"))
                    or any(ord(c) < 32 for c in path) or not _sha(sha)):
                raise MCFError("invalid runtime code identity")
        paths = tuple(p for p, _ in code)
        if paths != tuple(sorted(set(paths))):
            raise MCFError("ambiguous/noncanonical runtime code identity")

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> ForwardIdentity:
        if not isinstance(record, Mapping) or set(record) != IDENTITY_FIELDS:
            raise MCFError("missing/unknown forward identity fields")
        code = record["runtime_code_sha256"]
        if not isinstance(code, Mapping) or any(not isinstance(k, str) for k in code):
            raise MCFError("invalid runtime code map")
        return cls(record["candidate_id"],
                   tuple((k, record[k]) for k in sorted(HASH_FIELDS)),
                   tuple(sorted(code.items())))

    def as_record(self) -> dict:
        return {"candidate_id": self.candidate_id, **dict(self.hashes),
                "runtime_code_sha256": dict(self.runtime_code_sha256)}


def bind_forward_evidence(identity: ForwardIdentity) -> dict:
    """Seal producer-supplied lineage; this never certifies economic validity."""
    if not isinstance(identity, ForwardIdentity):
        raise MCFError("validated forward identity required")
    row = {"schema": VERSION, "identity": identity.as_record()}
    return {**row, "binding_sha256": digest(row)}


@dataclass(frozen=True, slots=True)
class BindingAssessment:
    state: str
    mismatched_fields: tuple[str, ...] = ()

    @property
    def binding_valid(self) -> bool:
        return self.state == "BOUND_MATCH"


def assess_forward_binding(expected: ForwardIdentity, artifact: object) -> BindingAssessment:
    """Fail closed on legacy, malformed, stale or mismatched submitted lineage.

    Staleness is a mismatch to the independently expected current registration,
    window, snapshot, report, policy or code. No inferred baseline or time TTL.
    """
    if not isinstance(expected, ForwardIdentity):
        raise MCFError("independently validated expected identity required")
    if artifact is None:
        return BindingAssessment("MISSING_BINDING")
    if not isinstance(artifact, Mapping):
        return BindingAssessment("INVALID_BINDING")
    if "schema" not in artifact:
        return BindingAssessment("LEGACY_UNBOUND")
    if artifact["schema"] != VERSION:
        return BindingAssessment("UNSUPPORTED_SCHEMA")
    if set(artifact) != {"schema", "identity", "binding_sha256"}:
        return BindingAssessment("INVALID_BINDING")
    try:
        submitted = ForwardIdentity.from_record(artifact["identity"])
    except MCFError:
        return BindingAssessment("INVALID_BINDING")
    if bind_forward_evidence(submitted) != dict(artifact):
        return BindingAssessment("INVALID_BINDING")
    want, got = expected.as_record(), submitted.as_record()
    mismatch = tuple(k for k in sorted(IDENTITY_FIELDS) if want[k] != got[k])
    return BindingAssessment("BINDING_MISMATCH", mismatch) if mismatch else BindingAssessment("BOUND_MATCH")


def require_forward_binding(expected: ForwardIdentity, artifact: object) -> BindingAssessment:
    """Mandatory prerequisite; callers must separately require economic gates."""
    result = assess_forward_binding(expected, artifact)
    if not result.binding_valid:
        raise MCFError(f"candidate-specific forward evidence rejected: {result.state}; "
                       f"fields={','.join(result.mismatched_fields)}")
    return result
