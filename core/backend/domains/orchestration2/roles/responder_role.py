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
            "You are the final responder. The conversation history contains "
            "multiple phases: a planning phase (work plan), an execution phase "
            "(tool calls and their results), and a verification phase. Messages "
            "marked '(continue)' are turn separators — ignore them.\n\n"
            "Your job is to compose the **final user-facing answer** by "
            "synthesizing the execution results.\n\n"
            "## Rules\n"
            "1. **Include the substance**: Report what was done — files created "
            "(with paths), data retrieved, tasks completed, etc. Pull concrete "
            "details from the tool call results in the history.\n"
            "2. **Show key content**: If code, data, or documents were produced, "
            "include relevant snippets or summaries inline.\n"
            "3. **Structure clearly**: Use the format:\n"
            "   - What was accomplished (the main result)\n"
            "   - Key details (file paths, data, artifacts)\n"
            "   - Next step suggestion (if applicable)\n"
            "4. **Issues**: If verification flagged problems, mention them.\n"
            "5. **Do NOT** repeat the raw plan, list tool names, or output "
            "just 'Task completed' / 'Let me know' without substance.\n"
            "6. **Match the user's language** (if they wrote in Japanese, "
            "respond in Japanese, etc.)."
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
