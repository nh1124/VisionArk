import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select
from models.database import Skill, ScheduledTask, ScheduledTaskStatus, ChatMessage
from llm import get_provider

class SkillMiningService:
    def __init__(self, db_session):
        self.db = db_session

    async def analyze_task_for_skills(self, task_id: str, user_id: str):
        """Analyze a completed task to see if it represents a repeatable skill."""
        print(f"[SkillMiningService] Analyzing task {task_id} for potential skills...")
        
        # 1. Fetch the task/message context
        # In VisionArk, we can fetch messages associated with the current session
        from sqlalchemy import select, desc
        from models.database import ChatMessage, ChatSession
        
        # We need the session_id. Let's assume we can find it via the last message of the user/task
        # Simplified: Fetch last 10 messages for this user to get context
        stmt = (
            select(ChatMessage)
            .join(ChatSession)
            .filter(ChatSession.project_id != None) # Usually tied to a project
            .order_by(desc(ChatMessage.created_at))
            .limit(10)
        )
        res = await self.db.execute(stmt)
        messages = res.scalars().all()
        messages.reverse() # Chronological order

        if not messages:
            return

        # 2. Heuristic: Only mine if there are tool calls (indicating a complex procedure)
        has_tools = any(m.meta_payload and m.meta_payload.get("tool_calls") for m in messages)
        if not has_tools:
            print("[SkillMiningService] Task too simple for skill mining (no tool calls).")
            return

        # 3. Format context for LLM
        context_parts = []
        for m in messages:
            role = m.role.upper()
            content = m.content
            tool_info = ""
            if m.meta_payload and m.meta_payload.get("tool_calls"):
                tool_info = f"\n[TOOLS USED: {json.dumps(m.meta_payload['tool_calls'])}]"
            context_parts.append(f"{role}: {content}{tool_info}")

        analysis_context = "\n---\n".join(context_parts)

        # 4. Generate Draft
        await self.generate_draft_skill(user_id, analysis_context)

    async def generate_draft_skill(self, user_id: str, analysis_context: str):
        """Use LLM to generate a SKILL.md draft from context."""
        from tools.utils import get_user_api_key
        api_key = await get_user_api_key(user_id, self.db)
        llm = get_provider(api_key=api_key) 
        
        system_prompt = (
            "You are a Skill Architect. Your job is to extract repeatable 'Agent Skills' "
            "from user interaction logs. A Skill should be a Markdown document (SKILL.md) "
            "with YAML frontmatter and clear instructions.\n\n"
            "Focus on the PROCEDURAL DNA. What steps did the agent take to succeed?\n"
            "Return ONLY a JSON object with: 'name', 'description', 'id' (kebab-case), and 'content' (Markdown body)."
        )
        
        user_prompt = (
            f"Analyze the following interaction and define a useful skill that summarizes the expertise shown:\n\n"
            f"### INTERACTION LOG\n{analysis_context}\n\n"
            f"### REQUIREMENTS\n"
            f"1. Name should be concise (e.g., 'Competitor Analysis', 'Data Cleaning').\n"
            f"2. Content must follow the SKILL.md format with instructions.\n"
            f"3. Do not include specific user data, keep it as a generalized template."
        )
        
        from llm.base_provider import SimpleMessage

        try:
            response = await llm.complete_async([
                SimpleMessage(role="system", content=system_prompt),
                SimpleMessage(role="user", content=user_prompt)
            ], preferred_model="gemini-3-flash-preview")
            
            # Extract JSON from response content (handling potential markdown blocks)
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            data = json.loads(content)
            
            # Check for duplicates (Semantic Skeleton)
            # await self._check_duplicate_skill(data['name'])

            # Save as Draft
            new_skill = Skill(
                id=f"draft-{data['id']}-{uuid.uuid4().hex[:6]}",
                user_id=user_id,
                name=data['name'],
                description=data['description'],
                content=data['content'],
                metadata_payload={"source": "mining", "distilled_at": datetime.utcnow().isoformat()},
                is_draft=True,
                is_active=False 
            )
            self.db.add(new_skill)
            await self.db.commit()
            print(f"[SkillMiningService] Generated draft skill: {new_skill.id}")
        except Exception as e:
            print(f"[SkillMiningService] Error generating draft: {e}")
            import traceback
            traceback.print_exc()
            
    async def run_batch_mining(self, user_id: str):
        """
        Periodically analyze recent successful sessions for a specific user.
        """
        from sqlalchemy import select
        from models.database import ChatSession, Project
        
        print(f"[SkillMiningService] Starting batch mining cycle for user {user_id}...")
        
        # 1. Fetch high-value completed tasks (sessions) for this user
        stmt = (
            select(ChatSession)
            .join(Project)
            .filter(Project.user_id == user_id)
            .limit(20)
        )
        res = await self.db.execute(stmt)
        sessions = res.scalars().all()
        
        for session in sessions:
            await self.analyze_task_for_skills(session.id, user_id)
                
        print(f"[SkillMiningService] Batch mining cycle complete for user {user_id}.")
