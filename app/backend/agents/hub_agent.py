"""
Hub Agent - Central orchestration agent
Implements hub-specific prompt loading, log paths, and LBS integration
"""
from pathlib import Path
from typing import List
from agents.base_agent import BaseAgent
from utils.paths import get_hub_dir, get_global_prompt
from models.message import Message, MessageRole, AttachedFile
from datetime import date


class HubAgent(BaseAgent):
    """Hub agent with Hub-specific logic and LBS integration"""
    
    def __init__(self):
        # Set hub_dir BEFORE calling super().__init__() 
        # because _load_history_from_log() needs it
        self.hub_dir = get_hub_dir()
        super().__init__()

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
        Hub-specific prompt loading with full command and LBS documentation
        Prepends global system prompt for shared guidelines
        """
        # Start with global prompt
        global_prompt = get_global_prompt()
        separator = "\n\n---\n\n# Hub Agent (Role-Specific Instructions)\n\n" if global_prompt else ""
        
        # Load Hub-specific prompt
        prompt_path = self.hub_dir / "system_prompt.md"
        hub_prompt = prompt_path.read_text(encoding='utf-8') if prompt_path.exists() else self._get_default_hub_prompt()
        
        # Load Past Archive Summary (This is to keep track of past)
        # ToDo: should be implemented

        return global_prompt + separator + hub_prompt
    
    def get_chat_log_path(self) -> Path:
        """Hub-specific log path"""
        return self.hub_dir / "chat.log"
    
    def chat_with_context(self, user_message: str, db_session=None) -> str:
        """
        Hub-specific chat with LBS context
        Adds meta_info about current load scores as formatted string
        """
        from services.lbs_engine import LBSEngine
        
        # Build LBS context as formatted string
        meta_info_str = None
        if db_session:
            try:
                engine = LBSEngine(db_session)
                today = date.today()
                
                # Get daily load
                daily_load = engine.get_daily_load(today)
                
                # Build formatted meta_info string
                meta_info_str = f"Load: {daily_load:.1f}/10.0 | Capacity: 10.0"
                
            except Exception as e:
                print(f"[Hub] Failed to load LBS context: {e}")
        
        # Create message with meta_info string
        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            meta_info=meta_info_str  # String, not dict!
        )
        
        # Add to history
        self.conversation_history.append(msg)
        
        # Get LLM response
        if not self.system_prompt:
            self.system_prompt = self.load_system_prompt()
        
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        messages = self.llm.format_messages(self.system_prompt, llm_messages)
        response = self.llm.complete(messages)
        
        # Create assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        self.conversation_history.append(assistant_msg)
        
        # Save to log
        self._save_to_log(msg)
        self._save_to_log(assistant_msg)
        
        return response.content
