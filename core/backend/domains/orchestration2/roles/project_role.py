"""ProjectRole: System prompt builder for project agents.

Ports the prompt-building logic from ProjectNode.on_execute() and
BaseNode.load_system_prompt() to orchestration2's BaseRole protocol.
"""

from __future__ import annotations

import logging
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, RoleResult

logger = logging.getLogger(__name__)


class ProjectRole:
    """Builds the system prompt for a project-bound agent.

    Implements the orchestration2 BaseRole protocol.
    All VisionArk-specific data is accessed via ``ctx.metadata``.
    """

    name: str = "project"

    def build_prompt(self, ctx: ExecutionContext) -> str:
        """Build the complete system prompt synchronously.

        NOTE: The orchestration2 protocol defines ``build_prompt`` as sync.
        Heavy async work (DB queries for roster, knowledge) must be done
        *before* this call — the caller (engine_setup or step_executor)
        should pre-populate ``ctx.metadata`` with the needed data.

        Expected metadata keys (pre-populated by engine_setup):
            system_prompt_components: list[str]  — loaded prompt text blocks
            agent_profile: str | None            — DB agent system_prompt
            user_profile: str | None             — user context info
            knowledge_context: str | None        — RAG results
            team_roster: str | None              — formatted roster
            user_settings: dict                  — language, timezone, etc.
            project_plan: str | None             — PLAN.md content
            skills_text: str | None              — injected skill instructions
        """
        parts: list[str] = []

        # 1. Prompt components (identity, formatting, etc.)
        components = ctx.metadata.get("system_prompt_components", [])
        if components:
            parts.extend(components)
        else:
            parts.append("You are a helpful AI assistant managing a project.")

        # 2. Execution behavior (critical for preventing output overflow)
        parts.append(
            "## Execution Rules\n"
            "You are in the EXECUTE phase. A planner has already analyzed the "
            "user's request and produced a work plan (the previous assistant "
            "message in conversation history).\n\n"
            "**Follow these rules strictly:**\n"
            "1. **Follow the plan**: Execute ONLY what the plan specifies.\n"
            "2. **Simple requests**: If the plan says 'Reply directly' or has "
            "only one trivial step, respond to the user immediately in natural "
            "language. Do NOT call tools or list capabilities.\n"
            "3. **Tool usage**: Only call tools when the plan explicitly "
            "requires an action (e.g., 'search files', 'create document'). "
            "Use function calling to invoke tools — never describe tools "
            "in your text response.\n"
            "4. **NEVER list or describe available tools** in your response. "
            "The user does not need to see tool names or descriptions.\n"
            "5. **Be concise**: Your response should address the user's "
            "request directly. Avoid meta-commentary about what you could do."
        )

        # 3. Agent-specific system prompt (from DB)
        node_prompt = ctx.metadata.get("agent_profile")
        if node_prompt:
            parts.append(f"\n## Role Profile\n{node_prompt}")

        # 3. Skills injection
        # Prefer step-specific active skills text if available (injected by StepExecutor)
        # Fall back to global skills_text (all skills) if not found (legacy behavior)
        skills_text = ctx.metadata.get("active_skills_text") or ctx.metadata.get("skills_text")
        if skills_text:
            logger.debug(
                "ProjectRole injecting skills_text (%d chars, source=%s)",
                len(skills_text),
                "active_skills_text" if ctx.metadata.get("active_skills_text") else "skills_text",
            )
            parts.append(f"\n## Active Skills\n{skills_text}")

        # 4. Project plan (PLAN.md)
        plan = ctx.metadata.get("project_plan")
        if plan:
            parts.append(f"\n## Project Plan (PLAN.md)\n{plan}")

        # 5. User profile
        user_profile = ctx.metadata.get("user_profile")
        if user_profile:
            parts.append(f"\n## User Profile\n{user_profile}")

        # 6. Knowledge context (RAG)
        knowledge = ctx.metadata.get("knowledge_context")
        if knowledge:
            parts.append(f"\n## Relevant Knowledge\n{knowledge}")

        # 7. Team roster
        roster = ctx.metadata.get("team_roster")
        if roster:
            parts.append(roster)

        # 8b. Integration Tools
        integration_tools = ctx.metadata.get("integration_tools_text")
        if integration_tools:
            parts.append(f"\n## Available Integration Tools\n{integration_tools}")

        # 9. User settings (timezone, language)
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
        logger.debug("ProjectRole prompt total size: %d chars", len(prompt))
        return prompt

    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult:
        """Post-process LLM output. For ProjectRole this is a pass-through."""
        return RoleResult(
            role_name=self.name,
            output=llm_output,
            done=False,
        )
