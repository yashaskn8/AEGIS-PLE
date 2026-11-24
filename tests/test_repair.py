import asyncio
import json
import unittest
from hashlib import sha256

from aegis.models import Profile
from aegis.repair import solve
from aegis.ci_evidence import replay

RAW = b'{"micrometres":[490,490]}'
MODEL = "gemini-4-neon"
PROFILE = Profile.parse("google-cloud/" + MODEL)


def proposal(total=1, **changes):
    return {"source_sha256": sha256(RAW).hexdigest(), "count": 2,
            "total_mm": total, **changes}


def response(value, **changes):
    return {"model": MODEL, "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(value)}}],
            "usage": {"completion_tokens": 30}, **changes}


class Scripted:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        return next(self.replies)


class Repair(unittest.IsolatedAsyncioTestCase):
    async def test_verified_first_attempt(self):
        provider = Scripted([response(proposal())])
        result = await solve(RAW, PROFILE, provider)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.verified["total_mm"], 1)
        self.assertFalse(provider.requests[0]["stream"])

    async def test_targeted_retry(self):
        provider = Scripted([response(proposal(0)), response(proposal())])
        result = await solve(RAW, PROFILE, provider)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.reasons, ("independent arithmetic mismatch",))
        self.assertEqual(result.reserved_output_tokens, 512)
        self.assertEqual([r["reasoning_effort"] for r in provider.requests], ["low", "medium"])

    async def test_budget_no_acceptance(self):
        provider = Scripted([response(proposal(0))])
        result = await solve(RAW, PROFILE, provider, output_budget=256)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.verified)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(provider.requests), 1)

    async def test_stale_and_malformed(self):
        provider = Scripted([response(proposal(source_sha256="0" * 64)),
                             response(proposal(count=True)), response(proposal())])
        result = await solve(RAW, PROFILE, provider)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(result.status, "VERIFIED_SYNTHETIC")
        self.assertEqual(result.reasons, ("source or output schema mismatch",) * 2)

    async def test_wrong_model_and_usage(self):
        provider = Scripted([response(proposal(), model="wrong"),
                             response(proposal(), usage={"completion_tokens": 999})])
        result = await solve(RAW, PROFILE, provider, attempts=2)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.verified)

    async def test_timeout_and_zero_budget(self):
        async def slow(request):
            await asyncio.sleep(1)
        result = await solve(RAW, PROFILE, slow, attempts=1, call_timeout=0.01)
        self.assertEqual(result.reasons, ("provider timeout",))
        self.assertIsNone(result.verified)
        provider = Scripted([])
        result = await solve(RAW, PROFILE, provider, output_budget=0)
        self.assertEqual(result.attempts, 0)
        self.assertEqual(provider.requests, [])

    async def test_reject_actions(self):
        reply = response(proposal())
        reply["choices"][0]["message"]["tool_calls"] = [{"type": "function"}]
        result = await solve(RAW, PROFILE, Scripted([reply]), attempts=1)
        self.assertEqual(result.status, "BLOCKED")

    async def test_invalid_profile(self):
        forged = Profile(PROFILE.declaration, "another-model", PROFILE.family)
        with self.assertRaises(ValueError):
            await solve(RAW, forged, Scripted([]))

    async def test_latest_historical_record(self):
        commit = "e78bae31b266a8769f04ab04d67f6956ee2cb9bf"
        result = replay("research/evidence/" + commit + ".json",
                        expected_commit=commit, expected_run=45434441700, expected_tests=43)
        self.assertEqual(result["promotion"], "BLOCKED")
