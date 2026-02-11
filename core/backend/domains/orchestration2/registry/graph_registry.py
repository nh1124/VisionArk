"""Graph registry: name -> compiled GraphSpec."""

from __future__ import annotations

from ..errors import DuplicateNameError, RegistryKeyError
from ..models.graph_spec import GraphSpec

_REGISTRY_NAME = "GraphRegistry"


class GraphRegistry:
    def __init__(self) -> None:
        self._graphs: dict[str, GraphSpec] = {}

    def register(self, spec: GraphSpec) -> None:
        if spec.graph_name in self._graphs:
            raise DuplicateNameError(_REGISTRY_NAME, spec.graph_name)
        self._graphs[spec.graph_name] = spec

    def get(self, name: str) -> GraphSpec:
        if name not in self._graphs:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return self._graphs[name]

    def list(self) -> list[str]:
        return list(self._graphs.keys())

    def update(self, spec: GraphSpec) -> None:
        if spec.graph_name not in self._graphs:
            raise RegistryKeyError(_REGISTRY_NAME, spec.graph_name)
        self._graphs[spec.graph_name] = spec

    def delete(self, name: str) -> None:
        if name not in self._graphs:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        del self._graphs[name]

    def has(self, name: str) -> bool:
        return name in self._graphs
