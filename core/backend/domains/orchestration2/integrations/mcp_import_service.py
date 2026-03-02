"""MCP (Model Context Protocol) server management service.

Handles connecting to MCP servers via SSE/HTTP, syncing their tool lists,
and persisting the results to tool_registry.

API:
  sync_mcp_server(user_id, server_name, db) -> MCPSyncResult
  delete_mcp_server(user_id, server_name, db)
  list_mcp_servers(user_id, db) -> list[dict]
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class MCPSyncResult:
    ok: bool
    tool_names: list[str] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def success(cls, tool_names: list[str]) -> "MCPSyncResult":
        return cls(ok=True, tool_names=tool_names)

    @classmethod
    def fail(cls, reason: str) -> "MCPSyncResult":
        return cls(ok=False, error=reason)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def sync_mcp_server(
    user_id: str,
    server_name: str,
    db: AsyncSession,
) -> MCPSyncResult:
    """Connect to an MCP server, call tools/list, and upsert tool_registry rows.

    The server config (URL, headers) must already exist in mcp_server_configs.
    After syncing, tool_registry rows with origin_type='mcp', origin_id=server_name
    are created/updated for each tool.

    Returns MCPSyncResult with the list of synced tool names on success.
    """
    # Load server config
    config_row = await db.execute(
        text("""
            SELECT id, url, headers FROM mcp_server_configs
            WHERE user_id = :user_id AND name = :name
        """),
        {"user_id": user_id, "name": server_name},
    )
    config = config_row.fetchone()
    if config is None:
        return MCPSyncResult.fail(f"MCP server '{server_name}' not found")

    url: str = config.url
    headers: dict = config.headers or {}

    # Connect and list tools
    try:
        from mcp.client.sse import sse_client
        from mcp import ClientSession

        async with sse_client(url=url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
    except Exception as exc:
        # Record sync error and return failure
        await db.execute(
            text("""
                UPDATE mcp_server_configs
                SET sync_error = :err, updated_at = :now
                WHERE user_id = :user_id AND name = :name
            """),
            {"err": str(exc), "now": datetime.utcnow(), "user_id": user_id, "name": server_name},
        )
        await db.commit()
        logger.warning("MCP sync failed for server '%s': %s", server_name, exc)
        return MCPSyncResult.fail(f"Connection failed: {exc}")

    # Delete stale tools for this server before re-inserting
    await db.execute(
        text("""
            DELETE FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'mcp' AND origin_id = :name
        """),
        {"user_id": user_id, "name": server_name},
    )

    # Upsert tools
    now = datetime.utcnow()
    tool_names: list[str] = []
    for tool in tools_result.tools:
        tool_name = tool.name
        description = tool.description or ""
        params_schema = tool.inputSchema or {}

        vh = hashlib.sha256(
            json.dumps({"name": tool_name, "description": description}, sort_keys=True).encode()
        ).hexdigest()[:16]

        await db.execute(
            text("""
                INSERT INTO tool_registry
                    (id, user_id, name, description, params_schema,
                     origin_type, origin_id, status, is_active,
                     version_hash, activated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :name, :description,
                     CAST(:params AS JSON),
                     'mcp', :server_name, 'active', TRUE,
                     :vh, :now, :now, :now)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    description   = EXCLUDED.description,
                    params_schema = EXCLUDED.params_schema,
                    origin_type   = 'mcp',
                    origin_id     = EXCLUDED.origin_id,
                    status        = 'active',
                    is_active     = TRUE,
                    version_hash  = EXCLUDED.version_hash,
                    updated_at    = EXCLUDED.updated_at
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": tool_name,
                "description": description,
                "params": json.dumps(params_schema),
                "server_name": server_name,
                "vh": vh,
                "now": now,
            },
        )
        tool_names.append(tool_name)

    # Update last_synced_at and clear any previous error
    await db.execute(
        text("""
            UPDATE mcp_server_configs
            SET last_synced_at = :now, sync_error = NULL, updated_at = :now
            WHERE user_id = :user_id AND name = :name
        """),
        {"now": now, "user_id": user_id, "name": server_name},
    )

    await db.commit()
    logger.info("Synced MCP server '%s' for user %s: %d tools", server_name, user_id, len(tool_names))
    return MCPSyncResult.success(tool_names)


async def delete_mcp_server(user_id: str, server_name: str, db: AsyncSession) -> None:
    """Delete an MCP server config and all its tools.

    Raises ValueError if the server does not exist.
    """
    result = await db.execute(
        text("""
            SELECT 1 FROM mcp_server_configs
            WHERE user_id = :user_id AND name = :name
        """),
        {"user_id": user_id, "name": server_name},
    )
    if result.fetchone() is None:
        raise ValueError(f"MCP server '{server_name}' not found")

    # Delete tools
    await db.execute(
        text("""
            DELETE FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'mcp' AND origin_id = :name
        """),
        {"user_id": user_id, "name": server_name},
    )
    # Delete server config
    await db.execute(
        text("""
            DELETE FROM mcp_server_configs
            WHERE user_id = :user_id AND name = :name
        """),
        {"user_id": user_id, "name": server_name},
    )
    await db.commit()
    logger.info("Deleted MCP server '%s' for user %s", server_name, user_id)


async def list_mcp_servers(user_id: str, db: AsyncSession) -> list[dict]:
    """Return all MCP server configs with their tool counts."""
    servers_result = await db.execute(
        text("""
            SELECT id, name, display_name, url, headers, is_active,
                   last_synced_at, sync_error, created_at, updated_at
            FROM mcp_server_configs
            WHERE user_id = :user_id
            ORDER BY name
        """),
        {"user_id": user_id},
    )
    servers = servers_result.fetchall()

    # Fetch tool counts in one query
    tool_counts_result = await db.execute(
        text("""
            SELECT origin_id, COUNT(*) as cnt
            FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'mcp'
            GROUP BY origin_id
        """),
        {"user_id": user_id},
    )
    tool_counts = {row.origin_id: row.cnt for row in tool_counts_result.fetchall()}

    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "url": s.url,
            "headers": s.headers or {},
            "is_active": s.is_active,
            "last_synced_at": s.last_synced_at,
            "sync_error": s.sync_error,
            "tool_count": tool_counts.get(s.name, 0),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in servers
    ]
