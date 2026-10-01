"""Opt-in engineering checkpoints; no strategy object enters this channel."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

STAGES = (
    "frozen_input_admission", "runtime_initialization", "dataset_loading",
    "feature_cache_initialization", "liquidity_percentiles",
    "feature_signal_compilation", "simulation_replay", "result_accounting",
    "result_construction", "result_digest", "result_discard", "cleanup",
)
_SINK = ContextVar("mcf_capacity_diagnostic_sink", default=None)


@contextmanager
def engineering_telemetry(sink):
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


@contextmanager
def memory_stage(name):
    if name not in STAGES:
        raise ValueError("unknown engineering memory stage")
    sink = _SINK.get()
    if sink is not None:
        sink(name, "begin")  # synchronous write + flush BEFORE allocation
    yield
    # An exception never masquerades as a completed stage.
    if sink is not None:
        sink(name, "end")
