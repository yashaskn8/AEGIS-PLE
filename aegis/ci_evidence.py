"""Validate a controller-collected historical synthetic CI record.

Not an authentication mechanism: only a caller that independently fetched
GitHub metadata can establish the trusted provenance. A repository-local
record never authorizes release. Historical evidence is not current CI.
"""
import json
from pathlib import Path
import re

REQUIRED_STEPS = (
    "Set up job",
    "Run actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    "Record candidate and interpreter",
    "Install hash-pinned loopback dependency",
    "Run fail-closed synthetic checks",
    "Run bounded synthetic experiment",
    "Compare dependency verification with full recomputation",
    "Generate and compare bounded verification policies",
    "Post Run actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    "Complete job",
)


def require(condition, message):
    if condition is not True:
        raise ValueError(message)


def validate(record, *, expected_commit, expected_run, expected_tests):
    require(type(expected_commit) is str and re.fullmatch("[0-9a-f]{40}", expected_commit) is not None,
            "invalid independently supplied commit")
    require(type(expected_run) is int and expected_run > 0 and
            type(expected_tests) is int and expected_tests > 0, "invalid expected CI identity")
    require(record["schema"] == 1 and record["scope"] == "synthetic only", "record schema")
    require(record["promotion"] == "BLOCKED", "promotion must remain blocked")
    run = record["run"]
    require(record["commit"] == run["head_sha"] == expected_commit, "stale commit")
    require(run["id"] == expected_run, "wrong CI run")
    require(run["name"] == "Synthetic CI" and run["path"] == ".github/workflows/ci.yml"
            and run["head_branch"] == "main" and run["event"] == "push", "wrong workflow")
    require(run["status"] == "completed" and run["conclusion"] == "success", "unsuccessful run")
    require(record["tests"] == expected_tests, "mandatory test inventory mismatch")
    jobs = record["jobs"]
    require(type(jobs) is list and len(jobs) == 1, "unexpected job inventory")
    job = jobs[0]
    require(job["name"] == "verification" and job["status"] == "completed"
            and job["conclusion"] == "success", "unsuccessful verification job")
    steps = job["steps"]
    require(tuple(s["name"] for s in steps) == REQUIRED_STEPS, "missing, duplicate or unexpected step")
    require(all(s["status"] == "completed" and s["conclusion"] == "success" for s in steps),
            "incomplete or unsuccessful mandatory step")
    report = record["policy_report"]
    require(report["scope"] == "synthetic only" and report["promotion"] == "BLOCKED",
            "incorrect report scope")
    candidates = report["candidates"]
    require(len(candidates) == 16 and len({tuple(c["policy"]) for c in candidates}) == 16,
            "candidate inventory mismatch")

    def metrics(section, count):
        rows = section["rows"]
        require(len(rows) == count and section["cases"] == count, "case inventory mismatch")
        require(all(row["match"] is True for row in rows), "verification mismatch")
        require(all(type(row["verified"]) is bool and
                    type(row["candidate_checks"]) is int and type(row["oracle_checks"]) is int and
                    0 <= row["candidate_checks"] <= row["oracle_checks"] <= 4 for row in rows),
                "invalid observation")
        require(section["matches"] == count and
                section["verified"] == sum(row["verified"] for row in rows) and
                section["checks"] == sum(row["candidate_checks"] for row in rows) and
                section["baseline_checks"] == sum(row["oracle_checks"] for row in rows),
                "inconsistent metrics")
    for candidate in candidates:
        metrics(candidate["development"], 7)
    metrics(report["development"], 7)
    metrics(report["transfer"], 32)
    winner = min(candidates, key=lambda c: (c["development"]["checks"], len(c["policy"]), c["policy"]))
    require(winner["policy"] == report["selected"] and winner["development"] == report["development"],
            "selection does not match observed candidates")
    return {"status": "VERIFIED_HISTORICAL_RECORD", "commit": expected_commit,
            "run": expected_run, "tests": expected_tests, "promotion": "BLOCKED"}


def replay(path, *, expected_commit, expected_run, expected_tests):
    return validate(json.loads(Path(path).read_text()), expected_commit=expected_commit,
                    expected_run=expected_run, expected_tests=expected_tests)
