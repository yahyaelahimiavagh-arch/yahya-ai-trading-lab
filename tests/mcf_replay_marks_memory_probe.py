"""Observation-only, separately invokable synthetic MCF replay memory probe.

Run each mode in a *fresh process* with external memory/CPU limits:
  PYTHONPATH=tests:. python -B tests/mcf_replay_marks_memory_probe.py legacy
  PYTHONPATH=tests:. python -B tests/mcf_replay_marks_memory_probe.py proposed

Never reads runtime inputs, Development datasets, candidate registries or P10.
It does not execute ProductionRuntime, reveal synthetic economics or write files.
"""
from __future__ import annotations

import gc
import json
import resource
import sys
from decimal import Decimal

from mcf_replay_marks_baseline import baseline_simulate
from research.mass_candidate_factory import production as p


CADENCE = p.CADENCE_MS["15m"]
START = p.DEVELOPMENT_START_MS
SYMBOLS = tuple(f"SYN{i:03d}USDT" for i in range(6))
BARS = 12000


def rss_kib() -> int:
    with open("/proc/self/status", encoding="ascii") as status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    raise RuntimeError("Linux VmRSS unavailable")


def fixture():
    membership = p.ProductionUniverseBinding(
        p.UNIVERSE_EVIDENCE_ID,
        "a" * 64, "b" * 64, "c" * 64,
        (p.MembershipSnapshot(START, SYMBOLS, "a" * 64),),
    )
    series = []
    for j, symbol in enumerate(SYMBOLS):
        # Deliberately missing two source bars; all are invented dates/prices.
        times = tuple(START + (i + (2 if i >= 100 else 0) +
                               (3 if i >= 5000 else 0)) * CADENCE
                      for i in range(BARS))
        opens = tuple(str(100 + j * 3 + (i % 17)) for i in range(BARS))
        closes = tuple(str(101 + j * 3 + (i % 19)) for i in range(BARS))
        desired = tuple(i % 43 < 20 for i in range(BARS))
        available = tuple(i % 67 != 0 for i in range(BARS))
        series.append(p.ProductionSeries(symbol, "15m", times, opens,
                                         closes, desired, available))
    return membership, series


def main(argv):
    if len(argv) != 2 or argv[1] not in {"legacy", "proposed"}:
        raise SystemExit("expected mode legacy or proposed")
    mode = argv[1]
    simulator = baseline_simulate if mode == "legacy" else p._simulate
    membership, series = fixture()
    policy = p.ProductionCostPolicy()
    gc.collect()
    baseline = rss_kib()
    # The two scenarios must coexist, matching current production retention.
    outputs = []
    for item in series:
        for stress in (False, True):
            outputs.append(simulator(item, membership, policy, stress=stress))
    gc.collect()
    retained = rss_kib()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert len(outputs) == len(SYMBOLS) * 2
    assert retained >= 0 and peak >= retained
    print(json.dumps({
        "schema": "MCF_SYNTHETIC_REPLAY_MEMORY_PROBE/1.0.0",
        "mode": mode,
        "symbols": len(SYMBOLS),
        "bars_per_symbol": BARS,
        "scenarios": 2,
        "rss_after_fixture_kib": baseline,
        "rss_after_results_kib": retained,
        "peak_rss_kib": peak,
        "candidate_executed": False,
        "real_data_read": False,
        "performance_exposed": False,
        "source_input_modified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
