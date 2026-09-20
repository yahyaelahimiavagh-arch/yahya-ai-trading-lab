"""Transactional, deterministic journal for P6 analysis traces."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .contracts import AnalystDisposition, AnalystReason
from .grounding import GroundingCode, GroundingValidation


ANALYST_JOURNAL_SCHEMA_VERSION = 1
ANALYST_TRACE_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
TRACE_COLUMNS = (
    "trace_sha256",
    "request_sha256",
    "response_validation_sha256",
    "bundle_sha256",
    "grounding_sha256",
    "input_sha256",
    "report_sha256",
    "accepted",
    "grounding_code",
    "disposition",
    "reason",
    "grounded_claim_ids_json",
    "trace_json",
)


class AnalystJournalError(Exception):
    """Journal operation failed without exposing paths or SQL details."""


class AnalystTraceConflict(AnalystJournalError):
    """A response-validation identity is already bound to another trace."""


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_text(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_digest(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _decode_canonical_json(payload):
    if not isinstance(payload, str) or not payload:
        raise AnalystJournalError("Stored analyst trace JSON is invalid")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        raise AnalystJournalError("Stored analyst trace JSON is invalid") from None
    if _canonical_json(value) != payload:
        raise AnalystJournalError("Stored analyst trace JSON is noncanonical")
    return value


@dataclass(frozen=True, slots=True)
class AnalystTraceRecord:
    """Canonical durable identity for one grounded or fail-closed analysis trace."""

    trace_sha256: str
    request_sha256: str
    response_validation_sha256: str
    bundle_sha256: str
    grounding_sha256: str
    input_sha256: str
    report_sha256: str
    accepted: int
    grounding_code: str
    disposition: str
    reason: str
    grounded_claim_ids_json: str
    trace_json: str

    def __post_init__(self):
        digests = (
            self.trace_sha256,
            self.request_sha256,
            self.response_validation_sha256,
            self.bundle_sha256,
            self.grounding_sha256,
            self.input_sha256,
            self.report_sha256,
        )
        if any(not _valid_digest(value) for value in digests):
            raise AnalystJournalError("Stored analyst trace digest is invalid")
        if self.accepted not in (0, 1):
            raise AnalystJournalError("Stored analyst trace acceptance is invalid")

        try:
            code = GroundingCode(self.grounding_code)
            disposition = AnalystDisposition(self.disposition)
            reason = AnalystReason(self.reason)
        except ValueError:
            raise AnalystJournalError("Stored analyst trace enum is invalid") from None

        claim_ids = _decode_canonical_json(self.grounded_claim_ids_json)
        if (
            not isinstance(claim_ids, list)
            or any(not isinstance(item, str) or not item for item in claim_ids)
            or len(set(claim_ids)) != len(claim_ids)
            or claim_ids != sorted(claim_ids)
        ):
            raise AnalystJournalError("Stored grounded claim identities are invalid")

        trace = _decode_canonical_json(self.trace_json)
        expected_keys = {
            "schema_version",
            "request_sha256",
            "response_validation_sha256",
            "bundle_sha256",
            "grounding_sha256",
            "input_sha256",
            "report_sha256",
            "accepted",
            "grounding_code",
            "disposition",
            "reason",
            "grounded_claim_ids",
            "grounding_record",
        }
        if not isinstance(trace, dict) or set(trace) != expected_keys:
            raise AnalystJournalError("Stored analyst trace fields are invalid")
        if trace["schema_version"] != ANALYST_TRACE_SCHEMA_VERSION:
            raise AnalystJournalError("Stored analyst trace schema is unsupported")
        if "raw_response" in self.trace_json or "canonical_response_json" in self.trace_json:
            raise AnalystJournalError("Stored analyst trace contains raw provider material")

        grounding_record = trace["grounding_record"]
        if not isinstance(grounding_record, dict):
            raise AnalystJournalError("Stored grounding record is invalid")
        grounding_expected = {
            "schema_version",
            "request_sha256",
            "response_validation_sha256",
            "bundle_sha256",
            "accepted",
            "code",
            "grounded_claim_ids",
            "report",
            "report_sha256",
        }
        if set(grounding_record) != grounding_expected:
            raise AnalystJournalError("Stored grounding record fields are invalid")

        expected_values = {
            "request_sha256": self.request_sha256,
            "response_validation_sha256": self.response_validation_sha256,
            "bundle_sha256": self.bundle_sha256,
            "grounding_sha256": self.grounding_sha256,
            "input_sha256": self.input_sha256,
            "report_sha256": self.report_sha256,
            "accepted": bool(self.accepted),
            "grounding_code": self.grounding_code,
            "disposition": self.disposition,
            "reason": self.reason,
            "grounded_claim_ids": claim_ids,
        }
        if any(trace[key] != value for key, value in expected_values.items()):
            raise AnalystJournalError("Stored analyst trace row and JSON disagree")
        if (
            grounding_record["request_sha256"] != self.request_sha256
            or grounding_record["response_validation_sha256"]
            != self.response_validation_sha256
            or grounding_record["bundle_sha256"] != self.bundle_sha256
            or grounding_record["accepted"] is not bool(self.accepted)
            or grounding_record["code"] != self.grounding_code
            or grounding_record["grounded_claim_ids"] != claim_ids
            or grounding_record["report_sha256"] != self.report_sha256
            or not isinstance(grounding_record["report"], dict)
            or grounding_record["report"].get("input_sha256") != self.input_sha256
            or grounding_record["report"].get("disposition") != self.disposition
            or grounding_record["report"].get("reason") != self.reason
        ):
            raise AnalystJournalError("Stored grounding trace binding is invalid")

        if self.accepted:
            if (
                code is not GroundingCode.GROUNDED
                or disposition is not AnalystDisposition.REVIEW
                or reason is not AnalystReason.UNCERTAINTY_PRESENT
                or not claim_ids
            ):
                raise AnalystJournalError("Accepted analyst trace is not conservative")
        else:
            if (
                code is GroundingCode.GROUNDED
                or disposition is not AnalystDisposition.INSUFFICIENT_DATA
                or reason is not AnalystReason.NO_USABLE_CLAIMS
                or claim_ids
            ):
                raise AnalystJournalError("Rejected analyst trace did not fail closed")

        if _sha256_text(self.trace_json) != self.trace_sha256:
            raise AnalystJournalError("Stored analyst trace failed digest verification")

    def as_record(self):
        return _decode_canonical_json(self.trace_json)

    @classmethod
    def from_grounding(cls, grounding):
        if not isinstance(grounding, GroundingValidation):
            raise AnalystJournalError("Validated P6 grounding result is required")

        grounding_record = grounding.as_record()
        encoded_grounding = _canonical_json(grounding_record)
        if (
            "raw_response" in encoded_grounding
            or "canonical_response_json" in encoded_grounding
        ):
            raise AnalystJournalError("Grounding trace unexpectedly contains provider text")

        material = {
            "schema_version": ANALYST_TRACE_SCHEMA_VERSION,
            "request_sha256": grounding.validation.request.request_sha256,
            "response_validation_sha256": grounding.validation.validation_sha256,
            "bundle_sha256": grounding.validation.request.bundle.bundle_sha256,
            "grounding_sha256": grounding.grounding_sha256,
            "input_sha256": grounding.report.analysis_input.input_sha256,
            "report_sha256": grounding.report.report_sha256,
            "accepted": grounding.accepted,
            "grounding_code": grounding.code.value,
            "disposition": grounding.report.disposition.value,
            "reason": grounding.report.reason.value,
            "grounded_claim_ids": list(grounding.grounded_claim_ids),
            "grounding_record": grounding_record,
        }
        trace_json = _canonical_json(material)
        return cls(
            _sha256_text(trace_json),
            material["request_sha256"],
            material["response_validation_sha256"],
            material["bundle_sha256"],
            material["grounding_sha256"],
            material["input_sha256"],
            material["report_sha256"],
            1 if material["accepted"] else 0,
            material["grounding_code"],
            material["disposition"],
            material["reason"],
            _canonical_json(material["grounded_claim_ids"]),
            trace_json,
        )


class AnalystTraceJournal:
    """SQLite journal with atomic idempotent storage for sanitized P6 traces."""

    def __init__(self, path):
        if not isinstance(path, (str, Path)) or not str(path) or str(path) == ":memory:":
            raise AnalystJournalError("A persistent analyst journal path is required")
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise AnalystJournalError("Cannot prepare analyst journal directory") from None

        self._connection = None
        try:
            self._connection = sqlite3.connect(str(target), timeout=5)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._migrate()
        except AnalystJournalError:
            if self._connection is not None:
                self._connection.close()
            raise
        except sqlite3.Error:
            if self._connection is not None:
                self._connection.close()
            raise AnalystJournalError("Cannot open or migrate analyst journal") from None

    def _migrate(self):
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS analyst_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM analyst_schema_migrations"
            ).fetchone()
            current = row["version"]
            if current > ANALYST_JOURNAL_SCHEMA_VERSION:
                raise AnalystJournalError(
                    "Analyst journal schema is newer than this application"
                )
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE analyst_traces (
                        trace_sha256 TEXT PRIMARY KEY,
                        request_sha256 TEXT NOT NULL,
                        response_validation_sha256 TEXT NOT NULL UNIQUE,
                        bundle_sha256 TEXT NOT NULL,
                        grounding_sha256 TEXT NOT NULL UNIQUE,
                        input_sha256 TEXT NOT NULL,
                        report_sha256 TEXT NOT NULL,
                        accepted INTEGER NOT NULL,
                        grounding_code TEXT NOT NULL,
                        disposition TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        grounded_claim_ids_json TEXT NOT NULL,
                        trace_json TEXT NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    "INSERT INTO analyst_schema_migrations(version) VALUES (?)",
                    (ANALYST_JOURNAL_SCHEMA_VERSION,),
                )

    @staticmethod
    def _row_to_record(row):
        if row is None:
            return None
        try:
            return AnalystTraceRecord(*(row[name] for name in TRACE_COLUMNS))
        except (AnalystJournalError, KeyError, TypeError, ValueError):
            raise AnalystJournalError(
                "Stored analyst trace violates the canonical contract"
            ) from None

    def _select_by_response(self, response_validation_sha256):
        columns = ", ".join(TRACE_COLUMNS)
        return self._connection.execute(
            f"SELECT {columns} FROM analyst_traces "
            "WHERE response_validation_sha256 = ?",
            (response_validation_sha256,),
        ).fetchone()

    def _select_by_trace(self, trace_sha256):
        columns = ", ".join(TRACE_COLUMNS)
        return self._connection.execute(
            f"SELECT {columns} FROM analyst_traces WHERE trace_sha256 = ?",
            (trace_sha256,),
        ).fetchone()

    def _insert(self, record):
        columns = ", ".join(TRACE_COLUMNS)
        placeholders = ", ".join("?" for _ in TRACE_COLUMNS)
        self._connection.execute(
            f"INSERT INTO analyst_traces ({columns}) VALUES ({placeholders})",
            tuple(getattr(record, name) for name in TRACE_COLUMNS),
        )

    def record(self, grounding):
        record = AnalystTraceRecord.from_grounding(grounding)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._row_to_record(
                self._select_by_response(record.response_validation_sha256)
            )
            if existing is None:
                self._insert(record)
                result = record
            elif existing == record:
                result = existing
            else:
                raise AnalystTraceConflict(
                    "Response-validation identity conflicts with stored trace"
                )
            self._connection.commit()
            return result
        except AnalystJournalError:
            self._connection.rollback()
            raise
        except sqlite3.IntegrityError:
            self._connection.rollback()
            raise AnalystTraceConflict(
                "Analyst trace identity conflicts with durable journal state"
            ) from None
        except sqlite3.Error:
            self._connection.rollback()
            raise AnalystJournalError(
                "Cannot transactionally record analyst trace"
            ) from None

    def get(self, trace_sha256):
        if not _valid_digest(trace_sha256):
            raise AnalystJournalError("Analyst trace digest is invalid")
        try:
            return self._row_to_record(self._select_by_trace(trace_sha256))
        except AnalystJournalError:
            raise
        except sqlite3.Error:
            raise AnalystJournalError("Cannot read analyst journal") from None

    def get_by_response(self, response_validation_sha256):
        if not _valid_digest(response_validation_sha256):
            raise AnalystJournalError("Response-validation digest is invalid")
        try:
            return self._row_to_record(
                self._select_by_response(response_validation_sha256)
            )
        except AnalystJournalError:
            raise
        except sqlite3.Error:
            raise AnalystJournalError("Cannot read analyst journal") from None

    def count(self):
        try:
            return self._connection.execute(
                "SELECT COUNT(*) FROM analyst_traces"
            ).fetchone()[0]
        except sqlite3.Error:
            raise AnalystJournalError("Cannot count analyst journal traces") from None

    def canonical_json(self):
        columns = ", ".join(TRACE_COLUMNS)
        try:
            rows = self._connection.execute(
                f"SELECT {columns} FROM analyst_traces ORDER BY trace_sha256"
            ).fetchall()
            records = tuple(self._row_to_record(row).as_record() for row in rows)
        except AnalystJournalError:
            raise
        except sqlite3.Error:
            raise AnalystJournalError("Cannot export analyst journal") from None
        return _canonical_json(
            {
                "schema_version": ANALYST_JOURNAL_SCHEMA_VERSION,
                "traces": records,
            }
        ) + "\n"

    def schema_version(self):
        try:
            return self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM analyst_schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error:
            raise AnalystJournalError(
                "Cannot read analyst journal schema version"
            ) from None

    def close(self):
        try:
            self._connection.close()
        except sqlite3.Error:
            raise AnalystJournalError("Cannot close analyst journal") from None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
