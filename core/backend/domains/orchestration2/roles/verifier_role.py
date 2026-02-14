"""VerifierRole: Reviews execution results for completeness.

Used in the 'verify' step of the Plan -> Execute -> Verify -> Respond graph.
Checks whether the execution phase fulfilled the original user request.
"""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult


class VerifierRole:
    """Reviews the conversation history to verify execution completeness.

    Implements the orchestration2 BaseRole protocol.
    Can use inspection tools (read files, list files, etc.) to confirm results.
    """

    name: str = "verifier"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        parts: list[str] = []

        parts.append(
            "You are a verification assistant. Your job is to review what was "
            "planned and executed in this conversation and check for completeness.\n\n"
            "Instructions:\n"
            "- Look at the PLAN (early in the conversation) and the EXECUTION "
            "results (tool calls and their outputs).\n"
            "- You may use read-only tools (read files, list files, search) to "
            "inspect artifacts that were created or modified.\n"
            "- Produce a short verification summary:\n"
            "  * Which plan steps were completed successfully.\n"
            "  * Any issues, omissions, or errors found.\n"
            "  * An overall verdict: PASS or NEEDS ATTENTION.\n"
            "- Keep the summary concise (5-10 lines max).\n"
            "- If the original request was simple (greeting, Q&A), just confirm "
            "the response is adequate in one line."
        )

        return "\n\n".join(parts)

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Always signals not-done so the step emits DONE and transitions."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=False,
        )
