"""Provider-aware request construction, with no network transport.

Model declarations are copied as identifiers from the official models document.
Only fixed, explicit profiles are permitted; no model substitution or keys.
"""
from dataclasses import dataclass
from typing import Any, Self

MAX_CONTENT_BYTES = 256 * 1024

SPONSORED = frozenset((
    "gemini-4-argon", "gemini-4-carbon", "gemini-4-neon", "gemini-4-hydrogen",
    "gemini-3.8-flash", "gemini-3.1-pro-preview", "claude-opus-5-5",
    "gpt-oss-120b", "glm-5.2", "gemma-4-26b", "llama-4-maverick",
))


@dataclass(frozen=True)
class Profile:
    declaration: str
    model: str
    family: str

    @classmethod
    def parse(cls, declaration: object) -> Self:
        if type(declaration) is not str or not declaration.startswith("google-cloud/"):
            raise ValueError("unsupported model declaration")
        model = declaration.split("/", 1)[1]
        if model not in SPONSORED:
            raise ValueError("unknown sponsored model")
        family = "gemini" if model.startswith("gemini-") else "claude" if model.startswith("claude-") else "compatible"
        return cls(declaration, model, family)

    def request(self, messages: object, *, max_tokens: int,
                effort: str | None = None, stream: bool = True) -> dict[str, Any]:
        if self != Profile.parse(self.declaration) or type(stream) is not bool:
            raise ValueError("invalid provider profile or stream mode")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32000:
            raise ValueError("output budget outside synthetic profile")
        if type(messages) is not list or not messages or len(messages) > 64:
            raise ValueError("invalid message inventory")
        clean: list[dict[str, str]] = []
        content_bytes = 0
        for m in messages:
            if (type(m) is not dict or set(m) != {"role", "content"}
                    or m["role"] not in ("system", "user", "assistant")
                    or type(m["content"]) is not str or len(m["content"]) > 65536):
                raise ValueError("unsupported message shape")
            try:
                content_bytes += len(m["content"].encode("utf-8"))
            except UnicodeError as exc:
                raise ValueError("invalid message Unicode") from exc
            if content_bytes > MAX_CONTENT_BYTES:
                raise ValueError("aggregate content byte budget exceeded")
            clean.append(dict(m))
        body: dict[str, Any] = {"model": self.model, "messages": clean, "max_tokens": max_tokens, "stream": stream}
        if effort is not None:
            # Only profiles with explicitly documented controls. Others use defaults.
            allowed: dict[str, tuple[str, ...]] = {"gemini": ("low", "medium", "high"), "claude": ("low", "medium", "high", "max")}
            if effort not in allowed.get(self.family, ()):
                raise ValueError("unsupported reasoning effort")
            body["reasoning_effort"] = effort
        return body
