"""
Hub Agent - Central orchestration and LBS management
PM role with strategic decision-making and command execution
"""
from datetime import date, timedelta, datetime
from sqlalchemy.orm import Session
from pathlib import Path

from agents.base_agent import BaseAgent
from services.lbs_engine import LBSEngine
from utils.paths import get_hub_dir


class HubAgent(BaseAgent):
    """Hub orchestration agent with LBS awareness and command execution"""
    
    def __init__(self, db_session: Session):
        super().__init__(agent_type="hub", context_name="hub")
        self.db = db_session
        self.lbs_engine = LBSEngine(db_session)
        
        # Ensure hub_data directory exists and set up chat log
        hub_dir = get_hub_dir()
        hub_dir.mkdir(parents=True, exist_ok=True)
        self.chat_log_path = hub_dir / "chat.log"
        
        # Load conversation history if exists
        self._load_history()
    
    def _get_hub_prompt(self) -> str:
        """
        Override base Hub prompt with enhanced LBS management capabilities
        Per BLUEPRINT.md Section 2.3.B.3 (Processing)
        """
        return f"""# Hub Agent - Strategic Task Orchestrator

You are the **Hub Agent**, the central coordinator of the AI TaskManagement OS. Your primary role is to:

1. **Manage the LBS (Load Balancing System)**: Create and optimize tasks using commands
2. **Process Inbox Messages**: Review and act on reports from Spokes about progress, blockers, and needs
3. **Make Strategic Decisions**: Balance workload, adjust priorities, and reallocate resources
4. **Coordinate Between Spokes**: Facilitate information flow and dependencies

## Task Management via Commands

You can NOW create tasks directly using the `/create_task` command!

### Example Task Creation:
User: "Add a weekly meeting every Monday, workload 2.0"
You: "I'll create that task for you.

/create_task name="Weekly Meeting" spoke="meetings" workload=2.0 rule=WEEKLY days=mon

Done! The task is now in your schedule."

User: "I need to write my thesis chapter by December 15th, it's a lot of work"
You: "I'll add that high-priority task.

/create_task name="Thesis Chapter" spoke="research" workload=8.0 rule=ONCE due=2025-12-15

Created! This is a major task (8.0 workload) - I recommend not scheduling other heavy tasks that week."

## Strategic Resource Allocation (BLUEPRINT Requirement)

When a Spoke reports "need more time for experiment":
1. Analyze current LBS schedule (I provide auto-injected load data)
2. Identify low-priority tasks that could be deferred  
3. Propose trade-offs: "I recommend deferring Life Admin tasks next week (freeing 4.0 load) to accommodate the experiment"
4. **Execute adjustments** using `/create_task` or guide user to Tasks page

## Available Commands

### Spoke Management:
1. `/create_spoke <name>` - Create new project Spoke
2. `/check_inbox` - Review pending Spoke messages
3. `/send_message <spoke_name> <message>` - Send message to Spoke
4. `/kill <spoke_name>` - Delete Spoke permanently
5. `/archive [spoke_name]` - Archive Spoke or Hub conversation

### Task Management (NEW!):
1. `/create_task name="X" spoke="Y" workload=N [parameters]` - Create LBS task directly!
   - Required: name, workload (0-10)
   - Optional: spoke (defaults to context), rule (ONCE/WEEKLY/EVERY_N_DAYS/MONTHLY_DAY)
   - For ONCE: due=YYYY-MM-DD
   - For WEEKLY: days=mon,tue,wed,thu,fri,sat,sun
   - For EVERY_N_DAYS: interval=N
   - For MONTHLY_DAY: day=1-31

**When user asks to create a task, USE THIS COMMAND!**

## Communication Style

You are a strategic advisor and coordinator. When user asks about tasks or schedule:
1. **Create** tasks using `/create_task` command
2. **Analyze** current LBS status (auto-injected in context)
3. **Suggest** optimizations and trade-offs
4. **Execute** approved changes immediately

Example Strategic Response:
User: "I'm overwhelmed this week"
You: "Looking at your LBS data, this week averages 8.5/10 capacity - that's high! 
I can create a 'Recovery Day' task for Friday to ensure you don't overload:

/create_task name="Recovery Day" spoke="wellness" workload=0.5 rule=ONCE due=2025-12-06

Or I can defer your 'Literature Review' to next week. Which would you prefer?"

Current Date: {datetime.now().strftime("%Y-%m-%d")}

Remember: You can CREATE tasks directly now! Use the command when users ask for task management!
"""
    
    def _load_history(self):
        """Load conversation history from chat.log"""
        if not self.chat_log_path.exists():
            return
        
        try:
            with open(self.chat_log_path, 'r', encoding='utf-8') as f:
                current_role = None
                current_content = []
                
                for line in f:
                    line = line.strip()
                    if line.startswith("User:"):
                        if current_role:
                            self.conversation_history.append({
                                "role": current_role,
                                "content": "\n".join(current_content)
                            })
                        current_role = "user"
                        current_content = [line[5:].strip()]
                    elif line.startswith("Assistant:"):
                        if current_role:
                            self.conversation_history.append({
                                "role": current_role,
                                "content": "\n".join(current_content)
                            })
                        current_role = "assistant"
                        current_content = [line[10:].strip()]
                    elif line and current_role:
                        current_content.append(line)
                
                # Add last message
                if current_role and current_content:
                    self.conversation_history.append({
                        "role": current_role,
                        "content": "\n".join(current_content)
                    })
        except Exception as e:
            print(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Save conversation history to chat.log"""
        try:
            with open(self.chat_log_path, 'w', encoding='utf-8') as f:
                for msg in self.conversation_history:
                    role_label = "User" if msg["role"] == "user" else "Assistant"
                    f.write(f"{role_label}: {msg['content']}\n\n")
        except Exception as e:
            print(f"Failed to save history: {e}")
    
    def chat_with_context(self, user_message: str) -> str:
        """
        Chat with automatic LBS context injection and history persistence
        """
        # Get current LBS status
        today = date.today()
        today_load = self.lbs_engine.calculate_daily_load(today)
        weekly_stats = self.lbs_engine.get_weekly_stats(today - timedelta(days=today.weekday()))
        
        # Build enhanced context
        context_info = f"""
## Current LBS Status (Auto-injected)
- **Today ({today})**: Load {today_load['adjusted_load']:.1f} / {today_load['cap']} ({today_load['level']})
- **Today Task Count**: {today_load['task_count']} tasks across {today_load['unique_contexts']} contexts
- **Weekly Average**: {weekly_stats['average_load']:.1f}
- **Over-capacity Days This Week**: {weekly_stats['over_days']}
- **Recovery Rate**: {weekly_stats['recovery_rate']:.1f}%

----

User Message: {user_message}
"""
        
        # Use chat() which maintains conversation history
        response = self.chat(context_info)
        
        # Save history after each exchange
        self._save_history()
        
        return response
    
    def analyze_inbox(self, inbox_count: int) -> str:
        """Analyze pending inbox messages"""
        prompt = f"""You have {inbox_count} unprocessed messages in the Inbox from Spokes.
        
Please advise:
1. Should I review the Inbox now or later?
2. Any anticipated risks from delayed processing?
"""
        return self.chat(prompt)
    
    def suggest_reschedule(self, overloaded_date: date) -> str:
        """Suggest rescheduling for an overloaded date"""
        load_data = self.lbs_engine.calculate_daily_load(overloaded_date)
        
        prompt = f"""Date {overloaded_date} is overloaded:
- Adjusted Load: {load_data['adjusted_load']:.1f} / {load_data['cap']}
- Status: {load_data['level']}
- Tasks: {load_data['task_count']}

Tasks for that day:
{chr(10).join(f"- [{t['context']}] {t['task_name']} (Load: {t['load']})" for t in load_data['tasks'])}

Please suggest which tasks should be rescheduled and to which dates.
"""
        return self.chat(prompt)
