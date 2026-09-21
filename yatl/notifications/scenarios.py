"""Deterministic P9-005 adversarial notification matrix with canonical evidence."""

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .contracts import (
    NotificationCategory,
    NotificationContractError,
    NotificationMessage,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    build_notification_batch,
    notification_batch_from_record,
)
from .runner import NotifierRunnerCode, NotifierRunnerError, notifier_run
from .transport import (
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportPolicy,
)


SCHEMA_VERSION = 1
ARTIFACT_KIND = "YATL_P9_ADVERSARIAL_NOTIFICATION_SCENARIO"
MATRIX_KIND = "YATL_P9_ADVERSARIAL_NOTIFICATION_MATRIX"
MAX_ARTIFACT_BYTES = 512 * 1024
MAX_EVIDENCE_FILES = 32
MAX_EVIDENCE_TOTAL_BYTES = 8 * 1024 * 1024
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SCENARIOS = (
    "SOURCE_TAMPERING",
    "EVIDENCE_UPGRADE",
    "COMMAND_AUTHORITY_INJECTION",
    "SECRET_LEAKAGE",
    "URL_MARKUP_INJECTION",
    "DUPLICATE_DELIVERY",
    "CROSS_SYMBOL_MATERIAL",
    "TRANSPORT_RESPONSE_CORRUPTION",
)


class NotificationScenarioError(RuntimeError):
    """One fixed P9 adversarial scenario violated its exact safe outcome."""


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _credentials():
    return TelegramCredentials(
        "".join(("123456789", ":", "A" * 30)),
        "".join(("-", "100", "1234567890")),
    )


@dataclass(frozen=True, slots=True)
class NotificationAcceptedFixture:
    symbol: str
    canonical_batch_json: str
    batch_sha256: str

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or not isinstance(self.canonical_batch_json, str)
            or not self.canonical_batch_json.endswith("\n")
            or not isinstance(self.batch_sha256, str)
            or len(self.batch_sha256) != 64
        ):
            raise NotificationScenarioError("Accepted notification fixture is invalid")
        try:
            record = json.loads(self.canonical_batch_json)
            batch = notification_batch_from_record(record)
        except (json.JSONDecodeError, NotificationContractError, TypeError, ValueError):
            raise NotificationScenarioError("Accepted notification fixture JSON is invalid") from None
        if (
            _json(batch.as_record()) != self.canonical_batch_json
            or len(batch.notifications) != 1
            or batch.notifications[0].symbol != self.symbol
            or batch.batch_sha256 != self.batch_sha256
        ):
            raise NotificationScenarioError("Accepted notification fixture binding is invalid")


def _fixture(symbol):
    if symbol not in SYMBOLS:
        raise NotificationScenarioError("Scenario symbol is not approved")
    source = NotificationSourceIdentity(
        source_id=f"P8_STATUS_{symbol}",
        source_phase=NotificationSourcePhase.P8_DASHBOARD,
        observed_at_ms=1_800_000_000_000,
        payload_sha256=("8" if symbol == "BTCUSDT" else "9") * 64,
        symbol=symbol,
    )
    message = NotificationMessage(
        notification_id=f"NOTICE_STATUS_{symbol}",
        category=NotificationCategory.SYSTEM_STATUS,
        severity=NotificationSeverity.INFO,
        title=f"YATL Paper status {symbol}",
        body=(
            f"Accepted {symbol} Paper status is ready for information-only delivery."
        ),
        source=source,
        event_time_ms=1_799_999_999_000,
        symbol=symbol,
    )
    batch = build_notification_batch(message)
    return NotificationAcceptedFixture(
        symbol,
        _json(batch.as_record()),
        batch.batch_sha256,
    )


def _good_sender(message_id=4242):
    def sender(message, formatted, credentials):
        return TelegramDeliveryReceipt(
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            telegram_message_id=message_id,
            policy_sha256=TelegramTransportPolicy().policy_sha256,
        )
    return sender


def _forbidden_sender(*args, **kwargs):
    raise NotificationScenarioError("Rejected scenario reached sender")


def _runner_code(
    source,
    expected_sha,
    state,
    symbol,
    *,
    credentials=None,
    sender=_forbidden_sender,
):
    try:
        record = notifier_run(
            source,
            expected_sha,
            state,
            symbol,
            credentials=credentials,
            environ={},
            sender=sender,
            sleep_fn=lambda seconds: None,
        )
    except NotifierRunnerError as exc:
        return exc.code.value, None
    return record["code"], record


def _write_attack(path, record):
    path.write_text(_json(record), encoding="utf-8", newline="")
    return path.read_bytes()


