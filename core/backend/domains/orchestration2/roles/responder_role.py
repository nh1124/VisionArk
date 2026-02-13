"""ResponderRole: Terminal response formatter.

Used in the final 'responder' step of a graph to format the output message.
"""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult


class ResponderRole:
    """Formats the final response at the end of a run.

    Implements the orchestration2 BaseRole protocol.
    """

    name: str = "responder"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        """Responder doesn't need a complex system prompt."""
        return (
            "You are a response formatter. "
            "Summarize the conversation results clearly and concisely for the user."
        )

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Mark the response as done (terminal)."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=True,
        )
