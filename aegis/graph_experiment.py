"""Deterministic synthetic dependency invalidation experiment."""
import json
from .constraints import Controller, Requirement

NODES = (
    Requirement("source", ("revision",)),
    Requirement("quantity", ("items",), ("source",)),
    Requirement("label", ("label",)),
    Requirement("output", ("total", "items"), ("quantity", "label")),
)
CHECKS = {
    "source": lambda f: type(f["revision"]) is int and f["revision"] > 0,
    "quantity": lambda f: (type(f["items"]) is list and bool(f["items"])
                           and all(type(x) is int and 0 <= x <= 100 for x in f["items"])),
    "label": lambda f: type(f["label"]) is str and bool(f["label"].strip()),
    "output": lambda f: type(f["total"]) is int and f["total"] == sum(f["items"]),
}
SCENARIOS = (
    {"revision": 1, "items": [2, 3], "label": "sample", "total": 5},
    {"revision": 1, "items": [2, 3], "label": "revised", "total": 5},
    {"revision": 1, "items": [2, 4], "label": "revised", "total": 5},
    {"revision": 1, "items": [2, 4], "label": "revised", "total": 6},
    {"revision": 2, "items": [2, 4], "label": "revised", "total": 6},
    {"revision": 0, "items": [2, 4], "label": "revised", "total": 6},
    {"revision": 2, "items": [2, 4], "label": "revised", "total": 6},
)


def run():
    incremental = Controller(NODES, CHECKS)
    full = Controller(NODES, CHECKS)
    rows = []
    for index, facts in enumerate(SCENARIOS):
        a = incremental.evaluate(facts)
        b = full.evaluate(facts, reuse=False)
        if a.evidence != b.evidence:
            raise RuntimeError("incremental verification diverged from full oracle")
        rows.append({"scenario": index, "verified": a.verified,
                     "incremental_checks": a.evaluated, "full_checks": b.evaluated,
                     "reused": a.reused})
    return {"scope": "synthetic only", "scenarios": rows,
            "incremental_checks": sum(x["incremental_checks"] for x in rows),
            "full_checks": sum(x["full_checks"] for x in rows),
            "promotion": "BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
