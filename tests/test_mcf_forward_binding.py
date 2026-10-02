"""Synthetic metadata only: no market evidence, filesystem or performance runs."""
import copy
from dataclasses import FrozenInstanceError
import unittest

from research.mass_candidate_factory.adjudication import adjudicate_forward_provenance
from research.mass_candidate_factory.forward_binding import (
    HASH_FIELDS, VERSION, ForwardIdentity, assess_forward_binding,
    bind_forward_evidence, require_forward_binding,
)
from research.mass_candidate_factory.models import MCFError, canonical, digest


def identity_record():
    return {
        "candidate_id": "MCF-SYNTHETIC-A",
        **{k: digest({"fixture": k}) for k in HASH_FIELDS},
        "runtime_code_sha256": {
            "research/mass_candidate_factory/production.py": "a" * 64,
            "research/mass_candidate_factory/forward_binding.py": "b" * 64,
        },
    }


class ForwardBindingTest(unittest.TestCase):
    def setUp(self):
        self.record = identity_record()
        self.expected = ForwardIdentity.from_record(self.record)
        self.binding = bind_forward_evidence(self.expected)

    def test_exact_candidate_spec_and_lineage_accepted(self):
        result = require_forward_binding(self.expected, self.binding)
        self.assertEqual(result.state, "BOUND_MATCH")
        decision = adjudicate_forward_provenance(expected=self.expected, binding=self.binding)
        self.assertEqual(decision["candidate_id"], self.record["candidate_id"])
        self.assertFalse(decision["promotion_authorized"])
        self.assertFalse(decision["live_authorized"])
        self.assertEqual(decision["adjudication_sha256"],
                         digest({k: v for k, v in decision.items() if k != "adjudication_sha256"}))

    def test_every_identity_substitution_rejected_even_if_resealed(self):
        for field in self.record:
            with self.subTest(field=field):
                other = copy.deepcopy(self.record)
                other[field] = ({"different/code.py": "c" * 64} if field == "runtime_code_sha256"
                                else "MCF-SYNTHETIC-B" if field == "candidate_id" else "f" * 64)
                artifact = bind_forward_evidence(ForwardIdentity.from_record(other))
                result = assess_forward_binding(self.expected, artifact)
                self.assertFalse(result.binding_valid)
                self.assertEqual(result.mismatched_fields, (field,))
                with self.assertRaises(MCFError):
                    adjudicate_forward_provenance(expected=self.expected, binding=artifact)

    def test_missing_each_identity_field_fails_closed_even_if_rehashed(self):
        for field in self.record:
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.binding)
                del artifact["identity"][field]
                artifact["binding_sha256"] = digest({k: v for k, v in artifact.items()
                                                     if k != "binding_sha256"})
                self.assertEqual(assess_forward_binding(self.expected, artifact).state, "INVALID_BINDING")
                with self.assertRaises(MCFError):
                    require_forward_binding(self.expected, artifact)

    def test_missing_envelope_fields_or_unknown_fields_rejected(self):
        for field in self.binding:
            artifact = copy.deepcopy(self.binding)
            del artifact[field]
            with self.subTest(field=field), self.assertRaises(MCFError):
                require_forward_binding(self.expected, artifact)
        for where in ("identity", "envelope"):
            artifact = copy.deepcopy(self.binding)
            (artifact["identity"] if where == "identity" else artifact)["extra"] = "ambiguous"
            with self.subTest(where=where), self.assertRaises(MCFError):
                require_forward_binding(self.expected, artifact)

    def test_legacy_baseline_and_absent_evidence_cannot_supply_credibility(self):
        fixtures = (None, {}, {"candidate_sha256": "a" * 64, "disposition": "PASS_CANDIDATE"},
                    {"schema": "BASELINE_FORWARD_GATE/1.0.0", "disposition": "PASS_CANDIDATE"})
        states = ("MISSING_BINDING", "LEGACY_UNBOUND", "LEGACY_UNBOUND", "UNSUPPORTED_SCHEMA")
        for artifact, state in zip(fixtures, states):
            with self.subTest(state=state):
                self.assertEqual(assess_forward_binding(self.expected, artifact).state, state)
                with self.assertRaises(MCFError):
                    adjudicate_forward_provenance(expected=self.expected, binding=artifact)

    def test_stale_report_registration_window_snapshot_policy_code_and_runner_rejected(self):
        for field in ("forward_report_sha256", "forward_registration_sha256", "window_sha256",
                      "ingestion_snapshot_sha256", "gate_registry_sha256", "runner_input_sha256",
                      "runtime_code_sha256"):
            current = copy.deepcopy(self.record)
            current[field] = ({"new/code.py": "d" * 64} if field == "runtime_code_sha256" else "d" * 64)
            with self.subTest(field=field), self.assertRaises(MCFError):
                require_forward_binding(ForwardIdentity.from_record(current), self.binding)

    def test_tampered_digest_and_unsupported_schema_rejected(self):
        for field, value in (("binding_sha256", "0" * 64), ("schema", "MCF_FORWARD_EVIDENCE_BINDING/2.0.0")):
            artifact = copy.deepcopy(self.binding)
            artifact[field] = value
            with self.subTest(field=field), self.assertRaises(MCFError):
                require_forward_binding(self.expected, artifact)

    def test_canonical_order_serialization_and_hash(self):
        reversed_record = dict(reversed(list(self.record.items())))
        reversed_record["runtime_code_sha256"] = dict(reversed(list(self.record["runtime_code_sha256"].items())))
        reordered = bind_forward_evidence(ForwardIdentity.from_record(reversed_record))
        self.assertEqual(canonical(self.binding), canonical(reordered))
        self.assertTrue(canonical(self.binding).endswith(b"\n"))
        self.assertEqual(self.binding["binding_sha256"], digest({"schema": VERSION, "identity": self.record}))
        self.assertEqual(adjudicate_forward_provenance(expected=self.expected, binding=self.binding),
                         adjudicate_forward_provenance(expected=self.expected, binding=reordered))

    def test_immutable_provenance_and_detached_serialization(self):
        self.record["runtime_code_sha256"].clear()
        self.expected.as_record()["runtime_code_sha256"].clear()
        self.binding["identity"]["runtime_code_sha256"].clear()
        self.assertEqual(len(self.expected.runtime_code_sha256), 2)
        with self.assertRaises(FrozenInstanceError):
            self.expected.candidate_id = "B"
        with self.assertRaises(MCFError):
            ForwardIdentity(self.expected.candidate_id, list(self.expected.hashes), self.expected.runtime_code_sha256)

    def test_malformed_identity_inputs_fail_closed(self):
        for field, value in (("candidate_id", ""), ("candidate_id", " A"),
                             ("candidate_spec_sha256", True), ("candidate_spec_sha256", "A" * 64),
                             ("runtime_code_sha256", {}), ("runtime_code_sha256", {"../code.py": "a" * 64}),
                             ("runtime_code_sha256", {"/code.py": "a" * 64}),
                             ("runtime_code_sha256", {1: "a" * 64})):
            record = identity_record()
            record[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(MCFError):
                ForwardIdentity.from_record(record)
        for artifact in ([], "PASS", 1, True):
            with self.subTest(artifact=artifact), self.assertRaises(MCFError):
                require_forward_binding(self.expected, artifact)
        with self.assertRaises(MCFError):
            require_forward_binding(self.record, self.binding)


if __name__ == "__main__":
    unittest.main()
