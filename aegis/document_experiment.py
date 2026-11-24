"""Four-category fictional document reconciliation with fixed independent labels.

The labels describe records, not engineering designs. Baseline and ablations
receive the same inputs. The acceptance labels are controller-authored fixtures,
not computed by the candidate.
"""
from dataclasses import dataclass
import json
from .documents import reconcile
from .protocol import decode

CATEGORIES = ("structural", "civil", "electrical", "mechanical")


@dataclass(frozen=True)
class Case:
    category: str
    name: str
    documents: tuple[bytes, ...]
    expected: int | None


def record(family, revision, count):
    fields = {} if count is None else {"inventory_count": count}
    return json.dumps({"family": family, "revision": revision, "fields": fields},
                      sort_keys=True).encode()


def cases():
    output = []
    for index, category in enumerate(CATEGORIES):
        n = 20 + index
        m = lambda rev, value: record("register", rev, value)
        s = lambda rev, value: record("summary", rev, value)
        examples = (
            ("clean", (m(2,n),s(1,n)), n),
            ("obsolete_first", (m(1,n-1),m(2,n),s(1,n)), n),
            ("obsolete_last", (m(2,n),s(1,n),m(1,n-1)), n),
            ("missing_current", (m(1,n),s(1,n)), None),
            ("conflict", (m(2,n),s(1,n+1)), None),
            ("duplicate", (m(2,n),m(2,n),s(1,n)), None),
            ("unapproved_future", (m(2,n),s(1,n),m(3,n+1)), None),
            ("missing_fact", (m(2,None),s(1,None)), None),
            ("compound", (m(1,n),m(2,n),m(2,n+1),s(1,n+2)), None),
            ("malformed", (m(2,n),s(1,n),b'{"bad":'), None),
        )
        output.extend(Case(category, name, docs, expected) for name, docs, expected in examples)
    return tuple(output)


def baseline(case):
    # Intentionally naive first-readable-value strategy, not a frontier agent.
    for raw in case.documents:
        try:
            fields = decode(raw.decode())["fields"]
            if type(fields.get("inventory_count")) is int:
                return fields["inventory_count"]
        except Exception:
            continue
    return None


def revision_only(case):
    # Ablation: revision filtering, but no agreement/completeness enforcement.
    for raw in case.documents:
        try:
            item = decode(raw.decode())
            if item["revision"] == {"register": 2, "summary": 1}.get(item["family"]):
                value = item["fields"].get("inventory_count")
                if type(value) is int:
                    return value
        except Exception:
            continue
    return None


def candidate(case):
    result = reconcile({"register": 2, "summary": 1}, ("inventory_count",), case.documents)
    return result.facts[0].value if result.status == "VERIFIED_SYNTHETIC" else None


def run():
    rows = []
    for case in cases():
        actual = {name: fn(case) for name, fn in
                  (("baseline", baseline), ("revision_only", revision_only), ("full", candidate))}
        rows.append({"category": case.category, "case": case.name, "expected": case.expected,
                     "actual": actual, "correct": {k:v == case.expected for k,v in actual.items()}})
    metrics = {}
    for method in ("baseline", "revision_only", "full"):
        metrics[method] = {"correct": sum(r["correct"][method] for r in rows),
                           "false_accepts": sum(r["expected"] is None and r["actual"][method] is not None for r in rows),
                           "valid_records_recovered": sum(r["expected"] is not None and r["correct"][method] for r in rows)}
    if metrics["full"]["correct"] != len(rows) or metrics["full"]["false_accepts"]:
        raise RuntimeError("mandatory synthetic source reconciliation violation")
    return {"scope": "synthetic document inventory only", "cases": len(rows),
            "metrics": metrics, "rows": rows, "promotion": "BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
