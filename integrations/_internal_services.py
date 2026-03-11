"""Integration-internal service helpers — allowlist gateway.

This is the ONLY approved path for integrations to access backend domain
services.  integrations/** must import services from here, never directly
from domains.* or via va_sdk.

Architecture layers:
    integrations/**  →  _internal_services  →  domains/*/services
    integrations/**  →  va_sdk              →  authoring contracts only
    modules/**       →  va_sdk only          (cannot import from here)

Maintainer note: keep this list minimal and reviewed.  Every addition must
have a clear justification.  No ORM models, no repositories, no infra — only
stateless service classes with well-defined async methods.
"""

from domains.long_running.services.job_service import LongRunningJobService
from domains.native.run_service import NativeRunService as RunService
from domains.lbs.client import get_lbs_client as _get_lbs_client


async def get_lbs_client(user_id, session):
    """Gateway wrapper for LBS client access from integrations."""
    return await _get_lbs_client(user_id, session)

__all__ = [
    "LongRunningJobService",
    "RunService",
    "get_lbs_client",
]
