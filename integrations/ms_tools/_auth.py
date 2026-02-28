"""Internal Microsoft Graph authentication helper.

Credentials are read from environment variables:
  AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID

A user-delegated token can be passed directly via IntegrationContext.metadata["ms_access_token"].
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, dict] = {}


def get_app_token(scopes: list[str]) -> str | None:
    """Acquire an application-level MS Graph token via client credentials flow."""
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")
    tenant_id = os.environ.get("AZURE_TENANT_ID")

    if not all([client_id, client_secret, tenant_id]):
        logger.debug("Azure credentials not configured; offline-only mode active.")
        return None

    key = f"{client_id}:{','.join(sorted(scopes))}"
    cached = _TOKEN_CACHE.get(key)
    if cached and cached.get("expires_at", 0) > time.time() + 60:
        return cached["access_token"]

    try:
        import msal

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )
        result = app.acquire_token_for_client(scopes=scopes)
        if "access_token" in result:
            _TOKEN_CACHE[key] = {
                "access_token": result["access_token"],
                "expires_at": time.time() + result.get("expires_in", 3600),
            }
            return result["access_token"]
        logger.warning("MSAL error: %s", result.get("error_description", result.get("error")))
    except ImportError:
        logger.warning("msal not installed; run: pip install msal")
    except Exception as exc:
        logger.warning("Token acquisition failed: %s", exc)

    return None


def get_token_from_ctx(ctx: Any, scopes: list[str]) -> str | None:
    """Try injected user token first, then fall back to app credentials."""
    token = ctx.metadata.get("ms_access_token") if ctx.metadata else None
    return token or get_app_token(scopes)


def clear_token_cache() -> None:
    global _TOKEN_CACHE
    _TOKEN_CACHE.clear()
