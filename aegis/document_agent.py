"""Bounded offline report proposal and repair over fictional inventory records.

The trusted manifest and reconciler establish the facts. Synthetic provider
replies may propose formatting and content, but cannot invoke any tools or
override provenance. No external endpoint or real engineering design is used.
"""
import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from time import monotonic

from .documents import reconcile
from .models import Profile
from .protocol import decode, WireError
from .stream import collect
from .process_verify import verify_in_process
from .document_experiment import CATEGORIES, record


@dataclass(frozen=True)
class Result:
    status: str
    calls: int
    reserved_output: int
    reported_input: int
    reported_output: int
    diagnostics: tuple[str, ...]
    output: dict | None


def verified_projection(source):
    return {
        "input_binding": source.input_binding,
        "facts": [{"key": f.key, "value": f.value,
                   "sources": [asdict(s) for s in f.sources]} for f in source.facts],
    }


def matches(proposal, expected):
    # JSON serialization preserves boolean/int type distinction and source order.
    return json.dumps(proposal, sort_keys=True, allow_nan=False) == json.dumps(
        expected, sort_keys=True, allow_nan=False)


async def solve(manifest, required, documents, profile, provider, *, max_calls=3,
                output_budget=768, input_budget=4096, deadline_sec=5):
    if (type(profile) is not Profile or profile != Profile.parse(profile.declaration)
            or type(max_calls) is not int or not 1 <= max_calls <= 4
            or type(output_budget) is not int or not 0 <= output_budget <= 2048
            or type(input_budget) is not int or not 0 <= input_budget <= 16384
            or type(deadline_sec) not in (int, float) or not 0 < deadline_sec <= 10):
        raise ValueError("invalid offline limits")
    start = monotonic()
    source = reconcile(manifest, required, documents)
    if source.status != "VERIFIED_SYNTHETIC":
        return Result("BLOCKED", 0, 0, 0, 0, source.reasons, None)
    expected = verified_projection(source)
    # Send raw fictional records, not the verified answer, to the test provider.
    request_data = json.dumps({"manifest": manifest, "required": required,
        "documents": [decode(raw.decode()) for raw in documents],
        "document_hashes": [sha256(raw).hexdigest() for raw in documents],
        "input_binding": source.input_binding}, sort_keys=True)
    if len(request_data.encode()) > 16000:
        return Result("BLOCKED", 0, 0, 0, 0, ("input_size",), None)
    messages = [{"role": "system", "content": "Return only a JSON object containing input_binding and facts. Each fact has key, value, and sources (family, revision, content_hash). Use the controller manifest. No tools."},
                {"role": "user", "content": request_data}]
    calls = reserved = used_in = used_out = 0
    diagnostics = []
    for _ in range(max_calls):
        limit = min(256, output_budget - reserved)
        remaining = deadline_sec - (monotonic() - start)
        if limit < 64 or remaining <= 0 or used_in >= input_budget:
            break
        effort = ("low" if calls == 0 else "medium") if profile.family in ("claude", "gemini") else None
        request = profile.request(messages, max_tokens=limit, effort=effort)
        request["stream_options"] = {"include_usage": True}
        reserved += limit
        calls += 1
        try:
            async with asyncio.timeout(remaining):
                chunks = await provider(request)
            # Only a finite list of decoded chunks is accepted in this offline prototype.
            if type(chunks) is not list:
                raise WireError("unsupported stream transport")
            completion = collect(chunks, model=profile.model, output_limit=limit)
            used_in += completion.input_tokens
            used_out += completion.output_tokens
            if used_in > input_budget:
                diagnostics.append("reported_input_budget_exceeded")
                break
            candidate = decode(completion.content)
            if matches(candidate, expected):
                remaining = deadline_sec - (monotonic() - start)
                if remaining <= 0 or not await asyncio.to_thread(verify_in_process, manifest, required, documents, candidate, timeout=min(1.0, remaining)):
                    diagnostics.append("independent_process_rejected")
                    break
                if monotonic() - start >= deadline_sec:
                    diagnostics.append("deadline_exceeded")
                    break
                return Result("VERIFIED_SYNTHETIC", calls, reserved, used_in, used_out,
                              tuple(diagnostics), candidate)
            reason = "fact_or_provenance_mismatch"
        except TimeoutError:
            reason = "deadline_exceeded"
            diagnostics.append(reason)
            break
        except (WireError, ValueError, TypeError, KeyError, UnicodeError, RuntimeError):
            # Unknown consumption is not refunded; stop rather than speculate about cost.
            diagnostics.append("unverifiable_provider_response")
            break
        diagnostics.append(reason)
        messages.append({"role": "user", "content": "Rejected: fact_or_provenance_mismatch. Reconcile again; do not use unsupported sources."})
    return Result("BLOCKED", calls, reserved, used_in, used_out, tuple(diagnostics), None)


def chunks_for(model, payload, *, input_tokens=80, output_tokens=50):
    """Explicit scripted response helper; not a model measurement."""
    content = json.dumps(payload, sort_keys=True)
    return [{"model": model, "choices": [{"index": 0, "delta": {"content": content},
            "finish_reason": "stop"}]},
            {"model": model, "choices": [], "usage": {"prompt_tokens": input_tokens,
                "completion_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}}]


class Scripted:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        return next(self.replies)


async def experiment():
    rows = []
    profile = Profile.parse("google-cloud/gemini-4-neon")
    for i, category in enumerate(CATEGORIES):
        count = i + 5
        manifest = {"register": 2, "summary": 1}
        required = ("inventory_count",)
        documents = (record("register", 2, count), record("summary", 1, count))
        expected = verified_projection(reconcile(manifest, required, documents))
        wrong = json.loads(json.dumps(expected))
        wrong["facts"][0]["value"] += 1
        conflict = (documents[0], record("summary", 1, count + 1))
        for name, docs, script, label in (
            ("first_pass", documents, [expected], True),
            ("repair", documents, [wrong, expected], True),
            ("persistent_error", documents, [wrong, wrong], False),
            ("source_conflict", conflict, [], False),
        ):
            outcomes = {}
            for method, limit in (("single", 1), ("bounded_repair", 2)):
                provider = Scripted([chunks_for(profile.model, proposal) for proposal in script])
                result = await solve(manifest, required, docs, profile, provider, max_calls=limit)
                outcomes[method] = {"verified": result.status == "VERIFIED_SYNTHETIC",
                    "calls": result.calls, "reserved_output": result.reserved_output,
                    "reported_input": result.reported_input, "reported_output": result.reported_output}
            rows.append({"category": category, "case": name, "expected": label, "outcomes": outcomes})
    metrics = {}
    for method in ("single", "bounded_repair"):
        metrics[method] = {
            "correct": sum(row["expected"] == row["outcomes"][method]["verified"] for row in rows),
            "false_accepts": sum(not row["expected"] and row["outcomes"][method]["verified"] for row in rows),
            "calls": sum(row["outcomes"][method]["calls"] for row in rows),
            "reserved_output": sum(row["outcomes"][method]["reserved_output"] for row in rows),
        }
    if metrics["bounded_repair"]["correct"] != len(rows) or metrics["bounded_repair"]["false_accepts"]:
        raise RuntimeError("source-bound repair violated synthetic acceptance labels")
    return {"scope": "scripted provider document repair", "cases": len(rows), "rows": rows,
            "metrics": metrics, "promotion": "BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(experiment()), sort_keys=True))
