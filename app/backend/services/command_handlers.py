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
from utils.paths import get_spoke_dir


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
def handle_create_spoke(args: List[str], **kwargs) -> CommandResult:
    """
    Create a new Spoke workspace
    
    Usage: 
      /create_spoke <spoke_name>
      /create_spoke <spoke_name> prompt="Custom system prompt"
    
    Examples:
      /create_spoke research
      /create_spoke thesis prompt="You are a thesis writing assistant specialized in academic research."
    """
    if not args:
        return CommandResult(success=False, message="Usage: /create_spoke <spoke_name> [prompt=\"custom prompt\"]")
    
    spoke_name = args[0]
    
    # Parse optional custom prompt
    custom_prompt = None
    for arg in args[1:]:
        if arg.startswith("prompt="):
            custom_prompt = arg.split("=", 1)[1].strip('"').strip("'")
    
    try:
        spoke_dir = get_spoke_dir(spoke_name)
        
        if spoke_dir.exists():
            return CommandResult(success=False, message=f"Spoke '{spoke_name}' already exists")
        
        # Create directory structure
        spoke_dir.mkdir(parents=True, exist_ok=True)
        (spoke_dir / "artifacts").mkdir(exist_ok=True)
        (spoke_dir / "refs").mkdir(exist_ok=True)
        
        # Create custom or default prompt
        if custom_prompt:
            prompt_text = custom_prompt
        else:
            prompt_text = f"""# {spoke_name.replace('_', ' ').title()}

You are a specialized execution agent for the {spoke_name} project.
Focus on delivering high-quality work within this context.

## Available Commands

**IMPORTANT: You can use these commands DIRECTLY in your responses. Just include the command.**

- `/report "message"` - Send progress updates to Hub
- `/archive` - Archive conversation and start fresh  
- `/kill` - Delete this spoke (use with caution)

## How to Send Messages to Hub

When you complete a milestone or have important updates, **just use the /report command directly**:

**Correct:**
```
I've completed the analysis. Here are the findings...

/report "Analysis phase completed. Key findings: X, Y, Z."
```

**Don't ask permission - just do it when appropriate!**

## Reference Files

Files in your reference library are automatically loaded in your context.
Use them to provide informed, accurate responses.

Work efficiently and communicate proactively with the Hub.
"""
        
        (spoke_dir / "system_prompt.md").write_text(prompt_text, encoding='utf-8')
        
        # Create empty chat log
        (spoke_dir / "chat.log").touch()
        
        message = f"✅ Created Spoke: {spoke_name}"
        if custom_prompt:
            message += " (with custom prompt)"
        
        return CommandResult(
            success=True,
            message=message,
            data={"spoke_name": spoke_name, "path": str(spoke_dir), "custom_prompt": bool(custom_prompt)}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to create Spoke: {str(e)}")


@register_command("send_message", "Send a message to a Spoke", ["hub"])
def handle_send_message(args: List[str], **kwargs) -> CommandResult:
    """
    Send a message from Hub to a Spoke's chat log
    
    Usage: /send_message <spoke_name> <message>
    """
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /send_message <spoke_name> <message>")
    
    spoke_name = args[0]
    message = " ".join(args[1:])
    
    # Remove quotes if present
    if message.startswith('"') and message.endswith('"'):
        message = message[1:-1]
    
    try:
        spoke_dir = get_spoke_dir(spoke_name)
        
        if not spoke_dir.exists():
            return CommandResult(success=False, message=f"Spoke '{spoke_name}' does not exist")
        
        chat_log = spoke_dir / "chat.log"
        
        # Append message to chat log
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(chat_log, 'a', encoding='utf-8') as f:
            f.write(f"\nHub: [{timestamp}] {message}\n\n")
        
        return CommandResult(
            success=True,
            message=f"📨 Message sent to {spoke_name}",
            data={"spoke_name": spoke_name, "message": message}
        )
    except Exception as e:
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
        spoke_dir = get_spoke_dir(spoke_name)
        
        if not spoke_dir.exists():
            return CommandResult(success=False, message=f"Spoke '{spoke_name}' does not exist")
        
        # Delete all tasks belonging to this spoke (for consistency)
        try:
            client = LBSClient(user_id="dev_user")
            tasks = client.get_tasks(context=spoke_name)
            for t in tasks:
                client.delete_task(t["task_id"])
            print(f"[KILL] Deleted tasks for spoke '{spoke_name}' via LBS microservice")
        except Exception as lbs_err:
            print(f"[KILL] Warning: Failed to cleanup LBS tasks: {lbs_err}")
        
        # If killed from Spoke itself, send notification to Hub inbox
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
        
        # Delete the spoke directory
        shutil.rmtree(spoke_dir)
        
        return CommandResult(
            success=True,
            message=f"🗑️ Deleted Spoke: {spoke_name}",
            data={"spoke_name": spoke_name, "deleted": True, "redirect": True}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to delete Spoke: {str(e)}")


@register_command("archive", "Archive conversation and start fresh", ["hub", "spoke"])
def handle_archive(args: List[str], context_type: str = "hub", context_name: str = "hub", **kwargs) -> CommandResult:
    """
    Archive and rotate chat log
    
    Usage:
      From Hub: /archive [spoke_name]
      From Spoke: /archive
    """
    # Determine context
    if context_type == "spoke":
        target_spoke = context_name
        chat_log_path = get_spoke_dir(target_spoke) / "chat.log"
    elif args:
        # Hub archiving a specific spoke
        target_spoke = args[0]
        chat_log_path = get_spoke_dir(target_spoke) / "chat.log"
    else:
        # Hub archiving itself
        from utils.paths import get_hub_dir
        target_spoke = "hub"
        chat_log_path = get_hub_dir() / "chat.log"
    
    try:
        if not chat_log_path.exists():
            return CommandResult(success=False, message=f"No chat log found for {target_spoke}")
        
        # Create archive directory
        archive_dir = chat_log_path.parent / "archives"
        archive_dir.mkdir(exist_ok=True)
        
        # Move current log to archive
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"chat_{timestamp}.log"
        chat_log_path.rename(archive_path)
        
        # Create new empty log
        chat_log_path.touch()
        
        return CommandResult(
            success=True,
            message=f"📦 Archived {target_spoke} → {archive_path.name}",
            data={"archived_to": str(archive_path), "context": target_spoke}
        )
    except Exception as e:
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
        client = LBSClient(user_id="dev_user")
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
