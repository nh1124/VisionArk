"""Skill registry: name -> SkillDef + implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import DuplicateNameError, RegistryKeyError

if TYPE_CHECKING:
    from ..interfaces.skill import BaseSkill
    from ..models.skill import SkillDef

_REGISTRY_NAME = "SkillRegistry"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, tuple[SkillDef, BaseSkill]] = {}

    def register(self, skill_def: SkillDef, skill_impl: BaseSkill) -> None:
        if skill_def.name in self._skills:
            raise DuplicateNameError(_REGISTRY_NAME, skill_def.name)
        self._skills[skill_def.name] = (skill_def, skill_impl)

    def get(self, name: str) -> tuple[SkillDef, BaseSkill]:
        if name not in self._skills:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return self._skills[name]

    def get_def(self, name: str) -> SkillDef:
        return self.get(name)[0]

    def get_impl(self, name: str) -> BaseSkill:
        return self.get(name)[1]

    def list(self) -> list[SkillDef]:
        return [sd for sd, _ in self._skills.values()]

    def update(self, skill_def: SkillDef, skill_impl: BaseSkill) -> None:
        if skill_def.name not in self._skills:
            raise RegistryKeyError(_REGISTRY_NAME, skill_def.name)
        self._skills[skill_def.name] = (skill_def, skill_impl)

    def delete(self, name: str) -> None:
        if name not in self._skills:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        del self._skills[name]

    def has(self, name: str) -> bool:
        return name in self._skills
