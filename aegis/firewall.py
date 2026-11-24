"""Controller-owned verification for bounded synthetic fixtures.

A pass is scoped to exact supplied input, code and output. It is not release
approval. The controller and candidate currently share a process and trust
domain; do not execute untrusted candidate code here.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from hashlib import sha256
import inspect
import json
from pathlib import Path
from typing import Any

from .aggregation import Candidate, Fixture


class State(str, Enum):
    PENDING = "PENDING"
    IMPLEMENTED = "IMPLEMENTED"
    TESTED = "TESTED"
    VERIFIED = "VERIFIED"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


REQUIRED = ("output_schema", "independent_total")


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def code_digest(function: Candidate) -> str:
    path = inspect.getsourcefile(function)
    if path is None:
        raise ValueError("candidate has no inspectable source")
    return digest({"module": sha256(Path(path).read_bytes()).hexdigest(),
                   "function": function.__qualname__,
                   "source": inspect.getsource(function)})


@dataclass(frozen=True)
class Evidence:
    requirement: str
    state: State
    candidate: str
    fixture: str
    output: str
    verifier: str
    expected: str
    actual: str


@dataclass(frozen=True)
class Assessment:
    state: State
    evidence: tuple[Evidence, ...]
    reason: str


def gate(records: tuple[Evidence, ...], *, candidate: str, fixture: str,
         output: str, verifier: str) -> State:
    """Reject missing, duplicate, unexpected, stale or nonverified checks."""
    if len(records) != len(REQUIRED) or {r.requirement for r in records} != set(REQUIRED):
        return State.FAILED
    for record in records:
        if (record.candidate, record.fixture, record.output, record.verifier) != (
                candidate, fixture, output, verifier):
            return State.FAILED
        if record.state is not State.VERIFIED:
            return State.FAILED
    return State.VERIFIED


def assess(candidate: Candidate, fixture: Fixture) -> Assessment:
    """Execute candidate once; calculate expected result independently."""
    try:
        candidate_id = code_digest(candidate)
        fixture_id = digest(asdict(fixture))
        verifier_id = sha256(Path(__file__).read_bytes()).hexdigest()
        result = candidate(fixture.micrometres)
        valid = (type(result) is dict and set(result) == {"total_mm"}
                 and type(result["total_mm"]) is int)
        if not valid:
            return Assessment(State.FAILED, (), "output_schema: invalid result")
        output_id = digest(result)
        # Independent oracle: Decimal arithmetic, not candidate integer rounding.
        expected = int(sum(Decimal(x) / Decimal(1000)
                           for x in fixture.micrometres).quantize(
                               Decimal("1"), rounding=ROUND_HALF_UP))
        outcomes = (
            ("output_schema", True, "exact integer total_mm", "exact integer total_mm"),
            ("independent_total", result["total_mm"] == expected,
             str(expected), str(result["total_mm"])),
        )
        records = tuple(Evidence(name, State.VERIFIED if ok else State.FAILED,
                                 candidate_id, fixture_id, output_id, verifier_id,
                                 want, got) for name, ok, want, got in outcomes)
        state = gate(records, candidate=candidate_id, fixture=fixture_id,
                     output=output_id, verifier=verifier_id)
        return Assessment(state, records, "all checks verified" if state is State.VERIFIED
                          else "mandatory check failed")
    except Exception as exc:
        # Never turn an exception into a pass or log arbitrary candidate content.
        return Assessment(State.FAILED, (), f"execution failed: {type(exc).__name__}")
