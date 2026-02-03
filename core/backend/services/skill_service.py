from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import Skill, NodeSkill

class SkillService:
    @staticmethod
    async def get_node_skills(db: AsyncSession, node_id: str) -> List[Skill]:
        """Fetch all skills attached to a specific node."""
        stmt = (
            select(Skill)
            .join(NodeSkill, Skill.id == NodeSkill.skill_id)
            .filter(NodeSkill.node_id == node_id)
            .filter(Skill.is_active == True)
        )
        res = await db.execute(stmt)
        return res.scalars().all()

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
    def _get_skill_identifiers(skill: Skill) -> set[str]:
        metadata = skill.metadata_payload or {}
        identifiers = {skill.id, skill.name}
        metadata_id = metadata.get("id")
        if metadata_id:
            identifiers.add(metadata_id)
        return identifiers

    @classmethod
    def resolve_skills_for_intent(cls, skills: List[Skill], intent: Optional[str] = None) -> List[Skill]:
        """
        Resolve which skills apply for a given intent and handle conflicts.

        - If intent is provided, prefer skills whose metadata has `intents` including it.
          If no intent-specific skills exist, fall back to general skills (no intents set).
        - Conflicts are resolved by priority (higher first) using `priority` metadata.
        - `conflicts_with` can reference skill id, metadata id, or name.
        """
        if not skills:
            return []

        def get_intents(skill: Skill) -> List[str]:
            metadata = skill.metadata_payload or {}
            return metadata.get("intents") or []

        def get_priority(skill: Skill) -> int:
            metadata = skill.metadata_payload or {}
            return int(metadata.get("priority", 0))

        if intent:
            intent_skills = [s for s in skills if intent in get_intents(s)]
            general_skills = [s for s in skills if not get_intents(s)]
            candidates = intent_skills or general_skills
        else:
            candidates = list(skills)

        candidates.sort(key=get_priority, reverse=True)

        selected: List[Skill] = []
        blocked: set[str] = set()
        for skill in candidates:
            identifiers = cls._get_skill_identifiers(skill)
            if identifiers.intersection(blocked):
                continue

            metadata = skill.metadata_payload or {}
            conflicts = set(metadata.get("conflicts_with") or [])
            selected.append(skill)
            blocked.update(conflicts)

        return selected

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
    async def get_node_tool_policy(
        cls,
        db: AsyncSession,
        node_id: str,
        intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch and merge tool policies for a node."""
        skills = await cls.get_node_skills(db, node_id)
        resolved_skills = cls.resolve_skills_for_intent(skills, intent=intent)
        if not resolved_skills:
            return {}
        return cls.merge_tool_policies(resolved_skills)

    @classmethod
    async def inject_skills_to_prompt(
        cls,
        db: AsyncSession,
        node_id: str,
        original_prompt: str,
        intent: Optional[str] = None
    ) -> str:
        """Fetch skills and append them to the system prompt."""
        skills = await cls.get_node_skills(db, node_id)
        resolved_skills = cls.resolve_skills_for_intent(skills, intent=intent)
        if not resolved_skills:
            return original_prompt
            
        skill_instructions = cls.format_skill_instructions(resolved_skills)
        return original_prompt + skill_instructions
