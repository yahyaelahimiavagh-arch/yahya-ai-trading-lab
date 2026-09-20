"""Bounded local CLI for P6 evidence, validation and sanitized trace viewing."""

import argparse
import json
from enum import Enum
from pathlib import Path

from .contracts import EvidenceLayer
from .evidence import (
    EvidenceBundleError,
    build_evidence_bundle,
    build_layer_evidence,
)
from .grounding import GroundingBoundaryError, ground_model_response
from .journal import (
    AnalystJournalError,
    AnalystTraceJournal,
    AnalystTraceRecord,
)
from .request import ModelRequestBoundaryError, build_model_request
from .response import (
    MAX_MODEL_RESPONSE_BYTES,
    ModelResponseBoundaryError,
    validate_model_response,
)


ANALYST_CLI_SCHEMA_VERSION = 1
ANALYST_BUNDLE_SPEC_SCHEMA_VERSION = 1
MAX_BUNDLE_SPEC_BYTES = 32 * 1024
MAX_ANALYST_CLI_OUTPUT_BYTES = 32 * 1024

EXIT_OK = 0
EXIT_NOT_GROUNDED = 20
EXIT_INVALID = 21
EXIT_STORAGE = 22
EXIT_NOT_FOUND = 23
EXIT_OUTPUT = 24


class AnalystCliCode(str, Enum):
    EVIDENCE_READY = "EVIDENCE_READY"
    GROUNDED = "GROUNDED"
    NOT_GROUNDED = "NOT_GROUNDED"
    TRACE_READY = "TRACE_READY"
    TRACE_NOT_FOUND = "TRACE_NOT_FOUND"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_INPUT = "INVALID_INPUT"
    STORAGE_ERROR = "STORAGE_ERROR"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"


class AnalystCliError(Exception):
    """Stable local CLI failure that never includes caller-supplied values."""

    def __init__(self, code):
        if not isinstance(code, AnalystCliCode):
            raise TypeError("Analyst CLI error code is invalid")
        self.code = code
        super().__init__(code.value)


class _DuplicateJsonKey(ValueError):
    pass


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _exact_keys(record, expected):
    return isinstance(record, dict) and set(record) == set(expected)


def _read_bounded_text(path, max_bytes):
    if not isinstance(path, (str, Path)) or not str(path):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    try:
        with Path(path).open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None
    if len(payload) > max_bytes:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None


def _read_response_text(path):
    if not isinstance(path, (str, Path)) or not str(path):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    try:
        with Path(path).open("rb") as handle:
            payload = handle.read(MAX_MODEL_RESPONSE_BYTES + 1)
    except OSError:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None


def _valid_digest(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _load_json(path, max_bytes):
    raw = _read_bounded_text(path, max_bytes)
    if not raw:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_object)
    except (json.JSONDecodeError, _DuplicateJsonKey):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None
    return value


def load_bundle_spec(path):
    """Build one validated point-in-time P6 bundle from a bounded local JSON spec."""

    record = _load_json(path, MAX_BUNDLE_SPEC_BYTES)
    if not _exact_keys(
        record,
        ("schema_version", "symbol", "decision_time_ms", "evidence"),
    ):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    if record["schema_version"] != ANALYST_BUNDLE_SPEC_SCHEMA_VERSION:
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    if (
        not isinstance(record["symbol"], str)
        or type(record["decision_time_ms"]) is not int
        or not isinstance(record["evidence"], list)
        or len(record["evidence"]) != 4
    ):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)

    materials = []
    for raw_item in record["evidence"]:
        if not _exact_keys(
            raw_item,
            (
                "evidence_id",
                "layer",
                "observed_at_ms",
                "valid_through_ms",
                "payload",
            ),
        ):
            raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
        try:
            layer = EvidenceLayer(raw_item["layer"])
            material = build_layer_evidence(
                raw_item["evidence_id"],
                layer,
                record["symbol"],
                raw_item["observed_at_ms"],
                raw_item["valid_through_ms"],
                raw_item["payload"],
            )
        except (EvidenceBundleError, TypeError, ValueError):
            raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None
        materials.append(material)

    materials = tuple(sorted(materials, key=lambda item: item.evidence_id))
    try:
        return build_evidence_bundle(
            record["symbol"],
            record["decision_time_ms"],
            materials,
        )
    except (EvidenceBundleError, TypeError, ValueError):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None


def _evidence_summary(bundle):
    return {
        "symbol": bundle.symbol,
        "decision_time_ms": bundle.decision_time_ms,
        "strategy_evidence": bundle.strategy_evidence.value,
        "bundle_sha256": bundle.bundle_sha256,
        "input_sha256": bundle.analyst_input.input_sha256,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "layer": item.layer.value,
                "observed_at_ms": item.observed_at_ms,
                "valid_through_ms": item.valid_through_ms,
                "source_sha256": item.source_sha256,
                "provenance_sha256": item.provenance_sha256,
            }
            for item in bundle.evidence
        ],
    }


def _report_summary(report):
    return {
        "input_sha256": report.analysis_input.input_sha256,
        "claims": [claim.as_record() for claim in report.claims],
        "disposition": report.disposition.value,
        "reason": report.reason.value,
        "report_sha256": report.report_sha256,
    }


def analyst_evidence(path):
    bundle = load_bundle_spec(path)
    return {
        "schema_version": ANALYST_CLI_SCHEMA_VERSION,
        "command": "evidence",
        "ok": True,
        "code": AnalystCliCode.EVIDENCE_READY.value,
        "evidence": _evidence_summary(bundle),
    }


