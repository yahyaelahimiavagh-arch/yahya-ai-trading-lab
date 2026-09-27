import tempfile
import unittest
from pathlib import Path
from research.mass_candidate_factory.shards import layout,finalize
from research.mass_candidate_factory.models import MCFError
class ShardTest(unittest.TestCase):
    def test_idempotent_and_collision(self):
        sh=layout("B",5,2);self.assertEqual([(x["start"],x["end"]) for x in sh],[(0,2),(2,4),(4,5)])
        with tempfile.TemporaryDirectory() as d:
            r=[{"ordinal":0,"v":1},{"ordinal":1,"v":2}]
            a=finalize(Path(d),sh[0],r);self.assertEqual(a,finalize(Path(d),sh[0],r))
            with self.assertRaises(MCFError):finalize(Path(d),sh[0],[{"ordinal":0,"v":9},r[1]])
