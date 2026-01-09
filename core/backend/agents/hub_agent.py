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
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from uuid import uuid4
import time


class HubAgent(BaseAgent):
    """Hub agent with Hub-specific logic and LBS integration (per-user)"""
    
    @staticmethod
    async def _get_api_key(user_id: str, db_session: AsyncSession = None) -> Optional[str]:
        """Retrieve and decrypt Gemini API key for the user"""
        print(f"[HubAgent._get_api_key] Called with user_id={user_id}")
        if not user_id:
            return None
            
        from utils.encryption import decrypt_string
        
        # Use select() for async session
        from sqlalchemy import select
        result = await db_session.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = result.scalars().first()
        
        if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
            encrypted_key = settings.ai_config["gemini_api_key"]
            if encrypted_key == "********":
                return None
            return decrypt_string(encrypted_key)
        
        return None

    @classmethod
    async def get_or_create_hub_node(cls, user_id: str, db_session: AsyncSession) -> Node:
        """Find or create the HUB node for a user"""
        from sqlalchemy import select
        result = await db_session.execute(
            select(Node).filter(
                Node.user_id == user_id,
                Node.node_type == "HUB"
            )
        )
        node = result.scalars().first()
        
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
            await db_session.commit()
            
            # Create default profile
            profile = AgentProfile(
                id=str(uuid4()),
                node_id=node_id,
                system_prompt=None,
                is_active=True
            )
            db_session.add(profile)
            await db_session.commit()
            
        return node

    def __init__(self, user_id: str, db_session: AsyncSession, node_id: str, api_key: Optional[str] = None):
        super().__init__(node_id=node_id, db_session=db_session, api_key=api_key, user_id=user_id)
        self._setup_tools()

    @classmethod
    async def create(cls, user_id: str, db_session: AsyncSession):
        """Async factory method for HubAgent"""
        node = await cls.get_or_create_hub_node(user_id, db_session)
        api_key = await cls._get_api_key(user_id, db_session)
        agent = cls(user_id=user_id, db_session=db_session, node_id=node.id, api_key=api_key)
        await agent.initialize()
        return agent
    
    def _setup_tools(self):
        """Configure native function calling tools for Hub agent (stored at agent level)"""
        from tools import HUB_TOOL_DEFINITIONS, TOOL_FUNCTIONS
        
        # Store tools at agent level (persists across LLM refreshes)
        self.set_agent_tools(HUB_TOOL_DEFINITIONS, TOOL_FUNCTIONS)

    def _get_default_hub_prompt(self) -> str:
        # Default Hub prompt with tools and LBS info
        hub_default = """# Hub Agent (Project Manager Role)

You are the central orchestration agent (Hub) responsible for:
- Managing the LBS (Load Balancing System) across all projects
- Processing reports from Spoke agents
- Making strategic resource allocation decisions
- Preventing cognitive overload
- Maintaining the long-term project Knowledge Core
## Your Responsibilities
1. Monitor daily and weekly load scores using forecasting tools
2. Warn when capacity (CAP) is approaching or exceeded
3. Suggest task rescheduling when necessary
4. Process Inbox messages from Spokes and provide analysis
5. Record and retrieve project-wide institutional knowledge
6. Manage high-level project artifacts and references
7. **Process Synchronous Coordination Requests** from Spokes and provide immediate decisions/actions.

## Available Tools

### Project Management
- `create_spoke(spoke_name, custom_prompt)` - Create a new project workspace
- `create_multiple_spokes(spoke_names)` - Create several project workspaces at once
- `delete_spoke(spoke_name)` - Delete a spoke permanently

### Task Management (LBS)
- `create_task(task_name, workload, spoke, rule_type, due_date, days, interval_days, month_day, notes)` - Create an LBS task
- `list_tasks(context)` - List existing tasks, optionally filtered by context/spoke
- `update_task_details(task_id, ...)` - Update task properties including recurrence rules
- `delete_task_by_id(task_id)` - Delete a task permanently
- `complete_lbs_task(task_id, target_date, status)` - Record execution status (done/skipped/todo/in_progress) for a task on a specific date
- `update_user_condition(cognitive_fatigue, target_date, note)` - Set user's fatigue level (0=Energetic, 3=Tired, 5=Limit).
- `get_current_condition(target_date)` - Check the currently registered fatigue level.
- `reset_user_condition(target_date)` - Reset/Clear the fatigue level (back to default Lv0).

### LBS Forecasting & Schedule
- `get_load_on_day(target_date)` - Get workload forecast for a specific day
- `get_load_in_period(start_date, end_date)` - Get daily workload breakdown for a date range
- `get_lbs_schedule(start_date, end_date)` - Get unified schedule with all tasks and their loads
- `get_task_execution_history(task_id, start_date, end_date)` - Get execution history for a specific task
- `run_cleanup_cycle(target_date_range)` - Run self-maintenance to detect overloads and stale tasks.

### Knowledge Core
- `search_knowledge(query, limit)` - Query the knowledge repository for synthesized context
- `ingest_knowledge(content, label)` - Record new facts or info into long-term memory

### File & Artifact Operations
- `list_files(sub_dir)` - List files in 'refs', 'artifacts', or 'files'. Shows AI Indexing status.
- `read_reference(file_path)` - Read a file. Automatically ensures AI visibility via Gemini File API.
- `save_artifact(file_path, content, overwrite)` - Save content to artifacts directory
- `update_artifact(file_path, content, mode)` - Update or append to an existing artifact
- `delete_artifact(file_path)` - Permanently delete an artifact

**Note:** Your artifacts are stored in `hub_data/artifacts/`. You cannot directly access Spoke files.

### Research & External Services
- `google_search(query)` - Search Google for real-time information and documentation
- `execute_code(prompt)` - Perform complex calculations or simulations via Gemini code execution
- `search_places(query, lat, lng)` - Search for places and directions using Google Maps grounding
- `research_url(urls, query)` - Extract information or summarize content from specific URLs
- `generate_image(prompt, filename, aspect_ratio)` - Generate an image from a text description using AI. Images are saved to your artifacts/images/ folder.

### MD & Plan Management (Extended Tools)
- `get_md_structure(file_path)` - Extract heading hierarchy from a Markdown file
- `read_md_section(file_path, section_title)` - Read a specific section of a Markdown file
- `update_md_section(file_path, section_title, content, mode)` - Update or append to a Markdown section
- `init_plan(goal, strategy)` - Initialize `PLAN.md` with a standard template
- `get_current_status()` - Get `# Current Status` from `PLAN.md`
- `update_plan_progress(summary, percent_complete)` - Update progress and logs in `PLAN.md`

### Communication & Session
- `check_inbox()` - Check for new messages in the Hub's inbox. Returns summaries and IDs.
- `read_all_inbox_messages()` - Read the full content and payload of all pending inbox messages at once.
- `ask_spoke(spoke_name, message)` - Synchronously ask a project-specific Spoke a question and get a response. Interaction is recorded in histories.
- `archive_session()` - Archive current conversation and start fresh

## Tool Parameters: Required vs Optional

**CRITICAL:** Only pass parameters you need. Optional parameters can be omitted entirely (do not pass null).

| Tool | Required | Optional (can omit) |
|------|----------|---------------------|
| `create_spoke` | `spoke_name` | `custom_prompt` |
| `create_multiple_spokes` | `spoke_names` | - |
| `delete_spoke` | `spoke_name` | - |
| `create_task` | `task_name`, `workload` | `spoke`, `rule_type`, `due_date`, `days`, `interval_days`, `month_day`, `notes` |
| `list_tasks` | - | `context` |
| `update_task_details` | `task_id` | `task_name`, `workload`, `spoke`, `active`, `notes`, `rule_type`, `due_date`, `days`, `interval_days`, `month_day` |
| `delete_task_by_id` | `task_id` | - |
| `complete_lbs_task` | `task_id`, `target_date` | `status` (default: "done") |
| `update_user_condition` | `cognitive_fatigue` | `target_date`, `note` |
| `get_current_condition` | - | `target_date` |
| `reset_user_condition` | - | `target_date` |
| `get_load_on_day` | `target_date` | - |
| `get_load_in_period` | `start_date`, `end_date` | - |
| `get_lbs_schedule` | `start_date`, `end_date` | - |
| `search_knowledge` | `query` | `limit` |
| `ingest_knowledge` | `content` | `label` |
| `list_files` | `sub_dir` | - |
| `read_reference` | `file_path` | - |
| `save_artifact` | `file_path`, `content` | `overwrite` |
| `update_artifact` | `file_path`, `content` | `mode` |
| `delete_artifact` | `file_path` | - |
| `google_search` | `query` | - |
| `execute_code` | `prompt` | - |
| `search_places` | `query` | `lat`, `lng` |
| `research_url` | `urls`, `query` | - |
| `generate_image` | `prompt` | `filename`, `aspect_ratio` |
| `check_inbox` | - | - |
| `read_all_inbox_messages` | - | - |
| `process_inbox_message` | `message_id`, `action` | - |
| `ask_spoke` | `spoke_name`, `message` | - |
| `archive_session` | - | - |
| `get_task_execution_history` | `task_id`, `start_date`, `end_date` | - |
| `run_cleanup_cycle` | - | `target_date_range` |
| `get_md_structure` | `file_path` | - |
| `read_md_section` | `file_path`, `section_title` | - |
| `update_md_section` | `file_path`, `section_title`, `content` | `mode` |
| `init_plan` | `goal`, `strategy` | - |
| `get_current_status` | - | - |
| `update_plan_progress` | `summary` | `percent_complete` |

**Examples:**
```
✅ create_task(task_name="Review PR", workload=2.0)  # Only required params
✅ create_task(task_name="Weekly sync", workload=1.5, rule_type="WEEKLY", days="mon,wed,fri")
❌ create_task(task_name="Test", workload=1.0, spoke=null, due_date=null)  # Don't pass null!
```

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
2. `WEEKLY` - Recurring on specific days (use `days` array: ["mon", "tue", etc.])
3. `EVERY_N_DAYS` - Recurring every N days (use `interval_days`)
4. `MONTHLY_DAY` - Specific day each month (use `month_day`)

## IMPORTANT: Task vs Execution (Two Different Concepts)

The LBS system has TWO separate data models. Choosing the wrong tool will cause errors.

### Task (Definition/Template)
- **What it is:** The persistent master record defining WHAT to do, WHEN it recurs, and HOW much load it carries.
- **Fields:** `task_id`, `task_name`, `context`, `base_load_score`, `rule_type`, `due_date`, `days`, `active`, `notes`
- **Lifespan:** Created once, exists until deleted. Recurrence rules generate scheduled instances.
- **Tools to use:**
  - `create_task()` - Create a new task definition
  - `list_tasks()` - List task definitions
  - `update_task_details()` - Modify task properties (name, workload, recurrence, etc.)
  - `delete_task_by_id()` - Permanently delete a task definition

### Execution (Daily Status Record)
- **What it is:** A status record for a SPECIFIC task on a SPECIFIC date. Records whether the task was completed, skipped, or still pending.
- **Fields:** `task_id`, `target_date`, `status` (done/skipped/todo/in_progress)
- **Lifespan:** Created when user marks a task's status for a particular day. One record per task per date.
- **Tools to use:**
  - `complete_lbs_task(task_id, target_date, status)` - Record execution status for a date
  - `get_lbs_schedule(start_date, end_date)` - View tasks + their execution status

### Common Mistakes to Avoid
- ❌ DO NOT use `update_task_details` to mark a task as "done" - that changes the definition, not the daily status!
- ❌ DO NOT use `complete_lbs_task` to change task name or workload - that's for execution status only!
- ✅ To mark today's task as done: `complete_lbs_task(task_id, "2024-01-05", "done")`
- ✅ To change a task's workload: `update_task_details(task_id, workload=5.0)`

## Communication Style
- Strategic and meta-level (don't get into project details)
- Data-driven (cite load scores, capacities)
- Proactive (warn about bottlenecks before they occur)
- Use tools when appropriate to take action
"""
        return hub_default
    
    async def load_system_prompt(self) -> str:
        """Hub-specific prompt loading with async DB calls"""
        from sqlalchemy import select
        result = await self.db_session.execute(
            select(AgentProfile).filter(
                AgentProfile.node_id == self.node_id,
                AgentProfile.is_active == True
            ).order_by(AgentProfile.version.desc())
        )
        profile = result.scalars().first()
        
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
        
        # 4. Load latest archived summary
        previous_context = await self._load_latest_summary(context_type="hub", context_name="hub")
        
        return global_prompt + separator + hub_prompt + previous_context
    
    def get_node_name(self) -> str:
        return "hub"
    
    async def chat(self, user_message: str, attached_files: List[AttachedFile] = None, preferred_model: Optional[str] = None) -> str:
        """Hub-specific chat overrides BaseAgent.chat to inject LBS context"""
        from services.lbs_client import LBSClient
        from sqlalchemy import select
        from models.database import ServiceRegistry
        from utils.encryption import decrypt_string
        
        meta_info_str = None
        try:
            # Get user's LBS config
            lbs_api_key = None
            lbs_url = None
            
            result = await self.db_session.execute(
                select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == self.user_id,
                    ServiceRegistry.service_name == "lbs"
                )
            )
            service = result.scalars().first()
            
            if service:
                lbs_url = service.base_url
                if service.api_key_encrypted:
                    try:
                        lbs_api_key = decrypt_string(service.api_key_encrypted)
                    except Exception: pass
            
            client = LBSClient(base_url=lbs_url, api_key=lbs_api_key)
            t0 = time.time()
            daily_data = await client.calculate_load(date.today())
            print(f"[Hub/Timing] LBS calculate_load: {time.time()-t0:.2f}s")
            load = daily_data.get("adjusted_load", 0.0)
            meta_info_str = f"Load: {load:.1f}/10.0 | Capacity: 10.0"
        except Exception as e:
            print(f"[Hub] Failed to load LBS context: {e}")
        
        # 3. Use BaseAgent.chat which handles KnowledgeCore integration and LLM calls
        tool_context = {
            'session': self.db_session,
            'user_id': self.user_id,
            'node_id': self.node_id,
            'node_type': 'HUB',
            'context_name': 'hub'
        }
        
        return await super().chat(
            user_message,
            attached_files=attached_files,
            preferred_model=preferred_model,
            tool_context=tool_context,
            meta_info=meta_info_str
        )
