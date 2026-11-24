import json
import unittest
from unittest.mock import patch
from aegis.deterministic_route import solve, experiment
from aegis.document_experiment import record
from aegis.disciplines import FILE,summarize
from aegis.frontier import MATRIX


class Deterministic(unittest.TestCase):
    def test_zero_call_route(self):
        r = experiment()
        self.assertEqual((r["cases"],r["correct"],r["false_accepts"],r["model_calls"]),(40,40,0,0))

    def test_worker_veto(self):
        with patch("aegis.deterministic_route.verify_in_process",return_value=False):
            r = solve({"register":2},("inventory_count",),(record("register",2,4),))
        self.assertEqual(r["status"],"BLOCKED")
        self.assertIsNone(r["output"])

    def test_discipline_matrix(self):
        r = summarize(json.loads(MATRIX.read_text()),json.loads(FILE.read_text()))
        self.assertEqual(r["discipline_scores"],308)
        self.assertEqual({k:v[0]["score"] for k,v in r["leaders"].items()},
                         {"structural":.576,"civil":.782,"electrical":.490,"mechanical":.472})

    def test_matrix_inconsistent(self):
        o,d = json.loads(MATRIX.read_text()),json.loads(FILE.read_text())
        d["pairs"][0]["scores"]["civil"] = 0
        with self.assertRaises(ValueError):
            summarize(o,d)
