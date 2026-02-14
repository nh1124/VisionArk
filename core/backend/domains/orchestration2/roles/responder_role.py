"""ResponderRole: Terminal response formatter.

Used in the final 'respond' step of the Plan -> Execute -> Verify -> Respond
graph to synthesize a proper user-facing answer from the full run history.
"""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult


class ResponderRole:
    """Synthesizes the final user-facing response from the full conversation.

    Implements the orchestration2 BaseRole protocol.
    This role makes an LLM call with the full conversation history
    (plan, execution, verification) and produces the actual answer.
    """

    name: str = "responder"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        parts: list[str] = []

        parts.append(
            "You are the final responder. The conversation history contains a "
            "planning phase, an execution phase (with tool calls and results), "
            "and a verification phase.\n\n"
            "Your job:\n"
            "- Compose the actual answer to the user's ORIGINAL request.\n"
            "- Focus on what was accomplished and deliver the result.\n"
            "- If files or artifacts were created, mention them and show key "
            "content (code snippets, summaries) as appropriate.\n"
            "- If there were issues noted in verification, mention them briefly.\n"
            "- Do NOT repeat the plan or the verification log.\n"
            "- Do NOT just say 'Task completed' — give a substantive response.\n"
            "- Match the user's language (if they wrote in Japanese, respond in "
            "Japanese, etc.)."
        )

        # Inject user settings for language/timezone awareness
        settings = ctx.metadata.get("user_settings", {})
        if settings:
            lang = settings.get("language", "")
            if lang:
                parts.append(f"User's preferred language: {lang}")

        return "\n\n".join(parts)

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Mark the response as done (terminal)."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=True,
        )
