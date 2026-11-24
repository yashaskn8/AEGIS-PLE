from dataclasses import replace
import random
import unittest

from aegis.aggregation import Fixture, aggregate_first, premature_rounding
from aegis.experiment import run
from aegis.firewall import State, assess, gate


def malformed(values):
    return {"total_mm": True}


def broken(values):
    raise RuntimeError("synthetic failure")


class Foundation(unittest.TestCase):
    def test_defect(self):
        result = assess(premature_rounding, Fixture("defect", (490, 490)))
        self.assertIs(result.state, State.FAILED)
        self.assertEqual(result.evidence[1].expected, "1")
        self.assertEqual(result.evidence[1].actual, "0")

    def test_correction(self):
        result = assess(aggregate_first, Fixture("defect", (490, 490)))
        self.assertIs(result.state, State.VERIFIED)

    def test_schema_and_exception(self):
        fixture = Fixture("invalid", (1,))
        for candidate in (malformed, broken):
            self.assertIs(assess(candidate, fixture).state, State.FAILED)

    def test_fixture_validation(self):
        for values in ((), (-1,), (True,), (1_000_001,), (1,) * 101):
            with self.assertRaises(ValueError):
                Fixture("invalid", values)

    def test_missing_duplicate_stale_and_failed_evidence(self):
        result = assess(aggregate_first, Fixture("gate", (200, 300)))
        first, second = result.evidence
        binding = dict(candidate=first.candidate, fixture=first.fixture,
                       output=first.output, verifier=first.verifier)
        self.assertIs(gate(result.evidence, **binding), State.VERIFIED)
        for records in ((), (first,), (first, first),
                        (first, replace(second, output="stale")),
                        (first, replace(second, verifier="stale")),
                        (first, replace(second, candidate="other")),
                        (first, replace(second, fixture="other")),
                        (first, replace(second, state=State.FAILED)),
                        (first, replace(second, requirement="unexpected"))):
            self.assertIs(gate(records, **binding), State.FAILED)

    def test_transfer_and_bounded_recommendation(self):
        report = run()
        self.assertEqual(report["candidate_executions"], 12)
        self.assertEqual(report["recommended"], "aggregate_first")
        self.assertEqual(report["promotion"], "BLOCKED")
        self.assertEqual(report["champion"], "premature_rounding")

    def test_seeded_differential_and_metamorphic(self):
        rng = random.Random(20261124)
        for index in range(100):
            values = tuple(rng.randrange(0, 10000) for _ in range(8))
            with self.subTest(index=index):
                self.assertIs(assess(aggregate_first, Fixture(str(index), values)).state,
                              State.VERIFIED)
                original = aggregate_first(values)
                self.assertEqual(original, aggregate_first(tuple(reversed(values))))
                self.assertEqual(original, aggregate_first(values + (0,)))
                self.assertEqual(original, aggregate_first((sum(values),)))

    def test_boundary_cases(self):
        for value, expected in ((0, 0), (499, 0), (500, 1), (999, 1), (1500, 2)):
            self.assertEqual(aggregate_first((value,)), {"total_mm": expected})
            self.assertIs(assess(aggregate_first, Fixture(str(value), (value,))).state,
                          State.VERIFIED)
