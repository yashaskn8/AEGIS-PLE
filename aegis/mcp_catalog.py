"""Bounded read-only MCP exchange with an explicitly fictional local peer.

The controller owns the service, method, schema, record identity and expected
hash. Tool results are data, never commands. No direct HTTP or model access.
"""
import base64
import binascii
from hashlib import sha256
import json
import re
from typing import Any

from .protocol import Session, Transport, WireError, decode, encode, text

SERVICE = "http://127.0.0.1:8000/mcp/"
VERSION = "2025-03-26"
MAX_BODY = 1_000_000
MAX_TOOLS = 256
MAX_LOOKUPS = 32
MAX_RECORD_BYTES = 8192
LOOKUP_NAME = "fictional_read"
LOOKUP_SCHEMA_JSON = json.dumps({"type": "object", "properties": {"record_id": {"type": "string"}},
                                 "required": ["record_id"], "additionalProperties": False}, sort_keys=True)


def valid_lookup(record_id: object, expected_sha256: object) -> bool:
    return (type(record_id) is str and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", record_id) is not None
            and type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None)


class CatalogSession(Session):
    def __init__(self, transport: Transport, *, io_timeout: float = 5.0) -> None:
        super().__init__(transport, io_timeout=io_timeout)
        self._catalog_declared = False
        self._catalog_started = False
        self._lookup_allowed = False
        self._catalog_session_id: str | None = None
        self._lookup_count = 0

    async def _recv(self) -> dict[str, Any]:
        frame = await super()._recv()
        if self.task is None and frame.get("type") == "task":
            servers = frame.get("mcp_servers")
            self._catalog_declared = (
                type(servers) is list and len(servers) == 1
                and servers[0] == {"name": "synthetic-catalog", "url": SERVICE,
                                   "transport": "streamable-http"}
            )
        return frame

    async def _post(self, message: dict[str, Any], *, session_id: str | None = None,
                    notify: bool = False) -> tuple[dict[str, Any] | None, dict[str, str]]:
        if not self._catalog_declared:
            raise WireError("synthetic catalog not declared")
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        if session_id is not None:
            headers["Mcp-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = VERSION
        raw = encode(message).encode()
        reply = await self._request("http", method="POST", url=SERVICE,
                                    headers=headers, body_b64=base64.b64encode(raw).decode())
        if (reply["ok"] is not True or reply.get("truncated") is not False
                or type(reply.get("status")) is not int):
            raise WireError("incomplete catalog response")
        if reply["status"] != (202 if notify else 200):
            raise WireError("unexpected catalog HTTP status")
        response_headers = reply.get("headers")
        if type(response_headers) is not dict or any(type(k) is not str or type(v) is not str
                                                       for k, v in response_headers.items()):
            raise WireError("invalid response headers")
        folded: dict[str, str] = {k.lower(): v for k, v in response_headers.items()}
        if len(folded) != len(response_headers):
            raise WireError("duplicate response header")
        if session_id is not None and folded.get("mcp-session-id", session_id) != session_id:
            raise WireError("catalog session identity changed")
        encoded = reply.get("body_b64")
        if type(encoded) is not str or len(encoded) > 4 * ((MAX_BODY + 2) // 3):
            raise WireError("catalog body budget exceeded")
        try:
            body = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError, binascii.Error) as exc:
            raise WireError("invalid catalog body") from exc
        if len(body) > MAX_BODY:
            raise WireError("catalog body budget exceeded")
        if notify:
            if body:
                raise WireError("unexpected notification body")
            return None, folded
        try:
            media = folded.get("content-type", "").split(";", 1)[0].strip().lower()
            if media == "application/json":
                envelope = decode(body.decode("utf-8"))
            elif media == "text/event-stream":
                # Only a single complete message event is accepted.
                lines = body.decode("utf-8").replace("\r\n", "\n").split("\n")
                events = [e for e in "\n".join(lines).split("\n\n") if e.strip()]
                payloads = []
                for event in events:
                    data = [l[5:].lstrip(" ") for l in event.split("\n") if l.startswith("data:")]
                    if data:
                        payloads.append("\n".join(data))
                if len(payloads) != 1:
                    raise WireError("ambiguous event stream")
                envelope = decode(payloads[0])
            else:
                raise WireError("unsupported response media")
        except UnicodeError as exc:
            raise WireError("invalid catalog text") from exc
        if (envelope.get("jsonrpc") != "2.0" or type(envelope.get("id")) is not int
                or envelope["id"] != message["id"] or "error" in envelope
                or type(envelope.get("result")) is not dict):
            raise WireError("uncorrelated or failed RPC")
        return envelope["result"], folded

    async def catalog(self) -> tuple[str, ...]:
        if self._catalog_started:
            raise WireError("catalog already attempted")
        self._catalog_started = True
        try:
            result, headers = await self._post({"jsonrpc": "2.0", "id": 1,
                "method": "initialize", "params": {"protocolVersion": VERSION,
                "capabilities": {}, "clientInfo": {"name": "aegis-synthetic", "version": "1"}}})
            if result is None or result.get("protocolVersion") != VERSION:
                raise WireError("unsupported protocol version")
            sid = headers.get("mcp-session-id")
            if sid is not None and (not 1 <= len(sid) <= 128 or
                                    any(not 33 <= ord(ch) <= 126 for ch in sid)):
                raise WireError("invalid session header")
            await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                             session_id=sid, notify=True)
            result, _ = await self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                                         session_id=sid)
            if result is None:
                raise WireError("missing tool catalog")
            tools = result.get("tools")
            if result.get("nextCursor") is not None or type(tools) is not list or len(tools) > MAX_TOOLS:
                raise WireError("catalog incomplete or too large")
            names = []
            lookup_allowed = False
            for tool in tools:
                if type(tool) is not dict or type(tool.get("inputSchema")) is not dict:
                    raise WireError("invalid tool metadata")
                name = text(tool.get("name"), "tool name", 128)
                names.append(name)
                if name == LOOKUP_NAME:
                    lookup_allowed = json.dumps(tool["inputSchema"], sort_keys=True) == LOOKUP_SCHEMA_JSON
            if len(set(names)) != len(names):
                raise WireError("duplicate tool names")
            self._catalog_session_id = sid
            self._lookup_allowed = lookup_allowed
            return tuple(sorted(names))
        except BaseException:
            self.poisoned = True
            raise

    async def fetch_record(self, record_id: str, expected_sha256: str) -> bytes:
        """Retrieve only a controller-selected fictional record with exact source binding."""
        if not self._lookup_allowed or not valid_lookup(record_id, expected_sha256):
            raise WireError("unapproved lookup schema or record binding")
        if self.busy or self.poisoned or self.terminal or self.cancelled or self._lookup_count >= MAX_LOOKUPS:
            raise WireError("lookup unavailable or budget exhausted")
        self._lookup_count += 1
        try:
            result, _ = await self._post({"jsonrpc": "2.0", "id": 2 + self._lookup_count,
                "method": "tools/call", "params": {"name": LOOKUP_NAME,
                    "arguments": {"record_id": record_id}}}, session_id=self._catalog_session_id)
            if result is None or set(result) != {"content", "isError"} or result["isError"] is not False:
                raise WireError("failed or unexpected tool result")
            content = result["content"]
            if (type(content) is not list or len(content) != 1 or type(content[0]) is not dict
                    or set(content[0]) != {"type", "text"} or content[0]["type"] != "text"
                    or type(content[0]["text"]) is not str):
                raise WireError("invalid record content")
            try:
                raw = content[0]["text"].encode("utf-8")
            except UnicodeError as exc:
                raise WireError("invalid record Unicode") from exc
            if not 0 < len(raw) <= MAX_RECORD_BYTES or sha256(raw).hexdigest() != expected_sha256:
                raise WireError("record integrity mismatch")
            return raw
        except BaseException:
            self.poisoned = True
            raise
