"""Bounded read-only ingestion of accepted P5/P6 SQLite evidence for P7."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    ANALYTICS_SCHEMA_VERSION,
    AnalyticsContractError,
    AnalyticsSourceIdentity,
    AnalyticsSourceKind,
)


INGESTION_SCHEMA_VERSION = 1
P5_JOURNAL_SCHEMA_VERSION = 1
P6_JOURNAL_SCHEMA_VERSION = 1
P5_POLICY_ID = "P5_LOCAL_PAPER_V1"
MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 4096
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

P5_COLUMNS = (
    "authorization_sha256",
    "effect_sha256",
    "decision_sha256",
    "readiness_sha256",
    "action",
    "approved_quantity",
    "policy_id",
    "intent_sha256",
)
P6_COLUMNS = (
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

FORBIDDEN_MATERIAL = (
    '"api_key":',
    '"api_secret":',
    '"password":',
    '"endpoint_url":',
    '"raw_response":',
    '"canonical_response_json":',
    '"private_key":',
    '"account_id":',
)


class AnalyticsIngestionError(AnalyticsContractError):
    """Accepted upstream evidence cannot be read safely and deterministically."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value):
    if not isinstance(value, str):
        raise AnalyticsIngestionError("Canonical digest material must be text")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _decode_canonical(value, label):
    if not isinstance(value, str) or not value:
        raise AnalyticsIngestionError(f"{label} is invalid")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        raise AnalyticsIngestionError(f"{label} is invalid") from None
    if _json(decoded) != value:
        raise AnalyticsIngestionError(f"{label} is noncanonical")
    return decoded


def _sha256_file(path):
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DATABASE_BYTES:
                    raise AnalyticsIngestionError("Upstream database is too large")
                digest.update(chunk)
    except AnalyticsIngestionError:
        raise
    except OSError:
        raise AnalyticsIngestionError("Upstream database cannot be read") from None
    if total == 0:
        raise AnalyticsIngestionError("Upstream database is empty")
    return digest.hexdigest()


def _safe_stat(path):
    try:
        stat = path.stat()
    except OSError:
        raise AnalyticsIngestionError("Upstream database cannot be inspected") from None
    if not path.is_file() or path.is_symlink() or stat.st_size <= 0:
        raise AnalyticsIngestionError("Upstream database path is invalid")
    if stat.st_size > MAX_DATABASE_BYTES:
        raise AnalyticsIngestionError("Upstream database is too large")
    return (stat.st_size, stat.st_mtime_ns, stat.st_ino)


def _connect_readonly(path):
    try:
        connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            connection.close()
            raise AnalyticsIngestionError("SQLite read-only guard is not active")
        connection.execute("PRAGMA trusted_schema = OFF")
        return connection
    except AnalyticsIngestionError:
        raise
    except (OSError, sqlite3.Error):
        raise AnalyticsIngestionError(
            "Upstream database cannot be opened read-only"
        ) from None


def _table_columns(connection, table):
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        raise AnalyticsIngestionError("Upstream schema cannot be inspected") from None
    return tuple(row["name"] for row in rows)


def _schema_version(connection, migration_table):
    try:
        row = connection.execute(
            f"SELECT COALESCE(MAX(version), 0) AS version FROM {migration_table}"
        ).fetchone()
    except sqlite3.Error:
        raise AnalyticsIngestionError("Upstream schema version is unavailable") from None
    value = row["version"] if row is not None else None
    if type(value) is not int:
        raise AnalyticsIngestionError("Upstream schema version is invalid")
    return value


def _scan_forbidden(text):
    lowered = text.lower()
    if any(item in lowered for item in FORBIDDEN_MATERIAL):
        raise AnalyticsIngestionError("Upstream evidence contains forbidden material")


