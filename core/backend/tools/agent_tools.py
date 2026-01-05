"""
Agent Tools - Native Function Calling Implementation
Replaces slash command system with Gemini native function calling
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, date
import uuid

from models.database import Node, AgentProfile, ChatSession, InboxQueue, ServiceRegistry
from services.lbs_client import LBSClient
from services.knowledge_core_service import KnowledgeCoreService
import asyncio
from pathlib import Path


# ==============================================================================
# Tool Execution Results
# ==============================================================================

class ToolResult:
    """Standard result format for tool execution"""
    def __init__(self, success: bool, message: str, data: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.data = data or {}
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data
        }


# ==============================================================================
# LBS Client Helper
# ==============================================================================

def _get_lbs_client(user_id: str, session: Session) -> LBSClient:
    """Get LBS client with user's registered LBS API key and remote user ID from ServiceRegistry"""
    from models.database import ServiceRegistry
    from utils.encryption import decrypt_string
    
    # Try to get user's registered LBS service config
    lbs_api_key = None
    lbs_url = None
    
    service = session.query(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "lbs"
    ).first()
    
    if service:
        lbs_url = service.base_url
        # Decrypt API key
        if service.api_key_encrypted:
            try:
                lbs_api_key = decrypt_string(service.api_key_encrypted)
            except Exception:
                pass  # Fall back to env var logic in LBSClient if decryption fails
    
    return LBSClient(base_url=lbs_url, api_key=lbs_api_key)


def _get_kc_service(user_id: str, session: Session) -> KnowledgeCoreService:
    """Get KnowledgeCore service for the user"""
    return KnowledgeCoreService(session, user_id)


def _get_file_service(user_id: str, session: Session) -> 'FileService':
    """Get FileService for the user with API key configuration"""
    from models.database import UserSettings
    from utils.encryption import decrypt_string
    from services.file_service import FileService
    
    api_key = None
    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        try:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        except Exception:
            pass
            
    return FileService(session, user_id, api_key=api_key)


def _resolve_agent_artifacts_dir(user_id: str, node_type: str, spoke_name: Optional[str] = None) -> Path:
    """
    Resolve the artifacts directory based on node type.
    Hub -> {user_dir}/hub_data/artifacts
    Spoke -> {user_dir}/spokes/{spoke_name}/artifacts
    """
    from utils.paths import get_user_hub_dir, get_spoke_dir
    
    if node_type == 'HUB':
        base_dir = get_user_hub_dir(user_id)
    elif node_type == 'SPOKE':
        if not spoke_name:
            raise ValueError("spoke_name is required for Spoke agents")
        base_dir = get_spoke_dir(user_id, spoke_name)
    else:
        raise ValueError(f"Unknown node_type: {node_type}")
        
    artifacts_dir = base_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


# ==============================================================================
# Hub Tools - Available to Hub Agent
# ==============================================================================

