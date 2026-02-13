"""Tool registry: name -> ToolDef + implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import DuplicateNameError, RegistryKeyError

if TYPE_CHECKING:
    from ..interfaces.tool import BaseTool
    from ..models.tool import ToolDef

_REGISTRY_NAME = "ToolRegistry"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDef, BaseTool]] = {}

    def register(self, tool_def: ToolDef, tool_impl: BaseTool) -> None:
        if tool_def.name in self._tools:
            raise DuplicateNameError(_REGISTRY_NAME, tool_def.name)
        self._tools[tool_def.name] = (tool_def, tool_impl)

    def get(self, name: str) -> tuple[ToolDef, BaseTool]:
        if name not in self._tools:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return self._tools[name]

    def get_def(self, name: str) -> ToolDef:
        return self.get(name)[0]

    def get_impl(self, name: str) -> BaseTool:
        return self.get(name)[1]

    def list(self) -> list[ToolDef]:
        return [td for td, _ in self._tools.values()]

    def update(self, tool_def: ToolDef, tool_impl: BaseTool) -> None:
        if tool_def.name not in self._tools:
            raise RegistryKeyError(_REGISTRY_NAME, tool_def.name)
        self._tools[tool_def.name] = (tool_def, tool_impl)

    def delete(self, name: str) -> None:
        if name not in self._tools:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        del self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools
