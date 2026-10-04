#!/usr/bin/env python3

# fastapi_server.py: FastAPI endpoints for health checks and webhooks.

import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

from utils.config import load_config
from utils.knowledge_base import KnowledgeBaseService, validate_entry

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


def _admin_token() -> str | None:
    """Return the configured token for administrative HTTP endpoints."""
    token = os.getenv("ADMIN_API_TOKEN", "").strip()
    return token or None


def _require_admin(authorization: str | None) -> None:
    """Require a valid Bearer token for administrative endpoints."""
    configured_token = _admin_token()
    supplied_token = ""
    if authorization and authorization.startswith("Bearer "):
        supplied_token = authorization.removeprefix("Bearer ").strip()

    if not configured_token or not secrets.compare_digest(
        supplied_token, configured_token
    ):
        raise HTTPException(
            status_code=401, detail="Invalid administrative credentials"
        )


@app.get("/admin/status")
async def admin_status(authorization: str | None = None) -> dict[str, Any]:
    """Return non-sensitive application configuration for administrators."""
    _require_admin(authorization)
    config = load_config()
    return {
        "status": "ok",
        "provider": config.get("provider"),
        "provider_model": config.get("provider_model"),
        "admin_api_token_configured": _admin_token() is not None,
    }


@app.post("/admin/knowledge")
async def admin_knowledge(
    payload: dict[str, Any], authorization: str | None = None
) -> dict[str, str]:
    """Add a validated knowledge entry through the administrative API."""
    _require_admin(authorization)

    document = payload.get("document")
    metadata = payload.get("metadata")
    if not isinstance(document, str) or not document.strip():
        raise HTTPException(
            status_code=422, detail="document must be a non-empty string"
        )
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="metadata is required")

    entry_data = {**metadata, "content": document}
    if "source" not in entry_data:
        entry_data["source"] = str(payload.get("source", "admin"))
    if payload.get("title") is not None:
        entry_data["title"] = payload["title"]
    try:
        validate_entry(entry_data)
        service = KnowledgeBaseService("knowledge.db")
        await service.initialize()
        entry = await service.ingest(entry_data)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": entry.id}


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

    A valid payload must be a dict containing either a top-level

    or nested 'hash' field.

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