def create_spoke(
    spoke_name: str,
    custom_prompt: Optional[str] = None,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Create a new Spoke (project workspace) for the user.
    
    Args:
        spoke_name: Name for the new spoke (project)
        custom_prompt: Optional custom system prompt for the spoke
        session: Database session (injected)
        user_id: User ID (injected)
    
    Returns:
        ToolResult with success status and spoke details
    """
    from agents.spoke_agent import SpokeAgent
    
    try:
        # Create DB Node and Profile
        node = SpokeAgent.get_or_create_spoke_node(user_id, spoke_name, session)
        
        if custom_prompt:
            profile = session.query(AgentProfile).filter(
                AgentProfile.node_id == node.id,
                AgentProfile.is_active == True
            ).first()
            if profile:
                profile.system_prompt = custom_prompt
                session.commit()
        
        return ToolResult(
            success=True,
            message=f"✅ Created Spoke: {spoke_name}",
            data={"spoke_name": spoke_name, "node_id": node.id}
        )
    except Exception as e:
        session.rollback()
        return ToolResult(success=False, message=f"Failed to create spoke: {str(e)}")


def create_multiple_spokes(
    spoke_names: List[str],
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Create multiple Spokes (project workspaces) at once.
    
    Args:
        spoke_names: List of names for the new spokes
        session: Database session (injected)
        user_id: User ID (injected)
    
    Returns:
        ToolResult with success status and list of created spokes
    """
    results = []
    errors = []
    
    for name in spoke_names:
        res = create_spoke(spoke_name=name, session=session, user_id=user_id)
        if res.success:
            results.append(name)
        else:
            errors.append(f"{name}: {res.message}")
            
    if not results:
        return ToolResult(success=False, message=f"Failed to create any spokes: {'; '.join(errors)}")
        
    msg = f"✅ Created {len(results)} spokes: {', '.join(results)}"
    if errors:
        msg += f" (Errors: {'; '.join(errors)})"
        
    return ToolResult(
        success=True,
        message=msg,
        data={"created": results, "errors": errors}
    )


def delete_spoke(
    spoke_name: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Delete a spoke (project) permanently.
    
    Args:
        spoke_name: Name of the spoke to delete
        session: Database session (injected)
        user_id: User ID (injected)
    
    Returns:
        ToolResult with success status
    """
    try:
        # Find and archive the node
        node = session.query(Node).filter(
            Node.user_id == user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ).first()
        
        if not node:
            return ToolResult(success=False, message=f"Spoke '{spoke_name}' not found")
        
        node.is_archived = True
        session.commit()
        
        # Clean up LBS tasks
        try:
            client = _get_lbs_client(user_id, session)
            tasks = client.get_tasks(context=spoke_name)
            for t in tasks:
                client.delete_task(t["task_id"])
        except Exception as lbs_err:
            print(f"[DELETE_SPOKE] Warning: Failed to cleanup LBS tasks: {lbs_err}")
        
        return ToolResult(
            success=True,
            message=f"🗑️ Deleted Spoke: {spoke_name}",
            data={"spoke_name": spoke_name, "deleted": True}
        )
    except Exception as e:
        session.rollback()
        return ToolResult(success=False, message=f"Failed to delete spoke: {str(e)}")


def create_task(
    task_name: str,
    workload: float,
    spoke: Optional[str] = None,
    rule_type: str = "ONCE",
    due_date: Optional[str] = None,
    days: Optional[str] = None,
    interval_days: Optional[int] = None,
    month_day: Optional[int] = None,
    notes: Optional[str] = None,
    *,
    session: Session,
    user_id: str,
    context_name: str = "general"
) -> ToolResult:
    """
    Create a new task in the LBS system.
    
    Args:
        task_name: Name of the task
        workload: Load score (0-10)
        spoke: Spoke/context for the task (defaults to current context)
        rule_type: ONCE, WEEKLY, EVERY_N_DAYS, or MONTHLY_DAY
        due_date: Due date for ONCE tasks (YYYY-MM-DD)
        days: Comma-separated days for WEEKLY tasks (e.g., "mon,wed,fri")
        interval_days: Interval for EVERY_N_DAYS tasks
        month_day: Day of the month (1-31) for MONTHLY_DAY tasks
        notes: Additional notes
        session: Database session (injected)
        user_id: User ID (injected)
        context_name: Current context name (injected)
    
    Returns:
        ToolResult with task details
    """
    try:
        task_data = {
            "task_name": task_name,
            "context": spoke or context_name,
            "base_load_score": float(workload),
            "rule_type": rule_type.upper(),
            "active": True,
            "notes": notes
        }
        
        if rule_type.upper() == "ONCE" and due_date:
            task_data["due_date"] = due_date
        
        elif rule_type.upper() == "WEEKLY" and days:
            # Parse comma-separated days into list
            days_list = [d.strip().lower() for d in days.split(",")]
            day_map = {d: True for d in days_list}
            task_data.update({
                "mon": day_map.get("mon", False),
                "tue": day_map.get("tue", False),
                "wed": day_map.get("wed", False),
                "thu": day_map.get("thu", False),
                "fri": day_map.get("fri", False),
                "sat": day_map.get("sat", False),
                "sun": day_map.get("sun", False)
            })
        
        elif rule_type.upper() == "EVERY_N_DAYS" and interval_days:
            task_data["interval_days"] = interval_days

        elif rule_type.upper() == "MONTHLY_DAY" and month_day:
            task_data["month_day"] = month_day
        
        client = _get_lbs_client(user_id, session)
        result = client.create_task(task_data)
        
        return ToolResult(
            success=True,
            message=f"✅ Created task: {task_name} (Workload: {workload})",
            data={"task_id": result.get("task_id"), "task_name": task_name}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to create task: {str(e)}")


def list_tasks(
    context: Optional[str] = None,
    *,
    session: Session,
    user_id: str,
    context_name: str = "general"
) -> ToolResult:
    """
    List tasks from the LBS system.
    
    Args:
        context: Specific context/spoke to filter by. Defaults to current context.
        session: Database session (injected)
        user_id: User ID (injected)
        context_name: Current context name (injected)
    """
    try:
        client = _get_lbs_client(user_id, session)
        target_context = context or context_name
        tasks = client.get_tasks(context=target_context)
        
        if not tasks:
            return ToolResult(
                success=True,
                message=f"No tasks found for context: {target_context}",
                data={"tasks": [], "context": target_context}
            )
        
        # Format tasks for display
        task_info = []
        for t in tasks:
            due = f" due {t.get('due_date')}" if t.get('due_date') else ""
            rule = f" ({t.get('rule_type')})"
            task_info.append(f"  • [{t.get('task_id')}] {t.get('task_name')} - Load: {t.get('base_load_score')}{due}{rule}")
            
        return ToolResult(
            success=True,
            message=f"📋 Tasks for {target_context}:\n" + "\n".join(task_info),
            data={"tasks": tasks, "context": target_context}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to list tasks: {str(e)}")


def update_task_details(
    task_id: str,
    task_name: Optional[str] = None,
    workload: Optional[float] = None,
    spoke: Optional[str] = None,
    active: Optional[bool] = None,
    notes: Optional[str] = None,
    rule_type: Optional[str] = None,
    due_date: Optional[str] = None,
    days: Optional[str] = None,
    interval_days: Optional[int] = None,
    month_day: Optional[int] = None,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Update an existing task in the LBS system.
    
    Args:
        task_id: ID of the task to update
        task_name: New name for the task
        workload: New load score (0-10)
        spoke: New spoke/context to assign the task to
        active: New active status
        notes: New notes
        rule_type: New recurrence rule (ONCE, WEEKLY, EVERY_N_DAYS, MONTHLY_DAY)
        due_date: New due date for ONCE tasks (YYYY-MM-DD)
        days: Comma-separated days for WEEKLY tasks (e.g., "mon,wed,fri")
        interval_days: Interval for EVERY_N_DAYS tasks
        month_day: Day of the month for MONTHLY_DAY tasks
    """
    try:
        updates = {}
        if task_name is not None: updates["task_name"] = task_name
        if workload is not None: updates["base_load_score"] = float(workload)
        if spoke is not None: updates["context"] = spoke
        if active is not None: updates["active"] = active
        if notes is not None: updates["notes"] = notes
        
        # Handle rule_type and related fields
        if rule_type is not None:
            updates["rule_type"] = rule_type.upper()
            
            if rule_type.upper() == "ONCE" and due_date:
                updates["due_date"] = due_date
            
            elif rule_type.upper() == "WEEKLY" and days:
                # Parse comma-separated days into boolean flags
                days_list = [d.strip().lower() for d in days.split(",")]
                day_map = {d: True for d in days_list}
                updates.update({
                    "mon": day_map.get("mon", False),
                    "tue": day_map.get("tue", False),
                    "wed": day_map.get("wed", False),
                    "thu": day_map.get("thu", False),
                    "fri": day_map.get("fri", False),
                    "sat": day_map.get("sat", False),
                    "sun": day_map.get("sun", False)
                })
            
            elif rule_type.upper() == "EVERY_N_DAYS" and interval_days:
                updates["interval_days"] = interval_days

            elif rule_type.upper() == "MONTHLY_DAY" and month_day:
                updates["month_day"] = month_day
        else:
            # Allow updating these fields even without changing rule_type
            if due_date is not None: updates["due_date"] = due_date
            if interval_days is not None: updates["interval_days"] = interval_days
            if month_day is not None: updates["month_day"] = month_day
            if days is not None:
                days_list = [d.strip().lower() for d in days.split(",")]
                day_map = {d: True for d in days_list}
                updates.update({
                    "mon": day_map.get("mon", False),
                    "tue": day_map.get("tue", False),
                    "wed": day_map.get("wed", False),
                    "thu": day_map.get("thu", False),
                    "fri": day_map.get("fri", False),
                    "sat": day_map.get("sat", False),
                    "sun": day_map.get("sun", False)
                })
        
        if not updates:
            return ToolResult(success=False, message="No updates provided")
            
        client = _get_lbs_client(user_id, session)
        result = client.update_task(task_id, updates)
        
        return ToolResult(
            success=True,
            message=f"✅ Updated task {task_id}",
            data={"task_id": task_id, "result": result}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to update task: {str(e)}")


def delete_task_by_id(
    task_id: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Delete a task from the LBS system.
    
    Args:
        task_id: ID of the task to delete
    """
    try:
        client = _get_lbs_client(user_id, session)
        client.delete_task(task_id)
        
        return ToolResult(
            success=True,
            message=f"🗑️ Deleted task {task_id}",
            data={"task_id": task_id}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to delete task: {str(e)}")


def complete_lbs_task(
    task_id: str,
    target_date: str,
    status: str = "done",
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Record an execution status for a specific task on a specific date.
    
    Args:
        task_id: ID of the task
        target_date: Date of execution (YYYY-MM-DD)
        status: Status to record (done, skipped, todo, in_progress)
    """
    try:
        from services.lbs_client import TaskStatus
        client = _get_lbs_client(user_id, session)
        
        # Validate status
        try:
            status_enum = TaskStatus(status.lower())
        except ValueError:
            return ToolResult(success=False, message=f"Invalid status: {status}. Use 'done', 'skipped', 'todo', or 'in_progress'.")
            
        dt = date.fromisoformat(target_date)
        result = client.toggle_task_completion(task_id, dt, status_enum)
        
        return ToolResult(
            success=True,
            message=f"✅ Task {task_id} marked as '{status}' for {target_date}.",
            data=result
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to complete task: {str(e)}")


def get_lbs_schedule(
    start_date: str,
    end_date: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Get the unified schedule including all tasks and their calculated loads.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        client = _get_lbs_client(user_id, session)
        schedule = client.get_schedule(start, end)
        
        if not schedule:
            return ToolResult(success=True, message=f"No tasks scheduled between {start_date} and {end_date}")
            
        lines = [f"📅 Schedule from {start_date} to {end_date}:\n"]
        for day in schedule:
            dt_str = day.get("date")
            total_load = day.get("total_load", 0.0)
            tasks = day.get("tasks", [])
            
            lines.append(f"● {dt_str} (Total Load: {total_load:.1f})")
            for t in tasks:
                status_icon = "✅" if t.get("status") == "done" else "🕒"
                lines.append(f"  └ {status_icon} [{t.get('task_id')}] {t.get('task_name')} ({t.get('load'):.1f})")
        
        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={"schedule": schedule}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get schedule: {str(e)}")


def get_task_execution_history(
    task_id: str,
    start_date: str,
    end_date: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Get the execution history (status records) for a specific task over a date range.
    
    Args:
        task_id: ID of the task to get history for
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        client = _get_lbs_client(user_id, session)
        history = client.get_task_history(task_id, start, end)
        
        if not history:
            return ToolResult(
                success=True, 
                message=f"No execution records found for task {task_id} between {start_date} and {end_date}",
                data={"history": [], "task_id": task_id}
            )
        
        # Format history for display
        lines = [f"📊 Execution history for task {task_id}:\n"]
        done_count = 0
        skipped_count = 0
        todo_count = 0
        
        for record in history:
            date_str = record.get("target_date", "N/A")
            status = record.get("status", "todo")
            
            if status == "done":
                icon = "✅"
                done_count += 1
            elif status == "skipped":
                icon = "⏭️"
                skipped_count += 1
            else:
                icon = "🕒"
                todo_count += 1
                
            lines.append(f"  {icon} {date_str}: {status}")
        
        lines.append(f"\nSummary: ✅ Done: {done_count} | ⏭️ Skipped: {skipped_count} | 🕒 Todo: {todo_count}")
        
        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={"history": history, "task_id": task_id, "done": done_count, "skipped": skipped_count, "todo": todo_count}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get task history: {str(e)}")


def check_inbox(
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Check the Hub's inbox for pending messages from Spokes.
    
    Args:
        session: Database session (injected)
        user_id: User ID (injected)
    
    Returns:
        ToolResult with pending messages
    """
    try:
        messages = session.query(InboxQueue).filter(
            InboxQueue.user_id == user_id,
            InboxQueue.is_processed == False
        ).order_by(InboxQueue.received_at.desc()).all()
        
        if not messages:
            return ToolResult(
                success=True,
                message="📭 Inbox is empty. No pending messages from Spokes.",
                data={"messages": [], "count": 0}
            )
        
        message_list = []
        for msg in messages:
            message_list.append({
                "id": msg.id,
                "spoke": msg.source_spoke,
                "type": msg.message_type,
                "summary": msg.payload.get("summary", "No summary"),
                "received_at": msg.received_at.isoformat() if msg.received_at else None
            })
        
        return ToolResult(
            success=True,
            message=f"📬 Found {len(messages)} pending message(s) in inbox.",
            data={"messages": message_list, "count": len(messages)}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to check inbox: {str(e)}")


def process_inbox_message(
    message_id: int,
    action: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Process an inbox message (accept or reject).
    
    Args:
        message_id: ID of the inbox message
        action: Either "accept" or "reject"
        session: Database session (injected)
        user_id: User ID (injected)
    
    Returns:
        ToolResult with processing status
    """
    if action not in ["accept", "reject"]:
        return ToolResult(success=False, message="Action must be 'accept' or 'reject'")
    
    try:
        msg = session.query(InboxQueue).filter(
            InboxQueue.id == message_id,
            InboxQueue.user_id == user_id
        ).first()
        
        if not msg:
            return ToolResult(success=False, message=f"Message {message_id} not found")
        
        msg.is_processed = True
        msg.processed_at = datetime.utcnow()
        
        if action == "reject":
            msg.error_log = "Rejected by user"
        
        session.commit()
        
        return ToolResult(
            success=True,
            message=f"✅ Message {message_id} {action}ed successfully.",
            data={"message_id": message_id, "action": action}
        )
    except Exception as e:
        session.rollback()
        return ToolResult(success=False, message=f"Failed to process message: {str(e)}")


# ==============================================================================
# Spoke Tools - Available to Spoke Agents
# ==============================================================================

def report_to_hub(
    summary: str,
    request: Optional[str] = None,
    *,
    session: Session,
    user_id: str,
    spoke_name: str
) -> ToolResult:
    """
    Send a report or request to the Hub agent via inbox.
    
    Args:
        summary: Summary of the report/progress
        request: Optional specific request for Hub's action
        session: Database session (injected)
        user_id: User ID (injected)
        spoke_name: Current spoke name (injected)
    
    Returns:
        ToolResult with submission status
    """
    try:
        inbox_msg = InboxQueue(
            user_id=user_id,
            source_spoke=spoke_name,
            message_type="share_update",
            payload={
                "type": "share_update",
                "target": "Hub",
                "timestamp": datetime.utcnow().isoformat(),
                "summary": summary,
                "request": request or ""
            },
            is_processed=False,
            received_at=datetime.utcnow()
        )
        
        session.add(inbox_msg)
        session.commit()
        
        return ToolResult(
            success=True,
            message="📤 Report sent to Hub inbox.",
            data={"inbox_id": inbox_msg.id, "summary": summary}
        )
    except Exception as e:
        session.rollback()
        return ToolResult(success=False, message=f"Failed to send report: {str(e)}")


def archive_session(
    *,
    session: Session,
    user_id: str,
    node_id: str,
    context_name: str
) -> ToolResult:
    """
    Archive the current chat session and start fresh.
    
    Args:
        session: Database session (injected)
        user_id: User ID (injected)
        node_id: Current node ID (injected)
        context_name: Current context name (injected)
    
    Returns:
        ToolResult with new session details
    """
    try:
        # Archive current active session
        active_session = session.query(ChatSession).filter(
            ChatSession.node_id == node_id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()).first()
        
        if active_session:
            active_session.is_archived = True
            session.commit()
        
        # Create new session
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            node_id=node_id,
            title=f"Session started {datetime.now().strftime('%Y-%m-%d')}",
            is_archived=False
        )
        session.add(new_session)
        session.commit()
        
        return ToolResult(
            success=True,
            message=f"📦 Archived session for {context_name}. New session started.",
            data={"new_session_id": new_session.id}
        )
    except Exception as e:
        session.rollback()
        return ToolResult(success=False, message=f"Failed to archive session: {str(e)}")

# ==============================================================================
# File Operation Tools (for Spoke agents) - User-Scoped Paths
# ==============================================================================

def save_artifact(
    file_path: str,
    content: str,
    overwrite: bool = False,
    *,
    user_id: str,
    node_type: str,
    spoke_name: Optional[str] = None,
    **kwargs
) -> ToolResult:
    """
    Save content to the agent's artifacts directory (user-scoped and isolated).
    """
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        artifacts_dir = _resolve_agent_artifacts_dir(user_id, node_type, spoke_name)
        full_path = artifacts_dir / file_path
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if full_path.exists() and not overwrite:
            return ToolResult(success=False, message=f"File exists: {file_path}. Set overwrite=True to replace.")
        
        full_path.write_text(content, encoding='utf-8')
        
        # Display name for user
        context_label = f"spokes/{spoke_name}" if node_type == 'SPOKE' else "hub_data"
        
        return ToolResult(
            success=True,
            message=f"✅ Saved file: {context_label}/artifacts/{file_path}",
            data={"file_path": file_path, "node_type": node_type, "full_path": str(full_path)}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to save file: {str(e)}")


def update_artifact(
    file_path: str,
    content: str,
    mode: str = 'w',
    *,
    user_id: str,
    node_type: str,
    spoke_name: Optional[str] = None,
    **kwargs
) -> ToolResult:
    """
    Update or append to an artifact in the agent's isolated artifacts directory.
    """
    if mode not in ['w', 'a', 'w+', 'a+']:
        return ToolResult(success=False, message="Mode must be 'w' (overwrite) or 'a' (append)")
    
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        artifacts_dir = _resolve_agent_artifacts_dir(user_id, node_type, spoke_name)
        full_path = artifacts_dir / file_path
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Determine Python file mode
        py_mode = 'a' if 'a' in mode else 'w'
        
        with open(full_path, py_mode, encoding='utf-8') as f:
            f.write(content)
        
        action = "Appended to" if py_mode == 'a' else "Updated"
        context_label = f"spokes/{spoke_name}" if node_type == 'SPOKE' else "hub_data"
        
        return ToolResult(
            success=True,
            message=f"✅ {action} file: {context_label}/artifacts/{file_path}",
            data={"file_path": file_path, "mode": mode, "full_path": str(full_path)}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to update file: {str(e)}")


def delete_artifact(
    file_path: str,
    *,
    user_id: str,
    node_type: str,
    spoke_name: Optional[str] = None,
    **kwargs
) -> ToolResult:
    """
    Delete an artifact from the agent's isolated artifacts directory.
    """
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        artifacts_dir = _resolve_agent_artifacts_dir(user_id, node_type, spoke_name)
        full_path = artifacts_dir / file_path
        
        if not full_path.exists():
            return ToolResult(success=False, message=f"File not found: {file_path}")
            
        full_path.unlink()
        
        context_label = f"spokes/{spoke_name}" if node_type == 'SPOKE' else "hub_data"
        
        return ToolResult(
            success=True,
            message=f"🗑️ Deleted file: {context_label}/artifacts/{file_path}",
            data={"file_path": file_path, "deleted": True}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to delete file: {str(e)}")


def read_reference(
    file_path: str,
    *,
    user_id: str,
    node_type: str,
    spoke_name: Optional[str] = None,
    session: Session = None,
    **kwargs
) -> ToolResult:
    """
    Read a file from refs/ or artifacts/. 
    Synchronizes with Gemini File API for AI visibility.
    """
    from utils.paths import get_spoke_dir, get_user_hub_dir
    from models.database import UploadedFile, Node
    import asyncio
    
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        if node_type == 'HUB':
            agent_base_dir = get_user_hub_dir(user_id)
        else:
            agent_base_dir = get_spoke_dir(user_id, spoke_name)
        
        # 1. Resolve storage path
        storage_path = None
        db_file = None
        if session:
            node_name = spoke_name if node_type == 'SPOKE' else 'hub'
            node = session.query(Node).filter(
                Node.user_id == user_id,
                Node.name == node_name,
                Node.node_type == node_type
            ).first()
            
            if node:
                db_file = session.query(UploadedFile).filter(
                    UploadedFile.node_id == node.id,
                    UploadedFile.filename == file_path
                ).first()
                if db_file:
                    storage_path = Path(db_file.storage_path)

        potential_paths = []
        if storage_path:
            potential_paths.append(storage_path)
            
        potential_paths.extend([
            agent_base_dir / "refs" / file_path,
            agent_base_dir / "files" / file_path,
            agent_base_dir / "artifacts" / file_path
        ])
        
        full_path = None
        for p in potential_paths:
            if p.exists() and p.is_file():
                full_path = p
                break
        
        if not full_path:
            return ToolResult(success=False, message=f"File not found: {file_path}")
        
        # 2. Sync with Gemini if it's a known DB file and not yet uploaded
        gemini_info = ""
        if db_file and not db_file.gemini_file_name:
            try:
                file_service = _get_file_service(user_id, session)
                # Run async upload in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(file_service.upload_to_gemini(db_file))
                loop.close()
                gemini_info = "\n\n(AI System: This file has been uploaded to Gemini File API for full-text visibility in upcoming turns.)"
            except Exception as e:
                print(f"[read_reference] Gemini sync failed: {e}")

        # 3. Read content
        try:
            content = full_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = f"[Binary file: {file_path}]"
        
        return ToolResult(
            success=True,
            message=f"📄 Content of {file_path}:\n\n{content}{gemini_info}",
            data={"file_path": file_path, "content": content}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to read file: {str(e)}")


def list_files(
    sub_dir: str = "refs",
    *,
    user_id: str,
    node_type: str,
    spoke_name: Optional[str] = None,
    session: Session = None,
    **kwargs
) -> ToolResult:
    """
    Unified tool to list files and their AI (Gemini) synchronization status.
    """
    from utils.paths import get_spoke_dir, get_user_hub_dir
    from models.database import UploadedFile, Node
    
    try:
        if sub_dir not in ['refs', 'artifacts', 'files']:
            return ToolResult(success=False, message="sub_dir must be 'refs', 'files', or 'artifacts'")
        
        node_name = spoke_name if node_type == 'SPOKE' else 'hub'
        if node_type == 'HUB':
            agent_base_dir = get_user_hub_dir(user_id)
        else:
            agent_base_dir = get_spoke_dir(user_id, spoke_name)
        
        found_files = {} # filename -> {size, uploaded}
        
        # 1. Get file metadata from Database
        if session:
            node = session.query(Node).filter(
                Node.user_id == user_id,
                Node.name == node_name,
                Node.node_type == node_type
            ).first()
            if node:
                db_files = session.query(UploadedFile).filter(UploadedFile.node_id == node.id).all()
                for f in db_files:
                    found_files[f.filename] = {
                        "size": f.size_bytes / 1024 if f.size_bytes else 0,
                        "uploaded": bool(f.gemini_file_name)
                    }
        
        # 2. Reconcile with Disk
        target_dir = agent_base_dir / sub_dir
        if target_dir.exists():
            for item in target_dir.rglob('*'):
                if item.is_file():
                    name = str(item.relative_to(target_dir))
                    if name not in found_files:
                        found_files[name] = {
                            "size": item.stat().st_size / 1024,
                            "uploaded": False
                        }
        
        # 3. Handle 'refs'/'files' unified view
        if sub_dir == 'refs' and (agent_base_dir / "files").exists():
            for item in (agent_base_dir / "files").rglob('*'):
                if item.is_file():
                    if item.name not in found_files:
                        found_files[item.name] = {
                            "size": item.stat().st_size / 1024,
                            "uploaded": False
                        }

        # 4. Format Output
        files_list = sorted(found_files.keys())
        context_label = f"spokes/{spoke_name}" if node_type == 'SPOKE' else "hub_data"
        
        if not files_list:
            return ToolResult(success=True, message=f"📁 {sub_dir}/ is empty", data={"files": []})
        
        lines = [f"📁 Files available in {context_label} ({sub_dir}):"]
        for name in files_list:
            meta = found_files[name]
            status = "✅ AI Indexed" if meta['uploaded'] else "⚠️ Local only"
            lines.append(f"  • {name} ({meta['size']:.1f} KB) - {status}")
            
        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={"files": found_files}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to list files: {str(e)}")




# ==============================================================================
# Gemini Research Wrapper
# ==============================================================================

def google_search(query: str, user_id: str, session: Session) -> ToolResult:
    """Wrapper function for Gemini Google Search research capability"""
    from google.genai import Client, types
    from models.database import UserSettings
    from utils.encryption import decrypt_string
    
    api_key = None
    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        try:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        except Exception:
            pass
            
    if not api_key:
        return ToolResult(success=False, message="Gemini API Key not found for research")
        
    # Initialize Client
    client = Client(api_key=api_key)
    
    try:
        # Use latest model for research
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
        )
        
        final_text = response.text
        # Process grounding metadata for citations
        if response.candidates and response.candidates[0].grounding_metadata:
            metadata = response.candidates[0].grounding_metadata
            if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point and metadata.search_entry_point.rendered_content:
                final_text += f"\n\n---\n{metadata.search_entry_point.rendered_content}"
            elif hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                sources = []
                for chunk in metadata.grounding_chunks:
                    if chunk.web:
                        sources.append(f"- [{chunk.web.title}]({chunk.web.uri})")
                if sources:
                    final_text += "\n\n**🔍 Search Sources:**\n" + "\n".join(set(sources))
                    
        return ToolResult(success=True, message=final_text)
    except Exception as e:
        return ToolResult(success=False, message=f"Research failed: {str(e)}")


def execute_code(prompt: str, user_id: str, session: Session) -> ToolResult:
    """Perform complex calculations or simulations via Gemini Code Execution"""
    from google.genai import Client, types
    from models.database import UserSettings
    from utils.encryption import decrypt_string
    
    api_key = None
    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        try:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        except Exception:
            pass
            
    if not api_key:
        return ToolResult(success=False, message="Gemini API Key not found for code execution")
    
    client = Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(code_execution=types.ToolCodeExecution())],
            )
        )
        return ToolResult(success=True, message=response.text)
    except Exception as e:
        return ToolResult(success=False, message=f"Code execution failed: {str(e)}")


def search_places(query: str, user_id: str, session: Session, lat: float = None, lng: float = None) -> ToolResult:
    """Search for places, businesses, and directions using Google Maps grounding"""
    from google.genai import Client, types
    from models.database import UserSettings
    from utils.encryption import decrypt_string
    
    api_key = None
    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        try:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        except Exception:
            pass
            
    if not api_key:
        return ToolResult(success=False, message="Gemini API Key not found for maps")
    
    client = Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    
    tool_config = None
    if lat is not None and lng is not None:
        tool_config = types.ToolConfig(
            retrieval_config=types.RetrievalConfig(
                lat_lng=types.LatLng(latitude=lat, longitude=lng)
            )
        )
        
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_maps=types.GoogleMaps())],
                tool_config=tool_config
            )
        )
        return ToolResult(success=True, message=response.text)
    except Exception as e:
        return ToolResult(success=False, message=f"Maps search failed: {str(e)}")


def research_url(urls: List[str], query: str, user_id: str, session: Session) -> ToolResult:
    """Extract information or summarize content from specific URLs using Gemini grounding"""
    from google.genai import Client, types
    from models.database import UserSettings
    from utils.encryption import decrypt_string
    
    api_key = None
    settings = session.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        try:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        except Exception:
            pass
            
    if not api_key:
        return ToolResult(success=False, message="Gemini API Key not found for URL research")
    
    client = Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
    
    # URL Context tool expects URLs in the prompt contents or potentially enabled
    full_prompt = f"Using information from the following URLs: {', '.join(urls)}\n\nQuery: {query}"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(url_context=types.UrlContext())],
            )
        )
        return ToolResult(success=True, message=response.text)
    except Exception as e:
        return ToolResult(success=False, message=f"URL research failed: {str(e)}")


