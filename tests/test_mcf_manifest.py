import unittest
from copy import deepcopy
from mcf_fixtures import family
from research.mass_candidate_factory.manifest import validate
from research.mass_candidate_factory.models import MCFError

class ManifestTest(unittest.TestCase):
    def test_valid_deterministic(self):
        m=family();self.assertEqual(validate(m),validate(deepcopy(m)))
    def test_exact_and_unbounded(self):
        for mutate in (lambda x:x.pop("source_refs"),lambda x:x.update(rogue=True),lambda x:x["parameter_domains"][0].update(stop=10000000),lambda x:x["market_scope"].update(universe_policy_ref="../p10"),lambda x:x["safety"].update(leverage=True),lambda x:x["generation_budget"].update(hidden_trials_forbidden=False),lambda x:x.update(data_dependencies=["ORDER_BOOK"]),lambda x:x["signal_template"].update(operator="eval")):
            m=family();mutate(m)
            with self.assertRaises(MCFError):validate(m)
