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
                    logger.warning(
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
