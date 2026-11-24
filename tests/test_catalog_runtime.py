"""A real WebSocket loopback with a local in-memory fictional record service."""
import asyncio
import base64
from hashlib import sha256
import json
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from aegis.catalog_runtime import INPUT, run_catalog_session, parse_bundle
from aegis.document_runtime import OUTPUT
from aegis.document_experiment import record
from aegis.mcp_catalog import CatalogSession, LOOKUP_SCHEMA_JSON, LOOKUP_NAME, SERVICE, MAX_LOOKUPS
from aegis.protocol import WireError, decode, encode
from tests.test_extensions import declared, replies, http, rpc
from tests.test_protocol import Peer
from tests.test_csv_documents import csv_doc


def tool(schema=None):
    return {"name": LOOKUP_NAME, "inputSchema": json.loads(LOOKUP_SCHEMA_JSON) if schema is None else schema}


def result(raw):
    return {"content": [{"type": "text", "text": raw.decode()}], "isError": False}


def manifest(store):
    return encode({"manifest":{"register":2,"summary":1}, "required":["inventory_count"],
                   "records":[{"record_id":k,"sha256":sha256(v).hexdigest()} for k,v in store.items()]}).encode()


class CatalogRuntime(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, *, fault=None):
        store = {"register": csv_doc("register", 2, {"inventory_count": 4}),
                 "summary": record("summary", 1, 4)}
        files = {INPUT:manifest(store)}
        methods, fetched = [], []
        async with serve(run_catalog_session, "127.0.0.1", 0, ping_interval=None) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}",proxy=None) as peer:
                await peer.send(encode(declared()))
                async with asyncio.timeout(5):
                    for _ in range(16):
                        msg = decode(await peer.recv())
                        kind = msg["type"]
                        if kind in ("done","error"):
                            return msg, files, methods, fetched
                        response = {"type":"result","id":msg["id"],"ok":True}
                        if kind == "http":
                            self.assertEqual(msg["url"],SERVICE)
                            req = decode(base64.b64decode(msg["body_b64"]).decode())
                            method = req["method"]
                            methods.append(method)
                            if method == "initialize":
                                from aegis.mcp_catalog import VERSION
                                response = http(int(msg["id"]),rpc(req["id"],{"protocolVersion":VERSION}))
                            elif method == "notifications/initialized":
                                response = http(int(msg["id"]),b"",status=202)
                            elif method == "tools/list":
                                response = http(int(msg["id"]),rpc(req["id"],{"tools":[tool()]}))
                            elif method == "tools/call":
                                self.assertEqual(req["params"]["name"],LOOKUP_NAME)
                                key = req["params"]["arguments"]["record_id"]
                                fetched.append(key)
                                if fault == "cancel":
                                    await peer.send(encode({"type":"cancel","reason":"synthetic"}))
                                    continue
                                raw = store[key]
                                if fault == "corrupt" and key == "summary":
                                    raw += b" "
                                response = http(int(msg["id"]),rpc(req["id"],result(raw)))
                                if fault == "changed_manifest" and key == "summary":
                                    files[INPUT] += b" "
                            else:
                                self.fail("unexpected RPC method")
                        elif kind == "read_file":
                            raw = files[msg["path"]]
                            response.update(content_b64=base64.b64encode(raw).decode(),size=len(raw),truncated=False)
                        elif kind == "write_file":
                            self.assertEqual(msg["path"],OUTPUT)
                            files[OUTPUT] = base64.b64decode(msg["content_b64"],validate=True)
                            response["size"] = len(files[OUTPUT])
                        else:
                            self.fail("unexpected wire action")
                        await peer.send(encode(response))
        self.fail("missing terminal message")

    async def test_catalog_to_verified_report(self):
        terminal, files, methods, fetched = await self.exchange()
        self.assertEqual(terminal["type"],"done")
        self.assertEqual(methods,["initialize","notifications/initialized","tools/list","tools/call","tools/call"])
        self.assertEqual(fetched,["register","summary"])
        report = json.loads(files[OUTPUT])
        self.assertEqual(report["model_calls"],0)
        self.assertEqual(report["report"]["facts"][0]["value"],4)
        self.assertEqual(len(report["report"]["facts"][0]["sources"]),2)

    async def test_corruption_change_and_cancel_fail_closed(self):
        for fault in ("corrupt","changed_manifest","cancel"):
            with self.subTest(fault=fault):
                terminal, files, _, _ = await self.exchange(fault=fault)
                self.assertNotIn(OUTPUT,files)
                self.assertEqual(terminal["type"],"done" if fault=="cancel" else "error")
                if fault=="cancel":
                    self.assertIn("incomplete",terminal["final_message"])

    async def test_schema_and_arguments_before_dispatch(self):
        raw = record("register",2,4)
        digest = sha256(raw).hexdigest()
        for schema in ({"type":"object"},dict(json.loads(LOOKUP_SCHEMA_JSON),additionalProperties=0)):
            peer = Peer(replies([tool(schema)]))
            s = CatalogSession(peer)
            await s.start(); await s.catalog()
            with self.assertRaises(WireError):
                await s.fetch_record("register",digest)
            self.assertEqual(len(peer.sent),3)
        peer = Peer(replies([tool()]))
        s = CatalogSession(peer)
        await s.start()
        with self.assertRaises(WireError):
            await s.fetch_record("register",digest)
        self.assertEqual(peer.sent,[])
        await s.catalog()
        for identity, binding in (("../bad",digest),("register","wrong")):
            with self.assertRaises(WireError):
                await s.fetch_record(identity,binding)
        self.assertEqual(len(peer.sent),3)

    async def test_result_compound_failures_poison_session(self):
        raw = record("register",2,4)
        digest = sha256(raw).hexdigest()
        for bad in (http(4,rpc(3,result(raw+b" "))),
                    http(4,rpc(3,dict(result(raw),isError=True))),
                    http(4,rpc(4,result(raw))),
                    http(4,rpc(3,result(raw)),headers={"Content-Type":"application/json","Mcp-Session-Id":"different"}),
                    http(4,rpc(3,dict(result(raw),content=[{"type":"text","text":raw.decode()},{"type":"text","text":"extra"}]))),
                    http(4,rpc(3,result(raw)),truncated=True)):
            peer = Peer(replies([tool()])+[bad])
            s = CatalogSession(peer)
            await s.start(); await s.catalog()
            with self.assertRaises(WireError):
                await s.fetch_record("register",digest)
            self.assertTrue(s.poisoned)
            with self.assertRaises(WireError):
                await s.fetch_record("register",digest)
            self.assertEqual(len(peer.sent),4)
            with self.assertRaises(WireError):
                await s.finish("not accepted")

    async def test_lookup_budget_and_exact_request_identity(self):
        raw = record("register",2,4)
        digest = sha256(raw).hexdigest()
        peer = Peer(replies([tool()])+[http(4+i,rpc(3+i,result(raw))) for i in range(MAX_LOOKUPS)])
        s = CatalogSession(peer)
        await s.start(); await s.catalog()
        for _ in range(MAX_LOOKUPS):
            self.assertEqual(await s.fetch_record("register",digest),raw)
        with self.assertRaises(WireError):
            await s.fetch_record("register",digest)
        self.assertEqual(len(peer.sent),3+MAX_LOOKUPS)
        requests = [decode(base64.b64decode(f["body_b64"]).decode()) for f in peer.sent[3:]]
        self.assertEqual([r["id"] for r in requests],list(range(3,3+MAX_LOOKUPS)))

    def test_manifest_validation_before_lookup(self):
        store = {"register":record("register",2,4),"summary":record("summary",1,4)}
        original = json.loads(manifest(store))
        for defect in (dict(original,required=[]),dict(original,records=[]),
                       dict(original,records=original["records"]*2),
                       dict(original,records=[{"record_id":"../bad","sha256":"0"*64}])):
            with self.assertRaises(ValueError):
                parse_bundle(encode(defect).encode())
