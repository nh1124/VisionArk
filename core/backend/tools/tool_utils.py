from typing import Optional, Dict, Type, Any
from tools.base import BaseTool

def get_tool_by_name(name: str) -> Optional[BaseTool]:
    """
    Find and return an instance of a tool by its name.
    Uses ToolRegistry if initialized, otherwise falls back to legacy discovery.
    """
    from services.tool_registry import ToolRegistry
    
    # Use registry if initialized
    if ToolRegistry.is_initialized():
        return ToolRegistry.get_tool(name)
    
    # Fallback: Legacy discovery from tools package only
    # This path is used before registry initialization (e.g., during import)
    import tools
    
    for attr_name in dir(tools):
        attr = getattr(tools, attr_name)
        try:
            if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                if hasattr(attr, 'name') and attr.name == name:
                    return attr()
        except TypeError:
            continue
            
    return None

def get_tool_class_by_name(name: str) -> Optional[Type[BaseTool]]:
    """
    Find and return the tool class by its name.
    Uses ToolRegistry if initialized, otherwise falls back to legacy discovery.
    """
    from services.tool_registry import ToolRegistry
    
    # Use registry if initialized
    if ToolRegistry.is_initialized():
        return ToolRegistry.get_tool_class(name)
    
    # Fallback: Legacy discovery
    import tools
    
    for attr_name in dir(tools):
        attr = getattr(tools, attr_name)
        try:
            if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                if hasattr(attr, 'name') and attr.name == name:
                    return attr
        except TypeError:
            continue
            
    return None
