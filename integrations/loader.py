import importlib
import logging
import pkgutil
import asyncio
from pathlib import Path
from typing import Generator, List, Tuple, Any

from sqlalchemy.ext.asyncio import AsyncSession

from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.engine.models.skill import SkillDef
from va_sdk import BaseTool
from .adapter import IntegrationToolAdapter

logger = logging.getLogger(__name__)


async def load_integration_tools(user_id: str, db: AsyncSession) -> List[Tuple[ToolDef, Any]]:
    """Discover and load tools from all available integrations.
    
    Returns:
        List of (ToolDef, ToolImpl) pairs compatible with orchestration2 engine.
    """
    results: List[Tuple[ToolDef, Any]] = []
    
    integrations_dir = Path(__file__).parent

    for item in integrations_dir.iterdir():
        if item.is_dir():
            if item.name.startswith("_") or item.name == "loader" or item.name == "adapter":
                continue

            pkg_name = item.name
            
            # Skip hidden/special directories
            if pkg_name.startswith("_") or pkg_name in ["loader", "adapter"]:
                continue

            agent_tools_path = item / "agent_tools.py"
            if not agent_tools_path.exists():
                continue

            try:
                # Import integrations.{pkg_name} (__init__.py) which defines get_tools()
                # with proper user activation gate (is_active check).
                # Do NOT import agent_tools directly — that bypasses the auth guard.
                module_path = f"integrations.{pkg_name}"
                module = importlib.import_module(module_path)
                
                tools_instances: List[BaseTool] = []

                if hasattr(module, "get_tools"):
                    func = getattr(module, "get_tools")
                    if asyncio.iscoroutinefunction(func):
                        tools_instances = await func(user_id, db)
                    else:
                        tools_instances = func(user_id, db)
                else:
                    # Fallback: scan for tool classes directly.
                    # WARNING: This bypasses the is_active check in get_tools().
                    # All integration packages MUST define get_tools() in __init__.py.
                    logger.error(
                        "Integration '%s' has no get_tools() in __init__.py. "
                        "Falling back to direct class scan — is_active check is SKIPPED.",
                        pkg_name
                    )
                    tools_instances = _scan_module_for_tools(module)

                if tools_instances:
                    logger.info("Loaded %d tools from integration '%s'", len(tools_instances), pkg_name)
                    for tool_instance in tools_instances:
                        if isinstance(tool_instance, BaseTool):
                            adapter = IntegrationToolAdapter(tool_instance)
                            results.append((adapter.definition, adapter))
                
            except Exception as e:
                logger.warning("Failed to load tools from integration '%s': %s", pkg_name, e)

    return results


async def load_integration_skills(
    user_id: str, db: AsyncSession
) -> List[Tuple[SkillDef, str]]:
    """Discover skill definitions from all integrations that expose get_skill_defs().

    Returns:
        List of (SkillDef, origin_id) pairs where origin_id is the integration package name.
    """
    results: List[Tuple[SkillDef, str]] = []

    integrations_dir = Path(__file__).parent

    for item in integrations_dir.iterdir():
        if not item.is_dir():
            continue
        pkg_name = item.name
        if pkg_name.startswith("_") or pkg_name in ["loader", "adapter"]:
            continue

        try:
            module_path = f"integrations.{pkg_name}"
            module = importlib.import_module(module_path)

            if not hasattr(module, "get_skill_defs"):
                continue

            skill_defs = module.get_skill_defs()
            if not skill_defs:
                continue

            for sd in skill_defs:
                if isinstance(sd, SkillDef):
                    results.append((sd, pkg_name))

            logger.info("Loaded %d skill defs from integration '%s'", len(skill_defs), pkg_name)

        except Exception as exc:
            logger.warning(
                "Failed to load skill defs from integration '%s': %s", pkg_name, exc
            )

    return results


