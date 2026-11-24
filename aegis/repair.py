"""Bounded proposal and repair over fictional measurement inventories.

The caller supplies a trusted test transport. The transport is not implemented
here and no endpoint, external tool, executable candidate, or secret is used.
Provider replies are untrusted data. Acceptance uses a separate Decimal oracle.
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
import json
from hashlib import sha256

from .aggregation import Fixture
from .models import Profile
from .protocol import decode

MAX_ATTEMPTS = 4
MAX_OUTPUT = 512
MAX_REPLY = 8192


@dataclass(frozen=True)
class Result:
    status: str
    attempts: int
    reserved_output_tokens: int
    reasons: tuple[str, ...]
    verified: dict[str, Any] | None


def extract(reply: object, model: str, limit: int) -> dict[str, Any]:
    if type(reply) is not dict or reply.get("model") != model:
        raise ValueError("provider identity mismatch")
    choices = reply.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise ValueError("invalid response choice")
    choice = choices[0]
    message = choice.get("message")
    if choice.get("finish_reason") != "stop" or type(message) is not dict:
        raise ValueError("incomplete response")
    if message.get("role") != "assistant" or message.get("tool_calls") or message.get("function_call"):
        raise ValueError("unexpected response action")
    usage = reply.get("usage")
    if type(usage) is not dict or type(usage.get("completion_tokens")) is not int:
        raise ValueError("missing output token accounting")
    if not 0 <= usage["completion_tokens"] <= limit:
        raise ValueError("reported output budget violation")
    content = message.get("content")
    if type(content) is not str or len(content.encode("utf-8")) > MAX_REPLY:
        raise ValueError("invalid proposal content")
    return decode(content)


def verify(proposal: dict[str, Any], fixture: Fixture) -> str | None:
    if (type(proposal) is not dict or set(proposal) != {"source_sha256", "count", "total_mm"}
            or proposal["source_sha256"] != fixture.identity
            or type(proposal["count"]) is not int or proposal["count"] != len(fixture.micrometres)
            or type(proposal["total_mm"]) is not int):
        return "source or output schema mismatch"
    with localcontext() as ctx:
        ctx.prec = 40
        expected = int(sum((Decimal(x) / Decimal(1000) for x in fixture.micrometres), Decimal(0))
                       .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return None if proposal["total_mm"] == expected else "independent arithmetic mismatch"


async def solve(raw: bytes, profile: Profile, provider: Callable[[dict[str, Any]], Awaitable[object]],
                *, attempts: int = 3, output_budget: int = 768,
                call_timeout: float = 2.0) -> Result:
    if (type(raw) is not bytes or len(raw) > MAX_REPLY or
            type(attempts) is not int or not 1 <= attempts <= MAX_ATTEMPTS or
            type(output_budget) is not int or not 0 <= output_budget <= MAX_ATTEMPTS * MAX_OUTPUT or
            type(call_timeout) not in (int, float) or not 0 < call_timeout <= 10
            or type(profile) is not Profile or profile != Profile.parse(profile.declaration)):
        raise ValueError("invalid controller limits")
    data = decode(raw.decode("utf-8"))
    if set(data) != {"micrometres"} or type(data["micrometres"]) is not list:
        raise ValueError("invalid fictional inventory")
    fixture = Fixture(sha256(raw).hexdigest(), tuple(data["micrometres"]))
    messages = [
        {"role": "system", "content": "Return only a JSON object with source_sha256, count and total_mm. Sum fictional micrometres, convert to millimetres, round half up only at the end. No tools."},
        {"role": "user", "content": json.dumps({"source_sha256": fixture.identity,
                                              "micrometres": fixture.micrometres})},
    ]
    reserved = calls = 0
    reasons = []
    for _ in range(attempts):
        # Reserve before calling. Unused or unverifiable allowance is not refunded.
        remaining = output_budget - reserved
        limit = min(256, remaining)
        if limit < 64:
            break
        effort = ("low" if calls == 0 else "medium") if profile.family in ("gemini", "claude") else None
        request = profile.request(messages, max_tokens=limit, effort=effort, stream=False)
        reserved += limit
        calls += 1
        end = asyncio.get_running_loop().time() + call_timeout
        try:
            async with asyncio.timeout_at(end):
                reply = await provider(request)
            if asyncio.get_running_loop().time() >= end:
                raise TimeoutError
            proposal = extract(reply, profile.model, limit)
            reason = verify(proposal, fixture)
            if asyncio.get_running_loop().time() >= end:
                raise TimeoutError
            if reason is None:
                return Result("VERIFIED_SYNTHETIC", calls, reserved, tuple(reasons), dict(proposal))
        except TimeoutError:
            reasons.append("provider timeout")
            break
        except (ValueError, TypeError, KeyError, RuntimeError):
            reasons.append("invalid or incomplete proposal")
            break
        except Exception:
            # Unknown consumption is not refunded; never retry an unverified reply.
            reasons.append("provider or protocol failure")
            break
        reasons.append(reason)
        # Only trusted diagnostic labels enter the next request; not raw model text.
        messages.append({"role": "user", "content": "Previous attempt rejected: " + reason + ". Recompute independently."})
    return Result("BLOCKED", calls, reserved, tuple(reasons), None)
