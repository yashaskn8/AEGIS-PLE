"""End-to-end fictional inventory reporting. Not a competition harness.

All paths and input types are controller-owned. No network model access,
candidate code execution, task-specific benchmark logic or real-world designs.
"""
from hashlib import sha256
import json

from .aggregation import Fixture, aggregate_first
from .firewall import State, assess
from .protocol import Cancelled, Session, WireError, decode

INPUT = "measurements.json"
OUTPUT = "report.json"
MAX_INPUT = 8192


def build_report(raw: bytes) -> bytes:
    if len(raw) > MAX_INPUT:
        raise ValueError("synthetic input too large")
    data = decode(raw.decode("utf-8"))
    if set(data) != {"micrometres"} or type(data["micrometres"]) is not list:
        raise ValueError("unexpected synthetic input")
    source_hash = sha256(raw).hexdigest()
    fixture = Fixture(source_hash, tuple(data["micrometres"]))
    result = aggregate_first(fixture.micrometres)
    proof = assess(aggregate_first, fixture)
    if proof.state is not State.VERIFIED:
        raise ValueError("calculation verification failed")
    # Bind the exact report candidate to the independently observed output.
    from .firewall import digest
    if any(e.output != digest(result) for e in proof.evidence):
        raise ValueError("candidate output changed between executions")
    report = {"scope": "synthetic only", "source_sha256": source_hash,
              "count": len(fixture.micrometres), **result,
              "verification": [e.requirement for e in proof.evidence]}
    return json.dumps(report, sort_keys=True, separators=(",", ":")).encode()


async def run_session(transport):
    session = Session(transport)
    verified = False
    try:
        await session.start()
        raw = await session.read(INPUT)
        report = build_report(raw)
        await session.write(OUTPUT, report)
        observed = await session.read(OUTPUT)
        if observed != report:
            raise WireError("readback differs from verified report")
        # A changed source invalidates the report even when its values happen to match.
        if await session.read(INPUT) != raw:
            raise WireError("source changed during report generation")
        verified = True
        await session.finish("Synthetic report.json written and read back; source hash verified.")
    except Cancelled:
        await session.finish("Cancelled; report verification incomplete." if not verified
                             else "Cancelled after synthetic report verification.")
    except (WireError, ValueError, UnicodeError, TypeError):
        if not session.terminal:
            await session.finish("Synthetic verification failed; output is not accepted.", failed=True)
