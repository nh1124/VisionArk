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
            "You are the final responder. Your output is the ONLY text the "
            "user will see. It must be a **complete, standalone response**.\n\n"
            "The conversation history contains multiple phases: planning, "
            "execution (tool calls and results), and verification.\n\n"
            "## Critical Rules\n"
            "1. **STANDALONE**: Your response must make sense on its own. "
            "Do NOT continue, extend, or complete a previous assistant "
            "message. Start fresh and write the full answer.\n"
            "2. **Synthesize, don't echo**: Read the execution results from "
            "history and rewrite them as a coherent user-facing report. "
            "Do NOT copy-paste raw tool outputs.\n"
            "3. **Include substance**: Report what was done — files created "
            "(with paths), data retrieved, tasks completed. Pull concrete "
            "details from tool call results in the history.\n"
            "4. **Show key content**: If code, data, or documents were "
            "produced, include relevant snippets or summaries inline.\n"
            "5. **Structure clearly**:\n"
            "   - What was accomplished (the main result)\n"
            "   - Key details (file paths, data, artifacts)\n"
            "   - Next step suggestion (if applicable)\n"
            "6. **Issues**: If verification flagged problems, mention them.\n"
            "7. **Do NOT** output just a fragment, a few trailing lines, "
            "'Task completed', or 'Let me know' without substance.\n"
            "8. **Match the user's language** (if they wrote in Japanese, "
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
