import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy import select
from shared.database import Skill, ScheduledTask, ScheduledTaskStatus, ChatMessage, ChatSubMessage, ToolUsage
from infrastructure.llm.orchestration2_provider import GeminiLLMProvider

class SkillMiningService:
    STATE_FILENAME = "mining_state.json"
    
    def __init__(self, db_session):
        self.db = db_session

    async def analyze_task_for_skills(self, task_id: str, user_id: str):
        """Analyze a completed task to see if it represents a repeatable skill."""
        print(f"[SkillMiningService] Analyzing task {task_id} for potential skills...")
        
        # 1. Fetch the task/message context
        # In VisionArk, we can fetch messages associated with the current session
        from sqlalchemy import select, desc
        from shared.database import ChatMessage, ChatSession
        
        # We need the session_id. Let's assume we can find it via the last message of the user/task
        # Simplified: Fetch last 10 messages for this user to get context
        from sqlalchemy.orm import selectinload
        stmt = (
            select(ChatMessage)
            .options(
                selectinload(ChatMessage.session),
                selectinload(ChatMessage.sub_messages).selectinload(ChatSubMessage.tool_calls)
            )
            .join(ChatSession)
            .filter(ChatSession.project_id != None) # Usually tied to a project
            .order_by(desc(ChatMessage.created_at))
            .limit(10)
        )
        res = await self.db.execute(stmt)
        messages = res.scalars().unique().all()
        messages.reverse() # Chronological order

        if not messages:
            return

        # 1.5. Throttling & Complexity Check (Guard)
        if not await self.validate_mining_request(task_id, user_id):
            return

        # 3. Format context for LLM
        context_parts = []
        for m in messages:
            role = m.role.upper()
            content = m.content
            tool_info = ""
            
            # 1. Check legacy tool calls
            if m.meta_payload and m.meta_payload.get("tool_calls"):
                tool_info = f"\n[LEGACY TOOLS: {json.dumps(m.meta_payload['tool_calls'])}]"
                
            # 2. Check new structured tool calls
            sub_actions = []
            if m.sub_messages:
                for sub in m.sub_messages:
                    if sub.tool_calls:
                        for tu in sub.tool_calls:
                            sub_actions.append({
                                "name": tu.name,
                                "args": tu.args,
                                "is_success": tu.is_success
                            })
            
            if sub_actions:
                tool_info += f"\n[STRUCTURED ACTIONS: {json.dumps(sub_actions)}]"
                
            context_parts.append(f"{role}: {content}{tool_info}")

        analysis_context = "\n---\n".join(context_parts)

        # 4. Generate Draft
        await self.generate_draft_skill(user_id, analysis_context, task_id)

    async def generate_draft_skill(self, user_id: str, analysis_context: str, task_id: str):
        """Use LLM to generate a SKILL.md draft from context."""
        from shared.service_helpers import get_user_api_key
        from domains.orchestration2.engine.models.message import Message
        from domains.orchestration2.engine.models.common import MessageRole

        api_key = await get_user_api_key(user_id, self.db)
        provider = GeminiLLMProvider(api_key=api_key)

        system_prompt = (
            "You are a Skill Architect. Your job is to extract repeatable 'Agent Skills' "
            "from user interaction logs. A Skill should be a Markdown document (SKILL.md) "
            "with YAML frontmatter and clear instructions.\n\n"
            "Focus on the PROCEDURAL DNA. What steps did the agent take to succeed?\n"
            "Identify SPECIFIC INTENTS (e.g., 'code_review', 'data_extraction') and assign a PRIORITY.\n\n"
            "Return ONLY valid JSON with keys: name, description, id, content, priority, intents."
        )

        user_prompt = (
            f"Analyze the following interaction and define a useful skill that summarizes the expertise shown:\n\n"
            f"### INTERACTION LOG\n{analysis_context}\n\n"
            f"### REQUIREMENTS\n"
            f"1. Name should be concise (e.g., 'Competitor Analysis', 'Data Cleaning').\n"
            f"2. Content must follow the SKILL.md format with instructions.\n"
            f"3. Do not include specific user data, keep it as a generalized template."
        )

        try:
            response = await provider.complete(
                [Message(role=MessageRole.USER, content=user_prompt)],
                system=system_prompt,
                model="gemini-2.5-flash-lite",
            )
            
            # response.content is now guaranteed to be a valid JSON string
            data = json.loads(response.content.strip())
            
            # Check for duplicates (Simple Name Check for now)
            if await self._check_duplicate_skill(data['name']):
                print(f"[SkillMiningService] Skill with name '{data['name']}' already exists. Skipping.")
                return

            # Save as Draft
            new_skill = Skill(
                id=f"draft-{data['id']}-{uuid.uuid4().hex[:6]}",
                user_id=user_id,
                name=data['name'],
                description=data['description'],
                content=data['content'],
                metadata_payload={
                    "source": "mining", 
                    "distilled_at": datetime.utcnow().isoformat(),
                    "priority": data.get("priority", 5),
                    "intents": data.get("intents", [])
                },
                is_draft=True,
                is_active=False 
            )
            self.db.add(new_skill)
            await self.db.commit()
            print(f"[SkillMiningService] Generated draft skill: {new_skill.id}")
            
            # Update Throttling State
            # Finding project_id again for state update
            # (Note: analyze_task_for_skills already has it, but let's be robust)
            from sqlalchemy import select
            from shared.database import ChatSession, ChatMessage
            stmt = select(ChatSession.project_id).join(ChatMessage).filter(ChatMessage.id == task_id)
            res = await self.db.execute(stmt)
            project_id = res.scalar()
            
            if project_id:
                self._update_mining_state(project_id, user_id)
        except Exception as e:
            print(f"[SkillMiningService] Error generating draft: {e}")
            import traceback
            traceback.print_exc()

    def is_complex_enough(self, messages: list) -> bool:
        """
        Evaluate if the interaction is complex enough to merit a skill.
        Criteria:
        - At least 3 tool calls total
        OR
        - Uses at least 2 distinct types of tools
        """
        total_tool_calls = 0
        distinct_tools = set()

        for m in messages:
            # Legacy Check
            if m.meta_payload and m.meta_payload.get("tool_calls"):
                calls = m.meta_payload["tool_calls"]
                if isinstance(calls, list):
                    total_tool_calls += len(calls)
                    for call in calls:
                        t_name = call.get("name") or call.get("function", {}).get("name")
                        if t_name:
                            distinct_tools.add(t_name)
            
            # New Structure Check
            if m.sub_messages:
                for sub in m.sub_messages:
                    if sub.tool_calls:
                        total_tool_calls += len(sub.tool_calls)
                        for tu in sub.tool_calls:
                            if tu.name:
                                distinct_tools.add(tu.name)
        
        return total_tool_calls >= 3 or len(distinct_tools) >= 2

    async def _check_duplicate_skill(self, name: str) -> bool:
        """Check if a skill with the same name already exists (Active or Draft)."""
        stmt = select(Skill).filter(Skill.name == name)
        res = await self.db.execute(stmt)
        return res.scalars().first() is not None

    def _get_mining_state_path(self, project_id: str, user_id: str) -> Optional[Path]:
        """Get the path to the mining state file in .visionark/"""
        try:
            from shared.paths import get_project_governance_dir
            state_dir = get_project_governance_dir(user_id, project_id)
            state_dir.mkdir(parents=True, exist_ok=True)
            return state_dir / self.STATE_FILENAME
        except Exception as e:
            print(f"[SkillMiningService] Error getting state path: {e}")
            return None

    def _check_throttling(self, project_id: str, user_id: str, interval_minutes: int = 10) -> bool:
        """
        Check if mining for this project should be throttled.
        Returns True if mining is allowed.
        """
        state_path = self._get_mining_state_path(project_id, user_id)
        if not state_path or not state_path.exists():
            return True
        
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            last_run_str = state.get("last_analyzed_at")
            if not last_run_str:
                return True
            
            last_run = datetime.fromisoformat(last_run_str)
            elapsed = (datetime.utcnow() - last_run).total_seconds()
            return elapsed > (interval_minutes * 60)
        except Exception as e:
            print(f"[SkillMiningService] Throttling check failed: {e}")
            return True

    def _update_mining_state(self, project_id: str, user_id: str):
        """Update the mining state file with the current timestamp."""
        state_path = self._get_mining_state_path(project_id, user_id)
        if not state_path:
            return
        
        try:
            state = {"last_analyzed_at": datetime.utcnow().isoformat()}
            state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"[SkillMiningService] Failed to update mining state: {e}")

    async def validate_mining_request(self, task_id: str, user_id: str) -> bool:
        """
        Conservative check to see if we should bother enqueuing or running LLM mining.
        Does NOT update state (that happens after drafting succeeds).
        """
        # 1. Fetch messages
        from sqlalchemy import select, desc
        from sqlalchemy.orm import selectinload
        from shared.database import ChatMessage, ChatSession
        
        stmt = (
            select(ChatMessage)
            .options(
                selectinload(ChatMessage.session),
                selectinload(ChatMessage.sub_messages).selectinload(ChatSubMessage.tool_calls)
            )
            .join(ChatSession)
            .filter(ChatSession.project_id != None)
            .order_by(desc(ChatMessage.created_at))
            .limit(10)
        )
        res = await self.db.execute(stmt)
        messages = res.scalars().unique().all()
        if not messages:
            return False
        
        # 2. Throttling check
        project_id = messages[0].session.project_id if messages[0].session else None
        if project_id:
            if not self._check_throttling(project_id, user_id):
                print(f"[SkillMiningService] Throttled: Guard rejected mining for project {project_id}.")
                return False
        
        # 3. Complexity check
        if not self.is_complex_enough(messages):
            print("[SkillMiningService] Complexity: Guard rejected mining (too simple).")
            return False
            
        return True

    async def run_batch_mining(self, user_id: str):
        """
        Periodically analyze recent successful sessions for a specific user.
        """
        from sqlalchemy import select
        from shared.database import ChatSession, Project
        
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
