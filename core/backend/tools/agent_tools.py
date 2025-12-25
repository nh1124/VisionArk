"""
Agent Tools - Native Function Calling Implementation
Replaces slash command system with Gemini native function calling
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from models.database import Node, AgentProfile, ChatSession, InboxQueue
from services.lbs_client import LBSClient


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
            client = LBSClient()
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
    days: Optional[str] = None,  # Changed to string (comma-separated)
    interval_days: Optional[int] = None,
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
        
        client = LBSClient()
        result = client.create_task(task_data)
        
        return ToolResult(
            success=True,
            message=f"✅ Created task: {task_name} (Workload: {workload})",
            data={"task_id": result.get("task_id"), "task_name": task_name}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to create task: {str(e)}")


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
                "notes": {
                    "type": "string",
                    "description": "Additional notes for the task"
                }
            },
            "required": ["task_name", "workload"]
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
    }
]


SPOKE_TOOL_DEFINITIONS = [
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
    }
]


# Map tool names to functions
TOOL_FUNCTIONS = {
    "create_spoke": create_spoke,
    "delete_spoke": delete_spoke,
    "create_task": create_task,
    "check_inbox": check_inbox,
    "process_inbox_message": process_inbox_message,
    "report_to_hub": report_to_hub,
    "archive_session": archive_session,
}