# ==============================================================================
# LBS & KC Extended Tools
# ==============================================================================

def get_load_on_day(
    target_date: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Get the total estimated workload for a specific future day.
    
    Args:
        target_date: Date to check (YYYY-MM-DD)
    """
    try:
        dt = date.fromisoformat(target_date)
        client = _get_lbs_client(user_id, session)
        result = client.calculate_load(dt)
        
        load = result.get("adjusted_load", 0.0)
        task_count = result.get("task_count", 0)
        
        return ToolResult(
            success=True,
            message=f"📊 Load Forecast for {target_date}: {load:.1f} (Based on {task_count} tasks)",
            data=result
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get load: {str(e)}")


def get_load_in_period(
    start_date: str,
    end_date: str,
    *,
    session: Session,
    user_id: str
) -> ToolResult:
    """
    Get a breakdown of daily workload for a specific period.
    
    Args:
        start_date: Start of the period (YYYY-MM-DD)
        end_date: End of the period (YYYY-MM-DD)
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        client = _get_lbs_client(user_id, session)
        heatmap = client.get_heatmap(start, end)
        
        if not heatmap:
            return ToolResult(success=True, message=f"No load data for period {start_date} to {end_date}")
        
        lines = [f"📅 Load Heatmap ({start_date} to {end_date}):\n"]
        for day in heatmap:
            day_str = day.get("date")
            load = day.get("adjusted_load", 0.0)
            status = day.get("level", "unknown")
            bar = "█" * int(min(load, 10)) + "░" * (10 - int(min(load, 10)))
            lines.append(f"  • {day_str}: [{bar}] {load:.1f} ({status})")
            
        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={"heatmap": heatmap}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get load period: {str(e)}")


def search_knowledge(
    query: str,
    limit: int = 5,
    *,
    session: Session,
    user_id: str,
    context_name: str = "general"
) -> ToolResult:
    """
    Search the Knowledge Core for relevant information, facts, and context.
    
    Args:
        query: Search query or question
        limit: Number of results to consider
    """
    try:
        service = _get_kc_service(user_id, session)
        # Using get_context for a synthesized answer/context
        context = service.get_context(query=query, agent_id=context_name)
        
        if not context or not context.get("summary"):
            return ToolResult(
                success=True, 
                message=f"🔍 No specific knowledge found for: '{query}'",
                data={"context": None}
            )
        
        summary = context.get("summary")
        return ToolResult(
            success=True,
            message=f"🧠 Knowledge Repository Result:\n\n{summary}",
            data=context
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Knowledge search failed: {str(e)}")


def ingest_knowledge(
    content: str,
    label: Optional[str] = None,
    *,
    session: Session,
    user_id: str,
    context_name: str = "general"
) -> ToolResult:
    """
    Ingest new information, notes, or data into the Knowledge Core.
    
    Args:
        content: The information to remember
        label: Optional category or label (e.g. 'research', 'meeting_notes')
    """
    try:
        service = _get_kc_service(user_id, session)
        
        # We can prepend the label to the content for better indexing if provided
        ingest_text = content
        if label:
            ingest_text = f"[{label}] {content}"
            
        ingest_id = service.ingest_message(
            text=ingest_text,
            role="assistant",  # Act as agent recording knowledge
            scope="global",
            agent_id=context_name
        )
        
        if not ingest_id:
            return ToolResult(success=False, message="Knowledge ingestion failed (service unavailable).")
            
        return ToolResult(
            success=True,
            message=f"📥 Successfully ingested knowledge into core (ID: {ingest_id})",
            data={"ingest_id": ingest_id}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to ingest knowledge: {str(e)}")


# ==============================================================================
# Tool Definitions for Gemini Function Calling
# ==============================================================================

HUB_TOOL_DEFINITIONS = [
    {
        "name": "create_spoke",
        "description": "Create a new Spoke (project workspace) for the user. Use this when the user wants to start a new project.",
        "parameters": {
            "type": "object",
            "properties": {
                "spoke_name": {
                    "type": "string",
                    "description": "Name for the new spoke (project). Use lowercase with underscores."
                },
                "custom_prompt": {
                    "type": "string",
                    "description": "Optional custom system prompt for the spoke's AI behavior."
                }
            },
            "required": ["spoke_name"]
        }
    },
    {
        "name": "create_multiple_spokes",
        "description": "Create multiple new Spokes (project workspaces) at once. Use this when the user wants to start several projects simultaneously.",
        "parameters": {
            "type": "object",
            "properties": {
                "spoke_names": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of names for the new spokes (projects). Use lowercase with underscores."
                }
            },
            "required": ["spoke_names"]
        }
    },
    {
        "name": "delete_spoke",
        "description": "Delete a spoke (project) permanently. Use with caution.",
        "parameters": {
            "type": "object",
            "properties": {
                "spoke_name": {
                    "type": "string",
                    "description": "Name of the spoke to delete."
                }
            },
            "required": ["spoke_name"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in the LBS (Load Balancing System).",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {
                    "type": "string",
                    "description": "Name of the task"
                },
                "workload": {
                    "type": "number",
                    "description": "Load score from 0-10 (how demanding is this task?)"
                },
                "spoke": {
                    "type": "string",
                    "description": "Context/spoke for the task. Defaults to current context."
                },
                "rule_type": {
                    "type": "string",
                    "description": "Recurrence rule: ONCE, WEEKLY, EVERY_N_DAYS, or MONTHLY_DAY"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date for ONCE tasks (YYYY-MM-DD format)"
                },
                "days": {
                    "type": "string",
                    "description": "Comma-separated days for WEEKLY tasks (e.g., 'mon,wed,fri')"
                },
                "interval_days": {
                    "type": "integer",
                    "description": "Interval for EVERY_N_DAYS tasks"
                },
                "month_day": {
                    "type": "integer",
                    "description": "Day of the month (1-31) for MONTHLY_DAY rule"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes for the task"
                }
            },
            "required": ["task_name", "workload"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List existing tasks from the LBS. Use this to see what tasks are currently scheduled.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Optional context/spoke to filter tasks by. Defaults to current context."
                }
            }
        }
    },
    {
        "name": "update_task_details",
        "description": "Update properties of an existing task in LBS including recurrence rules.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to update (get this from list_tasks)"
                },
                "task_name": {
                    "type": "string",
                    "description": "New name for the task"
                },
                "workload": {
                    "type": "number",
                    "description": "New load score (0-10)"
                },
                "spoke": {
                    "type": "string",
                    "description": "New spoke/context to assign the task to"
                },
                "active": {
                    "type": "boolean",
                    "description": "Whether the task is active"
                },
                "notes": {
                    "type": "string",
                    "description": "New notes for the task"
                },
                "rule_type": {
                    "type": "string",
                    "enum": ["ONCE", "WEEKLY", "EVERY_N_DAYS", "MONTHLY_DAY"],
                    "description": "Recurrence rule type"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date for ONCE tasks (YYYY-MM-DD format)"
                },
                "days": {
                    "type": "string",
                    "description": "Comma-separated days for WEEKLY tasks (e.g., 'mon,wed,fri')"
                },
                "interval_days": {
                    "type": "integer",
                    "description": "Interval for EVERY_N_DAYS tasks"
                },
                "month_day": {
                    "type": "integer",
                    "description": "Day of the month for MONTHLY_DAY rule"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "delete_task_by_id",
        "description": "Delete a task from LBS permanently.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to delete"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "check_inbox",
        "description": "Check the Hub's inbox for pending messages and reports from Spokes.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "process_inbox_message",
        "description": "Process a pending inbox message by accepting or rejecting it.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "integer",
                    "description": "ID of the inbox message to process"
                },
                "action": {
                    "type": "string",
                    "enum": ["accept", "reject"],
                    "description": "Action to take on the message"
                }
            },
            "required": ["message_id", "action"]
        }
    },
    {
        "name": "archive_session",
        "description": "Archive the current chat session and start a fresh conversation.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    # File operation tools
    {
        "name": "save_artifact",
        "description": "Save content to a file in the system. MUST BE USED whenever writing code, docs, or logs. DO NOT print the content in chat without saving it first.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory (e.g., 'draft.md', 'code/main.py')"
                },
                "content": {
                    "type": "string",
                    "description": "Full content of the file to save"
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Set True to overwrite existing file. Default is False."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "update_artifact",
        "description": "Update or append to an existing artifact. Use this for logging or iterative task updates.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory"
                },
                "content": {
                    "type": "string",
                    "description": "New content to write or append"
                },
                "mode": {
                    "type": "string",
                    "enum": ["w", "a"],
                    "description": "Write mode: 'w' for overwrite, 'a' for append. Default is 'w'."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "delete_artifact",
        "description": "Permanently delete an artifact from the system.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory to delete"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "read_reference",
        "description": "Read a file from the refs/ or artifacts/ directory. Automatically synchronizes with AI memory for better understanding.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within refs/ or artifacts/ directory (e.g., 'notes.md')"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files and their AI indexing status in either refs/ or artifacts/ directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "sub_dir": {
                    "type": "string",
                    "enum": ["refs", "artifacts", "files"],
                    "description": "Either 'refs', 'artifacts', or 'files'"
                }
            },
            "required": ["sub_dir"]
        }
    },
    {
        "name": "google_search",
        "description": "Search Google for real-time information, research, and technical documentation when internal knowledge is insufficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_load_on_day",
        "description": "Get the total workload forecast for a specific future day. Use this to check availability or planning.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["target_date"]
        }
    },
    {
        "name": "get_load_in_period",
        "description": "Get a breakdown of daily workload for a specific period. Use this to find the best time for new tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "search_knowledge",
        "description": "Search the Knowledge Core for relevant information, facts, and context across all projects.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or question"
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit of results"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ingest_knowledge",
        "description": "Record new information, facts, or data into the long-term Knowledge Core.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember"
                },
                "label": {
                    "type": "string",
                    "description": "Optional category label (e.g. 'research', 'personal_pref')"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "execute_code",
        "description": "Perform complex calculations, simulations, or data processing by executing Python code via Gemini.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task or calculation that requires code execution"
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "search_places",
        "description": "Search for places, businesses, restaurants, and directions using Google Maps grounding.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The place or business search query"
                },
                "lat": {
                    "type": "number",
                    "description": "Optional latitude for location context"
                },
                "lng": {
                    "type": "number",
                    "description": "Optional longitude for location context"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "research_url",
        "description": "Extract specific information, summarize, or query content from provided URLs using Gemini grounding.",
        "parameters": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of URLs to research"
                },
                "query": {
                    "type": "string",
                    "description": "Specific question or summary request for the provided URLs"
                }
            },
            "required": ["urls", "query"]
        }
    },
    {
        "name": "complete_lbs_task",
        "description": "Record an execution status for a specific task on a specific date (e.g. mark it as done).",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to complete"
                },
                "target_date": {
                    "type": "string",
                    "description": "Date of the execution (YYYY-MM-DD)"
                },
                "status": {
                    "type": "string",
                    "enum": ["done", "skipped", "todo", "in_progress"],
                    "description": "The status to record. Default is 'done'."
                }
            },
            "required": ["task_id", "target_date"]
        }
    },
    {
        "name": "get_lbs_schedule",
        "description": "Get the unified schedule including all tasks and their calculated loads for a range of dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "get_task_execution_history",
        "description": "Get the execution history (status records) for a specific task over a date range. Use this to see when a task was completed, skipped, or left as todo.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to get history for"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["task_id", "start_date", "end_date"]
        }
    }
]


