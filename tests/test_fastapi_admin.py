"""Tests for FastAPI administrative authorization and delegation."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import fastapi_server


def test_admin_requires_bearer_scheme_and_valid_token():
    """Reject absent, raw, and invalid administrative credentials."""
    with patch("fastapi_server._admin_token", return_value="secret"):
        for authorization in (None, "secret", "Bearer wrong"):
            with pytest.raises(HTTPException) as error:
                fastapi_server._require_admin(authorization)
            assert error.value.status_code == 401
        fastapi_server._require_admin("Bearer secret")


@pytest.mark.asyncio
async def test_admin_status_redacts_sensitive_configuration():
    """Expose only the documented status fields after authorization."""
    with (
        patch("fastapi_server._admin_token", return_value="secret"),
        patch("fastapi_server.load_config", return_value={"provider": "test", "provider_model": "model", "api_key": "hidden"}),
    ):
        response = await fastapi_server.admin_status("Bearer secret")
    assert response == {
        "status": "ok",
        "provider": "test",
        "provider_model": "model",
        "admin_api_token_configured": True,
    }


@pytest.mark.asyncio
async def test_admin_knowledge_rejects_invalid_entries_before_persistence():
    """Translate structured Knowledge Base validation into an HTTP error."""
    with patch("fastapi_server._admin_token", return_value="secret"):
        with pytest.raises(HTTPException) as error:
            await fastapi_server.admin_knowledge({}, "Bearer secret")
    assert error.value.status_code == 422