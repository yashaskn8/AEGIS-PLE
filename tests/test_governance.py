from copy import deepcopy
import json
from pathlib import Path
import unittest

from aegis.ci_evidence import validate, replay
from aegis.constraints import Controller
from aegis.graph_experiment import NODES, CHECKS, SCENARIOS

COMMIT = "e1f8c17921be07268a30874624bc9d50132f20c7"
RUN = 45434137959
ARCHIVE = Path("research/evidence") / (COMMIT + ".json")
BINDING = dict(expected_commit=COMMIT, expected_run=RUN, expected_tests=36)


class Governance(unittest.TestCase):
    def test_historical_replay(self):
        result = replay(ARCHIVE, **BINDING)
        self.assertEqual(result["status"], "VERIFIED_HISTORICAL_RECORD")
        self.assertEqual(result["promotion"], "BLOCKED")

    def test_stale_and_missing_ci(self):
        original = json.loads(ARCHIVE.read_text())
        for field, value in (("head_sha", "0" * 40), ("id", RUN + 1),
                             ("status", "in_progress"), ("conclusion", "cancelled")):
            record = deepcopy(original)
            record["run"][field] = value
            with self.assertRaises(ValueError):
                validate(record, **BINDING)

    def test_missing_skipped_duplicate_steps(self):
        original = json.loads(ARCHIVE.read_text())
        for change in ("missing", "skipped", "duplicate", "failed", "cancelled"):
            record = deepcopy(original)
            steps = record["jobs"][0]["steps"]
            if change == "missing":
                steps.pop(4)
            elif change == "duplicate":
                steps.append(steps[4])
            else:
                steps[4]["conclusion"] = "failure" if change == "failed" else change
            with self.assertRaises(ValueError):
                validate(record, **BINDING)

    def test_false_metrics_and_selection(self):
        original = json.loads(ARCHIVE.read_text())
        for change in ("metrics", "selection", "mismatch", "promotion"):
            record = deepcopy(original)
            report = record["policy_report"]
            if change == "metrics":
                report["transfer"]["checks"] = 0
            elif change == "selection":
                report["selected"] = []
            elif change == "mismatch":
                report["transfer"]["rows"][0]["match"] = False
            else:
                record["promotion"] = "ACCEPTED"
            with self.assertRaises(ValueError):
                validate(record, **BINDING)

    def test_budget_exhaustion(self):
        c = Controller(NODES, CHECKS)
        report = c.evaluate(SCENARIOS[0], max_checks=2)
        self.assertEqual(report.evaluated, 2)
        self.assertFalse(report.verified)
        self.assertTrue(any(x.reason == "verification budget exhausted" for x in report.evidence))
        self.assertTrue(c.evaluate(SCENARIOS[0]).verified)

    def test_budget_reuse_and_change(self):
        c = Controller(NODES, CHECKS)
        self.assertTrue(c.evaluate(SCENARIOS[0]).verified)
        r = c.evaluate(SCENARIOS[0], max_checks=0)
        self.assertTrue(r.verified)
        self.assertEqual(r.evaluated, 0)
        r = c.evaluate(SCENARIOS[1], max_checks=0)
        self.assertFalse(r.verified)
        self.assertEqual(r.evaluated, 0)

    def test_invalid_budget(self):
        c = Controller(NODES, CHECKS)
        for budget in (True, -1, 129, 1.5):
            with self.assertRaises(ValueError):
                c.evaluate(SCENARIOS[0], max_checks=budget)
