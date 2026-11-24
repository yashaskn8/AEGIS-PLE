"""Bounded, controller-declared count checks for fictional inventory reports.

No expressions, arbitrary code, design formulas or inferred requirements.
The graph checks source-bound integer counts. A separately written arithmetic
oracle checks every equality again before the report can be accepted.
"""
from dataclasses import asdict, dataclass
from typing import Any

from .constraints import Check, Controller, Requirement
from .firewall import digest


@dataclass(frozen=True)
class SumCheck:
    total: str
    parts: tuple[str, ...]


def _sum_check(plan: SumCheck) -> Check:
    def check(facts: dict[str, Any]) -> bool:
        return bool(all(type(v) is int for v in facts.values())
                    and facts[plan.total] == sum(facts[k] for k in plan.parts))
    return check


def _controller(plan: tuple[SumCheck, ...]) -> Controller:
    targets = {item.total for item in plan}
    nodes = tuple(Requirement(item.total, (item.total, *item.parts),
                              tuple(k for k in item.parts if k in targets)) for item in plan)
    return Controller(nodes, {item.total: _sum_check(item) for item in plan})


def parse_checks(raw: object, required: tuple[str, ...]) -> tuple[SumCheck, ...]:
    if type(raw) is not list or not 1 <= len(raw) <= 16:
        raise ValueError("invalid count check inventory")
    allowed = set(required)
    plan = []
    for item in raw:
        if type(item) is not dict or set(item) != {"total", "parts"}:
            raise ValueError("invalid count check schema")
        total, parts = item["total"], item["parts"]
        if (type(total) is not str or total not in allowed or type(parts) is not list
                or not 1 <= len(parts) <= 16 or any(type(k) is not str or k not in allowed for k in parts)
                or total in parts or len(set(parts)) != len(parts)):
            raise ValueError("invalid count check references")
        plan.append(SumCheck(total, tuple(sorted(parts))))
    if len({item.total for item in plan}) != len(plan):
        raise ValueError("duplicate count check target")
    normalized = tuple(sorted(plan, key=lambda item: item.total))
    _controller(normalized)  # reject cycles before any record retrieval
    return normalized


def verify_checks(plan: tuple[SumCheck, ...], proposal: dict[str, Any]) -> dict[str, Any]:
    values = {fact["key"]: fact["value"] for fact in proposal["facts"]}
    # Independently evaluate the equality by subtracting every component.
    # Explicit type tests prevent bools or numeric-looking text from passing.
    for item in plan:
        counts = [values[k] for k in (item.total, *item.parts)]
        if any(type(v) is not int or not 0 <= v <= 1_000_000 for v in counts):
            raise ValueError("non-count constraint operand")
        remainder = counts[0]
        for component in counts[1:]:
            remainder -= component
        if remainder != 0:
            raise ValueError("count constraint rejected")
    observed = _controller(plan).evaluate(values, reuse=False)
    if not observed.verified or observed.evaluated != len(plan):
        raise ValueError("count dependency graph rejected")
    checks = [asdict(item) for item in plan]
    evidence = [asdict(item) for item in observed.evidence]
    return {"checks": checks, "evidence": evidence,
            "binding": digest({"source": proposal["input_binding"], "checks": checks,
                               "facts": proposal["facts"], "evidence": evidence})}
