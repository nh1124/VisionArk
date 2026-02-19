"""PlannerRole: Creates a structured work plan before execution.

Used in the 'plan' step of the Plan -> Execute -> Verify -> Respond graph.
Produces a concise plan that subsequent steps can follow.
"""

from __future__ import annotations

import logging

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult

logger = logging.getLogger(__name__)

_FALLBACK_MAX_CHARS = 2000


class PlannerRole:
    """Analyzes the user request and produces a short, structured work plan.

    Implements the orchestration2 BaseRole protocol.
    All VisionArk-specific data is accessed via ``ctx.metadata``.
    """

    name: str = "planner"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        parts: list[str] = []

        # Core planning instruction with structured output
        parts.append(
            "You are a planning assistant. Your ONLY job is to analyze the user's "
            "request and produce a short, structured work plan.\n\n"
            "## Planning Rules\n"
            "1. **Analyze Capabilities**: Use ONLY the tools and skills listed in 'Available Capabilities'. Do not hallucinate tools.\n"
            "2. **Structure**: Output a numbered list of steps. Each step must be actionable.\n"
            "3. **Format**: Use the following format for each step:\n"
            "   - **Step N**: [Title]\n"
            "   - **Goal**: [What this step achieves]\n"
            "   - **Required Skill**: [Name of the skill from capabilities]\n"
            "   - **Required Tool**: [Name of the tool to use, if known]\n"
            "4. **Verification**: If a step involves a major action, consider a follow-up verification step.\n"
            "5. **Simple Requests**: If the request is simple (greetings, factual Q&A), output: '1. Reply directly.'\n\n"
            "## Output Example\n"
            "1. **Step 1**: Search for files\n"
            "   - **Goal**: Locate the relevant code.\n"
            "   - **Required Skill**: coding\n"
            "   - **Required Tool**: list_dir\n"
        )

        # Inject capabilities (Preferred source of truth)
        capabilities = ctx.metadata.get("planner_capabilities")
        if capabilities:
            parts.append(capabilities)
            logger.debug(
                "Planner using planner_capabilities (%d chars)", len(capabilities)
            )
        else:
            # Fallback: build a minimal summary (name + description only)
            # to avoid injecting full skill content which causes output overflow
            logger.warning(
                "planner_capabilities missing — using minimal fallback summary"
            )
            fallback_lines = ["## Available Skills (summary)"]
            skill_defs = ctx.metadata.get("skill_definitions", {})
            if skill_defs:
                for name in skill_defs:
                    fallback_lines.append(f"- **{name}**")
            else:
                skills_text = ctx.metadata.get("skills_text", "")
                # Extract only '### SkillName' headers from raw text
                for line in skills_text.splitlines():
                    if line.startswith("### "):
                        fallback_lines.append(f"- **{line[4:].strip()}**")

            integration_tools = ctx.metadata.get("integration_tools_text")
            if integration_tools:
                fallback_lines.append("\n## Available Integration Tools (summary)")
                for line in integration_tools.splitlines():
                    if line.startswith("### "):
                        fallback_lines.append(f"- **{line[4:].strip()}**")

            fallback_text = "\n".join(fallback_lines)
            if len(fallback_text) > _FALLBACK_MAX_CHARS:
                fallback_text = (
                    fallback_text[:_FALLBACK_MAX_CHARS]
                    + "\n... (truncated — capability list too long)"
                )
            parts.append(fallback_text)
            logger.debug("Fallback prompt size: %d chars", len(fallback_text))

        plan = ctx.metadata.get("project_plan")
        if plan:
            parts.append(f"\n## Project Plan (PLAN.md)\n{plan}")

        agent_profile = ctx.metadata.get("agent_profile")
        if agent_profile:
            parts.append(f"\n## Agent Profile\n{agent_profile}")


        prompt = "\n\n".join(parts)
        logger.debug("Planner prompt total size: %d chars", len(prompt))
        return prompt

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Always signals not-done so the step emits DONE and transitions."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=False,
        )
