from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest

from aegis.learned_policy import ARCHIVE, COMMIT, RUN, TESTS, load, reproduce, run
from aegis.ci_evidence import replay


class Learning(unittest.TestCase):
    def test_reproduce_archived_policy(self):
        learned = load()
        self.assertEqual(learned.source_commit, COMMIT)
        self.assertEqual(learned.nodes, frozenset(("label", "quantity", "source")))
        self.assertEqual(len(learned.evidence_digest), 64)

    def test_fresh_retention(self):
        result = run()
        self.assertEqual(result["correct"], 24)
        self.assertEqual(result["false_accepts"], 0)
        self.assertLess(result["checks"], result["baseline_checks"])
        self.assertEqual(result["promotion"], "BLOCKED")

    def test_reject_consistent_but_fabricated_archive(self):
        record = json.loads(ARCHIVE.read_text())
        # Input digest is not a scored aggregate; replay must still detect alteration.
        record["policy_report"]["transfer"]["rows"][0]["input"] = "0" * 64
        with self.assertRaises(ValueError):
            reproduce(record, expected_commit=COMMIT, expected_run=RUN, expected_tests=TESTS)

    def test_document_archive_replay(self):
        r = replay(ARCHIVE, expected_commit=COMMIT, expected_run=RUN, expected_tests=TESTS)
        self.assertEqual(r["promotion"], "BLOCKED")
        record = json.loads(ARCHIVE.read_text())
        record["document_report"]["metrics"]["full"]["false_accepts"] = 1
        with self.assertRaises(ValueError):
            reproduce(record, expected_commit=COMMIT, expected_run=RUN, expected_tests=TESTS)

    def test_oversize_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "archive.json"
            p.write_bytes(b"x" * 1_000_001)
            with self.assertRaises(ValueError):
                load(p)
