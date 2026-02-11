"""Role interface protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..models.execution import ExecutionContext, RoleResult


@runtime_checkable
class BaseRole(Protocol):
    name: str

    def build_prompt(self, ctx: ExecutionContext) -> str: ...

    def post_process(
        self, llm_output: str, ctx: ExecutionContext
    ) -> RoleResult: ...
