from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import Skill, ProjectSkill

class SkillService:
    @staticmethod
    async def get_agent_skills(db: AsyncSession, agent_id: str, intent: Optional[str] = None) -> List[Skill]:
        """
        Fetch and resolve skills for an agent.

        Logic:
        1. Fetch all active skills associated with the agent.
        2. Filter by intent if provided.
        3. Sort by priority (descending).
        4. Resolve conflicts: If a skill conflicts with another, the higher-priority one wins.
        """
        stmt = (
            select(Skill)
            .join(ProjectSkill, Skill.id == ProjectSkill.skill_id)
            .filter(ProjectSkill.agent_id == agent_id)
            .filter(Skill.is_active == True)
        )
        res = await db.execute(stmt)
        skills = list(res.scalars().all())

        if not skills:
            return []

        # 1. Intent Filtering
        if intent:
            filtered_skills = []
            for s in skills:
                meta = s.metadata_payload or {}
                intents = meta.get("intents", [])
                if intent in intents:
                    filtered_skills.append(s)
            
            # If we found intent-specific skills, use them. Otherwise fallback to general skills.
            if filtered_skills:
                skills = filtered_skills

        # 2. Priority Sorting (Higher priority first)
        def get_priority(s: Skill) -> int:
            return (s.metadata_payload or {}).get("priority", 0)
        
        skills.sort(key=get_priority, reverse=True)

        # 3. Conflict Resolution
        resolved_skills = []
        suppressed_ids = set()

        for s in skills:
            if s.id in suppressed_ids:
                continue
            
            resolved_skills.append(s)
            
            # Mark conflicting skills for suppression
            conflicts = (s.metadata_payload or {}).get("conflicts_with", [])
            if conflicts:
                suppressed_ids.update(conflicts)

        return resolved_skills

    @staticmethod
    def format_skill_instructions(skills: List[Skill]) -> str:
        """Format skill contents into a single instruction block."""
        if not skills:
            return ""

        header = "\n\n### ATTACHED SKILLS (Strategic Guidelines)\n"
        header += "> [!NOTE]\n"
        header += "> The following skills are provided as strategic guidelines. You are encouraged to follow these procedures when applicable, but you maintain the autonomy to adapt or combined tools as needed to achieve the objective efficiently.\n"
        
        footer = "\n### END OF SKILL GUIDELINES\n"
        
        skill_blocks = []
        for skill in skills:
            block = f"#### Skill Guideline: {skill.name}\n{skill.content}"
            skill_blocks.append(block)
            
        return header + "\n---\n".join(skill_blocks) + footer

    @staticmethod
    def merge_tool_policies(skills: List[Skill]) -> Dict[str, Any]:
        """
        Merge tool_policy metadata from multiple skills.

        Rules:
        - allowlist: union of all allowlists (if any are present)
        - denylist: union of all denylists
        - intent_map: union per intent
        - retry.max_attempts: most restrictive (minimum) when multiple defined
        - retry.fallback_tools: union per tool
        """
        allowlist: Optional[set[str]] = None
        denylist: set[str] = set()
        intent_map: Dict[str, set[str]] = {}
        retry: Dict[str, Any] = {"max_attempts": None, "fallback_tools": {}}

        for skill in skills:
            metadata = skill.metadata_payload or {}
            policy = metadata.get("tool_policy") or {}

            policy_allowlist = policy.get("allowlist")
            if policy_allowlist:
                if allowlist is None:
                    allowlist = set(policy_allowlist)
                else:
                    allowlist.update(policy_allowlist)

            denylist.update(policy.get("denylist", []) or [])

            for intent, tools in (policy.get("intent_map") or {}).items():
                intent_map.setdefault(intent, set()).update(tools or [])

            retry_policy = policy.get("retry") or {}
            max_attempts = retry_policy.get("max_attempts")
            if max_attempts is not None:
                retry_current = retry.get("max_attempts")
                retry["max_attempts"] = (
                    max_attempts
                    if retry_current is None
                    else min(retry_current, max_attempts)
                )

            for tool_name, fallbacks in (retry_policy.get("fallback_tools") or {}).items():
                retry["fallback_tools"].setdefault(tool_name, set()).update(fallbacks or [])

        if allowlist is not None:
            allowlist = allowlist.difference(denylist)

        merged = {
            "allowlist": sorted(allowlist) if allowlist is not None else None,
            "denylist": sorted(denylist),
            "intent_map": {k: sorted(v) for k, v in intent_map.items()},
            "retry": {
                "max_attempts": retry.get("max_attempts"),
                "fallback_tools": {
                    k: sorted(v) for k, v in retry.get("fallback_tools", {}).items()
                },
            },
        }
        return merged

    @classmethod
    async def get_agent_tool_policy(cls, db: AsyncSession, agent_id: str, intent: Optional[str] = None) -> Dict[str, Any]:
        """Fetch and merge tool policies for an agent."""
        skills = await cls.get_agent_skills(db, agent_id, intent=intent)
        if not skills:
            return {}
        return cls.merge_tool_policies(skills)

    @classmethod
    async def inject_skills_to_prompt(cls, db: AsyncSession, agent_id: str, original_prompt: str, intent: Optional[str] = None) -> str:
        """Fetch skills and append them to the system prompt."""
        skills = await cls.get_agent_skills(db, agent_id, intent=intent)
        if not skills:
            return original_prompt
            
        skill_instructions = cls.format_skill_instructions(skills)
        return original_prompt + skill_instructions
