"""Skill interface protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..models.execution import ExecutionContext, SkillResult
    from ..models.message import Message
    from ..models.skill import SkillDef


@runtime_checkable
class BaseSkill(Protocol):
    definition: SkillDef

    async def run(
        self, input_message: Message, ctx: ExecutionContext
    ) -> SkillResult: ...
