from itertools import permutations
import json
import unittest
from aegis.documents import reconcile
from aegis.document_experiment import record, run, cases

M = {"register": 2, "summary": 1}
R = ("inventory_count",)


class Documents(unittest.TestCase):
    def test_fixed_category_experiment(self):
        result = run()
        self.assertEqual(result["cases"], 40)
        self.assertEqual(result["metrics"]["full"]["correct"], 40)
        self.assertEqual(result["metrics"]["full"]["false_accepts"], 0)
        self.assertEqual(result["metrics"]["full"]["valid_records_recovered"], 12)
        self.assertLess(result["metrics"]["baseline"]["correct"], 40)
        self.assertEqual(len({x.category for x in cases()}), 4)

    def test_order_invariance(self):
        docs = (record("register", 1, 3), record("register", 2, 4),
                record("summary", 1, 4))
        result = reconcile(M, R, docs)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        for order in permutations(docs):
            self.assertEqual(reconcile(M, R, order), result)

    def test_no_obsolete_fallback(self):
        result = reconcile(M, R, (record("register", 1, 4), record("summary", 1, 4)))
        self.assertIn("missing_current_revision", result.reasons)
        self.assertEqual(result.facts, ())

    def test_conflicting_provenance(self):
        a = reconcile(M, R, (record("register", 2, 4), record("summary", 1, 4)))
        b = reconcile(M, R, (record("register", 2, 5), record("summary", 1, 4)))
        self.assertEqual(len(a.facts[0].sources), 2)
        self.assertNotEqual(a.input_binding, b.input_binding)
        self.assertEqual(b.reasons, ("conflicting_fact:inventory_count",))

    def test_unapproved_and_duplicate(self):
        docs = (record("register", 2, 4), record("summary", 1, 4))
        r = reconcile(M, R, docs + (record("register", 3, 4), docs[0]))
        self.assertEqual(set(r.reasons), {"unapproved_source_or_revision", "duplicate_revision"})
        self.assertFalse(r.facts)

    def test_malformed_boolean_duplicate_keys(self):
        for raw in (b'{"family":"register","family":"summary","revision":2,"fields":{}}',
                    record("register", 2, True), record("register", True, 1), b'\xff'):
            r = reconcile(M, R, (raw, record("summary", 1, 4)))
            self.assertIn("malformed_document", r.reasons)
            self.assertEqual(r.status, "BLOCKED")

    def test_manifest_and_limits(self):
        for m, r in (({"register": True}, R), (M, ("inventory_count", "inventory_count")),
                     (M, ()), ({}, R)):
            with self.assertRaises(ValueError):
                reconcile(m, r, ())
        with self.assertRaises(ValueError):
            reconcile(M, R, (b"x" * 8193,))

    def test_required_fact_absent(self):
        r = reconcile(M, R, (record("register", 2, None), record("summary", 1, None)))
        self.assertEqual(r.reasons, ("missing_fact:inventory_count",))
        self.assertFalse(r.facts)
