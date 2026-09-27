import unittest
from mcf_fixtures import policy
from research.mass_candidate_factory.exact import account,compare
from research.mass_candidate_factory.screening import float_account,screen
class ExactTest(unittest.TestCase):
    def test_discrepancy_and_gray_zone(self):
        s=(True,True,False,False,False);o=(10,11,12,13,14);c=o
        f=float_account(s,o,c,policy());e=account(s,o,c,policy())
        self.assertEqual(compare(f,e,guard_band="0.000001")["exact_recompute_state"],"EXACT_AGREES")
        x=screen(s,o,c,policy(),cost_policy_ref="COST/v1",thresholds={"minimum_signals":2},folds=((0,5),),fixture_id="SYNTHETIC-001")
        self.assertEqual(x["exact_recompute_state"],"EXACT_RECOMPUTED")
        self.assertNotEqual(x["result_state"],"DEVELOPMENT_SURVIVOR")