async def load_user_custom_tools(
    user_id: str, db: AsyncSession
) -> List[Tuple[ToolDef, Any]]:
    """Load tools uploaded by the user from their custom_tools directory.

    Each sub-directory under data/users/{user_id}/custom_tools/{tool_name}/
    that contains an __init__.py is loaded as a tool package.  The package
    must expose get_tools(user_id, db) returning a list of BaseTool instances.

    Tools are loaded via importlib.util (not from sys.path) so they never
    collide with integration or core packages.
    """
    import importlib.util
    import sys

    results: List[Tuple[ToolDef, Any]] = []

    try:
        from shared.paths import get_user_custom_tools_dir
        custom_tools_dir = get_user_custom_tools_dir(user_id)
    except Exception as exc:
        logger.warning("Could not resolve custom tools dir for user %s: %s", user_id, exc)
        return results

    if not custom_tools_dir.exists():
        return results

    for item in sorted(custom_tools_dir.iterdir()):
        if not item.is_dir():
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        tool_name = item.name
        module_key = f"__user_custom_{user_id}_{tool_name}__"

        try:
            # Re-use cached module if already loaded in this process
            if module_key in sys.modules:
                module = sys.modules[module_key]
            else:
                spec = importlib.util.spec_from_file_location(module_key, init_file)
                if spec is None or spec.loader is None:
                    logger.warning("Could not build spec for user tool '%s'", tool_name)
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_key] = module
                spec.loader.exec_module(module)  # type: ignore[union-attr]

            get_tools_fn = getattr(module, "get_tools", None)
            if get_tools_fn is None:
                logger.warning("User tool '%s' has no get_tools() — skipping", tool_name)
                continue

            if asyncio.iscoroutinefunction(get_tools_fn):
                tool_instances = await get_tools_fn(user_id, db)
            else:
                tool_instances = get_tools_fn(user_id, db)

            if not tool_instances:
                continue

            for tool_instance in tool_instances:
                if isinstance(tool_instance, BaseTool):
                    adapter = IntegrationToolAdapter(tool_instance)
                    results.append((adapter.definition, adapter))

            logger.info(
                "Loaded %d tools from user custom package '%s'",
                len(tool_instances), tool_name,
            )

        except Exception as exc:
            logger.warning(
                "Failed to load user custom tool '%s' for user %s: %s",
                tool_name, user_id, exc,
            )
            sys.modules.pop(module_key, None)

    return results


async def load_mcp_tools(
    user_id: str, db: AsyncSession
) -> List[Tuple[ToolDef, Any]]:
    """Load active MCP tools from tool_registry for this user.

    Queries tool_registry for rows with origin_type='mcp', is_active=True, then
    fetches server config (URL/headers) from mcp_server_configs by origin_id.
    Returns (ToolDef, MCPToolAdapter) pairs — no network calls here.
    """
    from sqlalchemy import text

    results: List[Tuple[ToolDef, Any]] = []

    try:
        # Fetch active MCP tools
        tool_rows = await db.execute(
            text("""
                SELECT t.name, t.description, t.params_schema, t.origin_id,
                       s.url, s.headers
                FROM tool_registry t
                JOIN mcp_server_configs s
                    ON s.user_id = t.user_id AND s.name = t.origin_id
                WHERE t.user_id = :user_id
                  AND t.origin_type = 'mcp'
                  AND t.is_active = TRUE
                  AND s.is_active = TRUE
                ORDER BY t.name
            """),
            {"user_id": user_id},
        )
        rows = tool_rows.fetchall()
    except Exception as exc:
        logger.warning("Failed to query MCP tools for user %s: %s", user_id, exc)
        return results

    if not rows:
        return results

    from .mcp_adapter import MCPToolAdapter

    for row in rows:
        params_schema = row.params_schema or {}
        if isinstance(params_schema, str):
            try:
                import json as _json
                params_schema = _json.loads(params_schema)
            except Exception:
                params_schema = {}

        adapter = MCPToolAdapter(
            server_name=row.origin_id,
            tool_name=row.name,
            description=row.description or "",
            url=row.url,
            headers=row.headers or {},
            input_schema=params_schema,
        )
        results.append((adapter.definition, adapter))

    logger.info("Loaded %d MCP tools for user %s", len(results), user_id)
    return results


def _scan_module_for_tools(module: Any) -> List[BaseTool]:
    """Scan a module for BaseTool subclasses and instantiate them."""
    tools = []
    for name, obj in vars(module).items():
        if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool:
            # Instantiate the tool. Assuming no-arg constructor as per BaseTool pattern.
            try:
                # Some tools might not have a no-arg constructor, but standard BaseTool usually does (pydantic model or simple class)
                # If they require config, they usually take it in `run` via context or kwargs.
                instance = obj()
                tools.append(instance)
            except Exception as e:
                logger.warning("Could not instantiate tool class '%s' in module '%s': %s", name, module.__name__, e)
    return tools
