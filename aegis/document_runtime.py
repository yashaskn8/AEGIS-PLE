"""Loopback-only fictional document reporting over the validated file protocol.

The synthetic peer supplies an explicit manifest and base64 records in a fixed
bundle. Nothing in candidate content chooses paths or invokes tools.
"""
import asyncio
import base64
import binascii

from .deterministic_route import solve
from .documents import reconcile
from .inventory_checks import parse_checks, verify_checks
from .protocol import Session, Cancelled, WireError, decode, encode

INPUT = "inventory_bundle.json"
OUTPUT = "inventory_report.json"
MAX_INPUT = 400_000


def build(raw):
    if type(raw) is not bytes or len(raw) > MAX_INPUT:
        raise ValueError("invalid bundle size")
    payload = decode(raw.decode("utf-8"))
    if (set(payload) not in ({"manifest","required","documents"},
                                {"manifest","required","documents","checks"})
            or type(payload["required"]) is not list
            or type(payload["documents"]) is not list or len(payload["documents"]) > 32):
        raise ValueError("invalid bundle schema")
    documents = tuple(base64.b64decode(d,validate=True) for d in payload["documents"])
    manifest, required = payload["manifest"], tuple(payload["required"])
    reconcile(manifest, required, ())
    plan = parse_checks(payload["checks"], required) if "checks" in payload else ()
    return render_report(manifest, required, documents, plan)


def render_report(manifest, required, documents, plan=()):
    result = solve(manifest, required, documents)
    if result["status"] != "VERIFIED_SYNTHETIC":
        raise WireError("document evidence blocked")
    report = {"scope":"synthetic only","model_calls":0,"report":result["output"]}
    if plan:
        report["count_verification"] = verify_checks(plan, result["output"], documents)
    return encode(report).encode()


async def run_document_session(transport):
    session = Session(transport)
    try:
        await session.start()
        raw = await session.read(INPUT)
        async with asyncio.timeout(session._remaining()):
            output = await asyncio.to_thread(build,raw)
        # Check source before writing and again after reading back output.
        if await session.read(INPUT) != raw:
            raise WireError("source changed before write")
        await session.write(OUTPUT,output)
        if await session.read(OUTPUT) != output:
            raise WireError("output readback mismatch")
        if await session.read(INPUT) != raw:
            raise WireError("source changed after write")
        await session.finish("Synthetic inventory report written and read back; provenance verified.")
    except Cancelled:
        await session.finish("Cancelled; report verification incomplete.")
    except (WireError, ValueError, UnicodeError, TypeError, binascii.Error, TimeoutError):
        if not session.terminal:
            await session.finish("Synthetic document verification failed; output is not accepted.",failed=True)