def _p5_canonical(connection):
    if _schema_version(connection, "execution_schema_migrations") != P5_JOURNAL_SCHEMA_VERSION:
        raise AnalyticsIngestionError("P5 execution journal schema is unsupported")
    if _table_columns(connection, "local_paper_intents") != P5_COLUMNS:
        raise AnalyticsIngestionError("P5 intent schema is ambiguous or unsupported")
    try:
        rows = connection.execute(
            "SELECT " + ", ".join(P5_COLUMNS)
            + " FROM local_paper_intents ORDER BY authorization_sha256"
        ).fetchall()
    except sqlite3.Error:
        raise AnalyticsIngestionError("P5 execution journal cannot be read") from None
    if len(rows) > MAX_RECORDS:
        raise AnalyticsIngestionError("P5 execution journal exceeds the record bound")

    records = []
    for row in rows:
        values = {name: row[name] for name in P5_COLUMNS}
        digests = (
            values["authorization_sha256"],
            values["effect_sha256"],
            values["decision_sha256"],
            values["readiness_sha256"],
            values["intent_sha256"],
        )
        if (
            any(not _valid_sha(value) for value in digests)
            or values["effect_sha256"] != values["authorization_sha256"]
            or values["action"] not in ("ENTER_LONG", "EXIT_LONG")
            or not isinstance(values["approved_quantity"], str)
            or not values["approved_quantity"]
            or values["policy_id"] != P5_POLICY_ID
        ):
            raise AnalyticsIngestionError("P5 intent row violates the accepted contract")
        material = {
            "schema_version": 1,
            "authorization_sha256": values["authorization_sha256"],
            "effect_sha256": values["effect_sha256"],
            "decision_sha256": values["decision_sha256"],
            "readiness_sha256": values["readiness_sha256"],
            "action": values["action"],
            "approved_quantity": values["approved_quantity"],
            "policy_id": values["policy_id"],
        }
        if _sha256_text(_json(material)) != values["intent_sha256"]:
            raise AnalyticsIngestionError("P5 intent digest verification failed")
        records.append({"schema_version": 1, **values})

    canonical = _json({
        "schema_version": P5_JOURNAL_SCHEMA_VERSION,
        "intents": records,
    }) + "\n"
    _scan_forbidden(canonical)
    return canonical, len(records)


