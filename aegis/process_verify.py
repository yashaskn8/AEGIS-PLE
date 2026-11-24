"""Fixed-script process boundary for data-only synthetic proposals."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

WORKER = Path(__file__).resolve().with_name("document_worker.py")


def verify_in_process(manifest, required, documents, proposal, *, timeout=1.0):
    if type(timeout) not in (float, int) or not 0 < timeout <= 2:
        return False
    try:
        request = json.dumps({"manifest": manifest, "required": required,
            "documents": [base64.b64encode(d).decode() for d in documents],
            "proposal": proposal}, allow_nan=False, separators=(",", ":")).encode()
        if len(request) > 500000:
            return False
        with TemporaryDirectory() as scratch:
            proc = subprocess.run([sys.executable, "-I", "-S", "-B", str(WORKER)],
                input=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=scratch, env={}, timeout=timeout, check=False)
        if proc.returncode != 0 or len(proc.stdout) > 256 or proc.stderr:
            return False
        result = json.loads(proc.stdout)
        return (type(result) is dict and set(result) == {"accepted","request_sha256"}
                and result["accepted"] is True
                and result["request_sha256"] == sha256(request).hexdigest())
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, RecursionError):
        return False
