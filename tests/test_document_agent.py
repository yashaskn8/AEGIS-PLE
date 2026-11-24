import asyncio
from copy import deepcopy
import io
import unittest
from unittest.mock import patch

from aegis import ci
from aegis.document_agent import solve, verified_projection, chunks_for, Scripted, experiment
from aegis.documents import reconcile
from aegis.document_experiment import record
from aegis.models import Profile

M = {"register": 2, "summary": 1}
R = ("inventory_count",)
D = (record("register", 2, 4), record("summary", 1, 4))
P = Profile.parse("google-cloud/gemini-4-neon")


def expected():
    return verified_projection(reconcile(M, R, D))


class DocumentAgent(unittest.IsolatedAsyncioTestCase):
    async def test_integrated_repair_experiment(self):
        r = await experiment()
        self.assertEqual(r["cases"], 16)
        self.assertEqual(r["metrics"]["bounded_repair"]["correct"], 16)
        self.assertEqual(r["metrics"]["single"]["correct"], 12)
        self.assertEqual(r["metrics"]["bounded_repair"]["false_accepts"], 0)

    async def test_source_conflict_no_provider(self):
        provider = Scripted([])
        result = await solve(M, R, (D[0], record("summary", 1, 5)), P, provider)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(provider.requests, [])

    async def test_forged_provenance_and_boolean(self):
        a, b = deepcopy(expected()), deepcopy(expected())
        a["facts"][0]["sources"][0]["content_hash"] = "0" * 64
        b["facts"][0]["value"] = True
        provider = Scripted([chunks_for(P.model, x) for x in (a, b, expected())])
        result = await solve(M, R, D, P, provider)
        self.assertEqual(result.calls, 3)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        self.assertEqual(result.diagnostics, ("fact_or_provenance_mismatch",) * 2)

    async def test_reported_input_over_budget(self):
        provider = Scripted([chunks_for(P.model, expected(), input_tokens=90)])
        result = await solve(M, R, D, P, provider, input_budget=80)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.diagnostics, ("reported_input_budget_exceeded",))

    async def test_no_retry_after_unaccounted_stream(self):
        bad = chunks_for(P.model, expected())[:-1]
        provider = Scripted([bad, chunks_for(P.model, expected())])
        result = await solve(M, R, D, P, provider)
        self.assertEqual(result.calls, 1)
        self.assertIsNone(result.output)
        self.assertEqual(result.diagnostics, ("unverifiable_provider_response",))

    async def test_zero_and_timeout(self):
        provider = Scripted([])
        self.assertEqual((await solve(M,R,D,P,provider,output_budget=0)).calls, 0)
        async def slow(request):
            await asyncio.sleep(1)
        r = await solve(M,R,D,P,slow,deadline_sec=0.01)
        self.assertEqual(r.diagnostics, ("deadline_exceeded",))
        self.assertIsNone(r.output)


    async def test_transport_error_no_unaccounted_retry(self):
        calls = []
        async def disconnected(request):
            calls.append(request)
            raise ConnectionResetError("synthetic peer disconnected")
        result = await solve(M, R, D, P, disconnected)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.output)
        self.assertEqual(result.calls, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.reserved_output, 256)
        self.assertEqual(result.diagnostics, ("unverifiable_provider_response",))

    async def test_late_reply_after_cancellation(self):
        async def late(request):
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                return chunks_for(P.model, expected())
        result = await solve(M, R, D, P, late, deadline_sec=0.01)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.output)
        self.assertEqual(result.calls, 1)
        self.assertEqual(result.diagnostics, ("deadline_exceeded",))


class GateNegative(unittest.TestCase):
    def test_missing_test_inventory_fails(self):
        with patch.object(ci.unittest.defaultTestLoader, "discover", return_value=unittest.TestSuite()), patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(ci.main(), 1)

    def test_failed_and_skipped_results_fail(self):
        class Fake:
            testsRun = len(ci.EXPECTED_IDS)
            skipped = []
            expectedFailures = []
            unexpectedSuccesses = []
            def wasSuccessful(self):
                return False
        # Supply the complete trusted inventory, then simulate observed runner outcomes.
        class Dummy(unittest.TestCase):
            def __init__(self, identity):
                super().__init__()
                self.identity = identity
            def id(self):
                return self.identity
        suite = unittest.TestSuite(Dummy(x) for x in ci.EXPECTED_IDS)
        with patch.object(ci.unittest.defaultTestLoader, "discover", return_value=suite), patch.object(ci.unittest.TextTestRunner, "run", return_value=Fake()), patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(ci.main(), 1)
        good_but_skipped = Fake()
        good_but_skipped.wasSuccessful = lambda: True
        good_but_skipped.skipped = ["mandatory"]
        with patch.object(ci.unittest.defaultTestLoader, "discover", return_value=suite), patch.object(ci.unittest.TextTestRunner, "run", return_value=good_but_skipped), patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(ci.main(), 1)
