"""DirectRole: Single-loop role that thinks, acts, and responds directly.

Combines planning, execution, and response into one multi-turn loop.
No plan/verify/respond pipeline — the model self-corrects within its own
tool-calling loop and the final text IS the user-facing response.
"""

from __future__ import annotations

import logging
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult

logger = logging.getLogger(__name__)


class DirectRole:
    """Single-step role: think → use tools → respond, all in one loop.

    Implements the orchestration2 BaseRole protocol.
    """

    name: str = "direct"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        """Build the complete system prompt.

        Expected metadata keys (pre-populated by engine_setup):
            system_prompt_components: list[str]
            agent_profile: str | None
            user_profile: str | None
            knowledge_context: str | None
            team_roster: str | None
            user_settings: dict
            project_plan: str | None
            active_skills_text: str | None
            skills_text: str | None
            integration_tools_text: str | None
        """
        parts: list[str] = []

        # 1. Prompt components (identity, formatting, etc.)
        components = ctx.metadata.get("system_prompt_components", [])
        if components:
            parts.extend(components)
        else:
            parts.append("You are a helpful AI assistant managing a project.")

        # 2. Behavioral rules — single-loop direct assistant
        parts.append(
            "## Behavioral Rules\n"
            "You handle the user's request in a single pass. There is no "
            "separate planning or verification step — you do everything here.\n\n"
            "**Follow these rules strictly:**\n"
            "1. **Think before you act**: Briefly consider the request internally. "
            "Do NOT output a plan to the user — just act.\n"
            "2. **Use tools when needed**: If the request requires action "
            "(searching, creating files, etc.), call the appropriate tools via "
            "function calling. You may call tools across multiple turns.\n"
            "3. **Respond directly**: Your text output IS the final user-facing "
            "response. Be clear, helpful, and concise. Do not re-summarize "
            "what tools did — integrate results naturally.\n"
            "4. **NEVER list or describe available tools** in your response. "
            "The user does not need to see tool names or descriptions.\n"
            "5. **Be concise**: Address the user's request directly. Avoid "
            "meta-commentary about what you could do.\n"
            "6. **Self-correct**: If a tool call fails or returns unexpected "
            "results, adapt and retry or inform the user. Do not give up silently."
        )

        # 3. Agent-specific system prompt (from DB)
        agent_profile = ctx.metadata.get("agent_profile")
        if agent_profile:
            parts.append(f"\n## Role Profile\n{agent_profile}")

        # 4. Skills injection
        skills_text = ctx.metadata.get("active_skills_text") or ctx.metadata.get("skills_text")
        if skills_text:
            logger.debug(
                "DirectRole injecting skills_text (%d chars, source=%s)",
                len(skills_text),
                "active_skills_text" if ctx.metadata.get("active_skills_text") else "skills_text",
            )
            parts.append(f"\n## Active Skills\n{skills_text}")

        # 5. Project plan (PLAN.md)
        plan = ctx.metadata.get("project_plan")
        if plan:
            parts.append(f"\n## Project Plan (PLAN.md)\n{plan}")

        # 6. User profile
        user_profile = ctx.metadata.get("user_profile")
        if user_profile:
            parts.append(f"\n## User Profile\n{user_profile}")

        # 7. Knowledge context (RAG)
        knowledge = ctx.metadata.get("knowledge_context")
        if knowledge:
            parts.append(f"\n## Relevant Knowledge\n{knowledge}")

        # 8. Team roster
        roster = ctx.metadata.get("team_roster")
        if roster:
            parts.append(roster)

        # 9. Integration Tools
        integration_tools = ctx.metadata.get("integration_tools_text")
        if integration_tools:
            parts.append(f"\n## Available Integration Tools\n{integration_tools}")

        # 10. User settings (timezone, language)
        settings = ctx.metadata.get("user_settings", {})
        if settings:
            tz = settings.get("timezone", "UTC")
            lang = settings.get("language", "en")
            location = settings.get("location", "")
            meta_lines = [f"- Timezone: {tz}", f"- Language: {lang}"]
            if location:
                meta_lines.append(f"- Location: {location}")
            parts.append("\n## User Environment\n" + "\n".join(meta_lines))

        prompt = "\n\n".join(parts)
        logger.debug("DirectRole prompt total size: %d chars", len(prompt))
        return prompt

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Post-process LLM output. Terminal — always returns done=True."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=True,
        )
