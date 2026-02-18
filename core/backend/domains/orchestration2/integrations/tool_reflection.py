from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from ..engine.agent_engine import AgentEngine
from ..engine.models.skill import SkillDef

logger = logging.getLogger(__name__)

async def register_and_reflect_integrations(
    user_id: str,
    db_session: AsyncSession,
    engine: AgentEngine,
    dynamic_skills: list[SkillDef]
) -> str:
    """Load integration tools, register them to engine, update skills, and return prompt text."""
    
    integration_tools_text = ""
    
    try:
        from integrations.loader import load_integration_tools
        integration_tools = await load_integration_tools(user_id, db_session)
        
        valid_integrations = []
        for tool_def, tool_impl in integration_tools:
            # Duplicate check: Core tools take precedence
            try:
                engine.get_tool(tool_def.name)
                logger.warning(
                    "Integration tool '%s' skipped (shadows existing core tool)", 
                    tool_def.name
                )
            except Exception:
                # Tool does not exist, safe to register
                engine.register_tool(tool_def, tool_impl)
                valid_integrations.append(tool_def)

        # Dynamic Reflection: Inject valid tools into "operation" skill (default)
        # and build prompt text.
        if valid_integrations:
            # Add to 'operation' skill
            for s in dynamic_skills:
                if s.name == "operation":
                    s.tools.extend([t.name for t in valid_integrations])
            
            # Build prompt text
            lines = ["The following external integration tools are available:\n"]
            for tool in valid_integrations:
                lines.append(f"- {tool.name}: {tool.description}")
                # Optional: Add args schema if helpful, but keeping it brief for now
            integration_tools_text = "\n".join(lines)
                
        logger.info("Registered %d integration tools", len(valid_integrations))
        
    except Exception as e:
        logger.warning("Failed to load integration tools: %s", e)

    return integration_tools_text
