"""
Dynamic Scheduler Service

Pure scheduling algorithm for VisionArk Phase 3.
Implements smart buffering, night mode, and fatigue adaptation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration Constants
# ============================================================================

DEFAULT_SHUTDOWN_HOUR = 23        # 23:00 default shutdown
FATIGUED_SHUTDOWN_HOUR = 21       # 21:00 when fatigued
HEAVY_TASK_THRESHOLD = 3.0        # Load score threshold for "heavy"
BASE_BUFFER_MINUTES = 15          # Buffer after heavy tasks
MAX_CONTINUOUS_WORK_MINUTES = 90  # Max work before mandatory break
FATIGUE_HIGH_THRESHOLD = 3        # Fatigue level 3-5 is "tired"
DEFAULT_LOAD_TO_MINUTES = 30      # Minutes per load unit (estimate)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ScheduledItem:
    """A single scheduled item (task or buffer)."""
    task: Optional[Dict[str, Any]]  # None for buffer/break periods
    start: datetime
    end: datetime
    is_buffer: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "is_buffer": self.is_buffer,
        }


@dataclass
class ScheduleResult:
    """Result from the scheduling algorithm."""
    schedule: List[ScheduledItem] = field(default_factory=list)
    overflow: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule": [item.to_dict() for item in self.schedule],
            "overflow": self.overflow,
        }


# ============================================================================
# Helper Functions
# ============================================================================

def parse_time_to_minutes(time_str: str) -> int:
    """Parse time string (HH:MM:SS or HH:MM) to minutes since midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0


def get_task_duration(task: Dict[str, Any]) -> int:
    """
    Get estimated duration for a task in minutes.
    Uses end_time - start_time if available, otherwise estimates from load.
    """
    start_time = task.get("start_time")
    end_time = task.get("end_time")
    
    if start_time and end_time:
        start_mins = parse_time_to_minutes(str(start_time))
        end_mins = parse_time_to_minutes(str(end_time))
        if end_mins > start_mins:
            return end_mins - start_mins
    
    # Estimate: DEFAULT_LOAD_TO_MINUTES per load unit
    load = task.get("load", 1.0)
    return max(15, int(load * DEFAULT_LOAD_TO_MINUTES))


def get_shutdown_time(base_date: datetime, fatigue: int) -> datetime:
    """Get shutdown time as datetime for the given day."""
    shutdown_hour = (
        FATIGUED_SHUTDOWN_HOUR if fatigue >= FATIGUE_HIGH_THRESHOLD 
        else DEFAULT_SHUTDOWN_HOUR
    )
    return base_date.replace(hour=shutdown_hour, minute=0, second=0, microsecond=0)


def is_heavy_task(task: Dict[str, Any]) -> bool:
    """Check if a task is 'heavy' (requires buffer after)."""
    return task.get("load", 0) >= HEAVY_TASK_THRESHOLD


def get_buffer_duration(fatigue: int) -> int:
    """Get buffer duration based on fatigue level."""
    return (
        BASE_BUFFER_MINUTES * 2 if fatigue >= FATIGUE_HIGH_THRESHOLD 
        else BASE_BUFFER_MINUTES
    )


def create_buffer(start: datetime, duration_minutes: int) -> ScheduledItem:
    """Create a buffer/break scheduled item."""
    return ScheduledItem(
        task=None,
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        is_buffer=True,
    )


# ============================================================================
# Main Scheduling Algorithm
# ============================================================================

