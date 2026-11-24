import base64
import unittest

from aegis.models import Profile
from aegis.mcp_catalog import CatalogSession, SERVICE, VERSION
from aegis.protocol import Session, WireError, encode, decode
from aegis.stream import collect
from tests.test_protocol import Peer, opening

MODEL = "gemini-4-neon"


def declared():
    f = opening()
    f["mcp_servers"] = [{"name": "synthetic-catalog", "url": SERVICE,
                         "transport": "streamable-http"}]
    return f


def rpc(request_id, result, *, sse=False):
    envelope = encode({"jsonrpc": "2.0", "id": request_id, "result": result})
    return ("data: " + envelope + "\n\n" if sse else envelope).encode()


def http(request_id, body, *, status=200, media="application/json", **extra):
    return {"type": "result", "id": str(request_id), "ok": True,
            "status": status, "truncated": False,
            "headers": {"Content-Type": media, "Mcp-Session-Id": "fictional"},
            "body_b64": base64.b64encode(body).decode(), **extra}


def replies(tools):
    return [declared(), http(1, rpc(1, {"protocolVersion": VERSION})),
            http(2, b"", status=202),
            http(3, rpc(2, {"tools": tools}, sse=True), media="text/event-stream")]


class Extensions(unittest.IsolatedAsyncioTestCase):
    async def test_usage(self):
        peer = Peer([opening()])
        s = Session(peer)
        await s.start()
        p = Profile.parse("google-cloud/" + MODEL)
        await s.usage(p, input_tokens=12, output_tokens=3, cache_read_tokens=2)
        self.assertEqual(peer.sent[-1], {"type": "usage", "model": MODEL,
                         "input_tokens": 12, "output_tokens": 3, "cache_read_tokens": 2})
        with self.assertRaises(WireError):
            await s.usage(Profile.parse("google-cloud/gpt-oss-120b"),
                          input_tokens=1, output_tokens=1)
        for n in (-1, True, 2**53):
            with self.assertRaises(WireError):
                await s.usage(p, input_tokens=n, output_tokens=1)
        with self.assertRaises(WireError):
            await s.usage(p, input_tokens=1, output_tokens=1, cache_read_tokens=2)

    async def test_no_completion_before_start(self):
        with self.assertRaises(WireError):
            await Session(Peer([])).finish("not started")

    async def test_catalog_handshake(self):
        peer = Peer(replies([{"name": "fictional_read", "inputSchema": {"type": "object"}}]))
        s = CatalogSession(peer)
        await s.start()
        self.assertEqual(await s.catalog(), ("fictional_read",))
        requests = [decode(base64.b64decode(f["body_b64"]).decode()) for f in peer.sent]
        self.assertEqual([r["method"] for r in requests],
                         ["initialize", "notifications/initialized", "tools/list"])
        self.assertEqual(peer.sent[-1]["headers"]["Mcp-Session-Id"], "fictional")
        with self.assertRaises(WireError):
            await s.catalog()

    async def test_catalog_not_declared(self):
        peer = Peer([opening()])
        s = CatalogSession(peer)
        await s.start()
        with self.assertRaises(WireError):
            await s.catalog()
        self.assertEqual(peer.sent, [])

    async def test_catalog_compound_failures(self):
        tool = {"name": "duplicate", "inputSchema": {}}
        scenarios = [replies([tool, tool]), replies([{"name": "bad"}])]
        mismatch = replies([])
        mismatch[-1] = http(3, rpc(99, {"tools": []}))
        scenarios.append(mismatch)
        truncated = replies([])
        truncated[-1]["truncated"] = True
        scenarios.append(truncated)
        for frames in scenarios:
            s = CatalogSession(Peer(frames))
            await s.start()
            with self.assertRaises(WireError):
                await s.catalog()


def chunk(content=None, finish=None, **extra):
    return {"model": MODEL, "choices": [{"index": 0, "delta": {"content": content},
                                        "finish_reason": finish}], **extra}


def usage(**extra):
    return {"model": MODEL, "choices": [], "usage": {"prompt_tokens": 12,
            "completion_tokens": 2, "total_tokens": 14, **extra}}


class Streams(unittest.TestCase):
    def test_stream_collection(self):
        r = collect([chunk("a"), chunk("b", "stop"), usage(prompt_tokens_details={"cached_tokens": 4})],
                    model=MODEL, output_limit=10)
        self.assertEqual((r.content, r.input_tokens, r.output_tokens, r.cache_read_tokens),
                         ("ab", 12, 2, 4))

    def test_missing_and_invalid_usage(self):
        for frames in ([chunk("a", "stop")], [usage()], [chunk("a", "stop"), usage(total_tokens=99)],
                       [chunk("a", "stop"), usage(completion_tokens=11)],
                       [chunk("a", "stop"), usage(), chunk("extra")]):
            with self.assertRaises(WireError):
                collect(frames, model=MODEL, output_limit=10)

    def test_reject_tool_and_wrong_model(self):
        action = chunk()
        action["choices"][0]["delta"]["tool_calls"] = []
        for frames in ([action], [chunk("a", "stop", model="different"), usage()]):
            with self.assertRaises(WireError):
                collect(frames, model=MODEL, output_limit=10)

    def test_stream_byte_boundary_and_invalid_unicode(self):
        exact = "界" * 2730 + "xx"
        self.assertEqual(collect([chunk(exact, "stop"), usage()], model=MODEL,
                                 output_limit=10).content, exact)
        for value in (exact + "x", chr(0xD800)):
            with self.assertRaises(WireError):
                collect([chunk(value, "stop"), usage()], model=MODEL, output_limit=10)
