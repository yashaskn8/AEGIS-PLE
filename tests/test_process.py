from copy import deepcopy
import json
import subprocess
import unittest
from unittest.mock import patch
from aegis.document_agent import verified_projection
from aegis.document_experiment import cases, record
from aegis.documents import reconcile
from aegis.process_verify import verify_in_process
from aegis.frontier import MATRIX, analyze

M = {"register":2, "summary":1}
R = ("inventory_count",)
D = (record("register",2,4),record("summary",1,4))


class Process(unittest.TestCase):
    def test_distinct_worker_agrees_on_valid_and_invalid(self):
        for case in cases():
            result = reconcile(M,R,case.documents)
            proposal = verified_projection(result)
            self.assertIs(verify_in_process(M,R,case.documents,proposal), case.expected is not None)

    def test_reject_changed_source_and_proposal(self):
        p = verified_projection(reconcile(M,R,D))
        for altered in (dict(p,input_binding="0"*64),dict(p,facts=[])):
            self.assertFalse(verify_in_process(M,R,D,altered))
        self.assertFalse(verify_in_process(M,R,(D[0],record("summary",1,5)),p))

    def test_worker_timeout_and_malformed_response(self):
        p = verified_projection(reconcile(M,R,D))
        with patch("aegis.process_verify.subprocess.run", side_effect=subprocess.TimeoutExpired("fixed",1)):
            self.assertFalse(verify_in_process(M,R,D,p))
        with patch("aegis.process_verify.subprocess.run", return_value=subprocess.CompletedProcess([],0,b'{"accepted":true}',b"")):
            self.assertFalse(verify_in_process(M,R,D,p))

    def test_published_frontier(self):
        result = analyze(json.loads(MATRIX.read_text()))
        self.assertEqual(result["pairs"],77)
        self.assertEqual(result["known_costs"],75)
        self.assertTrue(any(x["score"] == .525 for x in result["frontier"]))
        self.assertTrue(all(x["score"] >= .138 for x in result["frontier"]))

    def test_invalid_matrix(self):
        r = json.loads(MATRIX.read_text())
        r["pairs"][0]["cost_usd"] = -1
        with self.assertRaises(ValueError):
            analyze(r)

    def test_document_limits_before_encoding(self):
        # No unbounded base64 allocation or child launch for invalid inventories.
        for documents in ((b"x" * 8193,), (b"x",) * 33, ("not bytes",)):
            with self.subTest(documents=len(documents)), \
                    patch("aegis.process_verify.base64.b64encode") as encode, \
                    patch("aegis.process_verify.subprocess.run") as launch:
                self.assertFalse(verify_in_process(M, R, documents, {}))
                encode.assert_not_called()
                launch.assert_not_called()
