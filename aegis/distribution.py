"""Reproducible source distribution for the offline educational project only."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .quality import inventory, ROOT

MAX_BYTES = 8 * 1024 * 1024


def safe_path(name: str) -> bool:
    p = PurePosixPath(name)
    return (bool(name) and not p.is_absolute() and str(p) == name
            and ".." not in p.parts and "\\" not in name
            and name != "distribution-manifest.json")


def build(files: dict[str, bytes], commit: str) -> bytes:
    if not files or any(not safe_path(name) for name in files):
        raise ValueError("unsafe distribution inventory")
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("distribution size budget")
    manifest = {"scope": "synthetic educational source only", "commit": commit,
                "files": {k: sha256(v).hexdigest() for k, v in sorted(files.items())},
                "promotion": "BLOCKED"}
    members = {**files, "distribution-manifest.json":
               json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()}
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
        for name, content in sorted(members.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def verify(blob: bytes, expected: dict[str, bytes], commit: str) -> dict[str, bytes]:
    if len(blob) > MAX_BYTES + 100_000:
        raise ValueError("archive too large")
    with ZipFile(BytesIO(blob)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected) | {"distribution-manifest.json"}:
            raise ValueError("archive inventory mismatch")
        if any(i.file_size > MAX_BYTES or i.compress_type != ZIP_STORED for i in archive.infolist()):
            raise ValueError("unexpected archive format")
        if sum(i.file_size for i in archive.infolist()) > MAX_BYTES + 100_000:
            raise ValueError("archive uncompressed size budget")
        members = {name: archive.read(name) for name in names}
    manifest = json.loads(members.pop("distribution-manifest.json"))
    if (members != expected or manifest != {"scope": "synthetic educational source only",
            "commit": commit, "files": {k: sha256(v).hexdigest() for k,v in sorted(expected.items())},
            "promotion": "BLOCKED"}):
        raise ValueError("archive evidence mismatch")
    return members


def run(destination: Path) -> dict:
    checkout = inventory()
    source = {name: (ROOT / name).read_bytes() for name in checkout["files"]}
    if any(sha256(raw).hexdigest() != checkout["files"][name]["sha256"] for name,raw in source.items()):
        raise RuntimeError("source changed during build")
    blob = build(source, checkout["commit"])
    if blob != build(dict(reversed(list(source.items()))), checkout["commit"]):
        raise RuntimeError("nonreproducible package")
    members = verify(blob, source, checkout["commit"])
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch)
        for name, content in members.items():
            if not safe_path(name):
                raise ValueError("unsafe extraction path")
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        # Run the complete mandatory suite from the reconstructed archive.
        result = subprocess.run([sys.executable, "-B", "-m", "aegis.ci"],
            cwd=target, env={**os.environ,"PYTHONPATH":""}, capture_output=True,
            text=True, timeout=60, check=False)
        if result.returncode or "Mandatory synthetic test gate VERIFIED" not in result.stdout:
            raise RuntimeError("extracted distribution verification failed: " + result.stderr[-4000:])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(blob)
    if destination.read_bytes() != blob:
        raise RuntimeError("distribution write mismatch")
    return {"scope":"verified synthetic source distribution", "commit":checkout["commit"],
            "sha256":sha256(blob).hexdigest(), "bytes":len(blob), "files":len(source),
            "reproducible":True, "extracted_test_gate":"passed", "promotion":"BLOCKED"}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m aegis.distribution OUTPUT.zip")
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
