"""Synthetic count constraints across verified fictional record sources."""
import base64
from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

from aegis.constraints import Observation, Report
from aegis.document_runtime import build
from aegis.firewall import digest
from aegis.inventory_checks import parse_checks, verify_checks
from aegis.protocol import encode
from tests.test_csv_documents import csv_doc

REQUIRED = ("a", "b", "c", "subtotal", "total")
CHECKS = [{"total": "total", "parts": ["subtotal", "c"]},
          {"total": "subtotal", "parts": ["a", "b"]}]


def sources(a=2, b=3, c=4, subtotal=5, total=9):
    return {"register": csv_doc("register", 2, {"a": a, "b": b, "subtotal": subtotal}),
            "summary": encode({"family": "summary", "revision": 1,
                               "fields": {"c": c, "total": total, "subtotal": subtotal}}).encode()}


def bundle(store, checks=CHECKS):
    return encode({"manifest": {"register": 2, "summary": 1}, "required": list(REQUIRED),
                   "documents": [base64.b64encode(raw).decode() for raw in store.values()],
                   "checks": checks}).encode()


class InventoryChecks(unittest.TestCase):
    def test_chained_counts_and_binding(self):
        result = json.loads(build(bundle(sources())))
        verification = result["count_verification"]
        self.assertEqual([r["name"] for r in verification["evidence"]], ["subtotal", "total"])
        self.assertTrue(all(r["status"] == "VERIFIED" for r in verification["evidence"]))
        self.assertEqual(verification["binding"], digest({"source": result["report"]["input_binding"],
            "checks": verification["checks"], "facts": result["report"]["facts"],
            "evidence": verification["evidence"]}))
        permuted = [{"total": item["total"], "parts": item["parts"][::-1]} for item in CHECKS[::-1]]
        self.assertEqual(build(bundle(sources(), permuted)), build(bundle(sources())))
        changed = json.loads(build(bundle(sources(a=3, b=2))))
        self.assertNotEqual(changed["count_verification"]["binding"], verification["binding"])

    def test_invalid_plan_and_cycles(self):
        for plan in ([], [{"total": "a", "parts": ["b"]}, {"total": "b", "parts": ["a"]}],
                     [CHECKS[0], CHECKS[0]], [{"total": "a", "parts": ["a"]}],
                     [{"total": "a", "parts": ["missing"]}], [{"total": "a", "parts": ["b", "b"]}],
                     [{"total": "a", "parts": ["b"], "expression": "unsupported"}], [CHECKS[0]] * 17):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                parse_checks(plan, REQUIRED)

    def test_inconsistent_subtotal_and_text_blocked(self):
        for store in (sources(subtotal=6, total=10), sources(total=8), sources(a="2")):
            with self.assertRaises(ValueError):
                build(bundle(store))

    def test_both_verifiers_required(self):
        proposal = json.loads(build(bundle(sources())))["report"]
        plan = parse_checks(CHECKS, REQUIRED)
        with patch("aegis.inventory_checks.Controller.evaluate", return_value=Report(
                (Observation("subtotal", "x", "FAILED", "rejected"),), 1, 0)):
            with self.assertRaises(ValueError):
                verify_checks(plan, proposal)
        bad = deepcopy(proposal)
        next(f for f in bad["facts"] if f["key"] == "total")["value"] += 1
        with patch("aegis.inventory_checks.Controller.evaluate") as controller:
            with self.assertRaises(ValueError):
                verify_checks(plan, bad)
            controller.assert_not_called()

    def test_seeded_fresh_count_transfer(self):
        rng = random.Random(6471)
        for _ in range(12):
            a, b, c = (rng.randrange(0, 300_001) for _ in range(3))
            store = sources(a, b, c, a+b, a+b+c)
            result = json.loads(build(bundle(store)))
            self.assertEqual(len(result["count_verification"]["evidence"]), 2)
            with self.assertRaises(ValueError):
                build(bundle(sources(a, b, c, a+b, a+b+c+1)))
