"""PlannerRole: Creates a structured work plan before execution.

Used in the 'plan' step of the Plan -> Execute -> Verify -> Respond graph.
Produces a concise plan that subsequent steps can follow.
"""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult


class PlannerRole:
    """Analyzes the user request and produces a short, structured work plan.

    Implements the orchestration2 BaseRole protocol.
    All VisionArk-specific data is accessed via ``ctx.metadata``.
    """

    name: str = "planner"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        parts: list[str] = []

        # Core planning instruction
        parts.append(
            "You are a planning assistant. Your ONLY job is to analyze the user's "
            "request and produce a short, structured work plan.\n\n"
            "Rules:\n"
            "- Output a numbered list of concrete steps (max 7).\n"
            "- Each step should name the tool or action to use.\n"
            "- Do NOT execute any tools yourself — only plan.\n"
            "- If the request is simple (greetings, factual Q&A), output a single "
            "step: '1. Reply directly.'\n"
            "- End with a one-line summary of the expected outcome."
        )

        # Inject project context so the planner knows what tools/skills exist
        skills_text = ctx.metadata.get("skills_text")
        if skills_text:
            parts.append(f"\n## Available Skills\n{skills_text}")

        plan = ctx.metadata.get("project_plan")
        if plan:
            parts.append(f"\n## Project Plan (PLAN.md)\n{plan}")

        agent_profile = ctx.metadata.get("agent_profile")
        if agent_profile:
            parts.append(f"\n## Agent Profile\n{agent_profile}")

        integration_tools = ctx.metadata.get("integration_tools_text")
        if integration_tools:
            parts.append(f"\n## Available Integration Tools\n{integration_tools}")

        return "\n\n".join(parts)

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Always signals not-done so the step emits DONE and transitions."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=False,
        )
