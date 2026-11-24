"""Analyze published overall baseline scores, not predicted or measured AEGIS performance."""
import json
from math import isfinite
from pathlib import Path
from .models import SPONSORED

HARNESSES = frozenset(("claude-code", "pi", "opencode", "agy", "hermes", "codex", "openhands"))
MATRIX = Path("research/published_overall.json")


def analyze(record):
    pairs = record["pairs"]
    if (record["source"] != "https://ple-bench.com/leaderboard"
            or len(pairs) != 77 or {(x["model"],x["harness"]) for x in pairs}
            != {(m,h) for m in SPONSORED for h in HARNESSES}):
        raise ValueError("baseline inventory mismatch")
    known = []
    for x in pairs:
        score, cost, status = x["score"], x["cost_usd"], x["cost_status"]
        if type(score) not in (int,float) or not isfinite(score) or not 0 <= score <= 1:
            raise ValueError("invalid score")
        if status not in ("reported","approx","caveat","approx_caveat","missing"):
            raise ValueError("invalid cost status")
        if cost is None:
            if status != "missing":
                raise ValueError("missing cost must be marked")
        elif type(cost) not in (int,float) or not isfinite(cost) or cost <= 0 or status == "missing":
            raise ValueError("invalid cost")
        else:
            known.append(x)
    # Missing cost is excluded, not replaced by zero. Eligibility floor is
    # applied only for the displayed hypothetical qualifying subset.
    eligible = [x for x in known if x["score"] >= .138]
    frontier = [x for x in eligible if not any(
        y["score"] >= x["score"] and y["cost_usd"] <= x["cost_usd"]
        and (y["score"] > x["score"] or y["cost_usd"] < x["cost_usd"])
        for y in eligible)]
    return {"scope":"published baseline aggregate, not AEGIS", "pairs":len(pairs),
            "known_costs":len(known), "score_floor":.138,
            "frontier":sorted(frontier,key=lambda x:x["cost_usd"])}


if __name__ == "__main__":
    print(json.dumps(analyze(json.loads(MATRIX.read_text())),sort_keys=True))
