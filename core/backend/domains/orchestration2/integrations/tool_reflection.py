from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from ..engine.agent_engine import AgentEngine

logger = logging.getLogger(__name__)


async def register_and_reflect_integrations(
    user_id: str,
    db_session: AsyncSession,
    engine: AgentEngine,
) -> str:
    """Load integration tools, register them to engine, and return prompt text.

    Skills are populated from DB (seeded by definition_refresh_service).
    The 'operation' skill is updated via DB refresh rather than per-request
    mutation — operation append was removed in Phase D.
    """
    integration_tools_text = ""

    try:
        from integrations.loader import load_integration_tools, load_user_custom_tools, load_mcp_tools
        integration_tools = await load_integration_tools(user_id, db_session)
        custom_tools = await load_user_custom_tools(user_id, db_session)
        mcp_tools = await load_mcp_tools(user_id, db_session)
        all_tools = integration_tools + custom_tools + mcp_tools

        valid_integrations = []
        for tool_def, tool_impl in all_tools:
            # Core tools take precedence — skip if already registered.
            try:
                engine.get_tool(tool_def.name)
                logger.warning(
                    "Integration tool '%s' skipped (shadows existing core tool)",
                    tool_def.name,
                )
            except Exception:
                engine.register_tool(tool_def, tool_impl)
                valid_integrations.append(tool_def)

        if valid_integrations:
            lines = ["The following external integration tools are available:\n"]
            for tool in valid_integrations:
                lines.append(f"- {tool.name}: {tool.description}")
            integration_tools_text = "\n".join(lines)

        logger.info("Registered %d integration tools", len(valid_integrations))

    except Exception as exc:
        logger.warning("Failed to load integration tools: %s", exc)

    return integration_tools_text
