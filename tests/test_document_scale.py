"""Bounded scale and differential checks on fictional inventories only."""
import base64
from hashlib import sha256
import json
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

from aegis.document_agent import verified_projection
from aegis.documents import reconcile
from aegis.process_verify import MAX_REQUEST_BYTES, WORKER, verify_in_process


def record(family, revision, fields):
    return json.dumps({"family": family, "revision": revision, "fields": fields},
                      ensure_ascii=False, separators=(",", ":")).encode()


def maximum_fixture():
    families = tuple(f"doc{i:02d}" + "x" * 59 for i in range(32))
    required = tuple(f"field{i:02d}" + "x" * 57 for i in range(32))
    fields = {key: "z" * 128 for key in required}
    # Include printable Unicode while keeping each padded document in bounds.
    fields[required[-1]] = "界" * 128
    manifest = dict.fromkeys(families, 1000)
    docs = tuple(record(f, 1000, fields).ljust(8192, b" ") for f in families)
    return manifest, required, docs, fields


def expected_facts(manifest, required, docs, values):
    # Test oracle derived from the generated fixtures rather than reconciliation.
    sources = {key: [] for key in required}
    for raw in docs:
        item = json.loads(raw)
        if item["revision"] == manifest[item["family"]]:
            for key in item["fields"]:
                if key in sources:
                    sources[key].append({"family": item["family"],
                                         "revision": item["revision"],
                                         "content_hash": sha256(raw).hexdigest()})
    return [{"key": k, "value": values[k],
             "sources": sorted(sources[k], key=lambda s: s["family"])} for k in sorted(required)]


class DocumentScale(unittest.TestCase):
    def test_maximum_supported_inventory(self):
        m, r, docs, values = maximum_fixture()
        self.assertTrue(all(len(d) == 8192 for d in docs))
        result = reconcile(m, r, docs)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        proposal = verified_projection(result)
        self.assertEqual(proposal["facts"], expected_facts(m, r, docs, values))
        self.assertEqual(sum(len(f["sources"]) for f in proposal["facts"]), 1024)
        request = json.dumps({"manifest": m, "required": r,
            "documents": [base64.b64encode(d).decode() for d in docs],
            "proposal": proposal}, allow_nan=False, separators=(",", ":")).encode()
        self.assertGreater(len(request), 500_000)
        self.assertLessEqual(len(request), MAX_REQUEST_BYTES)
        self.assertTrue(verify_in_process(m, r, docs, proposal))

    def test_seeded_multifield_transfer_and_compound_faults(self):
        rng = random.Random(41823)
        for index in range(12):
            required = ("inventory_count", "room_label", "revision_note")
            values = {"inventory_count": rng.randrange(1_000_001),
                      "room_label": f"Room {index}", "revision_note": "最新"}
            manifest = {f"doc{i}": rng.randrange(2, 1000) for i in range(2 + index % 5)}
            docs = []
            for family, revision in manifest.items():
                docs.extend((record(family, revision - 1, {"inventory_count": 0}),
                             record(family, revision, values)))
            rng.shuffle(docs)
            valid = tuple(docs)
            proposal = verified_projection(reconcile(manifest, required, valid))
            self.assertEqual(proposal["facts"], expected_facts(manifest, required, valid, values))
            self.assertTrue(verify_in_process(manifest, required, valid, proposal))
            self.assertEqual(reconcile(manifest, required, tuple(reversed(valid))),
                             reconcile(manifest, required, valid))
            family = next(iter(manifest))
            revision = manifest[family]
            bad = valid + (record(family, revision, dict(values, inventory_count=True)),
                           record(family, revision + 1, values))
            rejected = reconcile(manifest, required, bad)
            self.assertEqual(rejected.status, "BLOCKED")
            self.assertFalse(verify_in_process(manifest, required, bad,
                                               verified_projection(rejected)))

    def test_oversized_request_rejected_before_launch_and_by_worker(self):
        with patch("aegis.process_verify.subprocess.run") as launch:
            self.assertFalse(verify_in_process({}, (), (), {"oversize": "x" * MAX_REQUEST_BYTES}))
            launch.assert_not_called()
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(WORKER)],
                                input=b" " * (MAX_REQUEST_BYTES + 1), capture_output=True,
                                timeout=2, check=True)
        self.assertFalse(json.loads(result.stdout)["accepted"])
