"""Reproduce an archived synthetic learning result before using its policy.

No candidate can change the check registry or generate executable code.
The archive is a historical observation, not an authorization token.
"""
from dataclasses import dataclass
import json
from pathlib import Path
from .ci_evidence import validate
from .firewall import digest
from .policy_search import search, compare

COMMIT = "a063077c2cb8eca6e83fc643924e3fd42262f8e6"
RUN = 45435657813
TESTS = 68
ARCHIVE = Path("research/evidence") / (COMMIT + ".json")


@dataclass(frozen=True)
class Learned:
    nodes: frozenset[str]
    evidence_digest: str
    source_commit: str


def reproduce(record, *, expected_commit, expected_run, expected_tests):
    validate(record, expected_commit=expected_commit,
             expected_run=expected_run, expected_tests=expected_tests)
    # Replay all development and transfer observations, not just the winner.
    if record["policy_report"] != search():
        raise ValueError("archived policy not reproducible with current checks")
    return Learned(frozenset(record["policy_report"]["selected"]), digest(record), expected_commit)


def load(path=ARCHIVE):
    if Path(path).stat().st_size > 1_000_000:
        raise ValueError("archive exceeds bounds")
    record = json.loads(Path(path).read_text())
    return reproduce(record, expected_commit=COMMIT, expected_run=RUN, expected_tests=TESTS)


def fresh():
    # Independently specified outcomes, including recovery after compound errors.
    rows = []
    for revision in (11, 12, 13, 14):
        initial = {"revision": revision, "items": [3, 7], "label": "inventory", "total": 10}
        rows.extend((
            (initial, True),
            (dict(initial, label="renamed"), True),
            (dict(initial, label="renamed", total=9), False),
            (dict(initial, label="renamed", revision=0, items=[-1]), False),
            (dict(initial, label="renamed", items=[8, 9], total=17), True),
            (dict(initial, label="renamed", items=[8, 9], total=17), True),
        ))
    return tuple(rows)


def run():
    policy = load()
    workload = fresh()
    report = compare(policy.nodes, tuple(facts for facts, _ in workload))
    labels = [expected for _, expected in workload]
    actual = [row["verified"] for row in report["rows"]]
    if report["matches"] != len(labels) or labels != actual:
        raise RuntimeError("learned policy failed retention")
    if report["checks"] >= report["baseline_checks"]:
        raise RuntimeError("learned policy did not retain check savings")
    return {"scope": "synthetic policy retention", "source_commit": policy.source_commit,
            "evidence_digest": policy.evidence_digest, "selected": sorted(policy.nodes),
            "correct": len(labels), "cases": len(labels),
            "false_accepts": sum(not e and a for e,a in zip(labels,actual)),
            "checks": report["checks"], "baseline_checks": report["baseline_checks"],
            "promotion": "BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
