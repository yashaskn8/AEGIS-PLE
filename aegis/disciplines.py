"""Analyze public aggregate scores only. No task data or model calls."""
import json
from pathlib import Path
from .frontier import MATRIX, analyze

FILE = Path("research/published_disciplines.json")
WEIGHTS = {"structural":6,"civil":9,"electrical":18,"mechanical":23}


def summarize(overall, disciplines):
    analyze(overall)
    if disciplines["source"] != overall["source"] or disciplines["weights"] != WEIGHTS:
        raise ValueError("source or task weighting mismatch")
    expected = {(p["model"],p["harness"]):p["score"] for p in overall["pairs"]}
    pairs = disciplines["pairs"]
    if len(pairs) != 77 or {(p["model"],p["harness"]) for p in pairs} != set(expected):
        raise ValueError("incomplete discipline matrix")
    for p in pairs:
        s = p["scores"]
        if set(s) != set(WEIGHTS) or any(type(x) not in (int,float) or not 0 <= x <= 1 for x in s.values()):
            raise ValueError("invalid discipline score")
        weighted = sum(s[k]*WEIGHTS[k] for k in WEIGHTS)/56
        if abs(weighted-expected[p["model"],p["harness"]]) > .0011:
            raise ValueError("rounded overall score inconsistency")
    leaders = {}
    for category in WEIGHTS:
        score = max(p["scores"][category] for p in pairs)
        leaders[category] = [{"model":p["model"],"harness":p["harness"],"score":score}
                             for p in pairs if p["scores"][category] == score]
    return {"scope":"published aggregate discipline matrix, not AEGIS", "pairs":len(pairs),
            "discipline_scores":len(pairs)*len(WEIGHTS), "leaders":leaders}


if __name__ == "__main__":
    print(json.dumps(summarize(json.loads(MATRIX.read_text()),json.loads(FILE.read_text())),sort_keys=True))
