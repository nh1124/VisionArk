"""Role registry: name -> BaseRole implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import DuplicateNameError, RegistryKeyError

if TYPE_CHECKING:
    from ..interfaces.role import BaseRole

_REGISTRY_NAME = "RoleRegistry"


class RoleRegistry:
    def __init__(self) -> None:
        self._roles: dict[str, BaseRole] = {}

    def register(self, role_impl: BaseRole) -> None:
        if role_impl.name in self._roles:
            raise DuplicateNameError(_REGISTRY_NAME, role_impl.name)
        self._roles[role_impl.name] = role_impl

    def get(self, name: str) -> BaseRole:
        if name not in self._roles:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return self._roles[name]

    def list(self) -> list[str]:
        return list(self._roles.keys())

    def update(self, role_impl: BaseRole) -> None:
        if role_impl.name not in self._roles:
            raise RegistryKeyError(_REGISTRY_NAME, role_impl.name)
        self._roles[role_impl.name] = role_impl

    def delete(self, name: str) -> None:
        if name not in self._roles:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        del self._roles[name]

    def has(self, name: str) -> bool:
        return name in self._roles
