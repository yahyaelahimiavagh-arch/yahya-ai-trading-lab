"""P10-004 bounded public forward ingestion and deterministic quality gate."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from yatl.data import (
    BINANCE_PUBLIC_BASE_URL,
    DATA_SOURCE,
    INTERVAL_MILLISECONDS,
    SYMBOLS,
    BinancePublicRestClient,
    HealthError,
    HistoricalDownloadError,
    NormalizationError,
    PublicRestError,
    build_health_report,
    download_range,
    normalize_rest_kline,
)

from .forward_store import ForwardCandleStore, ForwardStoreError
from .window import ForwardObservationIdentity, ForwardWindowSeal


FORWARD_INGESTION_ID = "P10_FORWARD_INGESTION_V1"
FORWARD_DATASET_KIND = "P10_BINANCE_SPOT_PUBLIC_CLOSED_OHLCV"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ForwardIngestionError(Exception):
    """Forward public-data collection failed without weakening the P10 seal."""


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value):
    payload = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ForwardDatasetEvidence:
    source: str
    symbol: str
    interval: str
    requested_start_time_ms: int
    requested_end_time_ms: int
    server_time_ms: int
    pages: int
    new_rows: int
    skipped_known_rows: int
    total_rows: int
    first_open_time_ms: int
    last_open_time_ms: int
    dataset_sha256: str
    health_sha256: str
    quality_pass: bool

    def __post_init__(self):
        duration = INTERVAL_MILLISECONDS.get(self.interval)
        if (
            self.source != DATA_SOURCE
            or self.symbol not in SYMBOLS
            or duration is None
            or type(self.requested_start_time_ms) is not int
            or type(self.requested_end_time_ms) is not int
            or type(self.server_time_ms) is not int
            or self.requested_start_time_ms
            != ForwardWindowSeal().forward_window_start_ms
            or self.requested_end_time_ms <= self.requested_start_time_ms
            or self.requested_start_time_ms % duration
            or self.requested_end_time_ms % duration
            or self.server_time_ms < self.requested_end_time_ms
            or type(self.pages) is not int
            or self.pages < 1
            or type(self.new_rows) is not int
            or self.new_rows < 0
            or type(self.skipped_known_rows) is not int
            or self.skipped_known_rows < 0
            or type(self.total_rows) is not int
            or self.total_rows
            != (self.requested_end_time_ms - self.requested_start_time_ms)
            // duration
            or self.new_rows + self.skipped_known_rows != self.total_rows
            or self.first_open_time_ms != self.requested_start_time_ms
            or self.last_open_time_ms
            != self.requested_end_time_ms - duration
            or SHA256_PATTERN.fullmatch(self.dataset_sha256) is None
            or SHA256_PATTERN.fullmatch(self.health_sha256) is None
            or self.quality_pass is not True
        ):
            raise ForwardIngestionError(
                "Forward dataset evidence is inconsistent or incomplete"
            )

    def as_record(self):
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ForwardIngestionSnapshot:
    ingestion_id: str
    dataset_kind: str
    generated_at_ms: int
    transport_base_url: str
    window_sha256: str
    candidate_sha256: str
    gate_registry_sha256: str
    p10_002_registration_sha256: str
    accepted_source_manifest_git_blob_sha1: str
    datasets: tuple[ForwardDatasetEvidence, ...]
    quality_pass: bool
    upstream_write_allowed: bool
    p1_manifest_write_allowed: bool
    economic_evaluation_allowed: bool
    strategy_evidence: str
    paper_only: bool
    live_master_lock: str
    trade_permission: bool
    order_endpoint: bool
    ai_direct_execution: bool

    def __post_init__(self):
        window = ForwardWindowSeal()
        expected_pairs = tuple(
            (symbol, interval)
            for symbol in window.symbols
            for interval in window.intervals
        )
        actual_pairs = tuple((item.symbol, item.interval) for item in self.datasets)
        if (
            self.ingestion_id != FORWARD_INGESTION_ID
            or self.dataset_kind != FORWARD_DATASET_KIND
            or type(self.generated_at_ms) is not int
            or self.generated_at_ms <= window.forward_window_start_ms
            or self.transport_base_url != BINANCE_PUBLIC_BASE_URL
            or self.window_sha256 != window.window_sha256
            or self.candidate_sha256 != window.candidate_sha256
            or self.gate_registry_sha256 != window.gate_registry_sha256
            or self.p10_002_registration_sha256
            != window.p10_002_registration_sha256
            or self.accepted_source_manifest_git_blob_sha1
            != window.accepted_source_manifest_git_blob_sha1
            or type(self.datasets) is not tuple
            or actual_pairs != expected_pairs
            or any(
                not isinstance(item, ForwardDatasetEvidence)
                or item.server_time_ms != self.generated_at_ms
                or item.quality_pass is not True
                for item in self.datasets
            )
            or self.quality_pass is not True
            or self.upstream_write_allowed is not False
            or self.p1_manifest_write_allowed is not False
            or self.economic_evaluation_allowed is not False
            or self.strategy_evidence != "INSUFFICIENT_EVIDENCE"
            or self.paper_only is not True
            or self.live_master_lock != "OFF"
            or self.trade_permission is not False
            or self.order_endpoint is not False
            or self.ai_direct_execution is not False
        ):
            raise ForwardIngestionError(
                "Forward ingestion snapshot violates P10-004 policy"
            )

    def as_record(self):
        return {
            "ingestion_id": self.ingestion_id,
            "dataset_kind": self.dataset_kind,
            "generated_at_ms": self.generated_at_ms,
            "transport_base_url": self.transport_base_url,
            "window_sha256": self.window_sha256,
            "candidate_sha256": self.candidate_sha256,
            "gate_registry_sha256": self.gate_registry_sha256,
            "p10_002_registration_sha256": self.p10_002_registration_sha256,
            "accepted_source_manifest_git_blob_sha1":
                self.accepted_source_manifest_git_blob_sha1,
            "datasets": [item.as_record() for item in self.datasets],
            "quality_pass": self.quality_pass,
            "safety": {
                "upstream_write_allowed": self.upstream_write_allowed,
                "p1_manifest_write_allowed": self.p1_manifest_write_allowed,
                "economic_evaluation_allowed":
                    self.economic_evaluation_allowed,
                "strategy_evidence": self.strategy_evidence,
                "paper_only": self.paper_only,
                "live_master_lock": self.live_master_lock,
                "trade_permission": self.trade_permission,
                "order_endpoint": self.order_endpoint,
                "ai_direct_execution": self.ai_direct_execution,
            },
        }

    @property
    def snapshot_sha256(self):
        return _sha256(self.as_record())


def _dataset_digest(candles):
    return _sha256([item.as_record() for item in candles])


def _health_digest(report):
    return _sha256(json.loads(report.to_json()))


def collect_forward_snapshot(store, client):
    """Collect one complete quality-gated forward snapshot into the P10 store.

    The exchange server clock is authoritative. The function downloads only
    closed ranges starting at the sealed P10 boundary and never writes the P1
    manifest or any upstream evidence.
    """
    if not isinstance(store, ForwardCandleStore):
        raise ForwardIngestionError("A P10-owned forward store is required")
    if not isinstance(client, BinancePublicRestClient):
        raise ForwardIngestionError("A Binance public REST client is required")

    window = ForwardWindowSeal()
    if store.window_sha256 != window.window_sha256:
        raise ForwardIngestionError("P10 store is bound to a different window")
    if getattr(client, "_base_url", None) != BINANCE_PUBLIC_BASE_URL:
        raise ForwardIngestionError("Forward ingestion requires the primary public host")

    try:
        server_time = client.server_time()
    except PublicRestError:
        raise ForwardIngestionError("Cannot read Binance public server time") from None

    cutoffs = {}
    for interval in window.intervals:
        duration = INTERVAL_MILLISECONDS[interval]
        cutoff = (server_time // duration) * duration
        if cutoff <= window.forward_window_start_ms:
            raise ForwardIngestionError(
                "Forward window has not produced a closed candle for every interval"
            )
        cutoffs[interval] = cutoff

    evidence = []
    for symbol in window.symbols:
        for interval in window.intervals:
            start = window.forward_window_start_ms
            end = cutoffs[interval]
            try:
                known = store.known_open_times(symbol, interval, start, end)
                batch = download_range(
                    client,
                    symbol,
                    interval,
                    start,
                    end,
                    known_open_times=known,
                )
                candles = tuple(
                    normalize_rest_kline(symbol, interval, row, server_time)
                    for row in batch.rows
                )
                for candle in candles:
                    if not candle.is_closed:
                        raise ForwardIngestionError(
                            "Forward download contains an open candle"
                        )
                    ForwardObservationIdentity(
                        source_id=candle.source,
                        symbol=candle.symbol,
                        interval=candle.interval,
                        open_time_ms=candle.open_time_ms,
                        close_time_ms=candle.close_time_ms,
                        is_closed=candle.is_closed,
                        window_sha256=window.window_sha256,
                    )
                if candles:
                    store.write_many(candles)
                stored = store.candles_between(symbol, interval, start, end)
                report = build_health_report(
                    DATA_SOURCE,
                    symbol,
                    interval,
                    start,
                    end,
                    stored,
                    server_time,
                )
            except ForwardIngestionError:
                raise
            except (
                ForwardStoreError,
                HealthError,
                HistoricalDownloadError,
                NormalizationError,
                PublicRestError,
                ValueError,
            ):
                raise ForwardIngestionError(
                    "Forward market-data collection failed safely"
                ) from None

            duration = INTERVAL_MILLISECONDS[interval]
            expected_rows = (end - start) // duration
            if (
                not report.backtest_ready
                or not report.fresh
                or report.failure_reasons
                or report.open_rows
                or report.malformed_rows
                or report.conflicting_rows
                or report.duplicate_open_times
                or report.historical_gap_open_times
                or report.unexpected_open_times
                or report.total_rows != expected_rows
                or report.unique_rows != expected_rows
                or report.closed_rows != expected_rows
                or len(stored) != expected_rows
            ):
                raise ForwardIngestionError(
                    "Forward data quality gate failed"
                )

            evidence.append(
                ForwardDatasetEvidence(
                    source=DATA_SOURCE,
                    symbol=symbol,
                    interval=interval,
                    requested_start_time_ms=start,
                    requested_end_time_ms=end,
                    server_time_ms=server_time,
                    pages=batch.pages,
                    new_rows=len(candles),
                    skipped_known_rows=batch.skipped_known_rows,
                    total_rows=len(stored),
                    first_open_time_ms=stored[0].open_time_ms,
                    last_open_time_ms=stored[-1].open_time_ms,
                    dataset_sha256=_dataset_digest(stored),
                    health_sha256=_health_digest(report),
                    quality_pass=True,
                )
            )

    snapshot = ForwardIngestionSnapshot(
        ingestion_id=FORWARD_INGESTION_ID,
        dataset_kind=FORWARD_DATASET_KIND,
        generated_at_ms=server_time,
        transport_base_url=BINANCE_PUBLIC_BASE_URL,
        window_sha256=window.window_sha256,
        candidate_sha256=window.candidate_sha256,
        gate_registry_sha256=window.gate_registry_sha256,
        p10_002_registration_sha256=window.p10_002_registration_sha256,
        accepted_source_manifest_git_blob_sha1=
            window.accepted_source_manifest_git_blob_sha1,
        datasets=tuple(evidence),
        quality_pass=True,
        upstream_write_allowed=False,
        p1_manifest_write_allowed=False,
        economic_evaluation_allowed=False,
        strategy_evidence="INSUFFICIENT_EVIDENCE",
        paper_only=True,
        live_master_lock="OFF",
        trade_permission=False,
        order_endpoint=False,
        ai_direct_execution=False,
    )
    return snapshot


def snapshot_from_record(record):
    if not isinstance(record, dict):
        raise ForwardIngestionError("Forward ingestion record is invalid")
    expected = {
        "ingestion_id",
        "dataset_kind",
        "generated_at_ms",
        "transport_base_url",
        "window_sha256",
        "candidate_sha256",
        "gate_registry_sha256",
        "p10_002_registration_sha256",
        "accepted_source_manifest_git_blob_sha1",
        "datasets",
        "quality_pass",
        "safety",
    }
    if set(record) != expected or not isinstance(record["datasets"], list):
        raise ForwardIngestionError("Forward ingestion record schema is invalid")
    safety = record["safety"]
    if not isinstance(safety, dict):
        raise ForwardIngestionError("Forward ingestion safety record is invalid")
    try:
        datasets = tuple(ForwardDatasetEvidence(**item) for item in record["datasets"])
        snapshot = ForwardIngestionSnapshot(
            ingestion_id=record["ingestion_id"],
            dataset_kind=record["dataset_kind"],
            generated_at_ms=record["generated_at_ms"],
            transport_base_url=record["transport_base_url"],
            window_sha256=record["window_sha256"],
            candidate_sha256=record["candidate_sha256"],
            gate_registry_sha256=record["gate_registry_sha256"],
            p10_002_registration_sha256=record["p10_002_registration_sha256"],
            accepted_source_manifest_git_blob_sha1=
                record["accepted_source_manifest_git_blob_sha1"],
            datasets=datasets,
            quality_pass=record["quality_pass"],
            upstream_write_allowed=safety["upstream_write_allowed"],
            p1_manifest_write_allowed=safety["p1_manifest_write_allowed"],
            economic_evaluation_allowed=safety["economic_evaluation_allowed"],
            strategy_evidence=safety["strategy_evidence"],
            paper_only=safety["paper_only"],
            live_master_lock=safety["live_master_lock"],
            trade_permission=safety["trade_permission"],
            order_endpoint=safety["order_endpoint"],
            ai_direct_execution=safety["ai_direct_execution"],
        )
    except (KeyError, TypeError, ValueError):
        raise ForwardIngestionError(
            "Forward ingestion record cannot be reconstructed"
        ) from None
    if snapshot.as_record() != record:
        raise ForwardIngestionError("Forward ingestion record is inconsistent")
    return snapshot
