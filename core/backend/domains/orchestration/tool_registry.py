"""
ToolRegistry: Centralized registry for all agent tools.
Discovers tools from both the tools package and integrations directory.
"""
import pkgutil
import importlib
from typing import Dict, Type, Optional, List
from pathlib import Path
from domains.orchestration.tools.base import BaseTool


class ToolRegistry:
    """
    Singleton registry for all agent tools.
    Call discover_all_tools() at startup to populate the registry.
    """
    _tools: Dict[str, Type[BaseTool]] = {}
    _initialized: bool = False

    @classmethod
    async def discover_all_tools(cls) -> None:
        """
        Discover and register all tools from:
        1. tools.library package
        2. integrations/*/agent_tools.py
        """
        if cls._initialized:
            print("[ToolRegistry] Already initialized, skipping discovery.")
            return

        print("[ToolRegistry] Discovering all tools...")
        
        # 1. Discover from domains.orchestration.tools.library
        cls._discover_tools_package()
        
        # 2. Discover from integrations
        cls._discover_integration_tools()
        
        cls._initialized = True
        print(f"[ToolRegistry] Discovery complete. {len(cls._tools)} tools registered.")

    @classmethod
    def _discover_tools_package(cls) -> None:
        """Discover tools from the tools.library package."""
        try:
            import tools.library as library_pkg
            library_path = Path(library_pkg.__file__).parent
            
            for module_info in pkgutil.iter_modules([str(library_path)]):
                if module_info.name.startswith("_"):
                    continue
                try:
                    module = importlib.import_module(f"tools.library.{module_info.name}")
                    cls._register_tools_from_module(module, f"tools.library.{module_info.name}")
                except Exception as e:
                    print(f"[ToolRegistry] Error loading tools.library.{module_info.name}: {e}")
        except Exception as e:
            print(f"[ToolRegistry] Error discovering tools package: {e}")

    @classmethod
    def _discover_integration_tools(cls) -> None:
        """Discover tools from integrations/*/agent_tools.py."""
        try:
            integrations_path = Path(__file__).parent.parent / "integrations"
            
            for module_info in pkgutil.iter_modules([str(integrations_path)]):
                if not module_info.ispkg:
                    continue
                try:
                    # Try to import agent_tools module
                    module = importlib.import_module(f"integrations.{module_info.name}.agent_tools")
                    cls._register_tools_from_module(module, f"integrations.{module_info.name}")
                except ModuleNotFoundError:
                    # Integration doesn't have agent_tools, skip
                    pass
                except Exception as e:
                    print(f"[ToolRegistry] Error loading integrations.{module_info.name}.agent_tools: {e}")
        except Exception as e:
            print(f"[ToolRegistry] Error discovering integration tools: {e}")

    @classmethod
    def _register_tools_from_module(cls, module, source: str) -> None:
        """Register all BaseTool subclasses from a module."""
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            try:
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseTool) and 
                    attr is not BaseTool and
                    hasattr(attr, 'name')):
                    
                    tool_name = attr.name
                    if tool_name in cls._tools:
                        existing = cls._tools[tool_name]
                        print(f"[ToolRegistry] Warning: Duplicate tool name '{tool_name}' "
                              f"({attr.__module__} vs {existing.__module__})")
                    else:
                        cls._tools[tool_name] = attr
            except TypeError:
                continue

    @classmethod
    def get_tool(cls, name: str) -> Optional[BaseTool]:
        """Get an instance of a tool by name."""
        if not cls._initialized:
            print(f"[ToolRegistry] Warning: Registry not initialized when requesting '{name}'")
            
        tool_class = cls._tools.get(name)
        if tool_class:
            return tool_class()
        return None

    @classmethod
    def get_tool_class(cls, name: str) -> Optional[Type[BaseTool]]:
        """Get a tool class by name (without instantiation)."""
        return cls._tools.get(name)

    @classmethod
    def list_all_tools(cls) -> List[str]:
        """List all registered tool names."""
        return list(cls._tools.keys())

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the registry has been initialized."""
        return cls._initialized
