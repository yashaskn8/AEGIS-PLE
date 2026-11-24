"""Bounded, controller-declared count checks for fictional inventory reports.

No expressions, arbitrary code, design formulas or inferred requirements.
Derived counts are explicitly distinct from observed source facts. A separately
written arithmetic oracle checks every equality before report acceptance.
"""
from dataclasses import asdict, dataclass
from typing import Any

from .constraints import Check, Controller, Requirement
from .documents import KEY, parse_record
from .firewall import digest


@dataclass(frozen=True)
class SumCheck:
    total: str
    parts: tuple[str, ...]
    derive: bool = False


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
    observed = set(required)
    plan: list[SumCheck] = []
    for item in raw:
        if type(item) is not dict or set(item) not in ({"total", "parts"}, {"total", "parts", "derive"}):
            raise ValueError("invalid count check schema")
        total, parts = item["total"], item["parts"]
        derive = "derive" in item
        if (derive and item["derive"] is not True
                or type(total) is not str or not KEY.fullmatch(total)
                or (derive and total in observed) or (not derive and total not in observed)
                or type(parts) is not list
                or not 1 <= len(parts) <= 16 or any(type(k) is not str for k in parts)
                or total in parts or len(set(parts)) != len(parts)):
            raise ValueError("invalid count check references")
        plan.append(SumCheck(total, tuple(sorted(parts)), derive))
    if len({item.total for item in plan}) != len(plan):
        raise ValueError("duplicate count check target")
    allowed = observed | {item.total for item in plan if item.derive}
    if any(not set(item.parts) <= allowed for item in plan):
        raise ValueError("unknown count check operand")
    normalized = tuple(sorted(plan, key=lambda item: item.total))
    _controller(normalized)  # reject cycles before any record retrieval
    return normalized


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError("non-count constraint operand")
    return value


def _derive(plan: tuple[SumCheck, ...], values: dict[str, Any],
            documents: tuple[bytes, ...]) -> list[dict[str, Any]]:
    pending = {item.total: item.parts for item in plan if item.derive}
    if not pending:
        return []
    if not documents or any(set(parse_record(raw)["fields"]) & set(pending) for raw in documents):
        raise ValueError("derived target appears in source or source unavailable")
    origins = {key: {key} for key in values}
    derived: list[dict[str, Any]] = []
    while pending:
        ready = sorted(key for key, parts in pending.items() if all(p in values for p in parts))
        if not ready:
            raise ValueError("unresolved count derivations")
        for key in ready:
            parts = pending.pop(key)
            total = 0
            for part in parts:
                total += _count(values[part])
            values[key] = _count(total)
            origins[key] = {origin for part in parts for origin in origins[part]}
            derived.append({"key": key, "value": total, "source_keys": sorted(origins[key])})
    return derived


def verify_checks(plan: tuple[SumCheck, ...], proposal: dict[str, Any],
                  documents: tuple[bytes, ...] = ()) -> dict[str, Any]:
    values = {fact["key"]: fact["value"] for fact in proposal["facts"]}
    derived = _derive(plan, values, documents)
    # Independently evaluate the equality by subtracting every component.
    for item in plan:
        counts = [_count(values[k]) for k in (item.total, *item.parts)]
        remainder = counts[0]
        for component in counts[1:]:
            remainder -= component
        if remainder != 0:
            raise ValueError("count constraint rejected")
    observed = _controller(plan).evaluate(values, reuse=False)
    if not observed.verified or observed.evaluated != len(plan):
        raise ValueError("count dependency graph rejected")
    checks = [{"total": item.total, "parts": item.parts, **({"derive": True} if item.derive else {})}
              for item in plan]
    evidence = [asdict(item) for item in observed.evidence]
    result: dict[str, Any] = {"checks": checks, "evidence": evidence}
    if derived:
        result["derived_facts"] = derived
    result["binding"] = digest({"source": proposal["input_binding"], "facts": proposal["facts"], **result})
    return result
