from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_planner_capabilities(skills: list[Any], tool_registry: Any) -> str:
    """Generate a snapshot of available capabilities for the planner."""
    lines = ["## Available Capabilities"]

    # 1. List Skills (name + description)
    if skills:
        lines.append("\n### Skills (High-level groupings)")
        for s in skills:
            name = getattr(s, "name", "")
            desc = getattr(s, "description", "")
            lines.append(f"- **{name}**: {desc}")

    # 2. List Tools by Skill (with optional per-skill instructions)
    lines.append("\n### Tools (Actionable commands)")

    # Map skill -> tools
    skill_tools_map: dict[str, list[str]] = {}
    for s in skills:
        name = getattr(s, "name", "")
        skill_tools_map[name] = list(getattr(s, "tools", []))

    for skill_name, tool_names in skill_tools_map.items():
        if not tool_names:
            continue

        lines.append(f"\n#### Skill: {skill_name}")

        # Inject instructions if the skill has them
        instructions = None
        skill_obj = next((s for s in skills if getattr(s, "name", "") == skill_name), None)
        if skill_obj:
            instructions = getattr(skill_obj, "instructions", None)
        if instructions:
            # Indent each line of instructions for readability
            indented = "\n".join(f"  {l}" for l in instructions.strip().splitlines())
            lines.append(f"  *Instructions:*\n{indented}")

        for t_name in tool_names:
            try:
                tool_def = tool_registry.get_def(t_name)
                desc = tool_def.description.split("\n")[0] if tool_def.description else "No description"
                lines.append(f"- `{t_name}`: {desc}")
            except Exception:
                lines.append(f"- `{t_name}`: (Tool definition not found)")

    return "\n".join(lines)


async def load_prompt_components(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    engine: Any | None = None,
    all_skills: list[Any] | None = None,
) -> dict[str, Any]:
    """Pre-load all data needed by ProjectRole.build_prompt().

    Returns a dict of metadata keys ready to merge into ctx.metadata.
    """
    result: dict[str, Any] = {}

    # 1. Prompt components (static files)
    try:
        from shared.paths import get_prompts_dir

        prompts_dir = get_prompts_dir()
        components = []
        for comp_name in ["identity", "formatting"]:
            comp_path = prompts_dir / "components" / f"{comp_name}.md"
            if comp_path.exists():
                components.append(comp_path.read_text(encoding="utf-8"))
        result["system_prompt_components"] = components
    except Exception as e:
        logger.warning("Failed to load prompt components: %s", e)

    # 2. Agent profile (DB)
    try:
        from shared.database import ProjectAgent

        res = await db.execute(
            select(ProjectAgent).filter(
                ProjectAgent.project_id == project_id,
                ProjectAgent.role_name == "project",
                ProjectAgent.status == "active",
            )
        )
        agent = res.scalars().first()
        if agent and agent.system_prompt:
            result["agent_profile"] = agent.system_prompt
    except Exception as e:
        logger.warning("Failed to load agent profile: %s", e)

    # 3. Project plan (PLAN.md)
    try:
        from shared.paths import get_plan_path

        plan_path = get_plan_path(user_id, project_id)
        if plan_path.exists():
            result["project_plan"] = plan_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("Failed to load project plan: %s", e)

    # 4. User settings
    try:
        from shared.database import UserSettings

        res = await db.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = res.scalars().first()
        if settings and settings.general_settings:
            result["user_settings"] = settings.general_settings
    except Exception as e:
        logger.warning("Failed to load user settings: %s", e)

    # 5. Workspace context (shared items resolved for this project)
    try:
        from domains.workspace.workspace_service import WorkspaceService

        ws_service = WorkspaceService(db, user_id)
        ws_items = await ws_service.resolve_context(project_id)
        if ws_items:
            lines = ["## Shared Workspace Context\n"]
            for item in ws_items:
                item_type = getattr(item, "item_type", "note") or "note"
                if item_type == "directory":
                    # Directories are structural; skip injecting them directly
                    continue
                lines.append(f"### {item.title}  (`{item.path}`, type: {item_type}, scope: {item.scope})")
                if item.tags:
                    lines.append(f"*Tags: {', '.join(item.tags)}*")
                if item_type == "file":
                    # Inject file metadata; content is fetched on demand to avoid token bloat
                    size = item.size_bytes or 0
                    size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
                    lines.append(
                        f"*File — MIME: {item.mime_type or 'unknown'}, Size: {size_str}, "
                        f"fetch via GET /api/workspace/files/{item.id}/content*"
                    )
                else:
                    # note: inject inline content
                    if item.content:
                        lines.append(item.content)
                lines.append("")
            result["workspace_context"] = "\n".join(lines)
    except Exception as e:
        logger.warning("Failed to load workspace context: %s", e)

    # 6. Planner capabilities (snapshot)
    if engine and all_skills:
        try:
            caps = _build_planner_capabilities(all_skills, engine.tools)
            result["planner_capabilities"] = caps
            logger.debug(
                "planner_capabilities built successfully (%d chars)", len(caps)
            )
        except Exception as e:
            logger.warning("Failed to build planner capabilities: %s", e)
    else:
        logger.debug(
            "Skipped planner_capabilities: engine=%s, all_skills=%s",
            engine is not None, all_skills is not None,
        )

    return result