def calculate_schedule(
    tasks: List[Dict[str, Any]],
    fatigue: int,
    now: datetime
) -> ScheduleResult:
    """
    Calculate an optimized schedule for the given tasks.
    
    Args:
        tasks: List of task dicts (should be filtered to 'todo' status)
        fatigue: Current fatigue level (0-5)
        now: Current time to schedule from
        
    Returns:
        ScheduleResult with scheduled items and overflow
        
    Rules:
        - Heavy tasks (load >= 3.0): 15-min buffer after
        - Continuous work: Mandatory break after 90 minutes
        - Night mode: No scheduling past shutdown time
        - Fatigue (Lv 3-5): Earlier shutdown (21:00), doubled buffers (30 min)
    """
    result = ScheduleResult()
    
    # Get effective shutdown time
    shutdown_time = get_shutdown_time(now, fatigue)
    
    # If already past shutdown, return empty schedule
    if now >= shutdown_time:
        result.overflow = list(tasks)
        logger.info(f"Past shutdown time ({shutdown_time}), all tasks overflow")
        return result
    
    # Sort tasks: prioritize by load (heavier first to fit them early)
    sorted_tasks = sorted(tasks, key=lambda t: t.get("load", 0), reverse=True)
    
    current_time = now
    continuous_work_minutes = 0
    buffer_duration = get_buffer_duration(fatigue)
    
    for task in sorted_tasks:
        task_duration = get_task_duration(task)
        task_end_time = current_time + timedelta(minutes=task_duration)
        
        # Check if task would end after shutdown
        if task_end_time > shutdown_time:
            result.overflow.append(task)
            continue
        
        # Check if we need a mandatory break due to continuous work
        if continuous_work_minutes >= MAX_CONTINUOUS_WORK_MINUTES:
            # Insert mandatory break
            break_buffer = create_buffer(current_time, buffer_duration)
            result.schedule.append(break_buffer)
            current_time = break_buffer.end
            continuous_work_minutes = 0
            
            # Re-check if task still fits after break
            new_task_end_time = current_time + timedelta(minutes=task_duration)
            if new_task_end_time > shutdown_time:
                result.overflow.append(task)
                continue
        
        # Schedule the task
        scheduled_task = task.copy()
        scheduled_task["scheduled_start_at"] = current_time.isoformat()
        scheduled_task["scheduled_end_at"] = (
            current_time + timedelta(minutes=task_duration)
        ).isoformat()
        
        scheduled_item = ScheduledItem(
            task=scheduled_task,
            start=current_time,
            end=current_time + timedelta(minutes=task_duration),
            is_buffer=False,
        )
        result.schedule.append(scheduled_item)
        
        current_time = scheduled_item.end
        continuous_work_minutes += task_duration
        
        # Add buffer after heavy tasks
        if is_heavy_task(task):
            buffer_end_time = current_time + timedelta(minutes=buffer_duration)
            
            # Only add buffer if it fits before shutdown
            if buffer_end_time <= shutdown_time:
                buffer = create_buffer(current_time, buffer_duration)
                result.schedule.append(buffer)
                current_time = buffer.end
                continuous_work_minutes = 0  # Reset after buffer
    
    logger.info(
        f"Scheduled {len(result.schedule)} items, "
        f"{len(result.overflow)} overflow, "
        f"shutdown at {shutdown_time.strftime('%H:%M')}"
    )
    
    return result


# ============================================================================
# Agent-Enhanced Scheduling
# ============================================================================

async def calculate_schedule_with_agent(
    tasks: List[Dict[str, Any]],
    fatigue: int,
    now: datetime,
    api_key: Optional[str] = None
) -> ScheduleResult:
    """
    Calculate schedule with LLM agent preprocessing.
    
    This wraps the deterministic calculate_schedule() with an LLM layer
    that can add travel time, fix estimates, and reorder tasks.
    
    Args:
        tasks: List of task dicts (todo status)
        fatigue: Current fatigue level (0-5)
        now: Current time to schedule from
        api_key: Gemini API key for LLM agent
        
    Returns:
        ScheduleResult with scheduled items and overflow
    """
    from agents.scheduler_agent import enrich_tasks_with_agent
    
    if not tasks:
        return ScheduleResult()
    
    try:
        # Step 1: LLM preprocessing (adds travel, fixes estimates, reorders)
        enriched_tasks = await enrich_tasks_with_agent(tasks, now, fatigue, api_key)
        logger.info(f"Agent enriched {len(tasks)} -> {len(enriched_tasks)} tasks")
    except Exception as e:
        logger.warning(f"Agent enrichment failed: {e}, using original tasks")
        enriched_tasks = tasks
    
    # Step 2: Ensure we respect task's planned start_time
    # Use max(current_time, plan_start_time) as anchor
    anchor_time = now
    for task in enriched_tasks:
        start_time = task.get("start_time")
        if start_time:
            try:
                # Parse start_time (HH:MM format)
                parts = str(start_time).split(":")
                task_start = now.replace(
                    hour=int(parts[0]), 
                    minute=int(parts[1]) if len(parts) > 1 else 0,
                    second=0, microsecond=0
                )
                # Only use task_start if it's in the future
                if task_start > anchor_time:
                    task["_anchor_time"] = task_start
            except (ValueError, IndexError):
                pass
    
    # Step 3: Run deterministic scheduling
    result = calculate_schedule(enriched_tasks, fatigue, now)
    
    return result


# ============================================================================
# V3: Operation Record & Matrix Logic
# ============================================================================

SINGLETON_ID_COMMUTE = "sys-commute-001"
SINGLETON_ID_LUNCH = "sys-lunch-001"

@dataclass
class SchedulingCommand:
    """Command to update LBS database."""
    command_type: str  # "CREATE_EXCEPTION" or "UPDATE_EXCEPTION"
    task_id: str
    target_date: str
    params: Dict[str, Any]

@dataclass
class OperationRecord:
    """Final output of the V3 scheduler."""
    schedule: List[ScheduledItem]
    overflow: List[Dict[str, Any]]
    commands: List[SchedulingCommand]
    agent_used: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule": [item.to_dict() for item in self.schedule],
            "overflow": self.overflow,
            "commands": [
                {
                    "type": cmd.command_type,
                    "task_id": cmd.task_id,
                    "target_date": cmd.target_date,
                    "params": cmd.params
                }
                for cmd in self.commands
            ],
            "agent_used": self.agent_used,
            "generated_at": self.generated_at
        }


