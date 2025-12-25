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
# File Operation Tools (for Spoke agents) - User-Scoped Paths
# ==============================================================================

def save_artifact(
    file_path: str,
    content: str,
    overwrite: bool = False,
    *,
    spoke_name: str,
    user_id: str = None,  # Injected from tool_context
    **kwargs
) -> ToolResult:
    """
    Save content to the spoke's artifacts directory (user-scoped).
    
    Args:
        file_path: Relative path within artifacts/ (e.g., 'draft.md')
        content: Full content of the file
        overwrite: Set True to overwrite existing file
        spoke_name: Current spoke name (injected from tool_context)
        user_id: User ID for scoped path (injected from tool_context)
    """
    from utils.paths import get_spoke_dir
    
    if not user_id:
        return ToolResult(success=False, message="User context not available")
    
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        # Use user-scoped path
        spoke_dir = get_spoke_dir(user_id, spoke_name)
        artifacts_dir = spoke_dir / "artifacts"
        full_path = artifacts_dir / file_path
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if full_path.exists() and not overwrite:
            return ToolResult(success=False, message=f"File exists: {file_path}. Set overwrite=True to replace.")
        
        full_path.write_text(content, encoding='utf-8')
        
        return ToolResult(
            success=True,
            message=f"✅ Saved file: artifacts/{file_path}",
            data={"file_path": file_path, "spoke": spoke_name, "full_path": str(full_path)}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to save file: {str(e)}")


def read_reference(
    file_path: str,
    *,
    spoke_name: str,
    user_id: str = None,
    session: Session = None,  # Injected from tool_context
    **kwargs
) -> ToolResult:
    """
    Read a file from the spoke's refs or files directory (user-scoped).
    Resolves original filenames to storage UUIDs via database.
    
    Args:
        file_path: Original filename or relative path
        spoke_name: Current spoke name
        user_id: User ID
        session: Database session
    """
    from utils.paths import get_spoke_dir
    from models.database import UploadedFile, Node
    
    if not user_id:
        return ToolResult(success=False, message="User context not available")
    
    try:
        if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
            return ToolResult(success=False, message="Path traversal not allowed")
        
        spoke_dir = get_spoke_dir(user_id, spoke_name)
        
        # 1. Search for file in database to resolve UUID naming
        storage_path = None
        if session:
            # Find the spoke node first
            node = session.query(Node).filter(
                Node.user_id == user_id,
                Node.name == spoke_name,
                Node.node_type == "SPOKE"
            ).first()
            
            if node:
                # Find the file by original filename
                db_file = session.query(UploadedFile).filter(
                    UploadedFile.node_id == node.id,
                    UploadedFile.filename == file_path
                ).first()
                
                if db_file:
                    storage_path = Path(db_file.storage_path)

        # 2. Try various path combinations if not found in DB
        potential_paths = []
        if storage_path:
            potential_paths.append(storage_path)
            
        # Legacy/direct paths
        potential_paths.extend([
            spoke_dir / "refs" / file_path,
            spoke_dir / "files" / file_path,
            spoke_dir / "artifacts" / file_path
        ])
        
        full_path = None
        for p in potential_paths:
            if p.exists() and p.is_file():
                full_path = p
                break
        
        if not full_path:
            return ToolResult(success=False, message=f"File not found: {file_path}")
        
        try:
            content = full_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = f"[Binary file: {file_path} - Use a code interpreter or specialized tool to process this file type]"
        
        return ToolResult(
            success=True,
            message=f"📄 Content of {file_path}:\n\n{content}",
            data={"file_path": file_path, "content": content, "storage_path": str(full_path)}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to read file: {str(e)}")


def list_directory(
    sub_dir: str = "refs",
    *,
    spoke_name: str,
    user_id: str = None,
    session: Session = None,
    **kwargs
) -> ToolResult:
    """
    List files in the spoke's refs, files, or artifacts directory (user-scoped).
    
    Args:
        sub_dir: Either 'refs', 'files', or 'artifacts'
        spoke_name: Current spoke name
        user_id: User ID
        session: Database session
    """
    from utils.paths import get_spoke_dir
    from models.database import UploadedFile, Node
    
    if not user_id:
        return ToolResult(success=False, message="User context not available")
    
    try:
        if sub_dir not in ['refs', 'artifacts', 'files']:
            return ToolResult(success=False, message="sub_dir must be 'refs', 'files', or 'artifacts'")
        
        spoke_dir = get_spoke_dir(user_id, spoke_name)
        
        # We'll collect files from both disk and DB to ensure original names are shown
        found_files = set()
        
        # 1. Check database for files in this node
        if session:
            node = session.query(Node).filter(
                Node.user_id == user_id,
                Node.name == spoke_name,
                Node.node_type == "SPOKE"
            ).first()
            if node:
                db_files = session.query(UploadedFile).filter(UploadedFile.node_id == node.id).all()
                for f in db_files:
                    found_files.add(f.filename)
        
        # 2. Check disk (refs and artifacts might have direct files)
        target_dir = spoke_dir / sub_dir
        if target_dir.exists():
            for item in target_dir.rglob('*'):
                if item.is_file():
                    found_files.add(str(item.relative_to(target_dir)))
        
        # 3. Special case: if sub_dir is 'refs', also check 'files' (unified view)
        if sub_dir == 'refs':
            files_dir = spoke_dir / "files"
            if files_dir.exists():
                for item in files_dir.rglob('*'):
                    if item.is_file():
                        # If it's a UUID name, we hopefully already got it from DB
                        # If not, add the filename
                        found_files.add(item.name)

        files_list = sorted(list(found_files))
        
        if not files_list:
            return ToolResult(success=True, message=f"📁 {sub_dir}/ is empty", data={"sub_dir": sub_dir, "files": []})
        
        return ToolResult(
            success=True,
            message=f"📁 Files available in {spoke_name} ({sub_dir}):\n" + "\n".join(f"  • {f}" for f in files_list),
            data={"sub_dir": sub_dir, "files": files_list}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to list directory: {str(e)}")


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
    # File operation tools
    {
        "name": "save_artifact",
        "description": "Save code, documentation, or any content to the artifacts directory. Use this to CREATE FILES instead of just showing code. Always use this when the user asks you to create, write, or save a file.",
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
        "name": "read_reference",
        "description": "Read a file from the refs/ (references) directory. Use this to access reference materials and documentation.",
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
        "name": "list_directory",
        "description": "List files in either the refs/ or artifacts/ directory. Use to see what files are available.",
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
    # Hub tools
    "create_spoke": create_spoke,
    "delete_spoke": delete_spoke,
    "create_task": create_task,
    "check_inbox": check_inbox,
    "process_inbox_message": process_inbox_message,
    # Spoke tools
    "report_to_hub": report_to_hub,
    "archive_session": archive_session,
    # File operation tools
    "save_artifact": save_artifact,
    "read_reference": read_reference,
    "list_directory": list_directory,
}
