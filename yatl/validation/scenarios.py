"""P10-009 deterministic adversarial matrix over the accepted P10 audit chain.

Every attack is re-signed before verification so rejection cannot rely only on a
stale outer digest. The matrix has no market-data transport, credential, order,
sizing, threshold-tuning, or Live authorization capability.
"""

import copy
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .cli import ValidationEvidenceBundle, _export_payload
from .registration import CandidateFreeze, EconomicGateRegistry
from .window import ForwardWindowSeal


SCHEMA_VERSION = 1
ARTIFACT_KIND = "YATL_P10_ADVERSARIAL_VALIDATION_SCENARIO"
MATRIX_KIND = "YATL_P10_ADVERSARIAL_VALIDATION_MATRIX"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_EVIDENCE_FILES = 32
MAX_EVIDENCE_TOTAL_BYTES = 16 * 1024 * 1024
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SCENARIOS = (
    "PRE_WINDOW_DATA_CONTAMINATION",
    "CANDIDATE_MUTATION_AFTER_SEAL",
    "THRESHOLD_MUTATION_AFTER_SEAL",
    "FEE_SLIPPAGE_REMOVAL",
    "FABRICATED_POSITIVE_PNL",
    "DRAWDOWN_SUPPRESSION",
    "SAMPLE_DELETION_CHERRY_PICKING",
    "CROSS_SYMBOL_CROSS_WINDOW_MATERIAL",
    "DATA_QUALITY_FAILURE",
    "RISK_SAFETY_BREACH",
    "EVIDENCE_LABEL_LIVE_READINESS_UPGRADE",
)

ACCEPTED = "ACCEPTED"
DIGEST_REJECTED = "AUDIT_DIGEST_REJECTED"
CANDIDATE_REJECTED = "CANDIDATE_IDENTITY_REJECTED"
GATES_REJECTED = "GATE_IDENTITY_REJECTED"
WINDOW_REJECTED = "WINDOW_IDENTITY_REJECTED"
SAFETY_REJECTED = "SAFETY_REJECTED"
PROVENANCE_REJECTED = "PROVENANCE_REJECTED"
PAPER_REJECTED = "PAPER_EVIDENCE_REJECTED"
ECONOMICS_REJECTED = "ECONOMICS_REJECTED"
GATE_RESULT_REJECTED = "GATE_RESULT_REJECTED"

_REQUIRED_AUDIT_KEYS = {
    "schema_version",
    "candidate",
    "gate_registry",
    "window",
    "provenance",
    "forward_paper",
    "economics",
    "gate",
    "audit_sha256",
}
_HEX = frozenset("0123456789abcdef")


