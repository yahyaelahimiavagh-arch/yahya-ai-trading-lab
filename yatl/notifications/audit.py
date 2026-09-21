"""Independent fail-closed final acceptance audit for complete P9 notifications."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    NotificationCategory,
    NotificationContractError,
    NotificationMessage,
    NotificationPolicy,
    NotificationSeverity,
    NotificationSourceIdentity,
    NotificationSourcePhase,
    build_notification_batch,
    notification_batch_from_record,
)
from .delivery import (
    DeliveryGuardError,
    DeliveryGuardPolicy,
    DeliveryState,
    DeliveryStatus,
    delivery_identity,
    guarded_send,
)
from .formatter import NotificationFormatError, format_notification
from .runner import RUNNER_ID
from .scenarios import (
    MAX_ARTIFACT_BYTES,
    SCENARIOS,
    SYMBOLS,
    NotificationAcceptedFixture,
    NotificationScenarioError,
    run_adversarial_notification_matrix,
    scenario_artifact_json,
)
from .transport import (
    TELEGRAM_HOST,
    TELEGRAM_METHOD,
    TELEGRAM_PATH_SUFFIX,
    TELEGRAM_TRANSPORT_ID,
    TelegramCredentials,
    TelegramDeliveryReceipt,
    TelegramTransportError,
    TelegramTransportPolicy,
)


EXPECTED_NOTIFICATION_POLICY_SHA256 = (
    "e5274de931300114fccffc772c971c99b5ba140a2632d98f897687e591be0a35"
)
EXPECTED_TRANSPORT_POLICY_SHA256 = (
    "26428411750db1d2290e9d54fc60b831f5497077822e3e26be63a60acf9cc9d4"
)
EXPECTED_DELIVERY_POLICY_SHA256 = (
    "6d180d548e5294cb7974ce4023ddff2f83bbbe2b707beb25cfdb76f81bb87533"
)
EXPECTED_INDEX_SHA256 = (
    "30a2c7ff705e9ecc3e83d5fa6b7ec38f9e432a6f6cd9a7f9ae531ca8b040c063"
)
EXPECTED_IDENTITY_SET_SHA256 = (
    "37531b4283d3e7da22040b28eb5c73dfb76d7281938b9170e6d6d31a238206e1"
)
EXPECTED_DELIVERY_RESULTS = {
    "BTCUSDT": {
        "receipt_sha256":
            "3227c782954cd702f37ee47c20afb84a8f70995a0ffba9ff390b74e962e9d39c",
        "state_sha256":
            "bde63ec6a33bcfb24c6873e09897a01d5c3da54317a8a169e9d2ec76c6f9b2ee",
    },
    "ETHUSDT": {
        "receipt_sha256":
            "caac64faa4a4ef313d1e1a8903ad966f9c14f444a023bd990a73c7c7282e9517",
        "state_sha256":
            "9f60be0e7f53f13203191734eb0f3f4e706529d10801b42f5bbe2f837323eb13",
    },
}
EXPECTED_IDENTITIES = {
    "BTCUSDT": {
        "source_sha256":
            "c3760b062c0fc4cf8659706cd7559eb092982abf9578d05e32ee3745caf3b089",
        "message_sha256":
            "ab54d79501ebbc492b463e6fcf6b302fc88c8f35b0e17ef59fc0f01b16611d38",
        "batch_sha256":
            "4ee903b4638a2a206e549b6df566d3f37c8e46e15c276bac048cda7b0bff63e6",
        "formatted_sha256":
            "9e8771647a75c209c59ab8336abfb023571d249e9ccff3fae79653b051a19693",
        "delivery_id":
            "4d5a074dfbd32a7bfb252fe4bc91ed8720e1fb8de17c1bf8775ce67538c98d25",
    },
    "ETHUSDT": {
        "source_sha256":
            "389d269ebb97f85e18c092812b8f71161b2c0270e2884089d55bfcec0eb7fabf",
        "message_sha256":
            "aa3fcc7528806e1537597a72e420b226e77c92c46b514ad26fbd6dfa84377a62",
        "batch_sha256":
            "e565a671acef8774b6484fdd8493e259f98a2b1ca40fdd3a3e5b63618ff4f9f9",
        "formatted_sha256":
            "1e2e1a6d35ef025631f3c2965e75488e48e09e363473bcf4acebccf424767012",
        "delivery_id":
            "18929ca6d6c88af9d0bd2c6d70354064ab12c03fc010a1ed3ad1e3b3fc56089c",
    },
}
MAX_EVIDENCE_TOTAL_BYTES = 8 * 1024 * 1024
EXPECTED_RUNNER_ID = "P9_NOTIFIER_RUNNER_V1"
_HEX = frozenset("0123456789abcdef")


class P9AuditError(RuntimeError):
    """P9 policy, identities, delivery boundaries or evidence are inconsistent."""


def _compact_json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json(value):
    return _compact_json(value) + "\n"


def _sha256(value):
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _audit_policy_hashes():
    notification = NotificationPolicy()
    transport = TelegramTransportPolicy()
    delivery = DeliveryGuardPolicy()

    if notification.policy_sha256 != EXPECTED_NOTIFICATION_POLICY_SHA256:
        raise P9AuditError("Frozen P9 notification policy digest changed")
    if transport.policy_sha256 != EXPECTED_TRANSPORT_POLICY_SHA256:
        raise P9AuditError("Frozen P9 transport policy digest changed")
    if delivery.policy_sha256 != EXPECTED_DELIVERY_POLICY_SHA256:
        raise P9AuditError("Frozen P9 delivery policy digest changed")

    notification_false = (
        notification.allow_telegram_transport,
        notification.allow_network_transport,
        notification.allow_credentials,
        notification.allow_bot_token,
        notification.allow_chat_id,
        notification.allow_inbound_updates,
        notification.allow_inbound_commands,
        notification.allow_callback_actions,
        notification.allow_webhook_receiver,
        notification.allow_polling_receiver,
        notification.allow_execution_control,
        notification.allow_live_control,
        notification.allow_strategy_optimizer,
        notification.allow_risk_authorization_controller,
        notification.allow_api_key_surface,
        notification.allow_source_write,
        notification.allow_short,
        notification.allow_margin,
        notification.allow_futures,
        notification.allow_leverage,
        notification.allow_withdrawal,
        notification.allow_trade_permission,
        notification.allow_order_endpoint,
        notification.allow_ai_command_execution,
        notification.allow_strategy_evidence_upgrade,
    )
    if (
        notification.outbound_only is not True
        or notification.notification_only is not True
        or notification.read_only is not True
        or notification.paper_only is not True
        or notification.live_master_lock != "OFF"
        or notification.spot_only is not True
        or any(value is not False for value in notification_false)
    ):
        raise P9AuditError("P9 notification safety boundary changed")

    transport_false = (
        transport.redirects_allowed,
        transport.proxies_allowed,
        transport.inbound_updates_allowed,
        transport.inbound_commands_allowed,
        transport.callback_actions_allowed,
        transport.webhook_receiver_allowed,
        transport.polling_receiver_allowed,
        transport.execution_control_allowed,
        transport.live_control_allowed,
        transport.trade_permission,
        transport.order_endpoint,
        transport.ai_direct_execution,
    )
    if (
        transport.transport_id != TELEGRAM_TRANSPORT_ID
        or transport.host != TELEGRAM_HOST
        or transport.host != "api.telegram.org"
        or transport.port != 443
        or transport.method != TELEGRAM_METHOD
        or transport.method != "POST"
        or transport.path_suffix != TELEGRAM_PATH_SUFFIX
        or transport.path_suffix != "/sendMessage"
        or transport.tls_required is not True
        or transport.outbound_only is not True
        or transport.send_message_only is not True
        or transport.parse_mode != "NONE"
        or transport.credentials_source != "ENVIRONMENT_ONLY"
        or transport.timeout_seconds != 10.0
        or transport.max_response_bytes != 16_384
        or transport.max_request_bytes != 20_000
        or transport.max_text_chars != 4_096
        or any(value is not False for value in transport_false)
    ):
        raise P9AuditError("P9 transport boundary changed")

    delivery_false = (
        delivery.retry_http_status,
        delivery.retry_api_rejected,
        delivery.retry_invalid_response,
        delivery.persistent_storage,
        delivery.upstream_mutation,
        delivery.control_loop,
        delivery.trade_permission,
        delivery.order_endpoint,
        delivery.ai_direct_execution,
    )
    if (
        delivery.max_delivery_records != 256
        or delivery.max_attempts != 3
        or delivery.network_backoff_seconds != (1, 2)
        or delivery.max_rate_limit_wait_seconds != 30
        or delivery.max_total_wait_seconds != 60
        or delivery.retry_network_error is not True
        or delivery.retry_rate_limit is not True
        or delivery.caller_managed_snapshot is not True
        or any(value is not False for value in delivery_false)
    ):
        raise P9AuditError("P9 delivery guard boundary changed")

    if RUNNER_ID != EXPECTED_RUNNER_ID:
        raise P9AuditError("P9 notifier runner identity changed")

    return (
        notification.policy_sha256,
        transport.policy_sha256,
        delivery.policy_sha256,
    )


def _accepted_fixture(symbol):
    """Build the frozen P9 audit fixture independently of P9-005 scenario helpers."""

    if symbol not in SYMBOLS:
        raise P9AuditError("P9 audit fixture symbol is unsupported")

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
    replay = notification_batch_from_record(batch.as_record())
    formatted = format_notification(message)
    identity = delivery_identity(message, formatted)

    if replay != batch:
        raise P9AuditError("P9 notification contract replay changed")

    observed = {
        "source_sha256": source.identity_sha256,
        "message_sha256": message.message_sha256,
        "batch_sha256": batch.batch_sha256,
        "formatted_sha256": formatted.formatted_sha256,
        "delivery_id": identity,
    }
    if observed != EXPECTED_IDENTITIES[symbol]:
        raise P9AuditError("Frozen P9 notification identity changed")

    return (
        NotificationAcceptedFixture(
            symbol,
            _json(batch.as_record()),
            batch.batch_sha256,
        ),
        observed,
    )


def _audit_identity_set():
    fixtures = {}
    identities = {}
    for symbol in SYMBOLS:
        first_fixture, first = _accepted_fixture(symbol)
        second_fixture, second = _accepted_fixture(symbol)
        if first_fixture != second_fixture or first != second:
            raise P9AuditError("P9 identity replay changed")
        fixtures[symbol] = first_fixture
        identities[symbol] = first

    identity_set_sha = _sha256(_compact_json(identities))
    if (
        identities != EXPECTED_IDENTITIES
        or identity_set_sha != EXPECTED_IDENTITY_SET_SHA256
    ):
        raise P9AuditError("P9 accepted identity set changed")
    return fixtures, identities, identity_set_sha


def _audit_delivery_replay(identities):
    """Recompute delivery acknowledgement and restart dedupe with no real network."""

    if identities != EXPECTED_IDENTITIES:
        raise P9AuditError("P9 delivery replay received unknown identities")

    credentials = TelegramCredentials(
        "".join(("123456789", ":", "A" * 30)),
        "".join(("-", "100", "1234567890")),
    )
    transport_policy = TelegramTransportPolicy()
    results = {}

    for offset, symbol in enumerate(SYMBOLS, start=1):
        fixture, observed = _accepted_fixture(symbol)
        batch = notification_batch_from_record(
            json.loads(fixture.canonical_batch_json)
        )
        message = batch.notifications[0]
        rendered = format_notification(message)
        calls = []

        def sender(
            supplied_message,
            supplied_rendered,
            supplied_credentials,
            *,
            expected_message=message,
            expected_rendered=rendered,
        ):
            if (
                supplied_message != expected_message
                or supplied_rendered != expected_rendered
                or supplied_credentials is not credentials
            ):
                raise P9AuditError("P9 delivery sender binding changed")
            calls.append(supplied_message.message_sha256)
            return TelegramDeliveryReceipt(
                notification_sha256=supplied_message.message_sha256,
                formatted_sha256=supplied_rendered.formatted_sha256,
                telegram_message_id=9_100 + offset,
                policy_sha256=transport_policy.policy_sha256,
            )

        def no_sleep(seconds):
            raise P9AuditError("P9 accepted delivery unexpectedly retried")

        first = guarded_send(
            message,
            rendered,
            credentials,
            state=DeliveryState(),
            sender=sender,
            sleep_fn=no_sleep,
        )
        second = guarded_send(
            message,
            rendered,
            credentials,
            state=first.state,
            sender=sender,
            sleep_fn=no_sleep,
        )
        expected_delivery = EXPECTED_DELIVERY_RESULTS[symbol]
        if (
            observed != identities[symbol]
            or first.status is not DeliveryStatus.DELIVERED
            or second.status is not DeliveryStatus.DUPLICATE_SUPPRESSED
            or first.delivery_id != identities[symbol]["delivery_id"]
            or second.delivery_id != first.delivery_id
            or first.receipt_sha256 != expected_delivery["receipt_sha256"]
            or second.receipt_sha256 != first.receipt_sha256
            or first.state.state_sha256 != expected_delivery["state_sha256"]
            or second.state != first.state
            or first.attempts != 1
            or first.wait_seconds != ()
            or second.attempts != 0
            or second.wait_seconds != ()
            or len(calls) != 1
        ):
            raise P9AuditError("P9 delivery or restart dedupe boundary changed")

        results[symbol] = {
            "delivery_id": first.delivery_id,
            "receipt_sha256": first.receipt_sha256,
            "state_sha256": first.state.state_sha256,
            "sender_calls": len(calls),
            "first_status": first.status.value,
            "restart_status": second.status.value,
        }
    return results


def _filename(symbol, scenario):
    return f"{symbol.lower()}-{scenario.lower().replace('_', '-')}.json"


def _expected_evidence(replay):
    files = {"p9-005-index.json": replay.index_json}
    for item in replay.runs:
        files[_filename(item.symbol, item.name)] = item.artifact_json
    if len(files) != 17:
        raise P9AuditError("P9 adversarial replay file coverage is incomplete")
    return files


def _decode_evidence(name, payload):
    try:
        text = payload.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise P9AuditError(f"P9 evidence JSON is invalid ({name})") from None
    if not isinstance(record, dict) or _json(record) != text:
        raise P9AuditError(f"P9 evidence JSON is noncanonical ({name})")

    lowered = text.casefold()
    forbidden = (
        '"bot_' + 'token"',
        '"chat_' + 'id"',
        '"api_' + 'key"',
        '"api_' + 'secret"',
        '"password"',
        '"credential"',
        '"private_' + 'key"',
        '"raw_' + 'response"',
        '"endpoint_' + 'url"',
        "authorization:",
        "bearer ",
        "http://" ,
        "https://" ,
        "traceback",
        "approved_" + "quantity",
        '"risk_' + 'authorization"',
        '"risk_' + 'authorization_payload"',
        '"risk_' + 'authorization_record"',
        "order_" + "request",
    )
    if (
        any(value in lowered for value in forbidden)
        or len(payload) > MAX_ARTIFACT_BYTES
    ):
        raise P9AuditError(f"P9 evidence contains forbidden material ({name})")
    return text, record


def _read_evidence(directory):
    target = (
        Path(directory)
        if isinstance(directory, (str, Path)) and str(directory)
        else None
    )
    if target is None or not target.is_dir() or target.is_symlink():
        raise P9AuditError("P9 evidence directory is invalid")

    expected_names = {"p9-005-index.json"} | {
        _filename(symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    }
    try:
        paths = tuple(sorted(target.iterdir(), key=lambda item: item.name))
        if (
            {item.name for item in paths} != expected_names
            or any(item.is_symlink() or not item.is_file() for item in paths)
        ):
            raise P9AuditError("P9 evidence directory contents are invalid")

        before = {}
        total = 0
        for path in paths:
            payload = path.read_bytes()
            total += len(payload)
            if (
                not payload
                or len(payload) > MAX_ARTIFACT_BYTES
                or total > MAX_EVIDENCE_TOTAL_BYTES
            ):
                raise P9AuditError("P9 evidence size is invalid")
            before[path.name] = payload
        after = {path.name: path.read_bytes() for path in paths}
    except P9AuditError:
        raise
    except OSError:
        raise P9AuditError("P9 evidence cannot be read safely") from None

    if before != after:
        raise P9AuditError("P9 evidence changed during final audit")

    decoded = {}
    records = {}
    for name, payload in before.items():
        decoded[name], records[name] = _decode_evidence(name, payload)
    return decoded, records


def _audit_evidence_records(records):
    index = records.get("p9-005-index.json")
    if not isinstance(index, dict):
        raise P9AuditError("P9 adversarial index is invalid")

    if (
        index.get("artifact_kind") != "YATL_P9_ADVERSARIAL_NOTIFICATION_MATRIX"
        or index.get("symbols") != list(SYMBOLS)
        or index.get("scenarios") != list(SCENARIOS)
        or index.get("accepted_batch_sha256")
        != {
            symbol: EXPECTED_IDENTITIES[symbol]["batch_sha256"]
            for symbol in SYMBOLS
        }
        or index.get("strategy_evidence") != "INSUFFICIENT_EVIDENCE"
        or index.get("paper_only") is not True
        or index.get("outbound_only") is not True
        or index.get("source_read_only") is not True
        or index.get("live_master_lock") != "OFF"
        or index.get("trade_permission") is not False
        or index.get("order_endpoints") is not False
        or index.get("ai_direct_execution") is not False
        or index.get("inbound_commands") is not False
        or index.get("real_network_called") is not False
    ):
        raise P9AuditError("P9 adversarial index safety boundary changed")

    expected_order = [
        (symbol, scenario)
        for symbol in SYMBOLS
        for scenario in SCENARIOS
    ]
    runs = index.get("runs")
    if (
        not isinstance(runs, list)
        or [(item.get("symbol"), item.get("scenario")) for item in runs]
        != expected_order
    ):
        raise P9AuditError("P9 adversarial index order or coverage changed")

    for item in runs:
        name = item.get("file")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or name not in records
            or item.get("passed") is not True
            or item.get("replay_equal") is not True
            or not _valid_sha(digest)
            or digest != _sha256(_json(records[name]))
        ):
            raise P9AuditError("P9 adversarial index reference changed")
        try:
            if scenario_artifact_json(records[name]) != _json(records[name]):
                raise P9AuditError("P9 adversarial scenario canonicalization changed")
        except NotificationScenarioError:
            raise P9AuditError("P9 adversarial scenario failed validation") from None


def _audit_source_safety():
    root = Path(__file__).parent
    production_files = (
        "contracts.py",
        "projection.py",
        "formatter.py",
        "transport.py",
        "delivery.py",
        "runner.py",
        "scenarios.py",
        "audit.py",
    )
    common_forbidden = (
        ("from yatl." + "execution"),
        ("import yatl." + "execution"),
        ("from yatl." + "account"),
        ("import yatl." + "account"),
        ("from yatl." + "risk"),
        ("import yatl." + "risk"),
        ("open" + "ai"),
        ("anth" + "ropic"),
        ("/api/v3/" + "order"),
        ("/f" + "api"),
        ("/d" + "api"),
        ("with" + "draw("),
    )
    direct_network = (
        ("http." + "client"),
        ("url" + "lib"),
        ("req" + "uests"),
        ("http" + "x"),
        ("aio" + "http"),
        ("web" + "sock" + "ets"),
        ("sock" + "et"),
        ("os." + "environ"),
        ("os." + "getenv"),
    )
    inbound = (
        ("get" + "Updates"),
        ("set" + "Webhook"),
        ("delete" + "Webhook"),
        ("answer" + "CallbackQuery"),
        ("edit" + "MessageText"),
        ("send" + "Photo"),
        ("send" + "Document"),
        ("forward" + "Message"),
    )

    try:
        texts = {
            name: (root / name).read_text(encoding="utf-8")
            for name in production_files
        }
    except OSError:
        raise P9AuditError("P9 source safety scan failed") from None

    for name, text in texts.items():
        lowered = text.casefold()
        if any(value.casefold() in lowered for value in common_forbidden):
            raise P9AuditError("P9 execution/account/risk safety boundary failed")
        if any(value.casefold() in lowered for value in inbound):
            raise P9AuditError("P9 inbound Telegram method detected")
        if name != "transport.py" and any(
            value.casefold() in lowered for value in direct_network
        ):
            raise P9AuditError("P9 direct network/environment capability escaped transport")

    runner = texts["runner.py"].casefold()
    if (
        ("add_" + "subparsers") in runner
        or ("input" + "(") in runner
        or ("eval" + "(") in runner
        or ("exec" + "(") in runner
    ):
        raise P9AuditError("P9 runner operator control surface changed")

    transport = texts["transport.py"].casefold()
    required_transport = (
        ("http." + "client"),
        ("ssl." + "create_default_context"),
        ("os." + "environ"),
        "sendmessage",
    )
    if any(value.casefold() not in transport for value in required_transport):
        raise P9AuditError("P9 accepted transport authority is incomplete")

    return True


@dataclass(frozen=True, slots=True)
class P9AuditResult:
    symbols: int
    scenarios: int
    runs: int
    files: int
    notification_policy_sha256: str
    transport_policy_sha256: str
    delivery_policy_sha256: str
    identity_set_sha256: str
    index_sha256: str
    exact_outcomes: bool
    replay_equal: bool
    identities_recomputed: bool
    formatter_recomputed: bool
    delivery_recomputed: bool
    evidence_verified: bool
    no_write: bool
    source_safe: bool

    def __post_init__(self):
        if (
            (self.symbols, self.scenarios, self.runs, self.files)
            != (2, 8, 16, 17)
            or self.notification_policy_sha256
            != EXPECTED_NOTIFICATION_POLICY_SHA256
            or self.transport_policy_sha256 != EXPECTED_TRANSPORT_POLICY_SHA256
            or self.delivery_policy_sha256 != EXPECTED_DELIVERY_POLICY_SHA256
            or self.identity_set_sha256 != EXPECTED_IDENTITY_SET_SHA256
            or self.index_sha256 != EXPECTED_INDEX_SHA256
            or self.exact_outcomes is not True
            or self.replay_equal is not True
            or self.identities_recomputed is not True
            or self.formatter_recomputed is not True
            or self.delivery_recomputed is not True
            or self.evidence_verified is not True
            or self.no_write is not True
            or self.source_safe is not True
        ):
            raise P9AuditError("P9 final audit result is inconsistent")


def audit_p9(evidence_dir):
    """Independently recompute P9 identities, safety boundaries and P9-005 evidence."""

    try:
        (
            notification_policy_sha,
            transport_policy_sha,
            delivery_policy_sha,
        ) = _audit_policy_hashes()
        source_safe = _audit_source_safety()
        fixtures, identities, identity_set_sha = _audit_identity_set()
        delivery_results = _audit_delivery_replay(identities)
        if any(
            delivery_results[symbol]["delivery_id"]
            != identities[symbol]["delivery_id"]
            for symbol in SYMBOLS
        ):
            raise P9AuditError("P9 delivery identity replay changed")

        replay = run_adversarial_notification_matrix(fixtures)
        replay_again = run_adversarial_notification_matrix(fixtures)
        if (
            replay != replay_again
            or _sha256(replay.index_json) != EXPECTED_INDEX_SHA256
        ):
            raise P9AuditError("P9 deterministic adversarial replay changed")

        expected_evidence = _expected_evidence(replay)
        evidence, records = _read_evidence(evidence_dir)
        _audit_evidence_records(records)

        if evidence != expected_evidence:
            raise P9AuditError("P9 published evidence differs from deterministic replay")

        if identities != EXPECTED_IDENTITIES:
            raise P9AuditError("P9 accepted notification identities changed")

        return P9AuditResult(
            symbols=len(SYMBOLS),
            scenarios=len(SCENARIOS),
            runs=len(replay.runs),
            files=len(evidence),
            notification_policy_sha256=notification_policy_sha,
            transport_policy_sha256=transport_policy_sha,
            delivery_policy_sha256=delivery_policy_sha,
            identity_set_sha256=identity_set_sha,
            index_sha256=_sha256(evidence["p9-005-index.json"]),
            exact_outcomes=True,
            replay_equal=True,
            identities_recomputed=True,
            formatter_recomputed=True,
            delivery_recomputed=True,
            evidence_verified=True,
            no_write=True,
            source_safe=source_safe,
        )
    except P9AuditError:
        raise
    except (
        NotificationContractError,
        NotificationFormatError,
        TelegramTransportError,
        DeliveryGuardError,
        NotificationScenarioError,
        TypeError,
        ValueError,
    ):
        raise P9AuditError("P9 independent final audit failed safely") from None
