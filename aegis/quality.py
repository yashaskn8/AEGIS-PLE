"""Deterministic clean-checkout integrity and bounded test-effectiveness gates.

Only fixed, trusted source mutations are exercised in temporary copies.
No candidate-generated code or official benchmark task data is used.
A fingerprint is evidence of this checkout, not protected authorization.
"""
from dataclasses import dataclass
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    old: str
    new: str
    test: str


MUTATIONS = (
    Mutation("contradictory_evidence", "aegis/firewall.py",
             "if record.state is not State.VERIFIED or record.expected != record.actual:",
             "if record.state is not State.VERIFIED:",
             "tests.test_constraints.Constraints.test_contradictory_evidence"),
    Mutation("ignore_worker_veto", "aegis/deterministic_route.py",
             "if not verify_in_process(manifest, required, documents, proposal):",
             "if False and not verify_in_process(manifest, required, documents, proposal):",
             "tests.test_deterministic.Deterministic.test_worker_veto"),
    Mutation("skip_conflict_rejection", "aegis/documents.py",
             'reasons.add("conflicting_fact:" + key)',
             'pass  # intentional synthetic mutation',
             "tests.test_documents.Documents.test_conflicting_provenance"),
    Mutation("skip_usage_model_lock", "aegis/protocol.py",
             'if getattr(self, "_usage_model", profile.model) != profile.model:',
             'if False:',
             "tests.test_extensions.Extensions.test_usage"),
)


def fingerprint(data):
    return sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=15)


def secret_findings(path, raw):
    """Narrow high-confidence credential patterns; not a complete secret scanner."""
    name = Path(path).name
    if name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".p12", ".key")):
        return ["credential_file"]
    patterns = {
        "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
        "github_token": rb"(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})",
        "google_api_key": rb"AIza[0-9A-Za-z_-]{35}",
        "openai_project_key": rb"sk-proj-[A-Za-z0-9_-]{40,}",
        "aws_access_key": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    }
    return [name for name, regex in patterns.items() if re.search(regex, raw)]


def inventory(root=ROOT):
    root = Path(root)
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    expected = os.environ.get("GITHUB_SHA")
    if expected is not None and expected != commit:
        raise RuntimeError("checkout commit mismatch")
    if git(root, "status", "--porcelain", "--untracked-files=normal").strip():
        raise RuntimeError("working tree must be clean")
    entries = git(root, "ls-files", "-z").decode("utf-8").split("\0")
    paths = [p for p in entries if p]
    if not paths or len(paths) != len(set(paths)):
        raise RuntimeError("invalid tracked inventory")
    records = {}
    for path in sorted(paths):
        file = root / path
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("unsupported tracked file: " + path)
        raw = file.read_bytes()
        if secret_findings(path, raw):
            raise RuntimeError("potential credential in tracked file: " + path)
        if path.endswith(".py"):
            compile(raw, path, "exec")
        records[path] = {"sha256": fingerprint(raw), "bytes": len(raw)}
    locked = importlib.metadata.version("websockets")
    if locked != "15.0.1":
        raise RuntimeError("dependency version mismatch")
    return {"scope":"synthetic checkout fingerprint", "commit":commit,
            "python":platform.python_version(), "platform":platform.platform(),
            "websockets":locked, "files":records,
            "tree_digest":fingerprint(json.dumps(records,sort_keys=True,separators=(",",":")).encode()),
            "promotion":"BLOCKED"}


def apply_mutation(source, mutation):
    if source.count(mutation.old) != 1:
        raise ValueError("mutation anchor must occur exactly once")
    modified = source.replace(mutation.old, mutation.new, 1)
    compile(modified, mutation.path, "exec")
    return modified


def test_outcome(root, test):
    # Run one declared test in a fresh interpreter; inspect structured result
    # rather than treating any nonzero exit (including import error) as a kill.
    driver = (
        "import json,unittest,sys;"
        "suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[1]);"
        "r=unittest.TextTestRunner(verbosity=0).run(suite);"
        "print(json.dumps({'run':r.testsRun,'failures':[t.id() for t,_ in r.failures],"
        "'errors':[t.id() for t,_ in r.errors],'skipped':len(r.skipped),"
        "'expected_failures':len(r.expectedFailures),'unexpected_successes':len(r.unexpectedSuccesses)}))"
    )
    result = subprocess.run([sys.executable, "-B", "-c", driver, test],
                            cwd=root, capture_output=True, timeout=15, check=True,
                            env={**os.environ, "PYTHONPATH":""})
    return json.loads(result.stdout)


def classify(outcome, test, *, mutant):
    return (outcome == {"run":1,"failures":[test] if mutant else [],
                        "errors":[],"skipped":0,"expected_failures":0,"unexpected_successes":0})


def mutation_gate(root=ROOT):
    root = Path(root)
    rows = []
    for mutation in MUTATIONS:
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)
            for name in ("aegis","tests"):
                shutil.copytree(root/name,target/name,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
            before = test_outcome(target,mutation.test)
            if not classify(before,mutation.test,mutant=False):
                raise RuntimeError("baseline test did not pass: " + mutation.name)
            file = target / mutation.path
            original = file.read_text()
            file.write_text(apply_mutation(original,mutation))
            after = test_outcome(target,mutation.test)
            if not classify(after,mutation.test,mutant=True):
                raise RuntimeError("mutation not killed by expected assertion: " + mutation.name)
            rows.append({"mutation":mutation.name,"test":mutation.test,
                         "source_sha256":fingerprint(original.encode()),
                         "baseline":before,"mutant":after})
    return {"scope":"targeted synthetic mutation gate","mutants":len(rows),
            "killed":len(rows),"rows":rows,"promotion":"BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(inventory(),sort_keys=True))
    print(json.dumps(mutation_gate(),sort_keys=True))
