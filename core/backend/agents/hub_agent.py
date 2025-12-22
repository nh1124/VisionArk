"""
Hub Agent - Central orchestration agent
Implements hub-specific prompt loading, log paths, and LBS integration
"""
from pathlib import Path
from typing import List, Optional
from agents.base_agent import BaseAgent
from utils.paths import get_user_hub_dir, get_user_global_prompt, get_global_prompt
from models.message import Message, MessageRole, AttachedFile
from models.database import UserSettings, Node, AgentProfile, get_engine, get_session
from datetime import date, datetime
from uuid import uuid4


class HubAgent(BaseAgent):
    """Hub agent with Hub-specific logic and LBS integration (per-user)"""
    
    def _get_api_key(self, user_id: str, db_session=None) -> Optional[str]:
        """Retrieve and decrypt Gemini API key for the user"""
        if not user_id:
            return None
            
        from models.database import UserSettings, get_engine, get_session
        from utils.encryption import decrypt_string
        
        # Use provided session or create temporary one
        session = db_session or get_session(get_engine())
        try:
            settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
                encrypted_key = settings.ai_config["gemini_api_key"]
                if encrypted_key == "********": # Should not happen with new logic but safe to check
                    return None
                return decrypt_string(encrypted_key)
        except Exception as e:
            print(f"[HubAgent] Failed to retrieve/decrypt API key: {e}")
        finally:
            if not db_session:
                session.close()
        return None

    @classmethod
    def get_or_create_hub_node(cls, user_id: str, db_session) -> Node:
        """Find or create the HUB node for a user"""
        node = db_session.query(Node).filter(
            Node.user_id == user_id,
            Node.node_type == "HUB"
        ).first()
        
        if not node:
            node_id = str(uuid4())
            node = Node(
                id=node_id,
                user_id=user_id,
                name="hub",
                display_name="Central Hub",
                node_type="HUB",
                lbs_access_level="WRITE"
            )
            db_session.add(node)
            db_session.commit()
            
            # Create default profile
            profile = AgentProfile(
                id=str(uuid4()),
                node_id=node_id,
                system_prompt=None, # Will fallback to default
                is_active=True
            )
            db_session.add(profile)
            db_session.commit()
            
        return node

    def __init__(self, user_id: str, db_session, node_id: Optional[str] = None):
        self.user_id = user_id
        self.db_session = db_session
        
        # Ensure we have a node_id
        if not node_id:
            node = self.get_or_create_hub_node(user_id, db_session)
            node_id = node.id
            
        api_key = self._get_api_key(user_id, db_session)
        super().__init__(node_id=node_id, db_session=db_session, api_key=api_key)

    def _get_default_hub_prompt(self) -> str:
        # Default Hub prompt with commands and LBS info
        hub_default = """# Hub Agent (Project Manager Role)

You are the central orchestration agent (Hub) responsible for:
- Managing the LBS (Load Balancing System) across all projects
- Processing reports from Spoke agents
- Making strategic resource allocation decisions
- Preventing cognitive overload

## Your Responsibilities
1. Monitor daily and weekly load scores
2. Warn when capacity (CAP) is approaching or exceeded
3. Suggest task rescheduling when necessary
4. Process Inbox messages from Spokes
5. Provide high-level strategic guidance

## Available Commands

You can execute commands directly:

- `/check_inbox` - Check for messages from Spokes
- `/create_spoke \"name\" [\"prompt\"]` - Create new project workspace
- `/archive` - Archive current conversation and start fresh
- `/kill spoke_name` - Delete a spoke
- `/create_task name=\"X\" spoke=\"Y\" workload=N rule=ONCE|WEEKLY due=DATE` - Create LBS task

Example:
- /create_task name=\"Task 1\" spoke=\"Spoke 1\" workload=5 rule=ONCE due=2025-12-05

Attention: 
- Don't use quotes before backslash

## LBS (Load Balancing System) Parameters

**Load Score Calculation:**
- Each task has `base_load_score` (0-10 scale)
- Daily load = sum of all tasks due that day
- Weekly load = sum of all tasks in week
- **Capacity (CAP):** Default 10.0 (adjustable)

**Warning Levels:**
- Load 8-10: Approaching capacity
- Load > 10: Over capacity (reschedule needed!)

**Task Rules:**
1. `ONCE` - Single deadline (use `due_date`)
2. `WEEKLY` - Recurring on specific days (mon, tue, wed, thu, fri, sat, sun)
3. `EVERY_N_DAYS` - Recurring every N days (use `interval_days`, `anchor_date`)
4. `MONTHLY_DAY` - Specific day each month (use `month_day`)

## Communication Style
- Strategic and meta-level (don't get into project details)
- Data-driven (cite load scores, capacities)
- Proactive (warn about bottlenecks before they occur)
- Use commands when appropriate
"""
        return hub_default
    
    def load_system_prompt(self) -> str:
        """
        Hub-specific prompt loading with full command and LBS documentation.
        Checks DB AgentProfile first, then fallbacks.
        """
        # 1. Try DB Profile
        profile = self.db_session.query(AgentProfile).filter(
            AgentProfile.node_id == self.node_id,
            AgentProfile.is_active == True
        ).order_by(AgentProfile.version.desc()).first()
        
        hub_prompt = None
        if profile and profile.system_prompt:
            hub_prompt = profile.system_prompt
        
        # 2. Fallback to File or Default
        if not hub_prompt:
            # Note: hub_dir is deprecated but we can use paths util if needed
            hub_dir = get_user_hub_dir(self.user_id)
            prompt_path = hub_dir / "system_prompt.md"
            if prompt_path.exists():
                hub_prompt = prompt_path.read_text(encoding='utf-8')
            else:
                hub_prompt = self._get_default_hub_prompt()
        
        # 3. Prepend global prompt
        global_prompt = get_user_global_prompt(self.user_id)
        separator = "\n\n---\n\n# Hub Agent (Role-Specific Instructions)\n\n" if global_prompt else ""
        
        return global_prompt + separator + hub_prompt
    
    def get_node_name(self) -> str:
        return "hub"
    
    def chat(self, user_message: str, attached_files: List[AttachedFile] = None, preferred_model: Optional[str] = None) -> str:
        """
        Hub-specific chat overrides BaseAgent.chat to inject LBS context
        """
        from services.lbs_client import LBSClient
        
        # 1. Load system prompt if not loaded
        if not self.system_prompt:
            self.system_prompt = self.load_system_prompt()
        
        # 2. Build LBS context
        meta_info_str = None
        try:
            client = LBSClient(user_id=self.user_id)
            daily_data = client.calculate_load(date.today())
            load = daily_data.get("adjusted_load", 0.0)
            meta_info_str = f"Load: {load:.1f}/10.0 | Capacity: 10.0"
        except Exception as e:
            print(f"[Hub] Failed to load LBS context: {e}")
        
        # 3. Create USER message
        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            attached_files=attached_files or [],
            meta_info=meta_info_str
        )
        self.conversation_history.append(msg)
        self._save_to_db(msg)
        
        # 4. Prepare messages for LLM
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        formatted_messages = self.llm.format_messages(self.system_prompt, llm_messages)
        
        # 5. Get LLM response
        response = self.llm.complete(formatted_messages, preferred_model=preferred_model)
        
        # 6. Create ASSISTANT message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        self.conversation_history.append(assistant_msg)
        self._save_to_db(assistant_msg)
        
        return response.content