def _p6_canonical(connection):
    if _schema_version(connection, "analyst_schema_migrations") != P6_JOURNAL_SCHEMA_VERSION:
        raise AnalyticsIngestionError("P6 analyst journal schema is unsupported")
    if _table_columns(connection, "analyst_traces") != P6_COLUMNS:
        raise AnalyticsIngestionError("P6 trace schema is ambiguous or unsupported")
    try:
        rows = connection.execute(
            "SELECT " + ", ".join(P6_COLUMNS)
            + " FROM analyst_traces ORDER BY trace_sha256"
        ).fetchall()
    except sqlite3.Error:
        raise AnalyticsIngestionError("P6 analyst journal cannot be read") from None
    if len(rows) > MAX_RECORDS:
        raise AnalyticsIngestionError("P6 analyst journal exceeds the record bound")

    records = []
    for row in rows:
        values = {name: row[name] for name in P6_COLUMNS}
        for name in (
            "trace_sha256",
            "request_sha256",
            "response_validation_sha256",
            "bundle_sha256",
            "grounding_sha256",
            "input_sha256",
            "report_sha256",
        ):
            if not _valid_sha(values[name]):
                raise AnalyticsIngestionError("P6 trace digest is invalid")
        if values["accepted"] not in (0, 1):
            raise AnalyticsIngestionError("P6 trace acceptance flag is invalid")

        claim_ids = _decode_canonical(
            values["grounded_claim_ids_json"],
            "P6 grounded claim identities",
        )
        trace = _decode_canonical(values["trace_json"], "P6 trace JSON")
        if (
            not isinstance(claim_ids, list)
            or any(not isinstance(item, str) or not item for item in claim_ids)
            or len(set(claim_ids)) != len(claim_ids)
            or claim_ids != sorted(claim_ids)
        ):
            raise AnalyticsIngestionError("P6 grounded claim identities are invalid")

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
        if (
            not isinstance(trace, dict)
            or set(trace) != expected_keys
            or trace["schema_version"] != 1
        ):
            raise AnalyticsIngestionError("P6 trace fields are unsupported")
        expected_values = {
            "request_sha256": values["request_sha256"],
            "response_validation_sha256": values["response_validation_sha256"],
            "bundle_sha256": values["bundle_sha256"],
            "grounding_sha256": values["grounding_sha256"],
            "input_sha256": values["input_sha256"],
            "report_sha256": values["report_sha256"],
            "accepted": bool(values["accepted"]),
            "grounding_code": values["grounding_code"],
            "disposition": values["disposition"],
            "reason": values["reason"],
            "grounded_claim_ids": claim_ids,
        }
        if any(trace.get(key) != value for key, value in expected_values.items()):
            raise AnalyticsIngestionError("P6 trace row and canonical JSON disagree")

        grounding = trace["grounding_record"]
        grounding_keys = {
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
        if (
            not isinstance(grounding, dict)
            or set(grounding) != grounding_keys
            or grounding.get("schema_version") != 1
            or grounding.get("request_sha256") != values["request_sha256"]
            or grounding.get("response_validation_sha256")
            != values["response_validation_sha256"]
            or grounding.get("bundle_sha256") != values["bundle_sha256"]
            or grounding.get("accepted") is not bool(values["accepted"])
            or grounding.get("code") != values["grounding_code"]
            or grounding.get("grounded_claim_ids") != claim_ids
            or grounding.get("report_sha256") != values["report_sha256"]
            or not isinstance(grounding.get("report"), dict)
            or grounding["report"].get("input_sha256") != values["input_sha256"]
            or grounding["report"].get("disposition") != values["disposition"]
            or grounding["report"].get("reason") != values["reason"]
        ):
            raise AnalyticsIngestionError("P6 grounding trace binding is invalid")

        if _sha256_text(values["trace_json"]) != values["trace_sha256"]:
            raise AnalyticsIngestionError("P6 trace digest verification failed")

        if values["accepted"] == 1:
            if (
                values["grounding_code"] != "GROUNDED"
                or values["disposition"] != "REVIEW"
                or values["reason"] != "UNCERTAINTY_PRESENT"
                or not claim_ids
            ):
                raise AnalyticsIngestionError("Accepted P6 trace is not conservative")
        else:
            if (
                values["grounding_code"] == "GROUNDED"
                or values["disposition"] != "INSUFFICIENT_DATA"
                or values["reason"] != "NO_USABLE_CLAIMS"
                or claim_ids
            ):
                raise AnalyticsIngestionError("Rejected P6 trace did not fail closed")

        _scan_forbidden(values["trace_json"])
        records.append({**trace, "trace_sha256": values["trace_sha256"]})

    canonical = _json({
        "schema_version": P6_JOURNAL_SCHEMA_VERSION,
        "traces": records,
    }) + "\n"
    _scan_forbidden(canonical)
    return canonical, len(records)


@dataclass(frozen=True, slots=True)
class UpstreamSourceSpec:
    """Explicit trusted binding between one local database and a P7 source identity."""

    source_id: str
    source_kind: AnalyticsSourceKind
    symbol: str
    observed_at_ms: int
    database_path: Path
    expected_database_sha256: str

    def __post_init__(self):
        try:
            path = Path(self.database_path)
        except TypeError:
            raise AnalyticsIngestionError("Upstream source path is invalid") from None
        if (
            not isinstance(self.source_id, str)
            or not isinstance(self.source_kind, AnalyticsSourceKind)
            or not isinstance(self.symbol, str)
            or type(self.observed_at_ms) is not int
            or self.observed_at_ms < 0
            or not _valid_sha(self.expected_database_sha256)
            or not str(path)
        ):
            raise AnalyticsIngestionError("Upstream source specification is invalid")
        object.__setattr__(self, "database_path", path)


@dataclass(frozen=True, slots=True)
class IngestedSource:
    """Sanitized read-only identity and canonical digest of one upstream journal."""

    identity: AnalyticsSourceIdentity
    database_sha256: str
    canonical_sha256: str
    record_count: int
    schema_version: int
    read_only: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.identity, AnalyticsSourceIdentity)
            or not _valid_sha(self.database_sha256)
            or not _valid_sha(self.canonical_sha256)
            or self.identity.source_sha256 != self.canonical_sha256
            or type(self.record_count) is not int
            or not 0 <= self.record_count <= MAX_RECORDS
            or self.schema_version != 1
            or self.read_only is not True
        ):
            raise AnalyticsIngestionError("Ingested source identity is invalid")

    def as_record(self):
        return {
            "identity": self.identity.as_record(),
            "database_sha256": self.database_sha256,
            "canonical_sha256": self.canonical_sha256,
            "record_count": self.record_count,
            "schema_version": self.schema_version,
            "read_only": self.read_only,
        }


