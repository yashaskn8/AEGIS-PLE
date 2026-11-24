import asyncio
import base64
from hashlib import sha256
import json
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from aegis.protocol import decode, encode
from aegis.synthetic_runtime import build_report, run_session, INPUT, OUTPUT
from aegis.policy_search import generate, search
from aegis.constraints import Controller
from aegis.graph_experiment import NODES, CHECKS, SCENARIOS
from tests.test_protocol import opening


class Runtime(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, *, corrupt=False, change=False, cancel=False):
        source = b'{"micrometres":[490,490]}'
        files = {INPUT: source}
        reads = 0
        async with serve(run_session, "127.0.0.1", 0, ping_interval=None) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}", proxy=None) as peer:
                await peer.send(encode(opening()))
                async with asyncio.timeout(3):
                    for _ in range(6):
                        message = decode(await peer.recv())
                        kind = message["type"]
                        if kind in ("done", "error"):
                            return message, files
                        if cancel:
                            await peer.send(encode({"type": "cancel", "reason": "synthetic"}))
                            cancel = False
                            continue
                        result = {"type": "result", "id": message["id"], "ok": True}
                        path = message["path"]
                        if kind == "write_file":
                            files[path] = base64.b64decode(message["content_b64"], validate=True)
                            result["size"] = len(files[path])
                        elif kind == "read_file":
                            data = files[path]
                            if path == INPUT:
                                reads += 1
                                if change and reads == 2:
                                    data = b'{"micrometres":[500]}'
                            if path == OUTPUT and corrupt:
                                data += b"!"
                            result.update(content_b64=base64.b64encode(data).decode(),
                                          size=len(data), truncated=False)
                        else:
                            self.fail("unexpected request")
                        await peer.send(encode(result))
        self.fail("no terminal message")

    async def test_socket_report(self):
        terminal, files = await self.exchange()
        self.assertEqual(terminal["type"], "done")
        result = json.loads(files[OUTPUT])
        self.assertEqual(result["total_mm"], 1)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["source_sha256"], sha256(files[INPUT]).hexdigest())

    async def test_socket_corrupt_readback(self):
        terminal, _ = await self.exchange(corrupt=True)
        self.assertEqual(terminal["type"], "error")

    async def test_socket_changed_source(self):
        terminal, _ = await self.exchange(change=True)
        self.assertEqual(terminal["type"], "error")

    async def test_socket_cancel(self):
        terminal, files = await self.exchange(cancel=True)
        self.assertEqual(terminal["type"], "done")
        self.assertNotIn(OUTPUT, files)
        self.assertIn("incomplete", terminal["final_message"])


class Policies(unittest.TestCase):
    def test_generated_inventory(self):
        policies = generate()
        self.assertEqual(len(policies), 16)
        self.assertEqual(len(set(policies)), 16)
        self.assertIn(frozenset(), policies)

    def test_equal_evidence_and_transfer(self):
        result = search()
        self.assertEqual(len(result["candidates"]), 16)
        self.assertTrue(all(c["development"]["matches"] == 7 for c in result["candidates"]))
        self.assertEqual(result["transfer"]["matches"], 32)
        self.assertLess(result["development"]["checks"], result["development"]["baseline_checks"])
        self.assertEqual(result["promotion"], "BLOCKED")

    def test_invalid_policy(self):
        controller = Controller(NODES, CHECKS)
        for policy in ({"source"}, frozenset(("unregistered",))):
            with self.assertRaises(ValueError):
                controller.evaluate(SCENARIOS[0], reuse_nodes=policy)

    def test_source_validation(self):
        for raw in (b'{"micrometres":[true]}', b'{"micrometres":[]}',
                    b'{"micrometres":[1],"extra":2}', b'{"micrometres":[-1]}'):
            with self.assertRaises(ValueError):
                build_report(raw)
