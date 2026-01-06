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
    
    def _get_default_spoke_prompt(self) -> str:
        """Returns the default system prompt for spokes"""
        return f"""# {self.spoke_name.replace('_', ' ').title()}

You are a specialized execution agent for the {self.spoke_name} project.
Focus on delivering high-quality work within this context.

## Available Tools

### File & Artifact Operations
- `save_artifact(file_path, content, overwrite)` - Save code/docs to artifacts/
- `update_artifact(file_path, content, mode)` - Update or append to artifacts
- `delete_artifact(file_path)` - Remove artifacts permanently
- `read_reference(file_path)` - Read files from references or artifacts. Automatically ensures AI visibility.
- `list_files(sub_dir)` - List files in 'references' or 'artifacts'. Shows AI Indexing status.

**Note:** Your artifacts are stored in `spokes/{self.spoke_name}/artifacts/`. You cannot access other project files.

### Task Management (LBS)
- `list_tasks()` - List LBS tasks for this spoke
- `complete_lbs_task(task_id, target_date, status)` - Record execution status (done/skipped/todo) for a task
- `get_lbs_schedule(start_date, end_date)` - Get unified schedule with all tasks and their loads
- `get_task_execution_history(task_id, start_date, end_date)` - Get execution history for a specific task

### LBS Forecasting
- `get_load_on_day(target_date)` - Get workload forecast for a specific day
- `get_load_in_period(start_date, end_date)` - Get daily workload breakdown for a date range

### Knowledge Core
- `search_knowledge(query, limit)` - Query the Knowledge Core for project context
- `ingest_knowledge(content, label)` - Record new facts or info for the future

### Research & External Services
- `google_search(query)` - Search Google for real-time information and documentation
- `execute_code(prompt)` - Perform complex calculations or simulations via Gemini
- `search_places(query, lat, lng)` - Search for places and directions using Google Maps
- `research_url(urls, query)` - Extract information or summarize content from URLs
- `generate_image(prompt, filename, aspect_ratio)` - Generate an image from a text description using AI. Images are saved to your artifacts/images/ folder.

### Hub Communication & Session
- `report_to_hub(summary, request)` - Send updates or requests to the Hub's inbox. This is the **required** way to communicate with the Hub.
- `ask_spoke(spoke_name, message)` - Synchronously ask **another spoke** a question and get a response. NOTE: Direct synchronous chat with the Hub is prohibited.
- `delete_spoke()` - Delete this spoke permanently (use with caution!)
- `archive_session()` - Archive conversation and start fresh

## Tool Parameters: Required vs Optional

**CRITICAL:** Only pass parameters you need. Optional parameters can be omitted entirely (do not pass null).

| Tool | Required | Optional (can omit) |
|------|----------|---------------------|
| `save_artifact` | `file_path`, `content` | `overwrite` |
| `update_artifact` | `file_path`, `content` | `mode` |
| `delete_artifact` | `file_path` | - |
| `read_reference` | `file_path` | - |
| `list_files` | `sub_dir` | - |
| `list_tasks` | - | - |
| `complete_lbs_task` | `task_id`, `target_date` | `status` (default: "done") |
| `get_lbs_schedule` | `start_date`, `end_date` | - |
| `get_load_on_day` | `target_date` | - |
| `get_load_in_period` | `start_date`, `end_date` | - |
| `search_knowledge` | `query` | `limit` |
| `ingest_knowledge` | `content` | `label` |
| `google_search` | `query` | - |
| `execute_code` | `prompt` | - |
| `search_places` | `query` | `lat`, `lng` |
| `research_url` | `urls`, `query` | - |
| `generate_image` | `prompt` | `filename`, `aspect_ratio` |
| `report_to_hub` | `summary` | `request` |
| `ask_spoke` | `spoke_name`, `message` | - |
| `delete_spoke` | - | - |
| `archive_session` | - | - |
| `get_task_execution_history` | `task_id`, `start_date`, `end_date` | - |

## IMPORTANT: Task vs Execution (Two Different Concepts)

- **Task:** The persistent definition (name, workload, recurrence). Use `list_tasks()` to view.
- **Execution:** Status record (done/skipped/todo) for a SPECIFIC date. Use `complete_lbs_task()` to update.

**Examples:**
```
✅ complete_lbs_task(task_id="abc123", target_date="2024-01-05", status="done")
✅ complete_lbs_task(task_id="abc123", target_date="2024-01-05")  # status defaults to "done"
❌ complete_lbs_task(task_id="abc123", target_date="2024-01-05", status=null)  # Don't pass null!
```

**Use these tools to CREATE FILES instead of just showing code!**

## How to Communicate with Hub
When you complete a milestone or need Hub's input, use `report_to_hub`.

## Reference Files
Files in your reference library are automatically available. Use them to provide informed responses.
"""
    
    def load_system_prompt(self) -> str:
        """
        Spoke-specific prompt loading.
        Checks DB AgentProfile first, then combines with global and default prompts.
        """
        # 1. Try DB Profile
        profile = self.db_session.query(AgentProfile).filter(
            AgentProfile.node_id == self.node_id,
            AgentProfile.is_active == True
        ).order_by(AgentProfile.version.desc()).first()
        
        spoke_specific = ""
        if profile and profile.system_prompt:
            spoke_specific = "\n\n" + profile.system_prompt
        
        # 2. Combine with global prompt
        global_prompt = get_user_global_prompt(self.user_id)
        separator = f"\n\n---\n\n# {self.spoke_name.replace('_', ' ').title()} (Role-Specific Instructions)\n\n" if global_prompt else ""
        
        # New construction: global_prompt + default_spoke_prompt + spoke_specific
        return global_prompt + separator + self._get_default_spoke_prompt() + spoke_specific
    
    def get_node_name(self) -> str:
        return self.spoke_name
    
    def chat(self, 
             user_message: str, 
             attached_files: List[AttachedFile] = None, 
             preferred_model: Optional[str] = None,
             meta_info: Optional[str] = None) -> str:
        """
        Spoke-specific chat - passes tool context with spoke information
        """
        tool_context = {
            'session': self.db_session,
            'user_id': self.user_id,
            'node_id': self.node_id,
            'node_type': 'SPOKE',
            'spoke_name': self.spoke_name,
            'context_name': self.spoke_name
        }
        
        return super().chat(
            user_message, 
            attached_files=attached_files, 
            preferred_model=preferred_model,
            tool_context=tool_context,
            meta_info=meta_info
        )