class ValidationScenarioError(RuntimeError):
    """One fixed P10 adversarial scenario violated its fail-closed contract."""


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _compact(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _audit_digest(record):
    material = {
        key: record[key]
        for key in (
            "schema_version",
            "candidate",
            "gate_registry",
            "window",
            "provenance",
            "forward_paper",
            "economics",
            "gate",
        )
    }
    return _sha256(_compact(material))


def _accepted_identity(bundle, audit_sha256):
    if not isinstance(bundle, ValidationEvidenceBundle) or not bundle.ready:
        raise ValidationScenarioError("Accepted P10 bundle is not ready")
    candidate = CandidateFreeze()
    gates = EconomicGateRegistry()
    window = ForwardWindowSeal()
    identity = {
        "symbols": list(window.symbols),
        "candidate_sha256": candidate.candidate_sha256,
        "gate_registry_sha256": gates.registry_sha256,
        "window_sha256": window.window_sha256,
        "ingestion_snapshot_sha256": bundle.snapshot.snapshot_sha256,
        "paper_run_sha256": bundle.run.run_sha256,
        "economics_sha256": bundle.economics.report_sha256,
        "gate_sha256": bundle.gate.report_sha256,
        "audit_sha256": audit_sha256,
    }
    if (
        tuple(identity["symbols"]) != SYMBOLS
        or any(
            not _valid_sha(identity[name])
            for name in (
                "candidate_sha256",
                "gate_registry_sha256",
                "window_sha256",
                "ingestion_snapshot_sha256",
                "paper_run_sha256",
                "economics_sha256",
                "gate_sha256",
                "audit_sha256",
            )
        )
    ):
        raise ValidationScenarioError("Accepted P10 identity is invalid")
    return identity


@dataclass(frozen=True, slots=True)
class ValidationAcceptedFixture:
    bundle: ValidationEvidenceBundle
    canonical_audit_json: str
    audit_sha256: str

    def __post_init__(self):
        if (
            not isinstance(self.bundle, ValidationEvidenceBundle)
            or not self.bundle.ready
            or not isinstance(self.canonical_audit_json, str)
            or not self.canonical_audit_json.endswith("\n")
            or not _valid_sha(self.audit_sha256)
            or len(self.canonical_audit_json.encode("utf-8")) > MAX_ARTIFACT_BYTES
        ):
            raise ValidationScenarioError("Accepted validation fixture is invalid")
        try:
            record = json.loads(self.canonical_audit_json)
        except json.JSONDecodeError:
            raise ValidationScenarioError("Accepted audit JSON is invalid") from None
        accepted_record, accepted_json = _export_payload(self.bundle)
        if (
            accepted_json != self.canonical_audit_json
            or accepted_record.get("audit_sha256") != self.audit_sha256
            or record != accepted_record
            or _audit_digest(record) != self.audit_sha256
            or _verify_audit(record, self) != ACCEPTED
        ):
            raise ValidationScenarioError("Accepted P10 audit binding is invalid")

    @property
    def identity(self):
        return _accepted_identity(self.bundle, self.audit_sha256)


def accepted_validation_fixture(bundle):
    if not isinstance(bundle, ValidationEvidenceBundle) or not bundle.ready:
        raise ValidationScenarioError("Accepted fixture bundle is invalid")
    record, encoded = _export_payload(bundle)
    return ValidationAcceptedFixture(
        bundle=bundle,
        canonical_audit_json=encoded,
        audit_sha256=record["audit_sha256"],
    )


def _safety_matches(record, accepted):
    paper = record.get("forward_paper")
    gate = record.get("gate")
    accepted_paper = accepted.get("forward_paper")
    accepted_gate = accepted.get("gate")
    if (
        not isinstance(paper, dict)
        or not isinstance(gate, dict)
        or not isinstance(accepted_paper, dict)
        or not isinstance(accepted_gate, dict)
    ):
        return False
    return (
        paper.get("safety") == accepted_paper.get("safety")
        and gate.get("safety") == accepted_gate.get("safety")
    )


def _verify_audit(record, fixture):
    if (
        not isinstance(record, dict)
        or set(record) != _REQUIRED_AUDIT_KEYS
        or record.get("schema_version") != 1
        or not _valid_sha(record.get("audit_sha256"))
    ):
        return DIGEST_REJECTED
    try:
        if _audit_digest(record) != record["audit_sha256"]:
            return DIGEST_REJECTED
        accepted = json.loads(fixture.canonical_audit_json)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return DIGEST_REJECTED

    if record.get("candidate") != accepted.get("candidate"):
        return CANDIDATE_REJECTED
    if record.get("gate_registry") != accepted.get("gate_registry"):
        return GATES_REJECTED
    if record.get("window") != accepted.get("window"):
        return WINDOW_REJECTED
    if not _safety_matches(record, accepted):
        return SAFETY_REJECTED
    if record.get("provenance") != accepted.get("provenance"):
        return PROVENANCE_REJECTED
    if record.get("forward_paper") != accepted.get("forward_paper"):
        return PAPER_REJECTED
    if record.get("economics") != accepted.get("economics"):
        return ECONOMICS_REJECTED
    if record.get("gate") != accepted.get("gate"):
        return GATE_RESULT_REJECTED
    if record != accepted:
        return DIGEST_REJECTED
    return ACCEPTED


def _resign(record):
    result = copy.deepcopy(record)
    result["audit_sha256"] = _audit_digest(result)
    return result


def _baseline_record(fixture):
    return json.loads(fixture.canonical_audit_json)


def _scenario_pre_window(record):
    start = ForwardWindowSeal().forward_window_start_ms
    datasets = record["provenance"]["ingestion"]["datasets"]
    datasets[0]["requested_start_time_ms"] = start - 900_000
    datasets[0]["first_open_time_ms"] = start - 900_000
    return PROVENANCE_REJECTED


def _scenario_candidate_mutation(record):
    record["candidate"]["configuration_sha256"] = "0" * 64
    return CANDIDATE_REJECTED


def _scenario_threshold_mutation(record):
    record["gate_registry"]["net_pnl_after_costs"][
        "minimum_net_return_after_costs"
    ] = "0"
    return GATES_REJECTED


def _scenario_fee_slippage_removal(record):
    pooled = record["economics"]["pooled"]
    pooled["executed_fee_quote"] = "0"
    pooled["executed_slippage_quote"] = "0"
    pooled["executed_total_cost_quote"] = "0"
    return ECONOMICS_REJECTED


def _scenario_fabricated_positive_pnl(record):
    pooled = record["economics"]["pooled"]
    pooled["net_pnl_after_costs_quote"] = "1000"
    pooled["net_return_after_costs"] = "0.05"
    pooled["final_equity_quote"] = "21000"
    return ECONOMICS_REJECTED


def _scenario_drawdown_suppression(record):
    pooled = record["economics"]["pooled"]
    for key in ("realized_drawdown", "sampled_liquidation_drawdown"):
        pooled[key]["maximum_drawdown_fraction"] = "0"
        pooled[key]["maximum_drawdown_quote"] = "0"
    return ECONOMICS_REJECTED


def _scenario_sample_deletion(record):
    symbol = record["economics"]["symbols"][0]
    trades = symbol.get("trades")
    if not isinstance(trades, list) or not trades:
        raise ValidationScenarioError("Sample deletion fixture has no completed trade")
    symbol["trades"] = trades[1:]
    symbol["completed_trades"] = max(0, int(symbol["completed_trades"]) - 1)
    record["economics"]["pooled"]["completed_trades"] = max(
        0,
        int(record["economics"]["pooled"]["completed_trades"]) - 1,
    )
    return ECONOMICS_REJECTED


def _scenario_cross_symbol_window(record):
    record["window"]["window_id"] = "FOREIGN_WINDOW"
    datasets = record["provenance"]["ingestion"]["datasets"]
    datasets[0]["symbol"] = "ETHUSDT"
    return WINDOW_REJECTED


def _scenario_data_quality_failure(record):
    ingestion = record["provenance"]["ingestion"]
    ingestion["quality_pass"] = False
    ingestion["datasets"][0]["quality_pass"] = False
    return PROVENANCE_REJECTED


def _scenario_risk_safety_breach(record):
    record["forward_paper"]["safety"]["trade_permission"] = True
    record["forward_paper"]["safety"]["order_endpoint"] = True
    record["gate"]["safety"]["trade_permission"] = True
    record["gate"]["safety"]["order_endpoint"] = True
    return SAFETY_REJECTED


def _scenario_live_upgrade(record):
    record["forward_paper"]["safety"]["strategy_evidence"] = "PROVEN"
    record["gate"]["safety"]["strategy_evidence"] = "PROVEN"
    record["gate"]["safety"]["p11_unlocked"] = True
    record["gate"]["safety"]["paper_only"] = False
    record["gate"]["safety"]["live_master_lock"] = "ON"
    return SAFETY_REJECTED


_HANDLERS = {
    "PRE_WINDOW_DATA_CONTAMINATION": _scenario_pre_window,
    "CANDIDATE_MUTATION_AFTER_SEAL": _scenario_candidate_mutation,
    "THRESHOLD_MUTATION_AFTER_SEAL": _scenario_threshold_mutation,
    "FEE_SLIPPAGE_REMOVAL": _scenario_fee_slippage_removal,
    "FABRICATED_POSITIVE_PNL": _scenario_fabricated_positive_pnl,
    "DRAWDOWN_SUPPRESSION": _scenario_drawdown_suppression,
    "SAMPLE_DELETION_CHERRY_PICKING": _scenario_sample_deletion,
    "CROSS_SYMBOL_CROSS_WINDOW_MATERIAL": _scenario_cross_symbol_window,
    "DATA_QUALITY_FAILURE": _scenario_data_quality_failure,
    "RISK_SAFETY_BREACH": _scenario_risk_safety_breach,
    "EVIDENCE_LABEL_LIVE_READINESS_UPGRADE": _scenario_live_upgrade,
}


def _run_scenario(fixture, name):
    if (
        not isinstance(fixture, ValidationAcceptedFixture)
        or name not in SCENARIOS
    ):
        raise ValidationScenarioError("Scenario fixture or name is invalid")

    accepted_before = fixture.canonical_audit_json
    identity_before = fixture.identity
    if _verify_audit(json.loads(accepted_before), fixture) != ACCEPTED:
        raise ValidationScenarioError("Accepted baseline does not verify")

    attack = _baseline_record(fixture)
    expected_code = _HANDLERS[name](attack)
    attack = _resign(attack)
    observed_code = _verify_audit(attack, fixture)

    accepted_after = fixture.canonical_audit_json
    identity_after = fixture.identity
    expected = {
        "attack_resigned": True,
        "verification_code": expected_code,
        "accepted_audit_unchanged": True,
        "accepted_identities_unchanged": True,
        "p11_unlocked": False,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }
    observed = {
        "attack_resigned": _audit_digest(attack) == attack["audit_sha256"],
        "verification_code": observed_code,
        "accepted_audit_unchanged": accepted_after == accepted_before,
        "accepted_identities_unchanged": identity_after == identity_before,
        "p11_unlocked": False,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
    }
    if (
        observed_code == ACCEPTED
        or expected != observed
        or _verify_audit(json.loads(accepted_after), fixture) != ACCEPTED
    ):
        raise ValidationScenarioError(
            f"Scenario failed closed invariant: {name}"
        )

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "symbols": list(SYMBOLS),
        "scenario": name,
        "accepted_identity": identity_before,
        "attack_audit_sha256": attack["audit_sha256"],
        "expected": expected,
        "observed": observed,
        "passed": True,
        "replay_equal": True,
        "paper_only": True,
        "live_master_lock": "OFF",
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "p11_unlocked": False,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "threshold_mutation_allowed": False,
        "candidate_mutation_allowed": False,
        "accepted_evidence_mutated": False,
        "real_network_called": False,
    }
    record["result_sha256"] = _sha256(_json(record))
    return record


