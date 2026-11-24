"""Task-local dependency verification for trusted, synthetic checks.

Candidates supply only JSON data, not executable check functions. Reuse is
limited to controller-owned in-memory evidence. No external cache is trusted.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

from .firewall import digest

MAX_NODES = 128
MAX_BYTES = 65536
MAX_FACTS = 128


@dataclass(frozen=True)
class Requirement:
    name: str
    facts: tuple[str, ...]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Observation:
    name: str
    binding: str
    status: str
    reason: str


@dataclass(frozen=True)
class Report:
    evidence: tuple[Observation, ...]
    evaluated: int
    reused: int

    @property
    def verified(self) -> bool:
        return bool(self.evidence) and all(x.status == "VERIFIED" for x in self.evidence)


Check = Callable[[dict[str, Any]], bool]


class Controller:
    """A bounded DAG whose check registry is owned by the trusted caller."""

    def __init__(self, requirements: tuple[Requirement, ...], checks: dict[str, Check]) -> None:
        if not 1 <= len(requirements) <= MAX_NODES:
            raise ValueError("invalid requirement count")
        nodes = {n.name: n for n in requirements}
        if len(nodes) != len(requirements) or set(nodes) != set(checks):
            raise ValueError("missing, extra or duplicate check")
        for node in requirements:
            if (not node.name or len(set(node.facts)) != len(node.facts)
                    or len(set(node.dependencies)) != len(node.dependencies)
                    or not set(node.dependencies) <= set(nodes)):
                raise ValueError("invalid dependencies or facts")
        ordered: list[Requirement] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError("cyclic requirements")
            if name in visited:
                return
            visiting.add(name)
            for dep in nodes[name].dependencies:
                visit(dep)
            visiting.remove(name)
            visited.add(name)
            ordered.append(nodes[name])

        for name in nodes:
            visit(name)
        self._order = tuple(ordered)
        self._checks = dict(checks)
        self._cache: dict[str, Observation] = {}
        self._version = sha256(Path(__file__).read_bytes()).hexdigest()

    def evaluate(self, facts: dict[str, Any], *, reuse: bool = True,
                 reuse_nodes: frozenset[str] | None = None,
                 max_checks: int | None = None) -> Report:
        if max_checks is not None and (type(max_checks) is not int or not 0 <= max_checks <= MAX_NODES):
            raise ValueError("invalid verification budget")
        if reuse_nodes is not None and (type(reuse_nodes) is not frozenset
                or not reuse_nodes <= {node.name for node in self._order}):
            raise ValueError("invalid reuse policy")
        if type(facts) is not dict or len(facts) > MAX_FACTS:
            raise ValueError("invalid fact inventory")
        if any(type(key) is not str for key in facts):
            raise ValueError("fact keys must be strings")
        encoded = json.dumps(facts, allow_nan=False, sort_keys=True)
        if len(encoded.encode()) > MAX_BYTES:
            raise ValueError("fact budget exceeded")
        # JSON roundtrip detaches caller-owned mutable values.
        facts = json.loads(encoded)
        current: dict[str, Observation] = {}
        evaluated = reused = 0
        for node in self._order:
            missing = tuple(key for key in node.facts if key not in facts)
            selected = {key: facts[key] for key in node.facts if key in facts}
            parents = [current[key] for key in node.dependencies]
            binding = digest({
                "version": self._version, "name": node.name,
                "facts": selected, "missing": missing,
                "dependencies": [(p.name, p.binding, p.status) for p in parents],
            })
            old = self._cache.get(node.name)
            # Only successful evidence is reusable: errors may be transient.
            if (reuse and (reuse_nodes is None or node.name in reuse_nodes)
                    and old and old.binding == binding and old.status == "VERIFIED"):
                current[node.name] = old
                reused += 1
                continue
            if missing or any(p.status != "VERIFIED" for p in parents):
                status, reason = "BLOCKED", "missing facts or unverified dependency"
            elif max_checks is not None and evaluated >= max_checks:
                status, reason = "BLOCKED", "verification budget exhausted"
            else:
                evaluated += 1
                try:
                    passed = self._checks[node.name](json.loads(json.dumps(selected)))
                    status = "VERIFIED" if passed is True else "FAILED"
                    reason = "check passed" if passed is True else "check rejected"
                except Exception as exc:
                    status, reason = "FAILED", type(exc).__name__
            current[node.name] = Observation(node.name, binding, status, reason)
        self._cache = current
        return Report(tuple(current.values()), evaluated, reused)