def analyst_validate(bundle_path, response_path, journal_path=None):
    bundle = load_bundle_spec(bundle_path)
    response_text = _read_response_text(response_path)
    try:
        request = build_model_request(bundle)
        response_validation = validate_model_response(request, response_text)
        grounding = ground_model_response(response_validation)
        trace = AnalystTraceRecord.from_grounding(grounding)
    except (
        EvidenceBundleError,
        ModelRequestBoundaryError,
        ModelResponseBoundaryError,
        GroundingBoundaryError,
        AnalystJournalError,
        TypeError,
        ValueError,
    ):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT) from None

    if journal_path is not None:
        try:
            with AnalystTraceJournal(journal_path) as journal:
                durable = journal.record(grounding)
        except AnalystJournalError:
            raise AnalystCliError(AnalystCliCode.STORAGE_ERROR) from None
        if durable != trace:
            raise AnalystCliError(AnalystCliCode.STORAGE_ERROR)

    return {
        "schema_version": ANALYST_CLI_SCHEMA_VERSION,
        "command": "validate",
        "ok": grounding.accepted,
        "code": (
            AnalystCliCode.GROUNDED.value
            if grounding.accepted
            else AnalystCliCode.NOT_GROUNDED.value
        ),
        "response_code": response_validation.code.value,
        "grounding_code": grounding.code.value,
        "bundle_sha256": bundle.bundle_sha256,
        "request_sha256": request.request_sha256,
        "response_validation_sha256": response_validation.validation_sha256,
        "grounding_sha256": grounding.grounding_sha256,
        "trace_sha256": trace.trace_sha256,
        "journaled": journal_path is not None,
        "report": _report_summary(grounding.report),
    }


def analyst_show(journal_path, trace_sha256):
    if not _valid_digest(trace_sha256):
        raise AnalystCliError(AnalystCliCode.INVALID_INPUT)
    try:
        with AnalystTraceJournal(journal_path) as journal:
            record = journal.get(trace_sha256)
    except AnalystJournalError:
        raise AnalystCliError(AnalystCliCode.STORAGE_ERROR) from None

    if record is None:
        return {
            "schema_version": ANALYST_CLI_SCHEMA_VERSION,
            "command": "show",
            "ok": False,
            "code": AnalystCliCode.TRACE_NOT_FOUND.value,
        }

    trace = record.as_record()
    grounding = trace["grounding_record"]
    return {
        "schema_version": ANALYST_CLI_SCHEMA_VERSION,
        "command": "show",
        "ok": True,
        "code": AnalystCliCode.TRACE_READY.value,
        "trace_sha256": record.trace_sha256,
        "bundle_sha256": record.bundle_sha256,
        "response_validation_sha256": record.response_validation_sha256,
        "grounding_sha256": record.grounding_sha256,
        "accepted": bool(record.accepted),
        "grounding_code": record.grounding_code,
        "report": {
            "input_sha256": record.input_sha256,
            "claims": grounding["report"]["claims"],
            "disposition": record.disposition,
            "reason": record.reason,
            "report_sha256": record.report_sha256,
        },
    }


def _exit_code(record):
    code = record.get("code")
    if code in {
        AnalystCliCode.EVIDENCE_READY.value,
        AnalystCliCode.GROUNDED.value,
        AnalystCliCode.TRACE_READY.value,
    }:
        return EXIT_OK
    if code == AnalystCliCode.NOT_GROUNDED.value:
        return EXIT_NOT_GROUNDED
    if code in {
        AnalystCliCode.INVALID_REQUEST.value,
        AnalystCliCode.INVALID_INPUT.value,
    }:
        return EXIT_INVALID
    if code == AnalystCliCode.STORAGE_ERROR.value:
        return EXIT_STORAGE
    if code == AnalystCliCode.TRACE_NOT_FOUND.value:
        return EXIT_NOT_FOUND
    return EXIT_OUTPUT


def _compact_error(command, code):
    return {
        "schema_version": ANALYST_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "code": code.value,
    }


def _render(record):
    encoded = _canonical_json(record)
    if len(encoded.encode("utf-8")) > MAX_ANALYST_CLI_OUTPUT_BYTES:
        raise AnalystCliError(AnalystCliCode.OUTPUT_TOO_LARGE)
    return encoded


class SafeArgumentParser(argparse.ArgumentParser):
    """Argparse without echoing rejected analyst-supplied values."""

    def error(self, message):
        raise AnalystCliError(AnalystCliCode.INVALID_REQUEST)


def _parser():
    parser = SafeArgumentParser(
        description="Bounded local P6 analyst commands; analysis only"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    evidence = commands.add_parser("evidence")
    evidence.add_argument("--bundle", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--bundle", required=True)
    validate.add_argument("--response", required=True)
    validate.add_argument("--journal")

    show = commands.add_parser("show")
    show.add_argument("--journal", required=True)
    show.add_argument("--trace-sha256", required=True)

    return parser


def main(argv=None):
    command = "invalid"
    try:
        args = _parser().parse_args(argv)
        command = args.command
        if args.command == "evidence":
            record = analyst_evidence(args.bundle)
        elif args.command == "validate":
            record = analyst_validate(args.bundle, args.response, args.journal)
        else:
            record = analyst_show(args.journal, args.trace_sha256)
        output = _render(record)
    except AnalystCliError as exc:
        record = _compact_error(command, exc.code)
        try:
            output = _render(record)
        except AnalystCliError:
            output = _canonical_json(
                _compact_error("invalid", AnalystCliCode.OUTPUT_TOO_LARGE)
            )
            record = _compact_error("invalid", AnalystCliCode.OUTPUT_TOO_LARGE)
    print(output)
    return _exit_code(record)


if __name__ == "__main__":
    raise SystemExit(main())
