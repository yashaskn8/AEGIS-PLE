import asyncio
import base64
import json
import unittest

from aegis.protocol import Cancelled, Session, WireError, decode, encode
from aegis.models import Profile, SPONSORED


def opening():
    return {"type": "task", "protocol": 1, "session": "synthetic",
            "instruction": "Summarize a fictional measurement table.",
            "workdir": "/app", "limits": {"agent_timeout_sec": 60,
            "max_write_bytes": 1000}, "mcp_servers": []}


class Peer:
    def __init__(self, frames):
        self.frames = asyncio.Queue()
        for frame in frames:
            self.frames.put_nowait(encode(frame))
        self.sent = []

    async def recv(self):
        return await self.frames.get()

    async def send(self, raw):
        self.sent.append(decode(raw))


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_trip(self):
        peer = Peer([opening(), {"type": "result", "id": "1", "ok": True,
                                 "content_b64": base64.b64encode(b"abc").decode(),
                                 "size": 3, "truncated": False},
                     {"type": "result", "id": "2", "ok": True, "size": 3}])
        session = Session(peer)
        await session.start()
        self.assertEqual(await session.read("input.csv"), b"abc")
        await session.write("output.txt", b"abc")
        await session.finish("Synthetic output written.")
        self.assertEqual([x["type"] for x in peer.sent], ["read_file", "write_file", "done"])
        self.assertEqual(peer.sent[1]["content_b64"], "YWJj")
        with self.assertRaises(WireError):
            await session.finish("duplicate")

    async def test_invalid_opening(self):
        frame = opening()
        frame["protocol"] = True
        with self.assertRaises(WireError):
            await Session(Peer([frame])).start()

    async def test_mismatched_id(self):
        peer = Peer([opening(), {"type": "result", "id": "2", "ok": True}])
        session = Session(peer)
        await session.start()
        with self.assertRaises(WireError):
            await session.read("input")
        with self.assertRaises(WireError):
            await session.read("input")
        with self.assertRaises(WireError):
            await session.finish("not verified")
        await session.finish("uncorrelated result", failed=True)
        self.assertEqual(peer.sent[-1]["type"], "error")

    async def test_cancel(self):
        peer = Peer([opening(), {"type": "cancel", "reason": "timeout"}])
        session = Session(peer)
        await session.start()
        with self.assertRaises(Cancelled):
            await session.read("input")
        with self.assertRaises(WireError):
            await session.write("out", b"data")
        await session.finish("Cancelled; no output verified.")
        self.assertEqual(peer.sent[-1]["type"], "done")

    async def test_timeout(self):
        peer = Peer([opening()])
        session = Session(peer, io_timeout=0.01)
        await session.start()
        with self.assertRaises(WireError):
            await session.read("input")
        await session.finish("timeout", failed=True)
        self.assertEqual(peer.sent[-1]["type"], "error")

    async def test_incomplete_files(self):
        for change in ({"truncated": True}, {"size": 4}, {"content_b64": "!!!"},
                       {"ok": False}):
            reply = {"type": "result", "id": "1", "ok": True, "size": 3,
                     "content_b64": "YWJj", "truncated": False, **change}
            session = Session(Peer([opening(), reply]))
            await session.start()
            with self.assertRaises(WireError):
                await session.read("input")

    async def test_bad_paths_and_writes(self):
        peer = Peer([opening()])
        session = Session(peer)
        await session.start()
        for path in ("../x", "/x", ".", "a\\b", ""):
            with self.assertRaises(WireError):
                await session.write(path, b"x")
        with self.assertRaises(WireError):
            await session.write("out", b"x" * 1001)
        self.assertEqual(peer.sent, [])

    async def test_concurrent_request_rejected(self):
        peer = Peer([opening()])
        session = Session(peer)
        await session.start()
        first = asyncio.create_task(session.read("a"))
        await asyncio.sleep(0)
        with self.assertRaises(WireError):
            await session.read("b")
        peer.frames.put_nowait(encode({"type": "result", "id": "1", "ok": True,
                                      "content_b64": "", "size": 0, "truncated": False}))
        self.assertEqual(await first, b"")

    async def test_strict_json(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '[]', b'{}', '{'):
            with self.assertRaises(WireError):
                decode(raw)


class Models(unittest.TestCase):
    def test_all_declarations(self):
        self.assertEqual(len(SPONSORED), 11)
        for model in SPONSORED:
            profile = Profile.parse("google-cloud/" + model)
            body = profile.request([{"role": "user", "content": "synthetic"}], max_tokens=10)
            self.assertEqual(body["model"], model)
            self.assertTrue(body["stream"])
            self.assertNotIn("temperature", body)

    def test_provider_controls(self):
        messages = [{"role": "user", "content": "synthetic"}]
        gemini = Profile.parse("google-cloud/gemini-4-neon")
        claude = Profile.parse("google-cloud/claude-opus-5-5")
        self.assertEqual(claude.request(messages, max_tokens=10, effort="max")["reasoning_effort"], "max")
        with self.assertRaises(ValueError):
            gemini.request(messages, max_tokens=10, effort="max")
        with self.assertRaises(ValueError):
            Profile.parse("google-cloud/not-a-model")
        with self.assertRaises(ValueError):
            gemini.request(messages, max_tokens=True)
        with self.assertRaises(ValueError):
            gemini.request([{"role": "tool", "content": "x"}], max_tokens=10)

    def test_aggregate_content_budget_and_unicode(self):
        profile = Profile.parse("google-cloud/gemini-4-neon")
        messages = [{"role": "user", "content": "界" * 65536},
                    {"role": "user", "content": "x" * 65536}]
        self.assertEqual(len(profile.request(messages, max_tokens=10)["messages"]), 2)
        with self.assertRaises(ValueError):
            profile.request(messages + [{"role": "user", "content": "x"}], max_tokens=10)
        with self.assertRaises(ValueError):
            profile.request([{"role": "user", "content": chr(0xD800)}], max_tokens=10)