def scenario_artifact_json(record):
    required = {
        "schema_version",
        "artifact_kind",
        "symbols",
        "scenario",
        "accepted_identity",
        "attack_audit_sha256",
        "expected",
        "observed",
        "passed",
        "replay_equal",
        "paper_only",
        "live_master_lock",
        "strategy_evidence",
        "p11_unlocked",
        "trade_permission",
        "order_endpoint",
        "ai_direct_execution",
        "threshold_mutation_allowed",
        "candidate_mutation_allowed",
        "accepted_evidence_mutated",
        "real_network_called",
        "result_sha256",
    }
    if (
        not isinstance(record, dict)
        or set(record) != required
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("artifact_kind") != ARTIFACT_KIND
        or tuple(record.get("symbols", ())) != SYMBOLS
        or record.get("scenario") not in SCENARIOS
        or record.get("passed") is not True
        or record.get("replay_equal") is not True
        or record.get("expected") != record.get("observed")
        or record.get("paper_only") is not True
        or record.get("live_master_lock") != "OFF"
        or record.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or record.get("p11_unlocked") is not False
        or record.get("trade_permission") is not False
        or record.get("order_endpoint") is not False
        or record.get("ai_direct_execution") is not False
        or record.get("threshold_mutation_allowed") is not False
        or record.get("candidate_mutation_allowed") is not False
        or record.get("accepted_evidence_mutated") is not False
        or record.get("real_network_called") is not False
        or not _valid_sha(record.get("attack_audit_sha256"))
    ):
        raise ValidationScenarioError("Scenario artifact identity is invalid")

    identity = record.get("accepted_identity")
    if (
        not isinstance(identity, dict)
        or tuple(identity.get("symbols", ())) != SYMBOLS
        or any(
            not _valid_sha(identity.get(name))
            for name in (
                "candidate_sha256",
                "gate_registry_sha256",
                "window_sha256",
                "ingestion_snapshot_sha256",
                "paper_run_sha256",
                "economics_sha256",
                "gate_sha256",
                "audit_sha256",
            )
        )
    ):
        raise ValidationScenarioError("Scenario accepted identity is invalid")

    material = dict(record)
    result_sha = material.pop("result_sha256", None)
    if result_sha != _sha256(_json(material)):
        raise ValidationScenarioError("Scenario artifact digest is inconsistent")

    encoded = _json(record)
    lowered = encoded.casefold()
    forbidden = (
        '"api_key"',
        '"api_secret"',
        '"password"',
        '"private_key"',
        '"credential"',
        '"credentials"',
        '"database_path"',
        '"raw_response"',
        "traceback",
        "select ",
        "update ",
        "insert ",
        "delete ",
    )
    if (
        any(item in lowered for item in forbidden)
        or len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES
    ):
        raise ValidationScenarioError("Scenario artifact contains forbidden material")
    return encoded


