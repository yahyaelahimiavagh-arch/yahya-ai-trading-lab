"""Deterministic P7 reconstruction of completed/open local-Paper trades."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from .contracts import AnalyticsSourceKind, StrategyEvidenceState
from .ingestion import (
    AnalyticsIngestionError,
    UpstreamSourceSpec,
    _connect_readonly,
    _safe_stat,
    _sha256_file,
)
from .timeline import (
    TimelineError,
    _intent_records,
    _validate_fill_material,
    _validate_order_material,
    build_unified_timeline,
)


TRADE_SCHEMA_VERSION = 1
DECIMAL_PRECISION = 256
PLAIN_DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class TradeReconstructionError(TimelineError):
    """Accepted durable evidence cannot form an exact Paper trade episode."""


class TradeBookStatus(str, Enum):
    NO_FILLS = "NO_FILLS"
    OPEN = "OPEN"
    FLAT = "FLAT"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decimal(value, label):
    if (
        not isinstance(value, str)
        or PLAIN_DECIMAL_PATTERN.fullmatch(value) is None
    ):
        raise TradeReconstructionError(f"{label} is not a canonical decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise TradeReconstructionError(f"{label} is invalid") from None
    if not number.is_finite():
        raise TradeReconstructionError(f"{label} is not finite")
    return number


def _sha(value, label):
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise TradeReconstructionError(f"{label} digest is invalid")
    return value


def _format_decimal(value):
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class AcceptedTradeFill:
    """Exact economics copied from one accepted durable P5 fill event."""

    fill_event_sha256: str
    authorization_sha256: str
    intent_sha256: str
    order_state_sha256: str
    fill_step_sha256: str
    fill_index: int
    action: str
    symbol: str
    decision_time_ms: int
    fill_time_ms: int
    quantity: str
    reference_price: str
    reason: str
    fee_bps: str
    slippage_bps: str
    execution_price: str
    gross_quote: str
    fee_quote: str
    slippage_quote: str
    cash_delta: str
    asset_delta: str

    def __post_init__(self):
        for value, label in (
            (self.fill_event_sha256, "Fill event"),
            (self.authorization_sha256, "Authorization"),
            (self.intent_sha256, "Intent"),
            (self.order_state_sha256, "Order state"),
            (self.fill_step_sha256, "Fill step"),
        ):
            _sha(value, label)
        if (
            type(self.fill_index) is not int
            or self.fill_index < 0
            or self.action not in ("ENTER_LONG", "EXIT_LONG")
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or type(self.decision_time_ms) is not int
            or type(self.fill_time_ms) is not int
            or self.decision_time_ms < 0
            or self.fill_time_ms < self.decision_time_ms
            or not isinstance(self.reason, str)
            or not self.reason
        ):
            raise TradeReconstructionError("Accepted trade fill identity is invalid")

        quantity = _decimal(self.quantity, "Fill quantity")
        reference = _decimal(self.reference_price, "Reference price")
        execution = _decimal(self.execution_price, "Execution price")
        gross = _decimal(self.gross_quote, "Gross quote")
        fee = _decimal(self.fee_quote, "Fee quote")
        slippage = _decimal(self.slippage_quote, "Slippage quote")
        fee_bps = _decimal(self.fee_bps, "Fee bps")
        slippage_bps = _decimal(self.slippage_bps, "Slippage bps")
        cash = _decimal(self.cash_delta, "Cash delta")
        asset = _decimal(self.asset_delta, "Asset delta")

        if (
            quantity <= 0
            or reference <= 0
            or execution <= 0
            or gross <= 0
            or fee < 0
            or slippage < 0
            or fee_bps < 0
            or slippage_bps < 0
        ):
            raise TradeReconstructionError("Accepted fill economics are out of bounds")
        if self.action == "ENTER_LONG":
            if cash >= 0 or asset != quantity:
                raise TradeReconstructionError(
                    "Entry fill cash/asset direction is inconsistent"
                )
        else:
            if cash <= 0 or asset != -quantity:
                raise TradeReconstructionError(
                    "Exit fill cash/asset direction is inconsistent"
                )

    def as_record(self):
        return {
            "fill_event_sha256": self.fill_event_sha256,
            "authorization_sha256": self.authorization_sha256,
            "intent_sha256": self.intent_sha256,
            "order_state_sha256": self.order_state_sha256,
            "fill_step_sha256": self.fill_step_sha256,
            "fill_index": self.fill_index,
            "action": self.action,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "fill_time_ms": self.fill_time_ms,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "reason": self.reason,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "execution_price": self.execution_price,
            "gross_quote": self.gross_quote,
            "fee_quote": self.fee_quote,
            "slippage_quote": self.slippage_quote,
            "cash_delta": self.cash_delta,
            "asset_delta": self.asset_delta,
        }


@dataclass(frozen=True, slots=True)
class CompletedPaperTrade:
    """One full long episode built only from accepted entry/exit cash effects."""

    trade_index: int
    symbol: str
    entry: AcceptedTradeFill
    exit: AcceptedTradeFill
    realized_pnl_quote: str
    total_fee_quote: str
    total_slippage_quote: str
    holding_time_ms: int
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if (
            type(self.trade_index) is not int
            or self.trade_index < 0
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not isinstance(self.entry, AcceptedTradeFill)
            or not isinstance(self.exit, AcceptedTradeFill)
            or self.entry.symbol != self.symbol
            or self.exit.symbol != self.symbol
            or self.entry.action != "ENTER_LONG"
            or self.exit.action != "EXIT_LONG"
            or self.entry.quantity != self.exit.quantity
            or self.exit.fill_time_ms < self.entry.fill_time_ms
            or type(self.holding_time_ms) is not int
            or self.holding_time_ms != self.exit.fill_time_ms - self.entry.fill_time_ms
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise TradeReconstructionError("Completed Paper trade identity is invalid")

        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            realized = (
                _decimal(self.entry.cash_delta, "Entry cash delta")
                + _decimal(self.exit.cash_delta, "Exit cash delta")
            )
            fees = (
                _decimal(self.entry.fee_quote, "Entry fee")
                + _decimal(self.exit.fee_quote, "Exit fee")
            )
            slippage = (
                _decimal(self.entry.slippage_quote, "Entry slippage")
                + _decimal(self.exit.slippage_quote, "Exit slippage")
            )
        if (
            _decimal(self.realized_pnl_quote, "Realized PnL") != realized
            or _decimal(self.total_fee_quote, "Trade fee") != fees
            or _decimal(self.total_slippage_quote, "Trade slippage") != slippage
        ):
            raise TradeReconstructionError(
                "Completed trade arithmetic differs from accepted fill cash effects"
            )

    def as_record(self):
        return {
            "trade_index": self.trade_index,
            "symbol": self.symbol,
            "entry": self.entry.as_record(),
            "exit": self.exit.as_record(),
            "realized_pnl_quote": self.realized_pnl_quote,
            "total_fee_quote": self.total_fee_quote,
            "total_slippage_quote": self.total_slippage_quote,
            "holding_time_ms": self.holding_time_ms,
            "strategy_evidence": self.strategy_evidence.value,
            "economics_source": "ACCEPTED_P5_FILL_CASH_EFFECTS",
        }

    @property
    def trade_sha256(self):
        return _digest({
            "schema_version": TRADE_SCHEMA_VERSION,
            "trade": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class OpenPaperTrade:
    """One still-open entry. It carries no invented exit or realized PnL."""

    symbol: str
    entry: AcceptedTradeFill
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )

    def __post_init__(self):
        if (
            self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not isinstance(self.entry, AcceptedTradeFill)
            or self.entry.symbol != self.symbol
            or self.entry.action != "ENTER_LONG"
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise TradeReconstructionError("Open Paper trade identity is invalid")

    def as_record(self):
        return {
            "symbol": self.symbol,
            "status": "OPEN",
            "entry": self.entry.as_record(),
            "realized_pnl_quote": None,
            "strategy_evidence": self.strategy_evidence.value,
        }

    @property
    def open_trade_sha256(self):
        return _digest({
            "schema_version": TRADE_SCHEMA_VERSION,
            "open_trade": self.as_record(),
        })


@dataclass(frozen=True, slots=True)
class FinalPortfolioEvidence:
    """Final accepted P5 portfolio values copied verbatim for reconciliation."""

    projection_sha256: str
    position: str
    asset_quantity: str
    cost_basis_quote: str
    realized_pnl_quote: str
    total_fee_quote: str
    total_slippage_quote: str
    closed_trades: int

    def __post_init__(self):
        _sha(self.projection_sha256, "Portfolio projection")
        if (
            self.position not in ("LONG", "FLAT")
            or type(self.closed_trades) is not int
            or self.closed_trades < 0
        ):
            raise TradeReconstructionError("Final portfolio identity is invalid")
        quantity = _decimal(self.asset_quantity, "Final asset quantity")
        cost_basis = _decimal(self.cost_basis_quote, "Final cost basis")
        _decimal(self.realized_pnl_quote, "Final realized PnL")
        fee = _decimal(self.total_fee_quote, "Final total fee")
        slippage = _decimal(self.total_slippage_quote, "Final total slippage")
        if quantity < 0 or cost_basis < 0 or fee < 0 or slippage < 0:
            raise TradeReconstructionError("Final portfolio values are out of bounds")
        if (self.position == "FLAT") is not (quantity == 0 and cost_basis == 0):
            raise TradeReconstructionError(
                "Final portfolio position and balances disagree"
            )

    def as_record(self):
        return {
            "projection_sha256": self.projection_sha256,
            "position": self.position,
            "asset_quantity": self.asset_quantity,
            "cost_basis_quote": self.cost_basis_quote,
            "realized_pnl_quote": self.realized_pnl_quote,
            "total_fee_quote": self.total_fee_quote,
            "total_slippage_quote": self.total_slippage_quote,
            "closed_trades": self.closed_trades,
        }


@dataclass(frozen=True, slots=True)
class PaperTradeReconstruction:
    """Canonical descriptive trade book derived from validated accepted evidence."""

    snapshot_time_ms: int
    symbol: str
    timeline_sha256: str
    status: TradeBookStatus
    completed: tuple[CompletedPaperTrade, ...]
    open_trade: OpenPaperTrade | None
    final_portfolio: FinalPortfolioEvidence | None
    strategy_evidence: StrategyEvidenceState = (
        StrategyEvidenceState.INSUFFICIENT_EVIDENCE
    )
    schema_version: int = TRADE_SCHEMA_VERSION

    def __post_init__(self):
        if (
            self.schema_version != TRADE_SCHEMA_VERSION
            or type(self.snapshot_time_ms) is not int
            or self.snapshot_time_ms < 0
            or self.symbol not in ("BTCUSDT", "ETHUSDT")
            or not _sha(self.timeline_sha256, "Timeline")
            or not isinstance(self.status, TradeBookStatus)
            or type(self.completed) is not tuple
            or any(not isinstance(item, CompletedPaperTrade) for item in self.completed)
            or (
                self.open_trade is not None
                and not isinstance(self.open_trade, OpenPaperTrade)
            )
            or (
                self.final_portfolio is not None
                and not isinstance(self.final_portfolio, FinalPortfolioEvidence)
            )
            or self.strategy_evidence
            is not StrategyEvidenceState.INSUFFICIENT_EVIDENCE
        ):
            raise TradeReconstructionError("Paper trade reconstruction is invalid")
        if tuple(item.trade_index for item in self.completed) != tuple(
            range(len(self.completed))
        ):
            raise TradeReconstructionError("Completed trade indexes are noncanonical")
        if any(item.symbol != self.symbol for item in self.completed):
            raise TradeReconstructionError("Completed trade is cross-symbol")
        if self.open_trade is not None and self.open_trade.symbol != self.symbol:
            raise TradeReconstructionError("Open trade is cross-symbol")

        expected = (
            TradeBookStatus.NO_FILLS
            if self.final_portfolio is None
            else TradeBookStatus.OPEN
            if self.open_trade is not None
            else TradeBookStatus.FLAT
        )
        if self.status is not expected:
            raise TradeReconstructionError("Trade-book status is inconsistent")
        if self.final_portfolio is None:
            if self.completed or self.open_trade is not None:
                raise TradeReconstructionError(
                    "Trade episodes exist without final portfolio evidence"
                )
        else:
            if self.final_portfolio.closed_trades != len(self.completed):
                raise TradeReconstructionError(
                    "Closed-trade count differs from accepted portfolio"
                )

    def as_record(self):
        return {
            "schema_version": self.schema_version,
            "snapshot_time_ms": self.snapshot_time_ms,
            "symbol": self.symbol,
            "timeline_sha256": self.timeline_sha256,
            "status": self.status.value,
            "completed": [
                {**item.as_record(), "trade_sha256": item.trade_sha256}
                for item in self.completed
            ],
            "open_trade": (
                None
                if self.open_trade is None
                else {
                    **self.open_trade.as_record(),
                    "open_trade_sha256": self.open_trade.open_trade_sha256,
                }
            ),
            "final_portfolio": (
                None
                if self.final_portfolio is None
                else self.final_portfolio.as_record()
            ),
            "strategy_evidence": self.strategy_evidence.value,
            "safety": {
                "descriptive_only": True,
                "read_only": True,
                "paper_only": True,
                "live_master_lock": "OFF",
                "upstream_mutation": False,
                "trade_permission": False,
                "order_endpoints": False,
                "quantity_authority": False,
                "risk_authorization_mutation": False,
                "ai_direct_execution": False,
            },
        }

    @property
    def reconstruction_sha256(self):
        return _digest(self.as_record())

    @property
    def canonical_json(self):
        return _json(self.as_record()) + "\n"


def _accepted_fill(item):
    payload = item["payload"]
    return AcceptedTradeFill(
        item["fill_event_sha256"],
        item["authorization_sha256"],
        item["intent_sha256"],
        item["order_state_sha256"],
        item["fill_step_sha256"],
        item["fill_index"],
        payload["action"],
        payload["symbol"],
        payload["decision_time_ms"],
        payload["fill_time_ms"],
        payload["quantity"],
        payload["reference_price"],
        payload["reason"],
        payload["fee_bps"],
        payload["slippage_bps"],
        payload["execution_price"],
        payload["gross_quote"],
        payload["fee_quote"],
        payload["slippage_quote"],
        payload["cash_delta"],
        payload["asset_delta"],
    )


def _portfolio_evidence(projection):
    if projection is None:
        return None
    payload = projection["payload"]
    portfolio = payload["portfolio"]
    return FinalPortfolioEvidence(
        projection["projection_sha256"],
        payload["position"],
        portfolio["asset_quantity"],
        portfolio["cost_basis_quote"],
        portfolio["realized_pnl_quote"],
        portfolio["total_fee_quote"],
        portfolio["total_slippage_quote"],
        portfolio["closed_trades"],
    )


def _build_episodes(symbol, fills):
    completed = []
    open_entry = None
    accepted_fills = []
    for item in fills:
        fill = _accepted_fill(item)
        accepted_fills.append(fill)
        if fill.action == "ENTER_LONG":
            if open_entry is not None:
                raise TradeReconstructionError(
                    "Overlapping accepted Paper entries are ambiguous"
                )
            open_entry = fill
            continue

        if open_entry is None:
            raise TradeReconstructionError(
                "Accepted Paper exit has no preceding open entry"
            )
        if fill.quantity != open_entry.quantity:
            raise TradeReconstructionError(
                "Accepted Paper exit quantity differs from open entry"
            )
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            realized = (
                _decimal(open_entry.cash_delta, "Entry cash delta")
                + _decimal(fill.cash_delta, "Exit cash delta")
            )
            fees = (
                _decimal(open_entry.fee_quote, "Entry fee")
                + _decimal(fill.fee_quote, "Exit fee")
            )
            slippage = (
                _decimal(open_entry.slippage_quote, "Entry slippage")
                + _decimal(fill.slippage_quote, "Exit slippage")
            )
        completed.append(
            CompletedPaperTrade(
                len(completed),
                symbol,
                open_entry,
                fill,
                _format_decimal(realized),
                _format_decimal(fees),
                _format_decimal(slippage),
                fill.fill_time_ms - open_entry.fill_time_ms,
            )
        )
        open_entry = None
    return tuple(completed), open_entry, tuple(accepted_fills)


def _reconcile(completed, open_entry, fills, final_portfolio):
    if not fills:
        if final_portfolio is not None or completed or open_entry is not None:
            raise TradeReconstructionError(
                "Empty fill history has unexpected trade or portfolio evidence"
            )
        return

    if final_portfolio is None:
        raise TradeReconstructionError(
            "Accepted fills exist without final portfolio evidence"
        )

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        realized = sum(
            (
                _decimal(item.realized_pnl_quote, "Trade realized PnL")
                for item in completed
            ),
            Decimal(0),
        )
        fees = sum(
            (_decimal(item.fee_quote, "Fill fee") for item in fills),
            Decimal(0),
        )
        slippage = sum(
            (_decimal(item.slippage_quote, "Fill slippage") for item in fills),
            Decimal(0),
        )
    if (
        realized
        != _decimal(final_portfolio.realized_pnl_quote, "Portfolio realized PnL")
        or fees != _decimal(final_portfolio.total_fee_quote, "Portfolio total fee")
        or slippage
        != _decimal(final_portfolio.total_slippage_quote, "Portfolio total slippage")
    ):
        raise TradeReconstructionError(
            "Reconstructed economics do not reconcile to accepted P5 portfolio"
        )

    if open_entry is None:
        if (
            final_portfolio.position != "FLAT"
            or _decimal(final_portfolio.asset_quantity, "Portfolio quantity") != 0
            or _decimal(final_portfolio.cost_basis_quote, "Portfolio cost basis") != 0
        ):
            raise TradeReconstructionError(
                "Flat trade book differs from accepted portfolio"
            )
    else:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            expected_basis = -_decimal(open_entry.cash_delta, "Open entry cash delta")
        if (
            final_portfolio.position != "LONG"
            or _decimal(final_portfolio.asset_quantity, "Portfolio quantity")
            != _decimal(open_entry.quantity, "Open entry quantity")
            or _decimal(final_portfolio.cost_basis_quote, "Portfolio cost basis")
            != expected_basis
        ):
            raise TradeReconstructionError(
                "Open trade differs from accepted portfolio balances"
            )


def reconstruct_paper_trades(snapshot_time_ms, specs):
    """Reconstruct accepted long-only Paper episodes without inventing economics."""

    try:
        timeline = build_unified_timeline(snapshot_time_ms, specs)
    except (TimelineError, AnalyticsIngestionError):
        raise TradeReconstructionError(
            "Trade reconstruction upstream timeline failed closed"
        ) from None

    if type(specs) is not tuple or len(specs) != 2:
        raise TradeReconstructionError(
            "Trade reconstruction requires exactly two source specs"
        )
    p5_specs = tuple(
        item
        for item in specs
        if isinstance(item, UpstreamSourceSpec)
        and item.source_kind is AnalyticsSourceKind.P5_EXECUTION_EVIDENCE
    )
    if len(p5_specs) != 1:
        raise TradeReconstructionError("Trade reconstruction requires one P5 source")
    spec = p5_specs[0]

    before_stat = _safe_stat(spec.database_path)
    before_sha = _sha256_file(spec.database_path)
    if before_sha != spec.expected_database_sha256:
        raise TradeReconstructionError("P5 database identity changed")

    connection = _connect_readonly(spec.database_path)
    try:
        intents = _intent_records(connection)
        _, _, all_states = _validate_order_material(
            connection,
            intents,
            spec.symbol,
            snapshot_time_ms,
        )
        fills, projection = _validate_fill_material(
            connection,
            intents,
            all_states,
            spec.symbol,
            snapshot_time_ms,
        )
    except (TimelineError, AnalyticsIngestionError):
        raise TradeReconstructionError(
            "Accepted P5 trade evidence failed closed"
        ) from None
    finally:
        try:
            connection.close()
        except Exception:
            raise TradeReconstructionError(
                "Read-only P5 database could not be closed safely"
            ) from None

    after_stat = _safe_stat(spec.database_path)
    after_sha = _sha256_file(spec.database_path)
    if before_stat != after_stat or before_sha != after_sha:
        raise TradeReconstructionError(
            "P5 database changed during trade reconstruction"
        )

    completed, open_entry, accepted_fills = _build_episodes(spec.symbol, fills)
    final_portfolio = _portfolio_evidence(projection)
    _reconcile(
        completed,
        open_entry,
        accepted_fills,
        final_portfolio,
    )

    open_trade = (
        None
        if open_entry is None
        else OpenPaperTrade(spec.symbol, open_entry)
    )
    status = (
        TradeBookStatus.NO_FILLS
        if not accepted_fills
        else TradeBookStatus.OPEN
        if open_trade is not None
        else TradeBookStatus.FLAT
    )
    return PaperTradeReconstruction(
        snapshot_time_ms,
        spec.symbol,
        timeline.timeline_sha256,
        status,
        completed,
        open_trade,
        final_portfolio,
    )
