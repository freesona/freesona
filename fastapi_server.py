# fastapi_server.py: FastAPI endpoints for health checks and webhooks.
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("FreesonaBot")

_mvsep_jobs: dict[str, asyncio.Future] = {}


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    _ = fastapi_app
    # Startup
    yield
    # Shutdown - clean up pending futures
    for job_hash, future in list(_mvsep_jobs.items()):
        if not future.done():
            future.cancel()
    _mvsep_jobs.clear()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/health")
@app.get("/health/")
async def health():
    return {"status": "ok"}


def register_mvsep_job(job_hash: str, future: asyncio.Future) -> None:
    _mvsep_jobs[job_hash] = future


def unregister_mvsep_job(job_hash: str) -> None:
    _mvsep_jobs.pop(job_hash, None)


def _mvsep_hash(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get("hash") or data.get("job_hash")
    return payload.get("hash") or payload.get("job_hash")


def _is_valid_mvsep_payload(payload: Any) -> bool:
    """
    Validates that the payload looks like a legitimate MVSEP webhook.
    MVSEP sends no auth token, so we validate shape instead.
    A valid payload must be a dict containing either a top-level or nested 'hash' field.
    """
    if not isinstance(payload, dict):
        return False
    return bool(_mvsep_hash(payload))


@app.api_route("/webhooks/mvsep", methods=["GET", "POST"])
async def mvsep_webhook(request: Request):
    if request.method == "GET":
        return {"status": "ok"}

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        logger.info("MVSEP webhook test request received without JSON.")
        return {"status": "ok"}

    if not _is_valid_mvsep_payload(payload):
        client = request.client
        client_host = client.host if client is not None else "unknown"
        logger.warning("MVSEP webhook rejected invalid payload from %s", client_host)
        return Response(status_code=400)

    job_hash = _mvsep_hash(payload)
    if not job_hash:
        return {"status": "ok"}

    future = _mvsep_jobs.get(job_hash)
    if future and not future.done():
        future.set_result(payload)
    else:
        logger.info(f"MVSEP webhook received for unknown job hash: {job_hash}")

    return {"status": "ok"}