@dataclass(frozen=True, slots=True)
class ValidationScenarioResult:
    name: str
    artifact_json: str
    result_sha256: str

    def __post_init__(self):
        if (
            self.name not in SCENARIOS
            or not isinstance(self.artifact_json, str)
            or not self.artifact_json.endswith("\n")
            or self.result_sha256 != _sha256(self.artifact_json)
        ):
            raise ValidationScenarioError("Scenario result identity is invalid")
        try:
            record = json.loads(self.artifact_json)
        except json.JSONDecodeError:
            raise ValidationScenarioError("Scenario result JSON is invalid") from None
        if (
            record.get("scenario") != self.name
            or scenario_artifact_json(record) != self.artifact_json
        ):
            raise ValidationScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class ValidationScenarioMatrixResult:
    runs: tuple[ValidationScenarioResult, ...]
    index_json: str

    def __post_init__(self):
        if (
            type(self.runs) is not tuple
            or tuple(item.name for item in self.runs) != SCENARIOS
            or not isinstance(self.index_json, str)
            or not self.index_json.endswith("\n")
            or len(self.index_json.encode("utf-8")) > MAX_ARTIFACT_BYTES
        ):
            raise ValidationScenarioError("Scenario matrix is incomplete or unordered")

        identities = []
        for item in self.runs:
            record = json.loads(item.artifact_json)
            identities.append(record["accepted_identity"])
        if not identities or any(value != identities[0] for value in identities[1:]):
            raise ValidationScenarioError("Accepted P10 identity drifted across matrix")

        expected_index = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": MATRIX_KIND,
            "symbols": list(SYMBOLS),
            "scenarios": list(SCENARIOS),
            "runs": [
                {
                    "scenario": item.name,
                    "file": _filename(item.name),
                    "sha256": item.result_sha256,
                    "passed": True,
                    "replay_equal": True,
                }
                for item in self.runs
            ],
            "accepted_identity": identities[0],
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "paper_only": True,
            "live_master_lock": "OFF",
            "p11_unlocked": False,
            "trade_permission": False,
            "order_endpoint": False,
            "ai_direct_execution": False,
            "threshold_mutation_allowed": False,
            "candidate_mutation_allowed": False,
            "accepted_evidence_mutated": False,
            "real_network_called": False,
        }
        try:
            actual = json.loads(self.index_json)
        except json.JSONDecodeError:
            raise ValidationScenarioError("Scenario matrix index JSON is invalid") from None
        if actual != expected_index or _json(actual) != self.index_json:
            raise ValidationScenarioError("Scenario matrix index is noncanonical")