@dataclass(frozen=True, slots=True)
class ReadOnlyIngestionManifest:
    """Deterministic manifest for one P5+P6 read-only analytics snapshot."""

    snapshot_time_ms: int
    sources: tuple[IngestedSource, ...]
    schema_version: int = INGESTION_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != INGESTION_SCHEMA_VERSION
            or type(self.snapshot_time_ms) is not int
            or self.snapshot_time_ms < 0
            or type(self.sources) is not tuple
            or len(self.sources) != 2
            or any(not isinstance(item, IngestedSource) for item in self.sources)
        ):
            raise AnalyticsIngestionError("Ingestion manifest identity is invalid")
        ids = tuple(item.identity.source_id for item in self.sources)
        kinds = tuple(item.identity.source_kind for item in self.sources)
        symbols = {item.identity.symbol for item in self.sources}
        if (
            ids != tuple(sorted(ids))
            or len(set(ids)) != len(ids)
            or set(kinds) != {
                AnalyticsSourceKind.P5_EXECUTION_EVIDENCE,
                AnalyticsSourceKind.P6_ANALYST_TRACE,
            }
            or len(symbols) != 1
            or any(
                item.identity.observed_at_ms > self.snapshot_time_ms
                for item in self.sources
            )
        ):
            raise AnalyticsIngestionError(
                "Ingestion manifest coverage, order, symbol or time is invalid"
            )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "snapshot_time_ms": self.snapshot_time_ms,
            "sources": [item.as_record() for item in self.sources],
            "safety": {
                "read_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "strategy_evidence": "INSUFFICIENT_EVIDENCE",
                "upstream_mutation": False,
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
        }

    @property
    def manifest_sha256(self):
        return _sha256_text(_json(self.as_record()))


def ingest_source(spec):
    """Read one closed local SQLite database without changing it."""

    if not isinstance(spec, UpstreamSourceSpec):
        raise AnalyticsIngestionError("A valid upstream source specification is required")
    path = spec.database_path
    before_stat = _safe_stat(path)
    before_sha = _sha256_file(path)
    if before_sha != spec.expected_database_sha256:
        raise AnalyticsIngestionError("Upstream database identity changed")

    connection = _connect_readonly(path)
    try:
        if spec.source_kind is AnalyticsSourceKind.P5_EXECUTION_EVIDENCE:
            canonical, count = _p5_canonical(connection)
            schema_version = P5_JOURNAL_SCHEMA_VERSION
        elif spec.source_kind is AnalyticsSourceKind.P6_ANALYST_TRACE:
            canonical, count = _p6_canonical(connection)
            schema_version = P6_JOURNAL_SCHEMA_VERSION
        else:
            raise AnalyticsIngestionError("Upstream source kind is unsupported")
    finally:
        try:
            connection.close()
        except sqlite3.Error:
            raise AnalyticsIngestionError(
                "Read-only upstream database could not be closed safely"
            ) from None

    after_stat = _safe_stat(path)
    after_sha = _sha256_file(path)
    if before_stat != after_stat or before_sha != after_sha:
        raise AnalyticsIngestionError("Upstream database changed during ingestion")

    canonical_sha = _sha256_text(canonical)
    identity = AnalyticsSourceIdentity(
        spec.source_id,
        spec.source_kind,
        spec.symbol,
        schema_version,
        spec.observed_at_ms,
        canonical_sha,
    )
    return IngestedSource(
        identity,
        before_sha,
        canonical_sha,
        count,
        schema_version,
    )


def ingest_readonly_sources(snapshot_time_ms, specs):
    """Create a deterministic P7 manifest from exactly one P5 and one P6 source."""

    if type(specs) is not tuple or len(specs) != 2:
        raise AnalyticsIngestionError("Exactly two immutable source specs are required")
    try:
        resolved = tuple(item.database_path.resolve() for item in specs)
    except (AttributeError, OSError):
        raise AnalyticsIngestionError("Upstream source path is invalid") from None
    if len(set(resolved)) != len(resolved):
        raise AnalyticsIngestionError("Upstream sources are ambiguous or duplicated")
    sources = tuple(
        sorted(
            (ingest_source(item) for item in specs),
            key=lambda item: item.identity.source_id,
        )
    )
    return ReadOnlyIngestionManifest(snapshot_time_ms, sources)
