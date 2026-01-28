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

    @classmethod
    async def inject_skills_to_prompt(cls, db: AsyncSession, node_id: str, original_prompt: str) -> str:
        """Fetch skills and append them to the system prompt."""
        skills = await cls.get_node_skills(db, node_id)
        if not skills:
            return original_prompt
            
        skill_instructions = cls.format_skill_instructions(skills)
        return original_prompt + skill_instructions
