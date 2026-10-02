"""Memory remediation: synthetic data only, no frozen Development execution."""
import ast
import copy
import gc
import io
import json
import tracemalloc
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, canonical
from research.mass_candidate_factory.production import (
    CADENCE_MS, DEVELOPMENT_END_MS, DEVELOPMENT_START_MS,
    MembershipSnapshot,
)
from research.mass_candidate_factory.production_features import (
    POPULATION_START_MS, ProductionBars, ProductionFeatureCache, liquidity_percentiles,
)
from research.mass_candidate_factory import production_runtime as runtime_module
from research.mass_candidate_factory.production_memory_diagnostic import (
    CHECKPOINT_KEYS, CheckpointSink, SAFETY, validate_checkpoint,
)
from research.mass_candidate_factory.production_memory_telemetry import engineering_telemetry
from test_mcf_production_features import bars
from test_mcf_production_runtime import binding, freeze_artifact
from mcf_memory_baseline import legacy_validate, LegacyProductionFeatureCache


FAMILIES = {
    'TREND_CROSSOVER': {'fast_window': 4, 'slow_window': 24},
    'BREAKOUT_CHANNEL': {'entry_window': 4, 'exit_window': 2, 'breakout_buffer_fraction': '0'},
    'SHORT_HORIZON_MEAN_REVERSION': {'lookback': 4, 'entry_z': '1', 'exit_z': '0.1', 'trend_filter': 'MA200_UP_ONLY'},
    'SIMPLE_STATISTICAL_DEVIATION': {'lookback': 4, 'entry_z': '1', 'exit_z': '0.1'},
    'VOLUME_CONFIRMED_DIRECTION': {'return_lookback': 2, 'volume_window': 4, 'return_threshold': '0.001', 'volume_multiple': '1'},
    'SESSION_TIME_EFFECT': {'return_lookback': 2, 'return_threshold': '0.001', 'session_start_utc': 0, 'session_length_hours': 12},
    'LIQUIDITY_CONDITIONED_ENTRY': {'signal_lookback': 2, 'liquidity_window': 4, 'liquidity_rank_floor': '0.5'},
    'LEAD_LAG': {'peer': 'BTCUSDT', 'lag_bars': 2, 'peer_return_threshold': '0.001', 'response_mode': 'MOMENTUM'},
    'PRICE_VOLUME_INTERACTION': {'price_lookback': 2, 'volume_window': 4, 'price_threshold': '0.001', 'volume_multiple': '1'},
    'TRADE_COUNT_CONFIRMED_DIRECTION': {'return_lookback': 2, 'trade_count_window': 4, 'return_threshold': '0.001', 'trade_count_multiple': '1'},
}


def synthetic_bars(symbol='AAAUSDT', rows=280, timeframe='1h', gaps=True):
    cadence = CADENCE_MS[timeframe]
    times = tuple(DEVELOPMENT_START_MS + i * cadence for i in range(rows)
                  if not gaps or i not in (25, 70))
    closes = tuple(100.0 + (i % 20) * 0.2 + i * 0.01 for i in range(len(times)))
    return ProductionBars('SYNTHETIC-' + symbol, symbol, timeframe, times,
                          closes, tuple(c + .1 for c in closes), tuple(c - .1 for c in closes), closes,
                          tuple(100.0 + (i % 7) * 10 for i in range(len(times))),
                          tuple(10000.0 + (i % 11) * 100 for i in range(len(times))),
                          tuple(100.0 + (i % 5) * 5 for i in range(len(times))))


def validation_outcome(validate, item):
    try:
        return ('return', validate(item))
    except Exception as exc:
        return (type(exc), str(exc))


def allocation_peak(action):
    gc.collect()
    tracemalloc.start()
    try:
        retained = action()
        current, peak = tracemalloc.get_traced_memory()
        return current, peak
    finally:
        tracemalloc.stop()