SPOKE_TOOL_DEFINITIONS = [
    # File operation tools
    {
        "name": "save_artifact",
        "description": "Save content to a file in the system. MUST BE USED whenever writing code, docs, or logs. DO NOT print the content in chat without saving it first.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory (e.g., 'draft.md', 'code/main.py')"
                },
                "content": {
                    "type": "string",
                    "description": "Full content of the file to save"
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Set True to overwrite existing file. Default is False."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "update_artifact",
        "description": "Update or append to an existing artifact. Use this for logging or iterative task updates.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory"
                },
                "content": {
                    "type": "string",
                    "description": "New content to write or append"
                },
                "mode": {
                    "type": "string",
                    "enum": ["w", "a"],
                    "description": "Write mode: 'w' for overwrite, 'a' for append. Default is 'w'."
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "delete_artifact",
        "description": "Permanently delete an artifact from the system.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within artifacts/ directory to delete"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "read_reference",
        "description": "Read a file from the refs/ or artifacts/ directory. Automatically synchronizes with AI memory for better understanding.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path within refs/ directory (e.g., 'notes.md')"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files and their AI indexing status in either refs/ or artifacts/ directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "sub_dir": {
                    "type": "string",
                    "description": "Either 'refs' or 'artifacts'"
                }
            },
            "required": ["sub_dir"]
        }
    },
    # Hub communication tools
    {
        "name": "report_to_hub",
        "description": "Send a progress report or request to the Hub agent. Use this to communicate with Hub.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of progress or the report content"
                },
                "request": {
                    "type": "string",
                    "description": "Optional specific request for Hub's action or decision"
                }
            },
            "required": ["summary"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List existing tasks from the LBS for this spoke.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "delete_spoke",
        "description": "Delete this spoke (current project) permanently. Use with caution.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "archive_session",
        "description": "Archive the current chat session and start a fresh conversation.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "google_search",
        "description": "Search Google for real-time information, research, and technical documentation when internal knowledge is insufficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_load_on_day",
        "description": "Get the total workload forecast for a specific future day. Use this to check availability or planning.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["target_date"]
        }
    },
    {
        "name": "get_load_in_period",
        "description": "Get a breakdown of daily workload for a specific period. Use this to find the best time for new tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "search_knowledge",
        "description": "Search the Knowledge Core for relevant information, facts, and context related to this project.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or question"
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit of results"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ingest_knowledge",
        "description": "Record new information, facts, or data into the long-term Knowledge Core.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember"
                },
                "label": {
                    "type": "string",
                    "description": "Optional category label"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "execute_code",
        "description": "Perform complex calculations, simulations, or data processing by executing Python code via Gemini.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task or calculation that requires code execution"
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "search_places",
        "description": "Search for places, businesses, restaurants, and directions using Google Maps grounding.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The place or business search query"
                },
                "lat": {
                    "type": "number",
                    "description": "Optional latitude for location context"
                },
                "lng": {
                    "type": "number",
                    "description": "Optional longitude for location context"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "research_url",
        "description": "Extract specific information, summarize, or query content from provided URLs using Gemini grounding.",
        "parameters": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of URLs to research"
                },
                "query": {
                    "type": "string",
                    "description": "Specific question or summary request for the provided URLs"
                }
            },
            "required": ["urls", "query"]
        }
    },
    {
        "name": "complete_lbs_task",
        "description": "Record an execution status for a specific task on a specific date (e.g. mark it as done).",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to complete"
                },
                "target_date": {
                    "type": "string",
                    "description": "Date of the execution (YYYY-MM-DD)"
                },
                "status": {
                    "type": "string",
                    "enum": ["done", "skipped", "todo", "in_progress"],
                    "description": "The status to record. Default is 'done'."
                }
            },
            "required": ["task_id", "target_date"]
        }
    },
    {
        "name": "get_lbs_schedule",
        "description": "Get the unified schedule including all tasks and their calculated loads for a range of dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "get_task_execution_history",
        "description": "Get the execution history (status records) for a specific task over a date range. Use this to see when a task was completed, skipped, or left as todo.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to get history for"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format"
                }
            },
            "required": ["task_id", "start_date", "end_date"]
        }
    }
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    # Hub tools
    "create_spoke": create_spoke,
    "create_multiple_spokes": create_multiple_spokes,
    "delete_spoke": delete_spoke,
    "create_task": create_task,
    "list_tasks": list_tasks,
    "update_task_details": update_task_details,
    "delete_task_by_id": delete_task_by_id,
    "check_inbox": check_inbox,
    "process_inbox_message": process_inbox_message,
    # Spoke tools
    "report_to_hub": report_to_hub,
    "archive_session": archive_session,
    "google_search": google_search,
    "execute_code": execute_code,
    "search_places": search_places,
    "research_url": research_url,
    # File operation tools
    "save_artifact": save_artifact,
    "update_artifact": update_artifact,
    "delete_artifact": delete_artifact,
    "read_reference": read_reference,
    "list_files": list_files,
    # LBS & KC Extended Tools
    "get_load_on_day": get_load_on_day,
    "get_load_in_period": get_load_in_period,
    "search_knowledge": search_knowledge,
    "ingest_knowledge": ingest_knowledge,
    "complete_lbs_task": complete_lbs_task,
    "get_lbs_schedule": get_lbs_schedule,
    "get_task_execution_history": get_task_execution_history,
}
