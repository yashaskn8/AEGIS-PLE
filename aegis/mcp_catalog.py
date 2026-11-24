"""Read-only MCP catalog exchange using a synthetic peer, never direct HTTP.

The controller sends only initialization, notification and catalog listing.
No arbitrary tool execution, URLs, headers or shell commands from a model.
"""
import base64
import binascii
from dataclasses import dataclass
from .protocol import Session, WireError, decode, encode, text

# Explicit fictional service identifier. No network connection is made here.
SERVICE = "http://127.0.0.1:8000/mcp/"
VERSION = "2025-03-26"
MAX_BODY = 1_000_000
MAX_TOOLS = 256


class CatalogSession(Session):
    async def start(self):
        # Capture the opening frame through the existing validated transport.
        return await super().start()

    async def _recv(self):
        frame = await super()._recv()
        if self.task is None and frame.get("type") == "task":
            servers = frame.get("mcp_servers")
            self._catalog_declared = (
                type(servers) is list and len(servers) == 1
                and servers[0] == {"name": "synthetic-catalog", "url": SERVICE,
                                   "transport": "streamable-http"}
            )
        return frame

    async def _post(self, message, *, session_id=None, notify=False):
        if not getattr(self, "_catalog_declared", False):
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
        headers = reply.get("headers")
        if type(headers) is not dict or any(type(k) is not str or type(v) is not str
                                              for k, v in headers.items()):
            raise WireError("invalid response headers")
        folded = {k.lower(): v for k, v in headers.items()}
        if len(folded) != len(headers):
            raise WireError("duplicate response header")
        try:
            body = base64.b64decode(reply["body_b64"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
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

    async def catalog(self):
        if getattr(self, "_catalog_started", False):
            raise WireError("catalog already attempted")
        self._catalog_started = True
        result, headers = await self._post({"jsonrpc": "2.0", "id": 1,
            "method": "initialize", "params": {"protocolVersion": VERSION,
            "capabilities": {}, "clientInfo": {"name": "aegis-synthetic", "version": "1"}}})
        if result.get("protocolVersion") != VERSION:
            raise WireError("unsupported protocol version")
        sid = headers.get("mcp-session-id")
        if sid is not None and (not 1 <= len(sid) <= 128 or
                                any(not 33 <= ord(ch) <= 126 for ch in sid)):
            raise WireError("invalid session header")
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                         session_id=sid, notify=True)
        result, _ = await self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                                     session_id=sid)
        tools = result.get("tools")
        if result.get("nextCursor") is not None or type(tools) is not list or len(tools) > MAX_TOOLS:
            raise WireError("catalog incomplete or too large")
        names = []
        for tool in tools:
            if type(tool) is not dict or type(tool.get("inputSchema")) is not dict:
                raise WireError("invalid tool metadata")
            names.append(text(tool.get("name"), "tool name", 128))
        if len(set(names)) != len(names):
            raise WireError("duplicate tool names")
        return tuple(sorted(names))
