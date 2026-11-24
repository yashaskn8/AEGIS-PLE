"""Validate historical quality observations and downloaded educational archives.

Caller-supplied digests must come from separately observed GitHub metadata/logs.
Repository-local anchors are regression fixtures, not independent release authority.
No artifact is extracted or executed by this verifier.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
from typing import Any
from zipfile import ZIP_STORED, BadZipFile, ZipFile

MAX_ARCHIVE = 9 * 1024 * 1024
MANIFEST = "distribution-manifest.json"


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def hex_digest(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def safe_path(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and str(path) == name and name != "." \
        and ".." not in path.parts and "\\" not in name and ":" not in name and "\x00" not in name


@dataclass(frozen=True)
class Binding:
    commit: str
    run: int
    job: int
    tests: int
    record_sha256: str
    steps: tuple[str, ...]
    workflow_policy_sha256: str | None = None


def validate(record: dict[str, Any], binding: Binding) -> None:
    require(hex_digest(binding.commit, 40) and hex_digest(binding.record_sha256), "invalid binding")
    require(all(type(x) is int and x > 0 for x in (binding.run, binding.job, binding.tests)),
            "invalid numeric binding")
    require(bool(binding.steps) and len(set(binding.steps)) == len(binding.steps), "invalid step policy")
    require(digest(record) == binding.record_sha256, "archive differs from observed record")
    require(record.get("scope") == "synthetic educational only" and record.get("promotion") == "BLOCKED",
            "unexpected scope or promotion")
    require(record.get("commit") == binding.commit and record.get("run_id") == binding.run
            and record.get("job_id") == binding.job and record.get("tests") == binding.tests,
            "wrong run identity")
    steps = record["steps"]
    require(tuple(s["name"] for s in steps) == binding.steps, "mandatory step inventory mismatch")
    require(all(s["status"] == "completed" and s["conclusion"] == "success" for s in steps),
            "mandatory step did not pass")
    require(tuple(record["mandatory_steps"]) == binding.steps[4:-2], "mandatory policy mismatch")
    reports = record["reports"]
    expected_reports = {"synthetic checkout fingerprint", "targeted synthetic mutation gate",
                        "verified synthetic source distribution"}
    if "Validate exact workflow policy" in binding.steps:
        expected_reports.add("synthetic workflow preflight")
        require(hex_digest(binding.workflow_policy_sha256), "missing trusted workflow digest")
    else:
        require(binding.workflow_policy_sha256 is None, "unexpected workflow digest")
    require(set(reports) == expected_reports, "missing or unexpected reports")
    if "synthetic workflow preflight" in expected_reports:
        preflight = reports["synthetic workflow preflight"]
        require(preflight["policy_sha256"] == binding.workflow_policy_sha256
                and type(preflight["steps"]) is int and preflight["steps"] == len(binding.steps) - 3,
                "workflow preflight mismatch")
    checkout = reports["synthetic checkout fingerprint"]
    package = reports["verified synthetic source distribution"]
    require(checkout["commit"] == package["commit"] == binding.commit, "stale report")
    require(all(r["scope"] == name and r["promotion"] == "BLOCKED" for name, r in reports.items()),
            "incorrect report scope")
    files = checkout["files"]
    require(bool(files) and all(safe_path(p) and hex_digest(v["sha256"]) and
            type(v["bytes"]) is int and v["bytes"] >= 0 for p, v in files.items()), "invalid file inventory")
    require(digest(files) == checkout["tree_digest"] and package["files"] == len(files), "inconsistent inventory")
    require(package["reproducible"] is True and package["extracted_test_gate"] == "passed"
            and hex_digest(package["sha256"]) and type(package["bytes"]) is int
            and 0 < package["bytes"] <= MAX_ARCHIVE, "invalid package evidence")
    mutation = reports["targeted synthetic mutation gate"]
    rows = mutation["rows"]
    require(len(rows) == mutation["killed"] == mutation["mutants"] > 0
            and len({r["mutation"] for r in rows}) == len(rows), "mutation inventory mismatch")
    for row in rows:
        baseline = {"run": 1, "failures": [], "errors": [], "skipped": 0,
                    "expected_failures": 0, "unexpected_successes": 0}
        require(row["baseline"] == baseline and row["mutant"] == dict(baseline, failures=[row["test"]])
                and hex_digest(row["source_sha256"]), "mutation did not fail designated assertion")
    artifact = record["artifact"]
    require(artifact["head_sha"] == binding.commit and artifact["expired"] is False
            and artifact["name"] == "aegis-educational-" + binding.commit
            and type(artifact["id"]) is int and artifact["id"] > 0
            and type(artifact["size_in_bytes"]) is int and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE
            and isinstance(artifact["digest"], str) and artifact["digest"].startswith("sha256:")
            and hex_digest(artifact["digest"][7:]), "invalid artifact metadata")


def verify_download(raw: bytes, *, commit: str, outer_sha: str, inner_sha: str,
                    tree_digest: str) -> dict[str, Any]:
    require(hex_digest(commit, 40) and all(hex_digest(v) for v in (outer_sha, inner_sha, tree_digest)),
            "invalid artifact anchors")
    require(len(raw) <= MAX_ARCHIVE and sha256(raw).hexdigest() == outer_sha, "outer artifact mismatch")
    try:
        with ZipFile(BytesIO(raw)) as outer:
            require(outer.namelist() == ["aegis-educational.zip"], "unexpected outer members")
            require(outer.infolist()[0].file_size <= MAX_ARCHIVE, "outer expansion limit")
            inner = outer.read("aegis-educational.zip")
        require(sha256(inner).hexdigest() == inner_sha, "inner archive mismatch")
        with ZipFile(BytesIO(inner)) as archive:
            entries = archive.infolist()
            names = archive.namelist()
            require(len(names) == len(set(names)) and MANIFEST in names and len(names) <= 1024,
                    "duplicate, missing or excessive members")
            require(all(safe_path(i.filename) and i.compress_type == ZIP_STORED
                        and i.external_attr >> 16 == 0o100644 for i in entries)
                    and sum(i.file_size for i in entries) <= MAX_ARCHIVE, "unsafe inner members")
            manifest = json.loads(archive.read(MANIFEST))
            files = {n: {"sha256": sha256(data).hexdigest(), "bytes": len(data)}
                     for n in names if n != MANIFEST for data in [archive.read(n)]}
        require(manifest == {"scope": "synthetic educational source only", "commit": commit,
                             "files": {k: v["sha256"] for k, v in files.items()}, "promotion": "BLOCKED"},
                "manifest mismatch")
        require(bool(files) and digest(files) == tree_digest, "downloaded tree mismatch")
    except (BadZipFile, RuntimeError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid artifact") from exc
    return {"commit": commit, "files": len(files), "outer_sha256": outer_sha,
            "inner_sha256": inner_sha, "tree_digest": tree_digest, "promotion": "BLOCKED"}