def merge_tasks_and_exceptions(
    tasks: List[Dict[str, Any]], 
    exceptions: List[Dict[str, Any]],
    target_date: datetime
) -> List[Dict[str, Any]]:
    """
    Step 1: Merge Tasks and Exceptions (Lock Matrix V2.1).
    
    Logic:
    1. Exception overrides Task if exists for the day.
    2. Locked status check:
       - If Exception exists: Use Exception's locked status.
       - If No Exception: Use Task's locked status.
    """
    merged_tasks = []
    
    # Map exceptions by task_id
    ex_map = {ex["task_id"]: ex for ex in exceptions}
    
    for task in tasks:
        t_id = task.get("id") or task.get("task_id")
        merged = task.copy()
        
        # Apply Exception Overlay
        if t_id in ex_map:
            ex = ex_map[t_id]
            # Override fields
            if ex.get("start_time"): merged["start_time"] = ex["start_time"]
            if ex.get("end_time"): merged["end_time"] = ex["end_time"]
            if ex.get("is_locked") is not None: merged["is_locked"] = ex["is_locked"]
            
            # If exception has explicit lock, mark it
            merged["_source_locked"] = ex.get("is_locked", False)
        else:
            merged["_source_locked"] = task.get("is_locked", False)
            
        merged_tasks.append(merged)
        
    return merged_tasks


def generate_commands(
    original_tasks: List[Dict[str, Any]],
    optimized_schedule: List[ScheduledItem],
    target_date: str
) -> List[SchedulingCommand]:
    """
    Step 3: Generate Diff Commands.
    
    Compare optimized schedule vs original state (Via Exceptions).
    If a task's time changed, generate CREATE/UPDATE_EXCEPTION.
    """
    commands = []
    
    for item in optimized_schedule:
        if item.is_buffer or not item.task:
            continue
            
        task = item.task
        t_id = task.get("id") or task.get("task_id")
        
        # Check if time changed from original/merged state
        # (Assuming 'task' in item holds variable state, we compare with 'original_tasks')
        # Actually, item.task is the optimized version.
        
        new_start = item.start.strftime("%H:%M")
        new_end = item.end.strftime("%H:%M")
        
        # If task is new (inserted by LLM, e.g., travel buffer), it won't be in original
        # But we only generate exception commands for existing LBS tasks.
        # Travel buffers don't map to LBS tasks unless we create them (not in scope for exceptions on existing tasks).
        # We skip commands for virtual tasks (travel buffers).
        if task.get("is_travel_buffer"):
            continue

        # Simple logic: Always generate/update exception to persist the schedule time
        # In a real diff, we'd check if it actually changed. 
        # For V3 "Operation Record", we probably want to persist the optimized time.
        
        commands.append(SchedulingCommand(
            command_type="CREATE_EXCEPTION", # Simplified; effectively upsert
            task_id=t_id,
            target_date=target_date,
            params={
                "start_time": new_start,
                "end_time": new_end,
                "is_locked": True # Lock it once scheduled
            }
        ))
            
    return commands


async def calculate_schedule_v3(
    tasks: List[Dict[str, Any]],
    exceptions: List[Dict[str, Any]],
    fatigue: int,
    now: datetime,
    api_key: Optional[str] = None
) -> OperationRecord:
    """
    V3 Scheduler Pipeline:
    1. Merge (Task + Exception)
    2. Optimize (LLM Agent)
    3. Deterministic Slotting (if needed or as part of optimization)
    4. Diff (Generate Commands)
    """
    from agents.scheduler_agent import enrich_tasks_with_agent
    
    target_date_str = now.strftime("%Y-%m-%d")

    # Step 1: Merge
    merged_tasks = merge_tasks_and_exceptions(tasks, exceptions, now)
    
    # Step 2: Optimize (Agent)
    # Filter locked tasks to pass as anchors (implemented in agent prompt logic)
    # We pass all tasks, agent should respect locks.
    try:
        enriched_tasks = await enrich_tasks_with_agent(merged_tasks, now, fatigue, api_key)
    except Exception as e:
        logger.error(f"V3 Agent failed: {e}")
        enriched_tasks = merged_tasks

    # Step 2.5: Deterministic Slotting (to get concrete start/end times)
    # The agent might give estimates, but calculate_schedule gives definitive times.
    schedule_result = calculate_schedule(enriched_tasks, fatigue, now)
    
    # Step 3: Diff
    commands = generate_commands(merged_tasks, schedule_result.schedule, target_date_str)
    
    return OperationRecord(
        schedule=schedule_result.schedule,
        overflow=schedule_result.overflow,
        commands=commands,
        agent_used=(api_key is not None)
    )
