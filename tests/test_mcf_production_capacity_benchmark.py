import json
import unittest
from types import SimpleNamespace

from research.mass_candidate_factory.models import MCFError
from research.mass_candidate_factory.production_capacity_benchmark import (
    BENCHMARK_CANDIDATE_COUNT,
    EXPECTED_EXECUTABLE_COUNT,
    run_capacity_benchmark,
    select_benchmark_candidates,
)


def candidate(index, family=None, timeframe=None):
    families = ("TREND_CROSSOVER", "BREAKOUT_CHANNEL", "SHORT_HORIZON_MEAN_REVERSION",
                "CRASH_REBOUND", "VOLUME_CONFIRMED_DIRECTION", "SESSION_TIME_EFFECT")
    timeframes = ("15m", "1h", "4h")
    return {
        "candidate_id": f"MCF-PROD-001-{index:06d}",
        "candidate_spec_sha256": f"{index % 16:x}" * 64,
        "family": family or families[index % len(families)],
        "timeframe": timeframe or timeframes[index % len(timeframes)],
    }


def inventory():
    return tuple(candidate(i) for i in range(EXPECTED_EXECUTABLE_COUNT))


class FakeRuntime:
    def __init__(self):
        self.executable_freeze = {
            "summary": {
                "generation_id": "MCF-PROD-001",
                "state": "PRE_OUTCOME_EXECUTABLE_SET_FROZEN",
                "executable_candidate_count": EXPECTED_EXECUTABLE_COUNT,
            },
            "executable": inventory(),
        }
        self.calls = []

    def run(self, candidate_id, *, director_authorized=False):
        self.calls.append((candidate_id, director_authorized))
        row = next(x for x in self.executable_freeze["executable"]
                   if x["candidate_id"] == candidate_id)
        return {
            "candidate_id": row["candidate_id"],
            "candidate_spec_sha256": row["candidate_spec_sha256"],
            # Deliberately include performance-like fields; benchmark output
            # must never expose them.
            "net_return": "999",
            "completed_trades": 999,
            "secret_ranking_score": "999",
        }


class TickClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        current = self.value
        self.value += 1.0
        return current


class Usage:
    def __init__(self, user, system, rss):
        self.ru_utime = user
        self.ru_stime = system
        self.ru_maxrss = rss


class CapacityBenchmarkTest(unittest.TestCase):
    def test_selection_is_deterministic_and_stratified(self):
        rows = inventory()
        first = select_benchmark_candidates(rows)
        second = select_benchmark_candidates(tuple(reversed(rows)))
        self.assertEqual(
            tuple(x["candidate_id"] for x in first),
            tuple(x["candidate_id"] for x in second),
        )
        self.assertEqual(len(first), BENCHMARK_CANDIDATE_COUNT)
        buckets = {(x["family"], x["timeframe"]) for x in first}
        self.assertGreaterEqual(len(buckets), 6)

    def test_selection_rejects_duplicates(self):
        rows = [candidate(i) for i in range(BENCHMARK_CANDIDATE_COUNT)]
        rows[-1] = dict(rows[0])
        with self.assertRaises(MCFError):
            select_benchmark_candidates(rows)

    def test_benchmark_exposes_capacity_only(self):
        runtime = FakeRuntime()
        usage_values = iter((Usage(1.0, 2.0, 100), Usage(7.5, 4.25, 456789)))
        progress = []
        result = run_capacity_benchmark(
            runtime,
            "a" * 64,
            clock=TickClock(),
            usage=lambda: next(usage_values),
            progress=lambda position, total: progress.append((position, total)),
        )
        self.assertEqual(result["status"], "CAPACITY_BENCHMARK_COMPLETE_NO_SELECTION")
        self.assertEqual(result["benchmark_candidate_count"], BENCHMARK_CANDIDATE_COUNT)
        self.assertEqual(len(runtime.calls), BENCHMARK_CANDIDATE_COUNT)
        self.assertTrue(all(authorized is True for _, authorized in runtime.calls))
        self.assertEqual(progress[-1], (BENCHMARK_CANDIDATE_COUNT, BENCHMARK_CANDIDATE_COUNT))
        self.assertEqual(result["cpu_user_seconds"], 6.5)
        self.assertEqual(result["cpu_system_seconds"], 2.25)
        self.assertEqual(result["peak_rss_kib"], 456789)
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("net_return", encoded)
        self.assertNotIn("completed_trades", encoded)
        self.assertNotIn("ranking", encoded)
        self.assertFalse(result["candidate_performance_exposed"])
        self.assertFalse(result["performance_artifacts_written"])
        self.assertFalse(result["selection_authorized"])
        self.assertFalse(result["full_batch_authorized"])

    def test_wrong_generation_size_fails_closed_before_run(self):
        runtime = FakeRuntime()
        runtime.executable_freeze["summary"]["executable_candidate_count"] -= 1
        with self.assertRaises(MCFError):
            run_capacity_benchmark(runtime, "a" * 64)
        self.assertEqual(runtime.calls, [])

    def test_bad_runner_identity_fails_closed_before_run(self):
        runtime = FakeRuntime()
        with self.assertRaises(MCFError):
            run_capacity_benchmark(runtime, "short")
        self.assertEqual(runtime.calls, [])


if __name__ == "__main__":
    unittest.main()
