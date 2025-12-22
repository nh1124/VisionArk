"""
Command Handlers
Implementation of slash commands referenced in BLUEPRINT Section 4.1
"""
from typing import List
from pathlib import Path
from datetime import datetime, date
from sqlalchemy.orm import Session
import uuid

from services.command_parser import register_command, CommandResult
from services.inbox_handler import InboxHandler
from services.lbs_client import LBSClient
from utils.paths import get_spoke_dir, get_user_hub_dir
from models.database import Node, AgentProfile, ChatSession, ChatMessage
from agents.spoke_agent import SpokeAgent
from agents.hub_agent import HubAgent


# ============================================================================
# HUB COMMANDS
# ============================================================================

@register_command("check_inbox", "Check and read inbox messages", ["hub"])
def handle_check_inbox(args: List[str], session: Session = None, **kwargs) -> CommandResult:
    """
    Fetch inbox messages and prepare them for Hub to read and respond to
    
    Usage: /check_inbox
    """
    if session is None:
        return CommandResult(success=False, message="No database session available")
    
    try:
        inbox = InboxHandler(session)
        messages = inbox.get_pending_messages()
        
        if not messages:
            return CommandResult(
                success=True,
                message="📭 Inbox is empty. No messages from Spokes.",
                data={"messages": [], "has_messages": False}
            )
        
        # Format messages for Hub to read and respond to
        message_content = []
        message_content.append(f"📬 You have {len(messages)} messages from Spokes:\n")
        
        for msg in messages:
            spoke = msg.source_spoke
            summary = msg.payload.get('summary', 'No summary')
            request = msg.payload.get('request', '')
            
            msg_text = f"\n**From {spoke}:**\n{summary}"
            if request:
                msg_text += f"\n*Request:* {request}"
            
            message_content.append(msg_text)
        
        # Don't auto-mark as processed - Hub needs to review and respond first
        formatted_msg = "\n".join(message_content)
        
        return CommandResult(
            success=True,
            message=formatted_msg,
            data={
                "messages": [
                    {
                        "id": msg.id,
                        "spoke": msg.source_spoke,
                        "summary": msg.payload.get('summary'),
                        "request": msg.payload.get('request')
                    }
                    for msg in messages
                ],
                "has_messages": True
            }
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to check inbox: {str(e)}")


@register_command("create_spoke", "Create a new Spoke (project)", ["hub"])
def handle_create_spoke(args: List[str], session: Session = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Create a new Spoke workspace and DB Node
    """
    if not args:
        return CommandResult(success=False, message="Usage: /create_spoke <spoke_name> [prompt=\"custom prompt\"]")
    
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")
        
    spoke_name = args[0]
    
    # Parse optional custom prompt
    custom_prompt = None
    for arg in args[1:]:
        if arg.startswith("prompt="):
            custom_prompt = arg.split("=", 1)[1].strip('"').strip("'")
    
    try:
        # 1. Create DB Node and Profile via SpokeAgent helper
        node = SpokeAgent.get_or_create_spoke_node(user_id, spoke_name, session)
        
        if custom_prompt:
            # Update AgentProfile with custom prompt
            profile = session.query(AgentProfile).filter(
                AgentProfile.node_id == node.id,
                AgentProfile.is_active == True
            ).first()
            if profile:
                profile.system_prompt = custom_prompt
                session.commit()
        
        message = f"✅ Created Spoke: {spoke_name}"
        if custom_prompt:
            message += " (with custom prompt)"
        
        return CommandResult(
            success=True,
            message=message,
            data={"spoke_name": spoke_name, "node_id": node.id, "custom_prompt": bool(custom_prompt)}
        )
    except Exception as e:
        if session: session.rollback()
        return CommandResult(success=False, message=f"Failed to create Spoke: {str(e)}")
@register_command("send_message", "Send a message to a Spoke", ["hub"])
def handle_send_message(args: List[str], session: Session = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Send a message from Hub to a Spoke's DB history
    """
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /send_message <spoke_name> <message>")
    
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    spoke_name = args[0]
    message_content = " ".join(args[1:])
    
    # Remove quotes if present
    if message_content.startswith('"') and message_content.endswith('"'):
        message_content = message_content[1:-1]
    
    try:
        # 1. Find the Spoke Node
        node = session.query(Node).filter(
            Node.user_id == user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ).first()
        
        if not node:
            return CommandResult(success=False, message=f"Spoke '{spoke_name}' does not exist")
        
        # 2. Get active session for that node
        chat_session = session.query(ChatSession).filter(
            ChatSession.node_id == node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()).first()
        
        if not chat_session:
            # Create one if missing
            chat_session = ChatSession(
                id=str(uuid.uuid4()),
                node_id=node.id,
                title="Migrated Session",
                is_archived=False
            )
            session.add(chat_session)
            session.commit()
            
        # 3. Add system message from Hub
        db_message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant", # Hub acts as assistant relative to the global context? 
                             # Or "system" to represent Hub. 
                             # Let's use "assistant" but with a Hub prefix in content or meta.
            content=f"[Hub -> {spoke_name}] {message_content}"
        )
        session.add(db_message)
        session.commit()

        # 4. Fallback to file if needed (optional)
        
        return CommandResult(
            success=True,
            message=f"📨 Message sent to {spoke_name}",
            data={"spoke_name": spoke_name, "node_id": node.id}
        )
    except Exception as e:
        if session: session.rollback()
        return CommandResult(success=False, message=f"Failed to send message: {str(e)}")


@register_command("kill", "Delete a spoke completely", ["hub", "spoke"])
def handle_kill(args: List[str], context_type: str = "hub", context_name: str = "hub", session: Session = None, **kwargs) -> CommandResult:
    """
    Delete a spoke permanently
    
    Usage: 
      From Hub: /kill <spoke_name>
      From Spoke: /kill (deletes current spoke)
    """
    import shutil
    
    # Determine which spoke to kill
    if context_type == "spoke":
        spoke_name = context_name
    elif args:
        spoke_name = args[0]
    else:
        return CommandResult(success=False, message="Usage: /kill <spoke_name>")
    
    try:
        # 1. Find and archive DB Node
        user_id = kwargs.get("user_id")
        node = session.query(Node).filter(
            Node.user_id == user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ).first() if session and user_id else None
        
        if node:
            node.is_archived = True
            session.commit()
            print(f"[KILL] Archived DB Node for spoke '{spoke_name}'")

        # 2. Delete LBS tasks
        try:
            client = LBSClient(user_id=user_id or "dev_user")
            tasks = client.get_tasks(context=spoke_name)
            for t in tasks:
                client.delete_task(t["task_id"])
            print(f"[KILL] Deleted tasks for spoke '{spoke_name}' via LBS microservice")
        except Exception as lbs_err:
            print(f"[KILL] Warning: Failed to cleanup LBS tasks: {lbs_err}")
        
        # 3. Handle inbox notification
        if context_type == "spoke" and session:
            meta_xml = f"""<meta-action type="share_update">
<target>Hub</target>
<timestamp>{datetime.now().isoformat()}</timestamp>
<summary>Spoke '{spoke_name}' has been terminated</summary>
<request></request>
</meta-action>"""
            inbox = InboxHandler(session)
            inbox.push_to_inbox(
                source_spoke=spoke_name,
                meta_action_xml=meta_xml
            )
        
        # 4. Delete physical directory
        spoke_dir = get_spoke_dir(user_id, spoke_name)
        if spoke_dir.exists():
            shutil.rmtree(spoke_dir)
        
        return CommandResult(
            success=True,
            message=f"🗑️ Deleted Spoke: {spoke_name}",
            data={"spoke_name": spoke_name, "deleted": True, "redirect": True}
        )
    except Exception as e:
        if session: session.rollback()
        return CommandResult(success=False, message=f"Failed to delete Spoke: {str(e)}")


@register_command("archive", "Archive conversation and start fresh", ["hub", "spoke"])
def handle_archive(args: List[str], context_type: str = "hub", context_name: str = "hub", session: Session = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Archive and rotate DB session
    """
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    # 1. Determine target node
    if context_type == "spoke":
        target_name = context_name
        node_type = "SPOKE"
    elif args:
        target_name = args[0]
        node_type = "SPOKE"
    else:
        target_name = "hub"
        node_type = "HUB"
        
    try:
        # 2. Find Node
        node = session.query(Node).filter(
            Node.user_id == user_id,
            Node.name == target_name,
            Node.node_type == node_type
        ).first()
        
        if not node:
            return CommandResult(success=False, message=f"Node '{target_name}' not found")
        
        # 3. Archive current active session
        active_session = session.query(ChatSession).filter(
            ChatSession.node_id == node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()).first()
        
        if active_session:
            active_session.is_archived = True
            session.commit()
            
        # 4. Create new session
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            node_id=node.id,
            title=f"Session started {datetime.now().strftime('%Y-%m-%d')}",
            is_archived=False
        )
        session.add(new_session)
        session.commit()
        
        return CommandResult(
            success=True,
            message=f"📦 Archived current session for {target_name}. New session started.",
            data={"node_id": node.id, "new_session_id": new_session.id}
        )
    except Exception as e:
        if session: session.rollback()
        return CommandResult(success=False, message=f"Failed to archive: {str(e)}")


@register_command("report", "Generate progress report for Hub", ["spoke"])
def handle_report(args: List[str], spoke_name: str = None, session: Session = None, **kwargs) -> CommandResult:
    """
    Generate a progress report
    
    Usage: /report [summary]
    """
    if session is None or spoke_name is None:
        return CommandResult(success=False, message="Missing context")
    
    summary = " ".join(args) if args else "Progress update from spoke"
    
    try:
        inbox = InboxHandler(session)
        
        # Create XML meta-action for inbox
        meta_xml = f"""<meta-action type="share_update">
    <target>Hub</target>
    <timestamp>{datetime.now().isoformat()}</timestamp>
    <summary>{summary}</summary>
    <request></request>
</meta-action>"""
        
        # Push to inbox queue
        inbox.push_to_inbox(
            source_spoke=spoke_name,
            meta_action_xml=meta_xml
        )
        
        return CommandResult(
            success=True,
            message=f"📤 Report sent to Hub inbox",
            data={"spoke": spoke_name, "summary": summary}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to send report: {str(e)}")


@register_command("check_inbox", "Fetch pending messages from Spokes", ["hub"])
def handle_check_inbox(args: List[str], session: Session = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    List pending messages in the Hub's inbox
    """
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")
    
    try:
        inbox = InboxHandler(session, user_id=user_id)
        messages = inbox.get_pending_messages()
        
        if not messages:
            return CommandResult(success=True, message="Your inbox is empty. No pending updates from Spokes.")
        
        report = [f"📬 Found {len(messages)} pending messages:"]
        for idx, msg in enumerate(messages):
            summary = msg.payload.get("summary", "No summary")
            report.append(f"{idx+1}. [{msg.source_spoke}] {summary} (ID: {msg.id})")
        
        report.append("\nUse `/process_inbox <id> <accept|reject>` to take action.")
        
        return CommandResult(
            success=True,
            message="\n".join(report),
            data={"count": len(messages), "message_ids": [m.id for m in messages]}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to check inbox: {str(e)}")


@register_command("process_inbox", "Process an inbox message", ["hub"])
def handle_process_inbox(args: List[str], session: Session = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Accept or reject a message from the inbox
    
    Usage: /process_inbox <message_id> <accept|reject>
    """
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /process_inbox <message_id> <accept|reject>")
    
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")
    
    try:
        msg_id = int(args[0])
        action = args[1].lower()
        
        if action not in ["accept", "reject"]:
            return CommandResult(success=False, message="Action must be 'accept' or 'reject'")
        
        inbox = InboxHandler(session, user_id=user_id)
        success = inbox.process_message(msg_id, action)
        
        if success:
            return CommandResult(success=True, message=f"✅ Message {msg_id} {action}ed successfully.")
        else:
            return CommandResult(success=False, message=f"Failed to process message {msg_id}. It may not exist or is already processed.")
            
    except ValueError:
        return CommandResult(success=False, message="Invalid message ID. Must be an integer.")
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to process inbox: {str(e)}")


# ============================================================================
# LBS TASK MANAGEMENT COMMANDS (NEW!)
# ============================================================================

@register_command("create_task", "Create a new LBS task", ["hub", "spoke"])
def handle_create_task(args: List[str], session: Session = None, context_name: str = None, **kwargs) -> CommandResult:
    """
    Create a new task in the LBS system
    
    Usage: /create_task name="<task_name>" spoke="<spoke>" workload=<0-10> [rule=ONCE|WEEKLY|EVERY_N_DAYS|MONTHLY_DAY] [due=YYYY-MM-DD] [days=mon,tue,wed]
    
    Examples:
      /create_task name="Weekly Meeting" spoke="meetings" workload=2.0 rule=WEEKLY days=mon,wed
      /create_task name="Thesis Draft" spoke="research" workload=8.0 rule=ONCE due=2025-12-15
      /create_task name="Gym" spoke="health" workload=1.5 rule=EVERY_N_DAYS interval=2
    """
    if session is None:
        return CommandResult(success=False, message="No database session available")
    
    # Parse key=value arguments
    parsed = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            # Remove quotes
            value = value.strip('"').strip("'")
            parsed[key] = value
    
    # Validate required fields
    if "name" not in parsed:
        return CommandResult(success=False, message="Missing required field: name")
    if "workload" not in parsed:
        return CommandResult(success=False, message="Missing required field: workload")
    
    # Default spoke to context if not specified
    spoke = parsed.get("spoke", context_name or "general")
    
    try:
        # Parse workload
        workload = float(parsed["workload"])
        
        # Build task data for client
        task_data = {
            "task_name": parsed["name"],
            "context": spoke,
            "base_load_score": workload,
            "rule_type": parsed.get("rule", "WEEKLY").upper(),
            "active": True,
            "notes": parsed.get("notes")
        }
        
        rule_type = task_data["rule_type"]
        
        # Handle rule-specific fields
        if rule_type == "ONCE":
            if "due" in parsed:
                task_data["due_date"] = parsed["due"]
        
        elif rule_type == "WEEKLY":
            if "days" in parsed:
                days = parsed["days"].lower().split(",")
                task_data.update({
                    "mon": "mon" in days,
                    "tue": "tue" in days,
                    "wed": "wed" in days,
                    "thu": "thu" in days,
                    "fri": "fri" in days,
                    "sat": "sat" in days,
                    "sun": "sun" in days
                })
        
        elif rule_type == "EVERY_N_DAYS":
            if "interval" in parsed:
                task_data["interval_days"] = int(parsed["interval"])
            if "anchor" in parsed:
                task_data["anchor_date"] = parsed["anchor"]
        
        elif rule_type == "MONTHLY_DAY":
            if "day" in parsed:
                task_data["month_day"] = int(parsed["day"])
        
        # Create task via microservice client
        client = LBSClient(user_id=kwargs.get("user_id", "dev_user"))
        result = client.create_task(task_data)
        
        return CommandResult(
            success=True,
            message=f"Created task: {parsed['name']} (ID: {result.get('task_id')}, Spoke: {spoke}, Workload: {workload})",
            data={
                "task_id": result.get("task_id"),
                "task_name": parsed["name"],
                "spoke": spoke,
                "workload": workload
            }
        )
    
    except ValueError as e:
        return CommandResult(success=False, message=f"Invalid value: {str(e)}")
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to create task: {str(e)}")