class FeatureCacheMemoryTest(unittest.TestCase):
    def assert_validation_equal(self, item, rejected=False):
        expected = validation_outcome(legacy_validate, item)
        actual = validation_outcome(ProductionBars.validate, item)
        self.assertEqual(actual, expected)
        if rejected:
            self.assertIs(actual[0], MCFError)
        else:
            self.assertEqual(actual, ('return', None))

    def test_valid_bars_all_timeframes_gaps_boundaries_and_zero_activity(self):
        for tf in CADENCE_MS:
            for gaps in (True, False):
                with self.subTest(timeframe=tf, gaps=gaps):
                    b = synthetic_bars(timeframe=tf, gaps=gaps)
                    self.assert_validation_equal(b)
                    self.assert_validation_equal(replace(b, base_volume=(0.0,) * len(b.times),
                                                        quote_volume=(0.0,) * len(b.times),
                                                        trade_count=(0.0,) * len(b.times)))
            cadence = CADENCE_MS[tf]
            self.assert_validation_equal(replace(bars(), timeframe=tf,
                times=tuple(POPULATION_START_MS + i * cadence for i in range(8))))
            self.assert_validation_equal(replace(bars(), timeframe=tf,
                times=tuple(DEVELOPMENT_END_MS - (8-i) * cadence for i in range(8))))

    def test_invalid_identity_length_timestamp_cadence_and_ohlc_same_error(self):
        b = bars()
        mutations = [
            {'evidence_partition': 'FRESH_OOS'}, {'dataset_id': ''}, {'symbol': 'AAA'},
            {'timeframe': '1d'}, {'times': (b.times[0],)}, {'closes': b.closes[:-1]},
            {'times': (b.times[0],) * 8}, {'times': tuple(reversed(b.times))},
            {'times': (POPULATION_START_MS - 3600000,) + b.times[1:]},
            {'times': b.times[:-1] + (DEVELOPMENT_END_MS,)},
            {'times': tuple(t + 1 for t in b.times)},
            {'times': tuple(float(t) for t in b.times)},
            {'highs': (1.0,) + b.highs[1:]}, {'lows': (999.0,) + b.lows[1:]},
            # Multiple simultaneous faults prove error precedence is preserved.
            {'opens': (0.0,) + b.opens[1:], 'base_volume': (-1.0,) + b.base_volume[1:]},
            {'opens': (0.0,) + b.opens[1:], 'quote_volume': (float('nan'),) + b.quote_volume[1:]},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_validation_equal(replace(b, **mutation), rejected=True)

    def test_every_numeric_column_nonfinite_and_sign_rejection_same_error(self):
        b = bars()
        fields = ('opens', 'highs', 'lows', 'closes', 'base_volume', 'quote_volume', 'trade_count')
        for field in fields:
            for value in (float('nan'), float('inf'), float('-inf'), -1.0):
                for index in (0, 7):
                    values = list(getattr(b, field)); values[index] = value
                    with self.subTest(field=field, value=value, index=index):
                        self.assert_validation_equal(replace(b, **{field: tuple(values)}), rejected=True)
            if field in fields[:4]:
                self.assert_validation_equal(replace(b, **{field: (0.0,) + getattr(b, field)[1:]}), rejected=True)

    def test_direct_cache_and_peer_validation_still_fail_closed(self):
        b = bars()
        for cls in (LegacyProductionFeatureCache, ProductionFeatureCache):
            for invalid in (replace(b, times=(b.times[0],) * 8),
                            replace(b, opens=(0.0,) + b.opens[1:])):
                with self.subTest(cache=cls.__name__), self.assertRaises(MCFError):
                    cls(invalid)
                with self.assertRaises(MCFError):
                    cls(b, {'AAAUSDT': invalid})
            with self.assertRaises(MCFError):
                cls(b, {'BTCUSDT': b})
            with self.assertRaises(MCFError):
                cls(b, {'AAAUSDT': replace(b, timeframe='4h', times=tuple(POPULATION_START_MS + i*14400000 for i in range(8)))})

    def test_no_repository_consumer_depends_on_removed_index(self):
        root = Path(__file__).resolve().parents[1]
        excluded = {Path(__file__).resolve(), Path(__file__).with_name('mcf_memory_baseline.py').resolve()}
        consumers = []
        for path in root.rglob('*.py'):
            if path.resolve() in excluded or any(p.startswith('.') for p in path.relative_to(root).parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if ((isinstance(node, ast.Attribute) and node.attr == '_index') or
                    (isinstance(node, ast.Constant) and node.value == '_index')):
                    consumers.append(str(path.relative_to(root)))
        self.assertEqual(consumers, [])
        cache = ProductionFeatureCache(bars())
        self.assertNotIn('_index', vars(cache))

    def test_features_identical_including_peers_liquidity_and_source_identity(self):
        target = synthetic_bars()
        peer = synthetic_bars('BTCUSDT', gaps=False)
        current = ProductionFeatureCache(target, {'BTCUSDT': peer})
        with patch.object(ProductionBars, 'validate', legacy_validate):
            previous = LegacyProductionFeatureCache(target, {'BTCUSDT': peer})
        self.assertIs(current.bars, target)
        self.assertIs(current.peers['BTCUSDT'], peer)
        for field in ('opens', 'highs', 'lows', 'closes', 'base_volume', 'quote_volume', 'trade_count'):
            for stat in ('mean', 'std', 'min', 'max', 'median', 'sum', 'quantile'):
                for lag in (0, 1):
                    args = dict(lag=lag, statistic=stat, quantile=.75 if stat=='quantile' else None)
                    with self.subTest(field=field, stat=stat, lag=lag):
                        self.assertEqual(current.rolling(field, 4, **args), previous.rolling(field, 4, **args))
        for window in (1, 4, 24):
            self.assertEqual(current.lagged_return(window), previous.lagged_return(window))
            self.assertEqual(current.zscore_vs_lagged(window), previous.zscore_vs_lagged(window))
            self.assertEqual(current.peer_return('BTCUSDT', window), previous.peer_return('BTCUSDT', window))
            self.assertEqual(current.peer_return('ETHUSDT', window), previous.peer_return('ETHUSDT', window))
        self.assertEqual(current.range_fraction(), previous.range_fraction())
        self.assertEqual(current.identity(), previous.identity())
        bound = replace(binding(), membership_snapshots=(MembershipSnapshot(DEVELOPMENT_START_MS, ('AAAUSDT', 'BTCUSDT'), 'a'*64),))
        self.assertEqual(liquidity_percentiles({'AAAUSDT': current, 'BTCUSDT': ProductionFeatureCache(peer)}, 4, bound),
                         liquidity_percentiles({'AAAUSDT': previous, 'BTCUSDT': LegacyProductionFeatureCache(peer)}, 4, bound))

    def test_all_ten_family_synthetic_signals_and_accounting_byte_equivalent(self):
        matrix = {s: synthetic_bars(s, gaps=s!='BTCUSDT') for s in ('AAAUSDT', 'BBBUSDT', 'BTCUSDT', 'ETHUSDT')}
        bound = replace(binding(), membership_snapshots=(MembershipSnapshot(DEVELOPMENT_START_MS, tuple(sorted(matrix)), 'a'*64),))
        for family, params in FAMILIES.items():
            with self.subTest(family=family):
                freeze = copy.deepcopy(freeze_artifact())
                candidate = freeze['executable'][0]
                candidate.update(family=family, parameter_vector=params)
                def run():
                    runtime = runtime_module.ProductionRuntime(synthetic_fixture=True, executable_freeze=freeze,
                        binding=bound, bars_by_timeframe={'1h': matrix})
                    result = runtime.run(candidate['candidate_id'])
                    return canonical(result), canonical({s: asdict(runtime_module.compile_candidate(candidate, cache,
                        universe_binding=bound, liquidity_percentile=runtime._liquidity_percentiles('1h',4)[s]
                        if family=='LIQUIDITY_CONDITIONED_ENTRY' else None))
                        for s,cache in runtime._timeframe_caches('1h').items()})
                with patch.object(ProductionBars, 'validate', legacy_validate), patch.object(runtime_module, 'ProductionFeatureCache', LegacyProductionFeatureCache):
                    baseline = run()
                self.assertEqual(run(), baseline)

    def test_runtime_keeps_all_validation_calls_and_rejects_map_mismatch(self):
        matrix = {s: synthetic_bars(s) for s in ('AAAUSDT', 'BBBUSDT', 'BTCUSDT', 'ETHUSDT')}
        bound = replace(binding(), membership_snapshots=(MembershipSnapshot(DEVELOPMENT_START_MS, tuple(sorted(matrix)), 'a'*64),))
        def runtime(items):
            return runtime_module.ProductionRuntime(synthetic_fixture=True, executable_freeze=freeze_artifact(),
                binding=bound, bars_by_timeframe={'1h': items})
        visited = []
        original = ProductionBars.validate
        def tracked(b):
            visited.append(b.symbol); return original(b)
        with patch.object(ProductionBars, 'validate', tracked):
            caches = runtime(matrix)._timeframe_caches('1h')
        self.assertEqual(len(visited), 14)  # admission 4, own bars 4, peers 6
        for symbol, cache in caches.items():
            self.assertIs(cache.bars, matrix[symbol])
            for peer_symbol, peer in cache.peers.items():
                self.assertIs(peer, matrix[peer_symbol])
        with self.assertRaises(MCFError):
            runtime({**matrix, 'AAAUSDT': matrix['BBBUSDT']})._timeframe_caches('1h')
        with self.assertRaises(MCFError):
            runtime({**matrix, 'AAAUSDT': synthetic_bars('AAAUSDT', timeframe='4h')})._timeframe_caches('1h')

    def test_synthetic_validation_allocation_is_bounded_with_row_count(self):
        for rows in (10000, 20000):
            b = synthetic_bars(rows=rows, gaps=False)
            _, old_peak = allocation_peak(lambda: legacy_validate(b))
            _, new_peak = allocation_peak(b.validate)
            self.assertGreater(old_peak, rows * 40)
            self.assertLess(new_peak, 16000)
            self.assertLess(new_peak, old_peak // 10)

    def test_synthetic_cache_has_no_per_timestamp_retained_allocation(self):
        b = synthetic_bars(rows=20000, gaps=False)
        with patch.object(ProductionBars, 'validate', legacy_validate):
            old_current, old_peak = allocation_peak(lambda: LegacyProductionFeatureCache(b))
        new_current, new_peak = allocation_peak(lambda: ProductionFeatureCache(b))
        self.assertGreater(old_current, 20000 * 20)
        self.assertLess(new_current, 16000)
        self.assertLess(new_peak, old_peak // 10)

    def test_remediated_synthetic_runtime_telemetry_excludes_economics(self):
        # Deliberately synthetic identity; never request or construct runtime authorization.
        identity = {'candidate_id': 'SYNTHETIC-MEMORY-TEST', 'candidate_spec_sha256': 'a'*64,
                    'runner_input_sha256': 'b'*64, 'git_sha': 'c'*40}
        stream = io.StringIO()
        runtime = runtime_module.ProductionRuntime(synthetic_fixture=True, executable_freeze=freeze_artifact(),
            binding=binding(), bars_by_timeframe={'1h': {s: synthetic_bars(s) for s in ('AAAUSDT','BBBUSDT')}})
        with engineering_telemetry(CheckpointSink(stream, identity)):
            result = runtime.run('MCF-PROD-001-000000')
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row), CHECKPOINT_KEYS)
            validate_checkpoint(row, identity)
        for field in ('completed_trades', 'aggregate_base_net_return', 'result_sha256',
                      'failure_reasons', 'f0_f3_state', 'per_symbol_base'):
            self.assertNotIn(field, stream.getvalue())
        for key in ('fresh_oos_read', 'recent_reserve_read', 'p10_read', 'p10_write', 'live',
                    'futures', 'leverage', 'short', 'order_endpoint', 'ai_direct_execution'):
            self.assertIs(SAFETY[key], False)
            if key in result['safety']:
                self.assertIs(result['safety'][key], False)
        self.assertIs(SAFETY['p11_locked'], True)
        self.assertEqual(SAFETY['live_master_lock'], 'OFF')


if __name__ == '__main__':
    unittest.main()
