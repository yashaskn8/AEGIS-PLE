"""Bounded, data-only verification policy generation and transfer evaluation.

A candidate is a subset of cache-eligible node names. It cannot supply code,
change checks, skip mandatory observations, alter fixtures or promote itself.
"""
from dataclasses import asdict
from itertools import combinations
import json
import random

from .constraints import Controller
from .firewall import digest
from .graph_experiment import NODES, CHECKS, SCENARIOS

MAX_POLICIES = 16
TRANSFER_SEED = 271828
TRANSFER_STEPS = 32


def generate():
    names = sorted(n.name for n in NODES)
    if len(names) > 4:
        raise ValueError("policy space exceeds declared budget")
    return tuple(frozenset(c) for size in range(len(names) + 1)
                 for c in combinations(names, size))


def transfer():
    rng = random.Random(TRANSFER_SEED)
    facts = dict(SCENARIOS[0])
    cases = []
    for _ in range(TRANSFER_STEPS):
        key = rng.choice(("revision", "items", "label", "total"))
        choices = {"revision": (0, 1, 2), "items": ([], [1, 2], [3, 4], [5]),
                   "label": ("", "fixture", "changed"), "total": (0, 3, 5, 7)}
        facts[key] = rng.choice(choices[key])
        cases.append(dict(facts))
    return tuple(cases)


def compare(policy, scenarios):
    candidate = Controller(NODES, CHECKS)
    oracle = Controller(NODES, CHECKS)
    calls = baseline = matches = accepted = 0
    rows = []
    for facts in scenarios:
        a = candidate.evaluate(facts, reuse_nodes=policy)
        b = oracle.evaluate(facts, reuse=False)
        equal = a.evidence == b.evidence
        calls += a.evaluated
        baseline += b.evaluated
        matches += equal
        accepted += a.verified
        rows.append({"input": digest(facts), "match": equal, "verified": a.verified,
                     "candidate_checks": a.evaluated, "oracle_checks": b.evaluated})
    return {"cases": len(scenarios), "matches": matches, "verified": accepted,
            "checks": calls, "baseline_checks": baseline, "rows": rows}


def search():
    policies = generate()
    if len(policies) > MAX_POLICIES:
        raise ValueError("candidate budget exceeded")
    candidates = []
    # Only development cases influence selection. Transfer is evaluated once
    # on the selected policy, not used to choose an alternative.
    for policy in policies:
        result = compare(policy, SCENARIOS)
        candidates.append({"policy": sorted(policy), "development": result})
    eligible = [c for c in candidates
                if c["development"]["matches"] == len(SCENARIOS)]
    if len(eligible) != len(candidates):
        raise RuntimeError("a policy changed mandatory verification outcomes")
    selected = min(eligible, key=lambda c: (c["development"]["checks"], len(c["policy"]), c["policy"]))
    validation = compare(frozenset(selected["policy"]), transfer())
    if validation["matches"] != TRANSFER_STEPS:
        raise RuntimeError("selected policy failed transfer")
    if selected["development"]["checks"] >= selected["development"]["baseline_checks"]:
        raise RuntimeError("no demonstrated development gain")
    return {"scope": "synthetic only", "candidates": candidates,
            "selected": selected["policy"], "development": selected["development"],
            "transfer": validation, "promotion": "BLOCKED"}


if __name__ == "__main__":
    # Report contains hashes and synthetic metrics only.
    print(json.dumps(search(), sort_keys=True))
