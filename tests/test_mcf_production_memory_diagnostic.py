import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from research.mass_candidate_factory.models import MCFError, canonical, digest
from research.mass_candidate_factory.production_capacity_benchmark import select_benchmark_candidates, AUTHORIZATION_TOKEN
from research.mass_candidate_factory.production_generator import freeze_executable_generation
from research.mass_candidate_factory.production_rules import BLOCKED_FAMILIES
from research.mass_candidate_factory.production_memory_diagnostic import (
    AUTH_SCHEMA, SCOPE, SAFETY, STAGES, CheckpointSink, CheckpointJournal,
    identities, main, supervise, target_identity, validate_authorization, validate_checkpoint, execute_worker,
)
from research.mass_candidate_factory.production_memory_telemetry import engineering_telemetry, memory_stage
from research.mass_candidate_factory.production_worker_runner import validate_authorization as validate_full
from test_mcf_production_runtime import binding, bars, freeze_artifact
from research.mass_candidate_factory.production_runtime import ProductionRuntime


class MemoryDiagnosticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = identities('a' * 64, 'b' * 40)

    def authorization(self):
        base = {'schema': AUTH_SCHEMA, 'scope': SCOPE, 'authorized': True,
                'candidate_position': 9, 'candidate_count': 1,
                **self.identity, 'benchmark_selection_sha256': target_identity()['benchmark_selection_sha256'],
                'safety': dict(SAFETY)}
        return {**base, 'authorization_sha256': digest(base)}

    def row(self, stage='dataset_loading', phase='begin', pid=123):
        return {**self.identity, 'stage': stage, 'phase': phase,
                'rss_kib': 100, 'peak_rss_kib': 200, 'elapsed_seconds': 1.0, 'pid': pid}

    def test_exact_ninth_frozen_member_no_outcomes(self):
        freeze = freeze_executable_generation(BLOCKED_FAMILIES)
        selected = select_benchmark_candidates(freeze['executable'])
        target = target_identity()
        self.assertEqual(target['candidate_id'], selected[8]['candidate_id'])
        self.assertEqual(target['candidate_spec_sha256'], selected[8]['candidate_spec_sha256'])
        self.assertEqual(target['candidate_id'], 'MCF-PROD-001-004784')
        self.assertEqual(target['candidate_spec_sha256'], '73395d80d49f24818b9aedf8dbbfac35df3ad585f7d510a11d90778e0861f6c9')
        self.assertEqual(target['benchmark_selection_sha256'], '03f02f30f576b9e71c906d47ee15c200364f04cd187f229c00e54030c50a5248')
        self.assertEqual(selected[8], select_benchmark_candidates(tuple(reversed(freeze['executable'])))[8])

    def test_arbitrary_override_rejected_even_with_recomputed_digest(self):
        validate_authorization(self.authorization(), self.identity)
        for key, value in [('candidate_id', 'MCF-PROD-001-000001'), ('candidate_position', 8),
                           ('candidate_count', 24), ('scope', 'DEVELOPMENT_FULL_6852'),
                           ('candidate_spec_sha256', 'f' * 64)]:
            doc = self.authorization(); doc[key] = value
            doc['authorization_sha256'] = digest({k:v for k,v in doc.items() if k != 'authorization_sha256'})
            with self.subTest(key=key), self.assertRaises(MCFError):
                validate_authorization(doc, self.identity)

    def test_economics_and_unexpected_fields_fail_closed(self):
        for field in ('pnl', 'returns', 'drawdown', 'sharpe', 'dsr', 'pbo', 'completed_trades',
                      'signal_count', 'gate_pass', 'survivor', 'rank', 'score', 'promotion',
                      'per_symbol_economics', 'unexpected'):
            with self.subTest(field=field), self.assertRaises(MCFError):
                validate_checkpoint({**self.row(), field: 999}, self.identity)
        for stage in ('profit=999', 'F0_F3_PASS'):
            with self.assertRaises(MCFError):
                validate_checkpoint(self.row(stage), self.identity)

    def test_nonnumeric_or_nonfinite_telemetry_rejected(self):
        for key, value in [('rss_kib', True), ('pid', '123'), ('elapsed_seconds', float('nan')),
                           ('elapsed_seconds', float('inf')), ('rss_kib', -1)]:
            with self.subTest(key=key), self.assertRaises(MCFError):
                validate_checkpoint({**self.row(), key:value}, self.identity)

    def test_checkpoints_flushed_before_next_stage(self):
        class Stream(io.StringIO):
            flush_count = 0
            def flush(self):
                self.flush_count += 1
        stream = Stream()
        with engineering_telemetry(CheckpointSink(stream, self.identity)):
            with memory_stage('dataset_loading'):
                self.assertEqual(stream.flush_count, 1)
                self.assertEqual(json.loads(stream.getvalue())['phase'], 'begin')
            with memory_stage('feature_cache_initialization'):
                self.assertEqual(stream.flush_count, 3)
        self.assertEqual(stream.flush_count, 4)

    def test_exception_has_no_false_end(self):
        stream = io.StringIO()
        with self.assertRaises(RuntimeError), engineering_telemetry(CheckpointSink(stream, self.identity)):
            with memory_stage('simulation_replay'):
                raise RuntimeError('private economics')
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        self.assertNotIn('private', stream.getvalue())

    def synthetic_child(self, fd, payload, kill=False, exit137=False):
        code = ('import os,sys,json,signal\n'
                f'rows=json.loads({json.dumps(payload)!r})\n'
                'for row in rows:\n'
                ' row["pid"]=os.getpid()\n'
                f' os.write({fd}, (json.dumps(row)+"\\n").encode())\n'
                # Deliberate stdout/stderr secrets must never persist.
                'print("PNL_SECRET_999", flush=True)\n'
                'print("SHARPE_SECRET_999", file=sys.stderr, flush=True)\n')
        if kill:
            code += 'os.kill(os.getpid(),signal.SIGKILL)\n'
        elif exit137:
            code += 'sys.exit(137)\n'
        return [sys.executable, '-c', code]

    def test_real_subprocess_sigkill_and_exit137_preserve_last_stage(self):
        payload = [self.row('frozen_input_admission'), self.row('frozen_input_admission', 'end'),
                   self.row('dataset_loading')]
        for kill in (True, False):
            with self.subTest(kill=kill), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'diagnostic'
                result = supervise(lambda fd: self.synthetic_child(fd, payload, kill, not kill), self.identity, root)
                self.assertEqual(result['child_exit_code'], 137)
                self.assertEqual(result['child_signal'], 9)
                self.assertFalse(result['diagnostic_completed'])
                self.assertEqual(result['status'], 'DIAGNOSTIC_INCOMPLETE')
                self.assertEqual(result['last_completed_stage'], 'frozen_input_admission')
                self.assertEqual(result['active_stage'], 'dataset_loading')
                self.assertEqual(len((root/'checkpoints.jsonl').read_text().splitlines()), 3)
                self.assertNotIn('SECRET', (root/'summary.json').read_text() + (root/'checkpoints.jsonl').read_text())
                self.assertIn('OOM_UNCONFIRMED', result['termination'])

    def test_unexpected_child_fields_never_persist(self):
        payload = [self.row(), {**self.row(phase='end'), 'pnl': 'PRIVATE_123'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'diagnostic'
            result = supervise(lambda fd: self.synthetic_child(fd, payload), self.identity, root)
            self.assertEqual(result['status'], 'DIAGNOSTIC_BOUNDARY_REJECTED')
            self.assertNotIn('PRIVATE', (root/'checkpoints.jsonl').read_text() + (root/'summary.json').read_text())
            self.assertFalse(result['diagnostic_completed'])

    def test_normal_completion_requires_all_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = [self.row(stage, phase) for stage in STAGES for phase in ('begin','end')]
            result = supervise(lambda fd: self.synthetic_child(fd, payload), self.identity, Path(tmp)/'diagnostic')
            self.assertTrue(result['diagnostic_completed'])
            for key in ('selection_authorized', 'full_batch_authorized', 'benchmark_retry_authorized'):
                self.assertIs(result[key], False)
        with tempfile.TemporaryDirectory() as tmp:
            result = supervise(lambda fd: self.synthetic_child(fd, []), self.identity, Path(tmp)/'diagnostic')
            self.assertFalse(result['diagnostic_completed'])

    def test_no_retry_or_full_batch_authority(self):
        doc = self.authorization()
        self.assertNotEqual(doc['scope'], AUTHORIZATION_TOKEN)
        with self.assertRaises(MCFError):
            validate_full(doc, plan_sha256='a'*64, runner_input_sha256='a'*64, git_sha='b'*40)
        for scope in (AUTHORIZATION_TOKEN, 'DEVELOPMENT_FULL_6852'):
            bad = {**doc, 'scope': scope}
            with self.assertRaises(MCFError):
                validate_authorization(bad, self.identity)

    def test_all_safety_locks_cannot_be_changed(self):
        for key in SAFETY:
            doc = self.authorization()
            doc['safety'][key] = not SAFETY[key] if type(SAFETY[key]) is bool else 'ON'
            doc['authorization_sha256'] = digest({k:v for k,v in doc.items() if k != 'authorization_sha256'})
            with self.subTest(key=key), self.assertRaises(MCFError):
                validate_authorization(doc, self.identity)

    def test_runtime_instrumentation_unchanged_synthetic_result(self):
        def runtime():
            return ProductionRuntime(synthetic_fixture=True, executable_freeze=freeze_artifact(),
                                     binding=binding(), bars_by_timeframe={'1h':{'AAAUSDT':bars('AAAUSDT'),'BBBUSDT':bars('BBBUSDT')}})
        plain = runtime().run('MCF-PROD-001-000000')
        emitted = []
        with engineering_telemetry(lambda stage, phase: emitted.append((stage,phase))):
            observed = runtime().run('MCF-PROD-001-000000')
        self.assertEqual(plain, observed)
        self.assertEqual(emitted, [(stage,phase) for stage in ('feature_cache_initialization',
            'feature_signal_compilation','simulation_replay','result_accounting','result_construction','result_digest')
            for phase in ('begin','end')])

    def test_cli_rejects_execution_without_new_authorization_before_data_read(self):
        with tempfile.TemporaryDirectory() as tmp, patch('research.mass_candidate_factory.production_memory_diagnostic.current_git_sha',return_value='b'*40), patch('research.mass_candidate_factory.production_runner_input.FrozenRunnerInput') as reader:
            args=['diagnose','--runtime-root',tmp,'--input-relative','runner-input/input-'+ 'a'*64+'.json',
                  '--expected-input-sha256','a'*64,'--expected-git-sha','b'*40]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(args),2)
            reader.assert_not_called()
            self.assertEqual(json.loads(out.getvalue())['status'],'DIAGNOSTIC_BLOCKED')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['preflight',*args[1:]]),0)
            reader.assert_not_called()
            for path in ('p10','fresh_oos','recent_reserve'):
                bad=list(args);bad[2]=str(Path(tmp)/path)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(bad),2)

    def test_worker_discards_synthetic_economics_and_cleans_up(self):
        class SyntheticRuntime:
            executable_freeze = None
            released = False
            def run(inner, candidate_id, *, director_authorized=False):
                self.assertEqual(candidate_id, self.identity['candidate_id'])
                self.assertIs(director_authorized, True)
                for stage in STAGES[2:-2]:
                    with memory_stage(stage):
                        pass
                return {**self.identity, 'pnl': 'SECRET_PNL', 'gate_pass': 'SECRET_GATE'}
            def release_transient_features(inner):
                inner.released = True
        runtime = SyntheticRuntime()
        args = SimpleNamespace(expected_input_sha256='a'*64, expected_git_sha='b'*40,
                               authorization=Path('/tmp/synthetic-auth'),runtime_root=Path('/tmp/synthetic-data'),
                               input_relative='runner-input/input-'+ 'a'*64+'.json')
        stream=io.StringIO()
        with patch('research.mass_candidate_factory.production_memory_diagnostic.current_git_sha',return_value='b'*40), \
             patch('research.mass_candidate_factory.production_memory_diagnostic.load_authorization'), \
             patch('research.mass_candidate_factory.production_memory_diagnostic.resource.setrlimit'), \
             patch('research.mass_candidate_factory.production_runner_input.FrozenRunnerInput'), \
             patch.object(ProductionRuntime,'from_frozen_input',return_value=runtime):
            execute_worker(args,stream)
        self.assertTrue(runtime.released)
        self.assertNotIn('SECRET',stream.getvalue())
        rows=[json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([(r['stage'],r['phase']) for r in rows],[(stage,phase) for stage in STAGES for phase in ('begin','end')])
        for row in rows: validate_checkpoint(row,self.identity)

    def test_cli_has_no_arbitrary_candidate_switch(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['diagnose', '--candidate-id', 'MCF-PROD-001-000001'])

    def test_stage_order_pid_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (Path(tmp)/'log').open('w') as log:
                journal=CheckpointJournal(log,self.identity,123)
                with self.assertRaises(MCFError):journal.accept(self.row(phase='end'))
                with self.assertRaises(MCFError):journal.accept(self.row(pid=124))
            root=Path(tmp)/'diagnostic';root.mkdir()
            with self.assertRaises(FileExistsError):supervise(lambda fd:[],self.identity,root)


if __name__ == '__main__':
    unittest.main()
