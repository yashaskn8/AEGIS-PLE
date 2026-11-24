"""Bounded PLE v1 wire subset for synthetic peers. No network or shell access.

A transport supplies async send(str) and recv() methods. The controller owns
all file paths; candidate/model output never directly invokes a transport.
Only one request may be outstanding. No task content is retained in logs.
"""
import asyncio
import base64
import binascii
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Protocol

MAX_FRAME = 16 * 1024 * 1024
MAX_FILE = 10_000_000
MAX_REQUESTS = 64


class WireError(Exception):
    pass


class Cancelled(WireError):
    pass


class Transport(Protocol):
    async def send(self, text: str) -> None: ...
    async def recv(self) -> str: ...


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WireError("duplicate JSON key")
        result[key] = value
    return result


def decode(raw: str) -> dict:
    try:
        if type(raw) is not str or len(raw.encode("utf-8")) > MAX_FRAME:
            raise WireError("invalid frame size or type")
        def invalid_constant(_):
            raise WireError("invalid JSON constant")
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
        if type(value) is not dict:
            raise WireError("expected object")
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WireError("invalid JSON") from exc


def encode(value: dict) -> str:
    try:
        raw = json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"))
        if len(raw.encode()) > MAX_FRAME:
            raise WireError("oversize frame")
        return raw
    except (ValueError, TypeError, RecursionError) as exc:
        raise WireError("invalid frame") from exc


def positive(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise WireError("invalid " + name)
    return value


def text(value, name, maximum=65536):
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        raise WireError("invalid " + name)
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise WireError("invalid " + name) from exc
    return value


@dataclass(frozen=True)
class Task:
    session: str
    instruction: str
    workdir: str
    timeout: int | None
    max_write: int

    @classmethod
    def parse(cls, frame):
        if frame.get("type") != "task" or type(frame.get("protocol")) is not int or frame["protocol"] != 1:
            raise WireError("unsupported opening frame")
        limits = frame.get("limits")
        if type(limits) is not dict or type(frame.get("mcp_servers")) is not list:
            raise WireError("invalid task capabilities")
        timeout = limits.get("agent_timeout_sec")
        if timeout is not None:
            positive(timeout, "deadline", 86400)
        write = positive(limits.get("max_write_bytes"), "write limit", MAX_FILE)
        root = text(frame.get("workdir"), "workdir", 1024)
        if not PurePosixPath(root).is_absolute() or ".." in PurePosixPath(root).parts:
            raise WireError("invalid working directory")
        return cls(text(frame.get("session"), "session", 128),
                   text(frame.get("instruction"), "instruction"), root, timeout, write)


class Session:
    """Sequential file subset with deadline, strict correlation and terminal guard.

    Intentionally narrower than PLE: no exec, HTTP, append or concurrent requests.
    The transport must be an authorized synthetic peer until policy is cleared.
    """
    def __init__(self, transport: Transport, *, io_timeout: float = 5.0):
        if not 0 < io_timeout <= 30:
            raise ValueError("invalid I/O timeout")
        self.transport = transport
        self.io_timeout = io_timeout
        self.task = None
        self.deadline = None
        self.count = 0
        self.terminal = False
        self.cancelled = False
        self.poisoned = False
        self.busy = False

    def _remaining(self):
        remaining = self.io_timeout
        if self.deadline is not None:
            remaining = min(remaining, self.deadline - asyncio.get_running_loop().time())
        if remaining <= 0:
            raise WireError("task deadline reached")
        return remaining

    async def _recv(self):
        try:
            async with asyncio.timeout(self._remaining()):
                value = decode(await self.transport.recv())
        except TimeoutError as exc:
            raise WireError("receive timeout") from exc
        if value.get("type") == "cancel":
            self.cancelled = True
            raise Cancelled("peer cancelled")
        return value

    async def start(self):
        if self.task is not None or self.terminal or self.busy or self.poisoned:
            raise WireError("cannot start session")
        self.busy = True
        try:
            self.task = Task.parse(await self._recv())
            if self.task.timeout is not None:
                self.deadline = asyncio.get_running_loop().time() + self.task.timeout
            return self.task
        except BaseException:
            self.poisoned = True
            raise
        finally:
            self.busy = False

    def _path(self, path):
        path = text(path, "path", 1024)
        # Synthetic controller uses relative paths only. Peer owns filesystem isolation.
        p = PurePosixPath(path)
        if p.is_absolute() or ".." in p.parts or str(p) == "." or "\\" in path:
            raise WireError("path outside synthetic scope")
        return str(p)

    async def _request(self, kind, **fields):
        if self.task is None or self.terminal or self.cancelled or self.poisoned or self.busy:
            raise WireError("session unavailable")
        if self.count >= MAX_REQUESTS:
            raise WireError("request budget exhausted")
        self.count += 1
        request_id = str(self.count)
        self.busy = True
        try:
            async with asyncio.timeout(self._remaining()):
                await self.transport.send(encode({"type": kind, "id": request_id, **fields}))
            reply = await self._recv()
            if reply.get("type") != "result" or reply.get("id") != request_id:
                raise WireError("uncorrelated result")
            if type(reply.get("ok")) is not bool:
                raise WireError("missing result status")
            return reply
        except BaseException:
            # A timed-out/mismatched request leaves ambiguous remote state.
            self.poisoned = True
            raise
        finally:
            self.busy = False

    async def read(self, path):
        reply = await self._request("read_file", path=self._path(path))
        if reply["ok"] is not True or reply.get("truncated") is not False:
            raise WireError("file unavailable or incomplete")
        try:
            data = base64.b64decode(reply["content_b64"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise WireError("invalid file encoding") from exc
        if type(reply.get("size")) is not int or reply["size"] != len(data) or len(data) > MAX_FILE:
            raise WireError("file size mismatch")
        return data

    async def write(self, path, data):
        if self.task is None or type(data) is not bytes or len(data) > self.task.max_write:
            raise WireError("invalid write payload")
        reply = await self._request("write_file", path=self._path(path),
                                    content_b64=base64.b64encode(data).decode(), append=False)
        if reply["ok"] is not True or type(reply.get("size")) is not int or reply["size"] != len(data):
            raise WireError("write not acknowledged")

    async def finish(self, message, *, failed=False):
        if self.terminal or self.busy:
            raise WireError("terminal frame already sent or operation outstanding")
        message = text(message, "terminal message", 4096)
        # Cancellation grants a separate short grace window; do not reuse task deadline.
        if self.poisoned and not self.cancelled and not failed:
            raise WireError("ambiguous session cannot report success")
        self.terminal = True
        frame = {"type": "error", "message": message} if failed else {"type": "done", "final_message": message}
        async with asyncio.timeout(self.io_timeout):
            await self.transport.send(encode(frame))