def _filename(name):
    return f"{name.lower().replace('_', '-')}.json"


def run_adversarial_validation_matrix(fixture):
    if not isinstance(fixture, ValidationAcceptedFixture):
        raise ValidationScenarioError("Validation scenario fixture is invalid")

    runs = []
    for name in SCENARIOS:
        first = scenario_artifact_json(_run_scenario(fixture, name))
        replay = scenario_artifact_json(_run_scenario(fixture, name))
        if first != replay:
            raise ValidationScenarioError(f"Scenario replay diverged: {name}")
        runs.append(
            ValidationScenarioResult(
                name=name,
                artifact_json=first,
                result_sha256=_sha256(first),
            )
        )

    identity = json.loads(runs[0].artifact_json)["accepted_identity"]
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "runs": [
            {
                "scenario": item.name,
                "file": _filename(item.name),
                "sha256": item.result_sha256,
                "passed": True,
                "replay_equal": True,
            }
            for item in runs
        ],
        "accepted_identity": identity,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "live_master_lock": "OFF",
        "p11_unlocked": False,
        "trade_permission": False,
        "order_endpoint": False,
        "ai_direct_execution": False,
        "threshold_mutation_allowed": False,
        "candidate_mutation_allowed": False,
        "accepted_evidence_mutated": False,
        "real_network_called": False,
    }
    return ValidationScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_validation_matrix(result, output_dir):
    if not isinstance(result, ValidationScenarioMatrixResult):
        raise ValidationScenarioError("Scenario matrix output is invalid")
    target = (
        Path(output_dir)
        if isinstance(output_dir, (str, Path)) and str(output_dir)
        else None
    )
    if target is None:
        raise ValidationScenarioError("Scenario evidence output directory is invalid")
    if target.exists():
        raise ValidationScenarioError("Existing scenario evidence will not be overwritten")
    parent = target.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise ValidationScenarioError("Scenario evidence parent is invalid")

    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir()
        payloads = {"p10-009-index.json": result.index_json}
        for item in result.runs:
            payloads[_filename(item.name)] = item.artifact_json
        if len(payloads) != 1 + len(SCENARIOS):
            raise ValidationScenarioError("Scenario evidence file count is invalid")

        total = 0
        for name in sorted(payloads):
            encoded = payloads[name].encode("utf-8")
            total += len(encoded)
            if (
                not encoded
                or len(encoded) > MAX_ARTIFACT_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise ValidationScenarioError("Scenario evidence size is invalid")
            (temporary / name).write_bytes(encoded)

        written = tuple(sorted(temporary.iterdir(), key=lambda item: item.name))
        if (
            len(written) > MAX_EVIDENCE_FILES
            or any(item.is_symlink() or not item.is_file() for item in written)
        ):
            raise ValidationScenarioError("Scenario evidence contents are invalid")
        os.replace(temporary, target)
        temporary = None
    except ValidationScenarioError:
        raise
    except OSError:
        raise ValidationScenarioError("Scenario evidence publication failed") from None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def validation_matrix_sha256(result):
    if not isinstance(result, ValidationScenarioMatrixResult):
        raise ValidationScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)
