"""Loopback-only educational WebSocket server.

This is deliberately not an official PLE entrypoint. A valid submission
requires separate authorization, official integration and validation.
"""
import asyncio
import os

from websockets.asyncio.server import serve

from aegis.protocol import MAX_FRAME
from aegis.synthetic_runtime import run_session
from aegis.document_runtime import run_document_session
from aegis.catalog_runtime import run_catalog_session


async def main():
    port = int(os.environ.get("PORT", "8765"))
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    mode = os.environ.get("AEGIS_SYNTHETIC_MODE", "measurements")
    handlers = {"measurements": run_session, "documents": run_document_session,
                "catalog_documents": run_catalog_session}
    if mode not in handlers:
        raise ValueError("invalid synthetic mode")
    handler = handlers[mode]
    async with serve(handler, "127.0.0.1", port, max_size=MAX_FRAME,
                     ping_interval=None, compression=None) as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