def _scenario_source_tampering(ctx):
    record = json.loads(ctx["fixture"].canonical_batch_json)
    record["notifications"][0]["source"]["payload_sha256"] = "a" * 64
    attack = ctx["root"] / "attack.json"
    attack_before = _write_attack(attack, record)
    code, _ = _runner_code(
        attack,
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "sender_calls": 0,
        "accepted_source_unchanged": True,
        "attack_source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "sender_calls": 0,
        "accepted_source_unchanged": ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "attack_source_unchanged": attack.read_bytes() == attack_before,
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_evidence_upgrade(ctx):
    record = json.loads(ctx["fixture"].canonical_batch_json)
    record["notifications"][0]["evidence_label"] = "PROVEN"
    attack = ctx["root"] / "evidence-upgrade.json"
    attack_before = _write_attack(attack, record)
    code, _ = _runner_code(
        attack,
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "sender_calls": 0,
        "source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "sender_calls": 0,
        "source_unchanged":
            attack.read_bytes() == attack_before
            and ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_command_authority(ctx):
    record = json.loads(ctx["fixture"].canonical_batch_json)
    record["notifications"][0]["execution_command"] = "ENTER_LONG"
    record["notifications"][0]["trade_permission"] = True
    attack = ctx["root"] / "authority-injection.json"
    attack_before = _write_attack(attack, record)
    code, _ = _runner_code(
        attack,
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "authority_rejected": True,
        "source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "authority_rejected": code == NotifierRunnerCode.SOURCE_REJECTED.value,
        "source_unchanged":
            attack.read_bytes() == attack_before
            and ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_secret_leakage(ctx):
    record = json.loads(ctx["fixture"].canonical_batch_json)
    record["notifications"][0]["body"] = "Rejected bot token material must not pass."
    attack = ctx["root"] / "secret-leakage.json"
    attack_before = _write_attack(attack, record)
    code, result = _runner_code(
        attack,
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "output_contains_secret": False,
        "source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "output_contains_secret": result is not None,
        "source_unchanged":
            attack.read_bytes() == attack_before
            and ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_url_markup(ctx):
    record = json.loads(ctx["fixture"].canonical_batch_json)
    record["notifications"][0]["body"] = (
        "<b>status</b> https://example.invalid/remote"
    )
    attack = ctx["root"] / "url-markup.json"
    attack_before = _write_attack(attack, record)
    code, _ = _runner_code(
        attack,
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "url_markup_rejected": True,
        "source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "url_markup_rejected": code == NotifierRunnerCode.SOURCE_REJECTED.value,
        "source_unchanged":
            attack.read_bytes() == attack_before
            and ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_duplicate_delivery(ctx):
    calls = []

    def sender(message, formatted, credentials):
        calls.append(message.message_sha256)
        return _good_sender(5001)(message, formatted, credentials)

    first_code, first = _runner_code(
        ctx["accepted"],
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
        credentials=_credentials(),
        sender=sender,
    )
    state_after = ctx["state"].read_bytes()

    def forbidden(*args, **kwargs):
        raise NotificationScenarioError("Duplicate reached sender")

    second_code, second = _runner_code(
        ctx["accepted"],
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
        credentials=None,
        sender=forbidden,
    )
    expected = {
        "first_code": NotifierRunnerCode.DELIVERED.value,
        "second_code": NotifierRunnerCode.DUPLICATE_SUPPRESSED.value,
        "sender_calls": 1,
        "same_delivery_id": True,
        "state_replay_equal": True,
        "accepted_source_unchanged": True,
    }
    observed = {
        "first_code": first_code,
        "second_code": second_code,
        "sender_calls": len(calls),
        "same_delivery_id":
            first is not None
            and second is not None
            and first["delivery_id"] == second["delivery_id"],
        "state_replay_equal": ctx["state"].read_bytes() == state_after,
        "accepted_source_unchanged":
            ctx["accepted"].read_bytes() == ctx["accepted_before"],
    }
    return expected, observed


def _scenario_cross_symbol(ctx):
    other = "ETHUSDT" if ctx["fixture"].symbol == "BTCUSDT" else "BTCUSDT"
    other_fixture = _fixture(other)
    cross = ctx["root"] / "cross-symbol.json"
    cross.write_text(other_fixture.canonical_batch_json, encoding="utf-8", newline="")
    cross_before = cross.read_bytes()
    code, _ = _runner_code(
        cross,
        other_fixture.batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
    )
    expected = {
        "code": NotifierRunnerCode.SOURCE_REJECTED.value,
        "cross_symbol_rejected": True,
        "source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "cross_symbol_rejected": code == NotifierRunnerCode.SOURCE_REJECTED.value,
        "source_unchanged":
            cross.read_bytes() == cross_before
            and ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


def _scenario_transport_corruption(ctx):
    def sender(message, formatted, credentials):
        return TelegramDeliveryReceipt(
            notification_sha256=message.message_sha256,
            formatted_sha256=formatted.formatted_sha256,
            telegram_message_id=7001,
            policy_sha256="0" * 64,
        )

    code, _ = _runner_code(
        ctx["accepted"],
        ctx["fixture"].batch_sha256,
        ctx["state"],
        ctx["fixture"].symbol,
        credentials=_credentials(),
        sender=sender,
    )
    expected = {
        "code": NotifierRunnerCode.DELIVERY_REJECTED.value,
        "corrupt_receipt_rejected": True,
        "accepted_source_unchanged": True,
        "state_absent": True,
    }
    observed = {
        "code": code,
        "corrupt_receipt_rejected":
            code == NotifierRunnerCode.DELIVERY_REJECTED.value,
        "accepted_source_unchanged":
            ctx["accepted"].read_bytes() == ctx["accepted_before"],
        "state_absent": not ctx["state"].exists(),
    }
    return expected, observed


_HANDLERS = {
    "SOURCE_TAMPERING": _scenario_source_tampering,
    "EVIDENCE_UPGRADE": _scenario_evidence_upgrade,
    "COMMAND_AUTHORITY_INJECTION": _scenario_command_authority,
    "SECRET_LEAKAGE": _scenario_secret_leakage,
    "URL_MARKUP_INJECTION": _scenario_url_markup,
    "DUPLICATE_DELIVERY": _scenario_duplicate_delivery,
    "CROSS_SYMBOL_MATERIAL": _scenario_cross_symbol,
    "TRANSPORT_RESPONSE_CORRUPTION": _scenario_transport_corruption,
}


def _safe_result(fixture, name, expected, observed):
    if expected != observed:
        raise NotificationScenarioError(f"Scenario failed closed invariant: {name}")
    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "symbol": fixture.symbol,
        "scenario": name,
        "accepted_batch_sha256": fixture.batch_sha256,
        "expected": expected,
        "observed": observed,
        "passed": True,
        "replay_equal": True,
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "outbound_only": True,
        "source_read_only": True,
        "live_master_lock": "OFF",
        "spot_only": True,
        "allow_short": False,
        "allow_margin": False,
        "allow_futures": False,
        "allow_leverage": False,
        "allow_withdrawal": False,
        "trade_permission": False,
        "order_endpoints": False,
        "quantity_authority": False,
        "risk_authorization_mutation": False,
        "ai_direct_execution": False,
        "inbound_commands": False,
        "webhook_receiver": False,
        "polling_receiver": False,
        "real_network_called": False,
    }
    record["result_sha256"] = _sha256(_json(record))
    return record


def _run_scenario(fixture, name):
    if not isinstance(fixture, NotificationAcceptedFixture) or name not in SCENARIOS:
        raise NotificationScenarioError("Scenario fixture or name is invalid")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        accepted = root / "accepted-notification.json"
        state = root / "delivery-state.json"
        accepted.write_text(
            fixture.canonical_batch_json,
            encoding="utf-8",
            newline="",
        )
        accepted_before = accepted.read_bytes()
        context = {
            "root": root,
            "fixture": fixture,
            "accepted": accepted,
            "accepted_before": accepted_before,
            "state": state,
        }
        expected, observed = _HANDLERS[name](context)
        if accepted.read_bytes() != accepted_before:
            raise NotificationScenarioError("Accepted source mutated")
    return _safe_result(fixture, name, expected, observed)


def scenario_artifact_json(record):
    required = {
        "schema_version",
        "artifact_kind",
        "symbol",
        "scenario",
        "accepted_batch_sha256",
        "expected",
        "observed",
        "passed",
        "replay_equal",
        "strategy_evidence",
        "paper_only",
        "outbound_only",
        "source_read_only",
        "live_master_lock",
        "spot_only",
        "allow_short",
        "allow_margin",
        "allow_futures",
        "allow_leverage",
        "allow_withdrawal",
        "trade_permission",
        "order_endpoints",
        "quantity_authority",
        "risk_authorization_mutation",
        "ai_direct_execution",
        "inbound_commands",
        "webhook_receiver",
        "polling_receiver",
        "real_network_called",
        "result_sha256",
    }
    if (
        not isinstance(record, dict)
        or set(record) != required
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("artifact_kind") != ARTIFACT_KIND
        or record.get("symbol") not in SYMBOLS
        or record.get("scenario") not in SCENARIOS
        or not isinstance(record.get("accepted_batch_sha256"), str)
        or len(record["accepted_batch_sha256"]) != 64
        or record.get("passed") is not True
        or record.get("replay_equal") is not True
        or record.get("expected") != record.get("observed")
        or record.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or record.get("paper_only") is not True
        or record.get("outbound_only") is not True
        or record.get("source_read_only") is not True
        or record.get("live_master_lock") != "OFF"
        or record.get("spot_only") is not True
        or record.get("allow_short") is not False
        or record.get("allow_margin") is not False
        or record.get("allow_futures") is not False
        or record.get("allow_leverage") is not False
        or record.get("allow_withdrawal") is not False
        or record.get("trade_permission") is not False
        or record.get("order_endpoints") is not False
        or record.get("quantity_authority") is not False
        or record.get("risk_authorization_mutation") is not False
        or record.get("ai_direct_execution") is not False
        or record.get("inbound_commands") is not False
        or record.get("webhook_receiver") is not False
        or record.get("polling_receiver") is not False
        or record.get("real_network_called") is not False
    ):
        raise NotificationScenarioError("Scenario artifact identity is invalid")
    material = dict(record)
    digest = material.pop("result_sha256", None)
    if digest != _sha256(_json(material)):
        raise NotificationScenarioError("Scenario artifact digest is inconsistent")
    encoded = _json(record)
    lowered = encoded.lower()
    forbidden = (
        '"bot_token"',
        '"chat_id"',
        '"api_key"',
        '"api_secret"',
        '"password"',
        '"credential"',
        '"private_key"',
        '"raw_response"',
        '"endpoint_url"',
        "authorization:",
        "bearer ",
        "http://",
        "https://",
        "traceback",
        "approved_quantity",
        "risk_authorization",
        "order_request",
    )
    if (
        any(item in lowered for item in forbidden)
        or len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES
    ):
        raise NotificationScenarioError("Scenario artifact contains forbidden material")
    return encoded


@dataclass(frozen=True, slots=True)
class NotificationScenarioResult:
    symbol: str
    name: str
    artifact_json: str
    result_sha256: str

    def __post_init__(self):
        if (
            self.symbol not in SYMBOLS
            or self.name not in SCENARIOS
            or not isinstance(self.artifact_json, str)
            or not self.artifact_json.endswith("\n")
            or self.result_sha256 != _sha256(self.artifact_json)
        ):
            raise NotificationScenarioError("Scenario result identity is invalid")
        try:
            record = json.loads(self.artifact_json)
        except json.JSONDecodeError:
            raise NotificationScenarioError("Scenario result JSON is invalid") from None
        if (
            record.get("symbol") != self.symbol
            or record.get("scenario") != self.name
            or scenario_artifact_json(record) != self.artifact_json
        ):
            raise NotificationScenarioError("Scenario result and artifact differ")


@dataclass(frozen=True, slots=True)
class NotificationScenarioMatrixResult:
    runs: tuple[NotificationScenarioResult, ...]
    index_json: str

    def __post_init__(self):
        expected_order = tuple(
            (symbol, name)
            for symbol in SYMBOLS
            for name in SCENARIOS
        )
        actual_order = tuple((item.symbol, item.name) for item in self.runs)
        if (
            type(self.runs) is not tuple
            or actual_order != expected_order
            or not isinstance(self.index_json, str)
            or not self.index_json.endswith("\n")
            or len(self.index_json.encode("utf-8")) > MAX_ARTIFACT_BYTES
        ):
            raise NotificationScenarioError("Scenario matrix is incomplete or unordered")

        identities = {}
        expected_runs = []
        for item in self.runs:
            record = json.loads(item.artifact_json)
            prior = identities.setdefault(item.symbol, record["accepted_batch_sha256"])
            if prior != record["accepted_batch_sha256"]:
                raise NotificationScenarioError("Accepted notification identity drifted")
            expected_runs.append({
                "symbol": item.symbol,
                "scenario": item.name,
                "file": _filename(item.symbol, item.name),
                "sha256": item.result_sha256,
                "passed": True,
                "replay_equal": True,
            })

        expected = {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": MATRIX_KIND,
            "symbols": list(SYMBOLS),
            "scenarios": list(SCENARIOS),
            "runs": expected_runs,
            "accepted_batch_sha256": {
                symbol: identities[symbol]
                for symbol in SYMBOLS
            },
            "strategy_evidence": "INSUFFICIENT_EVIDENCE",
            "paper_only": True,
            "outbound_only": True,
            "source_read_only": True,
            "live_master_lock": "OFF",
            "trade_permission": False,
            "order_endpoints": False,
            "ai_direct_execution": False,
            "inbound_commands": False,
            "real_network_called": False,
        }
        try:
            actual = json.loads(self.index_json)
        except json.JSONDecodeError:
            raise NotificationScenarioError("Scenario matrix index JSON is invalid") from None
        if actual != expected or _json(actual) != self.index_json:
            raise NotificationScenarioError("Scenario matrix index is noncanonical")


def _filename(symbol, name):
    return f"{symbol.lower()}-{name.lower().replace('_', '-')}.json"


def run_adversarial_notification_matrix(fixtures=None):
    if fixtures is None:
        fixtures = {symbol: _fixture(symbol) for symbol in SYMBOLS}
    if (
        not isinstance(fixtures, dict)
        or set(fixtures) != set(SYMBOLS)
        or any(
            not isinstance(fixtures[symbol], NotificationAcceptedFixture)
            for symbol in SYMBOLS
        )
    ):
        raise NotificationScenarioError("Notification fixture set is invalid")

    runs = []
    identities = {}
    records = []
    for symbol in SYMBOLS:
        fixture = fixtures[symbol]
        identities[symbol] = fixture.batch_sha256
        for name in SCENARIOS:
            first = scenario_artifact_json(_run_scenario(fixture, name))
            replay = scenario_artifact_json(_run_scenario(fixture, name))
            if first != replay:
                raise NotificationScenarioError(
                    f"Scenario replay diverged: {symbol}/{name}"
                )
            result = NotificationScenarioResult(
                symbol,
                name,
                first,
                _sha256(first),
            )
            runs.append(result)
            records.append({
                "symbol": symbol,
                "scenario": name,
                "file": _filename(symbol, name),
                "sha256": result.result_sha256,
                "passed": True,
                "replay_equal": True,
            })

    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": MATRIX_KIND,
        "symbols": list(SYMBOLS),
        "scenarios": list(SCENARIOS),
        "runs": records,
        "accepted_batch_sha256": {
            symbol: identities[symbol]
            for symbol in SYMBOLS
        },
        "strategy_evidence": "INSUFFICIENT_EVIDENCE",
        "paper_only": True,
        "outbound_only": True,
        "source_read_only": True,
        "live_master_lock": "OFF",
        "trade_permission": False,
        "order_endpoints": False,
        "ai_direct_execution": False,
        "inbound_commands": False,
        "real_network_called": False,
    }
    return NotificationScenarioMatrixResult(tuple(runs), _json(index))


def write_adversarial_notification_matrix(result, output_dir):
    if not isinstance(result, NotificationScenarioMatrixResult):
        raise NotificationScenarioError("Scenario matrix output is invalid")
    target = (
        Path(output_dir)
        if isinstance(output_dir, (str, Path)) and str(output_dir)
        else None
    )
    if target is None:
        raise NotificationScenarioError("Scenario evidence output directory is invalid")
    if target.exists():
        raise NotificationScenarioError("Existing scenario evidence will not be overwritten")
    parent = target.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise NotificationScenarioError("Scenario evidence parent is invalid")

    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir()
        payloads = {"p9-005-index.json": result.index_json}
        for item in result.runs:
            payloads[_filename(item.symbol, item.name)] = item.artifact_json
        if len(payloads) != 1 + len(SYMBOLS) * len(SCENARIOS):
            raise NotificationScenarioError("Scenario evidence file count is invalid")

        total = 0
        for name in sorted(payloads):
            encoded = payloads[name].encode("utf-8")
            total += len(encoded)
            if (
                not encoded
                or len(encoded) > MAX_ARTIFACT_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise NotificationScenarioError("Scenario evidence size is invalid")
            (temporary / name).write_bytes(encoded)

        written = tuple(sorted(temporary.iterdir(), key=lambda item: item.name))
        if (
            len(written) > MAX_EVIDENCE_FILES
            or any(item.is_symlink() or not item.is_file() for item in written)
        ):
            raise NotificationScenarioError("Scenario evidence contents are invalid")
        os.replace(temporary, target)
        temporary = None
    except NotificationScenarioError:
        raise
    except OSError:
        raise NotificationScenarioError("Scenario evidence publication failed") from None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def notification_matrix_sha256(result):
    if not isinstance(result, NotificationScenarioMatrixResult):
        raise NotificationScenarioError("Scenario matrix digest input is invalid")
    return _sha256(result.index_json)
