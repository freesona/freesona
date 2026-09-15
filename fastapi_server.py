#!/usr/bin/env python3

# fastapi_server.py: FastAPI endpoints for health checks and webhooks.

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from utils.config import configuration_summary, load_config, update_config_value
from utils.knowledge_base import KnowledgeBaseService
from utils.modules import OPTIONAL_MODULES, load_enabled_modules, normalized_module_name, save_module_state
from utils.config import save_config

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


def _admin_token() -> str:
    """Return the configured dashboard token without exposing it in responses."""
    return str(load_config().get("admin_api_token", ""))


def _require_admin(authorization: str | None) -> None:
    """Require a configured bearer token for administrative endpoints."""
    token = _admin_token()
    scheme, _, supplied = authorization.partition(" ") if authorization else ("", "", "")
    if scheme.lower() != "bearer":
        supplied = ""
    if not token or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Admin authentication required")





@app.get("/")

async def root():

    return {"status": "ok"}





@app.get("/health")

@app.get("/health/")

async def health():

    return {"status": "ok"}


@app.get("/admin/status")
async def admin_status(authorization: str | None = Header(default=None)):
    """Return a redacted runtime summary for authenticated administrators."""
    _require_admin(authorization)
    config = load_config()
    return {
        "status": "ok",
        "provider": config.get("provider"),
        "provider_model": config.get("provider_model"),
        "admin_api_token_configured": bool(_admin_token()),
    }


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(authorization: str | None = Header(default=None)):
    """Render a minimal authenticated administration landing page."""
    _require_admin(authorization)
    return "<html><body><h1>Freesona administration</h1><p>Use the /admin API routes to manage this instance.</p></body></html>"


@app.get("/admin/config")
async def admin_config(authorization: str | None = Header(default=None)):
    """Return a redacted configuration summary."""
    _require_admin(authorization)
    return configuration_summary()


@app.put("/admin/config/{key}")
async def admin_update_config(
    key: str, value: Any, authorization: str | None = Header(default=None)
):
    """Validate and persist one non-secret configuration value."""
    _require_admin(authorization)
    if any(marker in key.lower() for marker in ("token", "key", "secret", "password")):
        raise HTTPException(status_code=403, detail="Sensitive configuration cannot be changed through this route")
    try:
        saved = update_config_value(key, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"key": key, "value": saved}


@app.get("/admin/modules")
async def admin_modules(authorization: str | None = Header(default=None)):
    """Return configured optional module states."""
    _require_admin(authorization)
    return load_enabled_modules(load_config())


@app.put("/admin/modules/{name}")
async def admin_update_module(
    name: str, enabled: bool, authorization: str | None = Header(default=None)
):
    """Persist an optional module state for the next bot reload."""
    _require_admin(authorization)
    key = normalized_module_name(name)
    if key not in OPTIONAL_MODULES:
        raise HTTPException(status_code=422, detail="Unknown module")
    config = load_config()
    save_module_state(config, key, enabled)
    save_config(config)
    return {"name": key, "enabled": enabled, "restart_required": True}


def _knowledge_base_service() -> KnowledgeBaseService:
    """Create the configured structured Knowledge Base service."""
    return KnowledgeBaseService(str(load_config().get("knowledge_base_database", "knowledge.db")))


@app.post("/admin/knowledge")
async def admin_knowledge(
    payload: dict[str, Any], authorization: str | None = Header(default=None)
):
    """Validate and persist one structured Knowledge Base entry."""
    _require_admin(authorization)
    service = _knowledge_base_service()
    await service.initialize()
    try:
        entry = await service.ingest(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": entry.id, "persona": entry.persona, "revision": entry.revision}


@app.get("/admin/knowledge")
async def admin_list_knowledge(authorization: str | None = Header(default=None)):
    """List structured Knowledge Base records."""
    _require_admin(authorization)
    service = _knowledge_base_service()
    await service.initialize()
    return [entry.__dict__ for entry in await service.list_entries()]


@app.delete("/admin/knowledge/{entry_id}")
async def admin_delete_knowledge(
    entry_id: str, authorization: str | None = Header(default=None)
):
    """Delete one structured Knowledge Base record."""
    _require_admin(authorization)
    service = _knowledge_base_service()
    await service.initialize()
    if not await service.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return {"id": entry_id, "deleted": True}





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

        logger.warning(

            "MVSEP webhook rejected invalid payload from %s", client_host

        )

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

