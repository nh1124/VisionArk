import importlib
import logging
import pkgutil
import asyncio
from pathlib import Path
from typing import Generator, List, Tuple, Any

from sqlalchemy.ext.asyncio import AsyncSession

from domains.orchestration2.engine.models.tool import ToolDef
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
                # Import integrations.{pkg_name}.agent_tools
                module_path = f"integrations.{pkg_name}.agent_tools"
                module = importlib.import_module(module_path)
                
                tools_instances: List[BaseTool] = []

                if hasattr(module, "get_tools"):
                    func = getattr(module, "get_tools")
                    if asyncio.iscoroutinefunction(func):
                        tools_instances = await func(user_id, db)
                    else:
                        tools_instances = func(user_id, db)
                else:
                    # Fallback: scan for tool classes
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
