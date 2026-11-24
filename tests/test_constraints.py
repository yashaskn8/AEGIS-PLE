from dataclasses import replace
from decimal import localcontext
import random
import unittest

from aegis.aggregation import Fixture, aggregate_first
from aegis.constraints import Controller, Requirement
from aegis.firewall import State, assess, gate
from aegis.graph_experiment import CHECKS, NODES, SCENARIOS, run


class Constraints(unittest.TestCase):
    def test_contradictory_evidence(self):
        a, b = assess(aggregate_first, Fixture("proof", (500,))).evidence
        binding = dict(candidate=a.candidate, fixture=a.fixture,
                       output=a.output, verifier=a.verifier)
        self.assertIs(gate((a, replace(b, actual="999")), **binding), State.FAILED)

    def test_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            result = assess(aggregate_first, Fixture("precision", (999999,) * 100))
        self.assertIs(result.state, State.VERIFIED)

    def test_graph_schema(self):
        for nodes, checks in (
            ((Requirement("a", (), ("a",)),), {"a": lambda f: True}),
            ((Requirement("a", (), ("missing",)),), {"a": lambda f: True}),
            ((Requirement("a", ()), Requirement("a", ())), {"a": lambda f: True}),
            ((Requirement("a", ()),), {}),
            ((Requirement("a", ("x", "x")),), {"a": lambda f: True}),
        ):
            with self.assertRaises(ValueError):
                Controller(nodes, checks)

    def test_dependency_invalidation(self):
        c = Controller(NODES, CHECKS)
        self.assertEqual(c.evaluate(SCENARIOS[0]).evaluated, 4)
        self.assertEqual(c.evaluate(SCENARIOS[1]).evaluated, 2)
        self.assertFalse(c.evaluate(SCENARIOS[2]).verified)
        self.assertTrue(c.evaluate(SCENARIOS[3]).verified)
        self.assertEqual(c.evaluate(SCENARIOS[4]).evaluated, 3)

    def test_missing_and_compound_failures(self):
        c = Controller(NODES, CHECKS)
        c.evaluate(SCENARIOS[0])
        r = c.evaluate({"revision": 0, "label": "", "total": 5})
        self.assertEqual([x.status for x in r.evidence],
                         ["FAILED", "BLOCKED", "FAILED", "BLOCKED"])
        self.assertFalse(r.verified)
        self.assertTrue(c.evaluate(SCENARIOS[0]).verified)

    def test_failure_not_cached(self):
        calls = []
        def check(facts):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("transient")
            return True
        c = Controller((Requirement("x", ()),), {"x": check})
        self.assertFalse(c.evaluate({}).verified)
        self.assertTrue(c.evaluate({}).verified)
        self.assertEqual(len(calls), 2)

    def test_candidate_data_not_executable(self):
        c = Controller(NODES, CHECKS)
        f = dict(SCENARIOS[0], items=["not a number"])
        self.assertFalse(c.evaluate(f).verified)
        with self.assertRaises(ValueError):
            c.evaluate({"label": "x" * 65537})
        with self.assertRaises(ValueError):
            c.evaluate({"label": float("nan")})

    def test_randomized_differential(self):
        rng = random.Random(20261125)
        inc = Controller(NODES, CHECKS)
        full = Controller(NODES, CHECKS)
        facts = dict(SCENARIOS[0])
        for _ in range(100):
            key = rng.choice(["revision", "items", "label", "total"])
            options = {"revision": [0, 1, 2], "items": [[], [1, 2], [4, 5], None],
                       "label": ["", "a", "b"], "total": [0, 3, 9]}
            facts[key] = rng.choice(options[key])
            self.assertEqual(inc.evaluate(facts).evidence,
                             full.evaluate(facts, reuse=False).evidence)

    def test_experiment(self):
        r = run()
        self.assertEqual(len(r["scenarios"]), 7)
        self.assertLess(r["incremental_checks"], r["full_checks"])
        self.assertEqual([x["verified"] for x in r["scenarios"]],
                         [True, True, False, True, True, False, True])
        self.assertEqual(r["promotion"], "BLOCKED")
