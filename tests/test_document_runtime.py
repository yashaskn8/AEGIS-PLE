import asyncio
import base64
import json
import unittest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from aegis.document_runtime import INPUT,OUTPUT,run_document_session
from aegis.document_experiment import record
from aegis.protocol import encode,decode
from tests.test_protocol import opening


def bundle(conflict=False):
    docs = (record("register",2,4),record("summary",1,5 if conflict else 4))
    return encode({"manifest":{"register":2,"summary":1},"required":["inventory_count"],
                   "documents":[base64.b64encode(d).decode() for d in docs]}).encode()


class DocumentRuntime(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, *, conflict=False, change_at=0, corrupt=False, cancel_at=0):
        files = {INPUT:bundle(conflict)}
        reads = 0
        actions = 0
        async with serve(run_document_session,"127.0.0.1",0,ping_interval=None) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}",proxy=None) as peer:
                await peer.send(encode(opening()))
                async with asyncio.timeout(5):
                    for _ in range(8):
                        msg = decode(await peer.recv())
                        if msg["type"] in ("done","error"):
                            return msg,files
                        actions += 1
                        if actions == cancel_at:
                            await peer.send(encode({"type":"cancel","reason":"synthetic"}))
                            continue
                        result = {"type":"result","id":msg["id"],"ok":True}
                        path = msg["path"]
                        if msg["type"] == "write_file":
                            self.assertEqual(path,OUTPUT)
                            files[path] = base64.b64decode(msg["content_b64"],validate=True)
                            result["size"] = len(files[path])
                        elif msg["type"] == "read_file":
                            value = files[path]
                            if path == INPUT:
                                reads += 1
                                if reads == change_at:
                                    value = bundle(True)
                            if path == OUTPUT and corrupt:
                                value += b"!"
                            result.update(content_b64=base64.b64encode(value).decode(),
                                          size=len(value),truncated=False)
                        else:
                            self.fail("unexpected protocol action")
                        await peer.send(encode(result))
        self.fail("missing terminal message")

    async def test_success(self):
        terminal, files = await self.exchange()
        self.assertEqual(terminal["type"],"done")
        result = json.loads(files[OUTPUT])
        self.assertEqual(result["model_calls"],0)
        self.assertEqual(result["report"]["facts"][0]["value"],4)
        self.assertEqual(len(result["report"]["facts"][0]["sources"]),2)

    async def test_conflict_blocks_write(self):
        terminal,files = await self.exchange(conflict=True)
        self.assertEqual(terminal["type"],"error")
        self.assertNotIn(OUTPUT,files)

    async def test_prewrite_source_change(self):
        terminal,files = await self.exchange(change_at=2)
        self.assertEqual(terminal["type"],"error")
        self.assertNotIn(OUTPUT,files)

    async def test_postwrite_source_change(self):
        terminal,files = await self.exchange(change_at=3)
        self.assertEqual(terminal["type"],"error")
        self.assertIn(OUTPUT,files)

    async def test_corrupt_readback(self):
        terminal,_ = await self.exchange(corrupt=True)
        self.assertEqual(terminal["type"],"error")

    async def test_cancel_during_write(self):
        terminal,files = await self.exchange(cancel_at=3)
        self.assertEqual(terminal["type"],"done")
        self.assertIn("incomplete",terminal["final_message"])
        self.assertNotIn(OUTPUT,files)
