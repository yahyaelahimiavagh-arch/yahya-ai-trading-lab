"""Transactional, idempotent journal for accepted local Paper intents."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    EXECUTION_POLICY_ID,
    ExecutionContractError,
    ExecutionDisposition,
    LocalPaperExecutionDecision,
)


JOURNAL_SCHEMA_VERSION = 1
INTENT_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
INTENT_COLUMNS = (
    "authorization_sha256",
    "effect_sha256",
    "decision_sha256",
    "readiness_sha256",
    "action",
    "approved_quantity",
    "policy_id",
    "intent_sha256",
)


class ExecutionJournalError(Exception):
    """Journal operation failed without exposing paths or SQL details."""


class IntentConflict(ExecutionJournalError):
    """An authorization identity is already bound to different intent data."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class LocalPaperIntentRecord:
    """Canonical durable identity for one accepted local Paper effect."""

    authorization_sha256: str
    effect_sha256: str
    decision_sha256: str
    readiness_sha256: str
    action: str
    approved_quantity: str
    policy_id: str
    intent_sha256: str

    def __post_init__(self):
        digests = (
            self.authorization_sha256,
            self.effect_sha256,
            self.decision_sha256,
            self.readiness_sha256,
            self.intent_sha256,
        )
        if any(
            not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None
            for value in digests
        ):
            raise ExecutionJournalError("Stored intent digest is invalid")
        if self.effect_sha256 != self.authorization_sha256:
            raise ExecutionJournalError(
                "Local Paper effect identity differs from its authorization"
            )
        if (
            self.action not in ("ENTER_LONG", "EXIT_LONG")
            or not isinstance(self.approved_quantity, str)
            or not self.approved_quantity
            or self.policy_id != EXECUTION_POLICY_ID
        ):
            raise ExecutionJournalError("Stored intent fields are invalid")
        if self.intent_sha256 != self._expected_sha256():
            raise ExecutionJournalError("Stored intent failed digest verification")

    def _material(self):
        return {
            "schema_version": INTENT_SCHEMA_VERSION,
            "authorization_sha256": self.authorization_sha256,
            "effect_sha256": self.effect_sha256,
            "decision_sha256": self.decision_sha256,
            "readiness_sha256": self.readiness_sha256,
            "action": self.action,
            "approved_quantity": self.approved_quantity,
            "policy_id": self.policy_id,
        }

    def _expected_sha256(self):
        return hashlib.sha256(
            _canonical_json(self._material()).encode("utf-8")
        ).hexdigest()

    def as_record(self):
        return {**self._material(), "intent_sha256": self.intent_sha256}

    @classmethod
    def from_decision(cls, decision):
        if not isinstance(decision, LocalPaperExecutionDecision):
            raise ExecutionJournalError(
                "A complete local Paper execution decision is required"
            )
        try:
            reconstructed = LocalPaperExecutionDecision(
                decision.authorization,
                decision.readiness,
                decision.disposition,
                decision.reason,
                decision.action,
                decision.approved_quantity,
                decision.policy,
            )
        except (ExecutionContractError, TypeError, ValueError):
            raise ExecutionJournalError(
                "Local Paper decision failed deterministic reconstruction"
            ) from None
        if (
            reconstructed != decision
            or reconstructed.decision_sha256 != decision.decision_sha256
            or decision.disposition is not ExecutionDisposition.ACCEPT_LOCAL_PAPER
            or decision.approved_quantity is None
        ):
            raise ExecutionJournalError(
                "Only an accepted local Paper decision can enter the journal"
            )
        material = {
            "schema_version": INTENT_SCHEMA_VERSION,
            "authorization_sha256": decision.authorization_sha256,
            "effect_sha256": decision.authorization_sha256,
            "decision_sha256": decision.decision_sha256,
            "readiness_sha256": decision.readiness.readiness_sha256,
            "action": decision.action.value,
            "approved_quantity": decision.approved_quantity,
            "policy_id": decision.policy.policy_id,
        }
        digest = hashlib.sha256(
            _canonical_json(material).encode("utf-8")
        ).hexdigest()
        return cls(
            material["authorization_sha256"],
            material["effect_sha256"],
            material["decision_sha256"],
            material["readiness_sha256"],
            material["action"],
            material["approved_quantity"],
            material["policy_id"],
            digest,
        )


