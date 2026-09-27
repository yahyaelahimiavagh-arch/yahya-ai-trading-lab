import tempfile
import unittest
from pathlib import Path
from mcf_fixtures import family
from research.mass_candidate_factory.generator import generate
from research.mass_candidate_factory.shards import finalize
from research.mass_candidate_factory.ledger import make_result,reconcile
class LedgerTest(unittest.TestCase):
    def test_reconcile_retains_failures_and_rejects_missing(self):
        batch,valid,invalid=generate([family()],batch_id="CAL-001",shard_size=2)
        raw=sorted(valid+invalid,key=lambda r:r["ordinal"])
        with tempfile.TemporaryDirectory() as d:
            artifacts=[]
            for sh in batch["shard_layout"]:
                rows=[make_result(r,batch,sh,dataset_id="SYNTHETIC-001",state="STRUCTURALLY_INVALID" if r in invalid else "DEVELOPMENT_FAIL",failure_reasons=r.get("failure_reasons",["NO_EDGE"])) for r in raw[sh["start"]:sh["end"]]]
                p,sha=finalize(Path(d),sh,rows);artifacts.append((sh,p,sha))
            self.assertEqual(reconcile(batch,raw,artifacts,dataset_id="SYNTHETIC-001")["status"],"BATCH_COMPLETE")
            self.assertEqual(reconcile(batch,raw,artifacts[:-1],dataset_id="SYNTHETIC-001")["status"],"BATCH_INVALID")
