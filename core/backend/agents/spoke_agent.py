"""
Spoke Agent - Project-specific execution agent
Implements spoke-specific prompt loading and log paths
"""
from pathlib import Path
from typing import List, Optional
from agents.base_agent import BaseAgent
from utils.paths import get_spoke_dir, get_user_global_prompt, get_global_prompt
from models.message import AttachedFile, Message, MessageRole
from models.database import UserSettings, Node, AgentProfile, get_engine, get_session
from uuid import uuid4


class SpokeAgent(BaseAgent):
    """Spoke agent with Spoke-specific logic and file operation tools (per-user)"""
    
    @classmethod
    def get_or_create_spoke_node(cls, user_id: str, spoke_name: str, db_session) -> Node:
        """Find or create a SPOKE node for a user"""
        node = db_session.query(Node).filter(
            Node.user_id == user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ).first()
        
        if not node:
            node_id = str(uuid4())
            node = Node(
                id=node_id,
                user_id=user_id,
                name=spoke_name,
                display_name=spoke_name.replace('_', ' ').title(),
                node_type="SPOKE",
                lbs_access_level="READ_ONLY"
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

    @staticmethod
    def _get_api_key(user_id: str, db_session=None) -> Optional[str]:
        """Retrieve and decrypt Gemini API key for the user"""
        if not user_id:
            return None
            
        from utils.encryption import decrypt_string
        
        session = db_session or get_session(get_engine())
        try:
            settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
                encrypted_key = settings.ai_config["gemini_api_key"]
                if encrypted_key == "********":
                    return None
                return decrypt_string(encrypted_key)
        except Exception as e:
            print(f"[SpokeAgent] Failed to retrieve/decrypt API key: {e}")
        finally:
            if not db_session:
                session.close()
        return None

    def __init__(self, user_id: str, spoke_name: str, db_session, node_id: Optional[str] = None):
        self.user_id = user_id
        self.spoke_name = spoke_name
        self.db_session = db_session
        
        # Ensure we have a node_id
        if not node_id:
            node = self.get_or_create_spoke_node(user_id, spoke_name, db_session)
            node_id = node.id
            
        api_key = self._get_api_key(user_id, db_session)
        super().__init__(node_id=node_id, db_session=db_session, api_key=api_key, user_id=user_id)
        
        # Backward compatibility for file tools (can be refactored later to use DB files)
        self.spoke_dir = get_spoke_dir(user_id, spoke_name)
        
        # Add file operation tools after base initialization
        self._setup_tools()
    
    def _setup_tools(self):
        """Setup spoke tools for native function calling via Gemini.
        
        All tools (file operations + Hub communication) are now stored at agent level
        and passed directly to LLM.complete() to persist across LLM refreshes.
        """
        from tools import SPOKE_TOOL_DEFINITIONS, TOOL_FUNCTIONS
        
        # Store tools at agent level (persists across LLM refreshes)
        self.set_agent_tools(SPOKE_TOOL_DEFINITIONS, TOOL_FUNCTIONS)
    
    def load_system_prompt(self) -> str:
        """
        Spoke-specific prompt loading.
        Checks DB AgentProfile first, then fallbacks.
        """
        # 1. Try DB Profile
        profile = self.db_session.query(AgentProfile).filter(
            AgentProfile.node_id == self.node_id,
            AgentProfile.is_active == True
        ).order_by(AgentProfile.version.desc()).first()
        
        spoke_specific = None
        if profile and profile.system_prompt:
            spoke_specific = profile.system_prompt
        
        # 2. Fallback to File or Default
        if not spoke_specific:
            prompt_path = self.spoke_dir / "system_prompt.md"
            if prompt_path.exists():
                spoke_specific = prompt_path.read_text(encoding='utf-8')
        
        # 3. Combine with global prompt
        global_prompt = get_user_global_prompt(self.user_id)
        separator = f"\n\n---\n\n# {self.spoke_name.replace('_', ' ').title()} (Role-Specific Instructions)\n\n" if global_prompt else ""
        
        if spoke_specific:
            return global_prompt + separator + spoke_specific
        
        # Default Spoke prompt
        spoke_default = f"""# {self.spoke_name.replace('_', ' ').title()}

You are a specialized execution agent for the {self.spoke_name} project.
Focus on delivering high-quality work within this context.

## Available Tools

You have access to these tools via Function Calling:

**File Operations:**
- `save_artifact(file_path, content, overwrite=False)` - Save code/docs to artifacts/ 
- `read_reference(file_path)` - Read files from refs/
- `list_directory(sub_dir)` - List files in 'refs' or 'artifacts'

**Hub Communication:**
- `report_to_hub(summary, request)` - Send progress updates or requests to Hub
- `archive_session()` - Archive conversation and start fresh
**LBS Tasks:**
- `list_tasks()` - List tasks for this spoke

**Use these tools to CREATE FILES instead of just showing code!**

## How to Communicate with Hub

When you complete a milestone or need Hub's input, use the `report_to_hub` tool:

Example: 
- `report_to_hub(summary="Analysis phase completed. Key findings: X, Y, Z.")`
- `report_to_hub(summary="Draft complete", request="Please review and approve")`

## Reference Files

Files in your reference library are automatically loaded in your context.
Use them to provide informed, accurate responses.

Work efficiently and communicate proactively with the Hub.
"""
        return global_prompt + separator + spoke_default
    
    def get_node_name(self) -> str:
        return self.spoke_name
    
    def chat(self, user_message: str, attached_files=None, preferred_model=None) -> str:
        """
        Spoke-specific chat - passes tool context with spoke information
        """
        from models.message import AttachedFile
        
        tool_context = {
            'session': self.db_session,
            'user_id': self.user_id,
            'node_id': self.node_id,
            'spoke_name': self.spoke_name,
            'context_name': self.spoke_name
        }
        
        return super().chat(
            user_message, 
            attached_files=attached_files, 
            preferred_model=preferred_model,
            tool_context=tool_context
        )
