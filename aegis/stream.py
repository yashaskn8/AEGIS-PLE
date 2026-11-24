"""Offline OpenAI-compatible text-stream collector with strict usage evidence.

Consumes decoded synthetic chunks, not raw network streams. No tool actions.
Provider-specific reasoning history and native APIs remain outside this subset.
"""
from dataclasses import dataclass
from .protocol import WireError

MAX_CHUNKS = 256
MAX_TEXT = 8192


@dataclass(frozen=True)
class Completion:
    content: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


def collect(chunks, *, model, output_limit):
    if type(output_limit) is not int or not 1 <= output_limit <= 32000:
        raise ValueError("invalid output limit")
    parts = []
    size = 0
    stopped = False
    usage = None
    for index, chunk in enumerate(chunks):
        if index >= MAX_CHUNKS:
            raise WireError("stream chunk budget exceeded")
        if type(chunk) is not dict or chunk.get("model") != model or usage is not None:
            raise WireError("invalid stream identity or trailing chunk")
        choices = chunk.get("choices")
        if type(choices) is not list:
            raise WireError("invalid choices")
        if not choices:
            if not stopped or type(chunk.get("usage")) is not dict:
                raise WireError("premature usage frame")
            u = chunk["usage"]
            prompt, completion = u.get("prompt_tokens"), u.get("completion_tokens")
            details = u.get("prompt_tokens_details", {})
            if type(details) is not dict:
                raise WireError("invalid cache details")
            cached = details.get("cached_tokens", 0)
            if (any(type(n) is not int or not 0 <= n <= 2**53 - 1
                    for n in (prompt, completion, cached))
                    or completion > output_limit or cached > prompt
                    or ("total_tokens" in u and (type(u["total_tokens"]) is not int
                                                 or u["total_tokens"] != prompt + completion))):
                raise WireError("invalid usage")
            usage = (prompt, completion, cached)
            continue
        if stopped or len(choices) != 1 or type(choices[0]) is not dict:
            raise WireError("unexpected choice")
        choice = choices[0]
        delta = choice.get("delta")
        if (type(choice.get("index")) is not int or choice["index"] != 0
                or type(delta) is not dict or set(delta) - {"role", "content"}):
            raise WireError("unsupported stream delta")
        if "role" in delta and delta["role"] != "assistant":
            raise WireError("invalid assistant role")
        fragment = delta.get("content")
        if fragment is not None:
            if type(fragment) is not str:
                raise WireError("invalid content fragment")
            size += len(fragment.encode("utf-8"))
            if size > MAX_TEXT:
                raise WireError("stream text budget exceeded")
            parts.append(fragment)
        finish = choice.get("finish_reason")
        if finish is not None:
            if finish != "stop":
                raise WireError("incomplete stream")
            stopped = True
        if chunk.get("usage") is not None:
            raise WireError("unexpected usage placement")
    if not stopped or usage is None or not parts:
        raise WireError("stream lacks terminal content or usage")
    return Completion("".join(parts), *usage)
