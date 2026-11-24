"""Predeclared finite candidate experiment; never changes champion or releases."""

from dataclasses import asdict
import json

from .aggregation import Fixture, aggregate_first, premature_rounding
from .firewall import State, assess

DEVELOPMENT = (
    Fixture("rounding-counterexample", (490, 490)),
    Fixture("exact", (1000, 2000)),
)
TRANSFER = (
    Fixture("fresh-small-values", (260, 260, 260)),
    Fixture("fresh-overround", (510, 510, 510)),
    Fixture("fresh-tie", (200, 300)),
    Fixture("fresh-zero", (0,)),
)
# Published transfer fixtures are not a secret holdout.
CANDIDATES = (premature_rounding, aggregate_first)


def run() -> dict:
    results = {}
    for candidate in CANDIDATES:
        results[candidate.__name__] = {
            group: {fixture.identity: asdict(assess(candidate, fixture))
                    for fixture in fixtures}
            for group, fixtures in (("development", DEVELOPMENT), ("transfer", TRANSFER))
        }

    def passes(name: str, group: str) -> int:
        return sum(item["state"] is State.VERIFIED
                   for item in results[name][group].values())

    champion, challenger = (c.__name__ for c in CANDIDATES)
    # Fixed acceptance: strict development improvement, all transfer cases
    # verified, no per-fixture regression. Same number of executions per candidate.
    no_regression = all(
        results[champion][group][case]["state"] is not State.VERIFIED
        or results[challenger][group][case]["state"] is State.VERIFIED
        for group in ("development", "transfer") for case in results[champion][group]
    )
    recommend = (passes(challenger, "development") > passes(champion, "development")
                 and passes(challenger, "development") == len(DEVELOPMENT)
                 and passes(challenger, "transfer") == len(TRANSFER)
                 and no_regression)
    return {
        "scope": "synthetic only",
        "candidate_executions": len(CANDIDATES) * (len(DEVELOPMENT) + len(TRANSFER)),
        "champion": champion,
        "recommended": challenger if recommend else None,
        "promotion": "BLOCKED",
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