class ExecutionIntentJournal:
    """SQLite journal with one atomic effect identity per authorization."""

    def __init__(self, path):
        if not isinstance(path, (str, Path)) or not str(path) or path == ":memory:":
            raise ExecutionJournalError("A persistent journal path is required")
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise ExecutionJournalError(
                "Cannot prepare the journal directory"
            ) from None
        self._connection = None
        try:
            self._connection = sqlite3.connect(str(target), timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._migrate()
        except ExecutionJournalError:
            if self._connection is not None:
                self._connection.close()
            raise
        except sqlite3.Error:
            if self._connection is not None:
                self._connection.close()
            raise ExecutionJournalError(
                "Cannot open or migrate the execution journal"
            ) from None

    def _migrate(self):
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS execution_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM execution_schema_migrations"
            ).fetchone()
            current = row["version"]
            if current > JOURNAL_SCHEMA_VERSION:
                raise ExecutionJournalError(
                    "Execution journal schema is newer than this application"
                )
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE local_paper_intents (
                        authorization_sha256 TEXT PRIMARY KEY,
                        effect_sha256 TEXT NOT NULL UNIQUE,
                        decision_sha256 TEXT NOT NULL,
                        readiness_sha256 TEXT NOT NULL,
                        action TEXT NOT NULL,
                        approved_quantity TEXT NOT NULL,
                        policy_id TEXT NOT NULL,
                        intent_sha256 TEXT NOT NULL UNIQUE
                    )
                    """
                )
                self._connection.execute(
                    "INSERT INTO execution_schema_migrations(version) VALUES (?)",
                    (JOURNAL_SCHEMA_VERSION,),
                )

    @staticmethod
    def _row_to_record(row):
        if row is None:
            return None
        try:
            return LocalPaperIntentRecord(*(row[name] for name in INTENT_COLUMNS))
        except (ExecutionJournalError, KeyError, TypeError, ValueError):
            raise ExecutionJournalError(
                "Stored intent violates the canonical contract"
            ) from None

    def _select(self, authorization_sha256):
        columns = ", ".join(INTENT_COLUMNS)
        return self._connection.execute(
            f"SELECT {columns} FROM local_paper_intents "
            "WHERE authorization_sha256 = ?",
            (authorization_sha256,),
        ).fetchone()

    def _insert(self, record):
        columns = ", ".join(INTENT_COLUMNS)
        placeholders = ", ".join("?" for _ in INTENT_COLUMNS)
        self._connection.execute(
            f"INSERT INTO local_paper_intents ({columns}) VALUES ({placeholders})",
            tuple(getattr(record, name) for name in INTENT_COLUMNS),
        )

    def record(self, decision):
        record = LocalPaperIntentRecord.from_decision(decision)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._row_to_record(
                self._select(record.authorization_sha256)
            )
            if existing is None:
                self._insert(record)
                result = record
            elif existing == record:
                result = existing
            else:
                raise IntentConflict(
                    "Authorization identity conflicts with stored intent"
                )
            self._connection.commit()
            return result
        except ExecutionJournalError:
            self._connection.rollback()
            raise
        except sqlite3.IntegrityError:
            self._connection.rollback()
            raise IntentConflict(
                "Intent identity conflicts with durable journal state"
            ) from None
        except sqlite3.Error:
            self._connection.rollback()
            raise ExecutionJournalError(
                "Cannot transactionally record the local Paper intent"
            ) from None

    def get(self, authorization_sha256):
        if (
            not isinstance(authorization_sha256, str)
            or SHA256_PATTERN.fullmatch(authorization_sha256) is None
        ):
            raise ExecutionJournalError("Authorization digest is invalid")
        try:
            return self._row_to_record(self._select(authorization_sha256))
        except ExecutionJournalError:
            raise
        except sqlite3.Error:
            raise ExecutionJournalError("Cannot read the execution journal") from None

    def count(self):
        try:
            return self._connection.execute(
                "SELECT COUNT(*) FROM local_paper_intents"
            ).fetchone()[0]
        except sqlite3.Error:
            raise ExecutionJournalError("Cannot count journal intents") from None

    def canonical_json(self):
        columns = ", ".join(INTENT_COLUMNS)
        try:
            rows = self._connection.execute(
                f"SELECT {columns} FROM local_paper_intents "
                "ORDER BY authorization_sha256"
            ).fetchall()
            records = tuple(self._row_to_record(row).as_record() for row in rows)
        except ExecutionJournalError:
            raise
        except sqlite3.Error:
            raise ExecutionJournalError("Cannot export the execution journal") from None
        return _canonical_json(
            {"schema_version": JOURNAL_SCHEMA_VERSION, "intents": records}
        ) + "\n"

    def schema_version(self):
        try:
            return self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) "
                "FROM execution_schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise ExecutionJournalError(
                "Cannot read execution journal schema version"
            ) from None

    def close(self):
        try:
            self._connection.close()
        except sqlite3.Error:
            raise ExecutionJournalError("Cannot close the execution journal") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
