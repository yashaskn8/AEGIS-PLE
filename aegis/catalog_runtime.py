"""Fictional record retrieval and reporting via a fixed local catalog tool.

Only an explicitly selected synthetic runtime mode can use this path. The
manifest is trusted within this educational fixture, not a real authority.
"""
import asyncio

from .document_runtime import OUTPUT, render_report
from .documents import reconcile, MAX_DOCS
from .mcp_catalog import CatalogSession, valid_lookup
from .protocol import Cancelled, Transport, WireError, decode

INPUT = "inventory_catalog_bundle.json"
MAX_MANIFEST_BYTES = 16384


def parse_bundle(raw):
    if type(raw) is not bytes or len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("invalid catalog bundle size")
    bundle = decode(raw.decode("utf-8"))
    if set(bundle) != {"manifest", "required", "records"} or type(bundle["required"]) is not list:
        raise ValueError("invalid catalog bundle schema")
    manifest, required, records = bundle["manifest"], tuple(bundle["required"]), bundle["records"]
    # Reconcile an empty inventory to validate trusted manifest constraints before calls.
    reconcile(manifest, required, ())
    if type(records) is not list or not 1 <= len(records) <= MAX_DOCS:
        raise ValueError("invalid lookup inventory")
    identities = set()
    descriptors = []
    for item in records:
        if (type(item) is not dict or set(item) != {"record_id", "sha256"}
                or not valid_lookup(item["record_id"], item["sha256"])
                or item["record_id"] in identities):
            raise ValueError("invalid or duplicate lookup binding")
        identities.add(item["record_id"])
        descriptors.append((item["record_id"], item["sha256"]))
    return manifest, required, tuple(descriptors)


async def run_catalog_session(transport: Transport) -> None:
    session = CatalogSession(transport)
    try:
        await session.start()
        raw = await session.read(INPUT)
        manifest, required, descriptors = parse_bundle(raw)
        await session.catalog()
        documents = []
        for record_id, expected in descriptors:
            documents.append(await session.fetch_record(record_id, expected))
        async with asyncio.timeout(session._remaining()):
            report = await asyncio.to_thread(render_report, manifest, required, tuple(documents))
        if await session.read(INPUT) != raw:
            raise WireError("catalog manifest changed before write")
        await session.write(OUTPUT, report)
        if await session.read(OUTPUT) != report or await session.read(INPUT) != raw:
            raise WireError("catalog report or manifest changed")
        await session.finish("Synthetic catalog report written and read back; source hashes verified.")
    except Cancelled:
        await session.finish("Cancelled; catalog report verification incomplete.")
    except (WireError, ValueError, UnicodeError, TypeError, TimeoutError):
        if not session.terminal:
            await session.finish("Synthetic catalog verification failed; output is not accepted.", failed=True)
