import unittest
from copy import deepcopy
from mcf_fixtures import family
from research.mass_candidate_factory.generator import generate
from research.mass_candidate_factory.models import MCFError

class GeneratorTest(unittest.TestCase):
    def test_identity_preperformance_and_invalid(self):
        a=generate([family()],batch_id="CAL-001",shard_size=2)
        b=generate([deepcopy(family())],batch_id="CAL-001",shard_size=2)
        self.assertEqual(a,b)
        batch,valid,invalid=a
        self.assertEqual((batch["raw_candidate_count"],len(valid),len(invalid)),(6,4,2))
        self.assertEqual([r["ordinal"] for r in valid+invalid if r["candidate_id"]=="MCF-2026-01-000002"],[2])
        with self.assertRaises(MCFError):generate([family(),family()],batch_id="CAL-001")
