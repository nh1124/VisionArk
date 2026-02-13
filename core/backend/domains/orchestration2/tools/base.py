"""Shared utilities for orchestration2 tools.

These are VisionArk-specific helpers (NOT the protocol — that's in interfaces/tool.py).
Tools import from here for common patterns like extracting metadata, getting API keys, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..engine.models.execution import ExecutionContext, ToolResult
from ..engine.models.message import ToolCallRef
from ..engine.models.tool import ToolDef


def make_result(
    call: ToolCallRef,
    output: str,
    *,
    error: str | None = None,
) -> ToolResult:
    """Convenience builder for ToolResult."""
    return ToolResult(
        tool_name=call.tool_name,
        call_id=call.call_id,
        output=output,
        error=error,
    )


def fail(call: ToolCallRef, message: str) -> ToolResult:
    """Shorthand for an error ToolResult."""
    return ToolResult(
        tool_name=call.tool_name,
        call_id=call.call_id,
        output=message,
        error=message,
    )


def get_db(ctx: ExecutionContext) -> AsyncSession:
    """Extract db_session from metadata (raises KeyError if missing)."""
    return ctx.metadata["db_session"]


def get_project_id(ctx: ExecutionContext) -> str:
    return ctx.metadata["project_id"]


def get_user_id(ctx: ExecutionContext) -> str:
    return ctx.metadata["user_id"]


async def get_user_api_key(ctx: ExecutionContext) -> str | None:
    """Fetch the user's Gemini API key from UserSettings."""
    db = get_db(ctx)
    user_id = get_user_id(ctx)
    try:
        from shared.database import UserSettings

        res = await db.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = res.scalars().first()
        return settings.gemini_api_key if settings else None
    except Exception:
        return None


async def get_gemini_client(ctx: ExecutionContext) -> Any:
    """Get a google-genai Client using the user's API key."""
    from google.genai import Client

    key = await get_user_api_key(ctx)
    if not key:
        raise ValueError("No Gemini API key configured")
    return Client(api_key=key, http_options={"api_version": "v1alpha"})


async def resolve_artifacts_dir(ctx: ExecutionContext) -> Path:
    """Resolve the project artifacts directory."""
    from shared.paths import get_project_dir

    user_id = get_user_id(ctx)
    project_id = get_project_id(ctx)
    d = get_project_dir(user_id, project_id) / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def get_file_service(ctx: ExecutionContext) -> Any:
    """Get a FileService instance for the current user."""
    from domains.workspace.file_service import FileService

    db = get_db(ctx)
    user_id = get_user_id(ctx)
    key = await get_user_api_key(ctx)
    return FileService(db, user_id, api_key=key)
