"""
Command Handlers
Implementation of slash commands (Refactored V4: Project-Centric)
"""
from typing import List
from pathlib import Path
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
import uuid

from services.command_parser import register_command, CommandResult, _registry
from services.inbox_handler import InboxHandler
from services.lbs_client import LBSClient
from utils.paths import get_project_dir
from models.database import Node, AgentProfile, ChatSession, ChatMessage


# ============================================================================
# PROJECT COMMANDS (Unified)
# ============================================================================

@register_command("check_inbox", "Check and read inbox messages", ["hub"])
async def handle_check_inbox(args: List[str], session: AsyncSession = None, **kwargs) -> CommandResult:
    """
    Fetch inbox messages and prepare them for Hub to read and respond to
    
    Usage: /check_inbox
    """
    if session is None:
        return CommandResult(success=False, message="No database session available")
    
    user_id = kwargs.get("user_id")
    
    try:
        inbox = InboxHandler(session, user_id=user_id)
        messages = await inbox.get_pending_messages()
        
        if not messages:
            return CommandResult(
                success=True,
                message="📭 Inbox is empty. No messages from Projects.",
                data={"messages": [], "has_messages": False}
            )
        
        # Format messages for Hub to read and respond to
        message_content = []
        message_content.append(f"📬 You have {len(messages)} messages from Projects:\n")
        
        for msg in messages:
            # Source project (formerly spoke)
            project = msg.source_project
            summary = msg.payload.get('summary', 'No summary')
            request = msg.payload.get('request', '')
            
            msg_text = f"\n**From {project}:**\n{summary}"
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
                        "project": msg.source_project,
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


@register_command("create_project", "Create a new Project", ["hub"])
async def handle_create_project(args: List[str], session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Create a new Project workspace and DB Node
    """
    if not args:
        return CommandResult(success=False, message="Usage: /create_project <project_name> [prompt=\"custom prompt\"]")
    
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")
        
    project_name = args[0]
    
    # Parse optional custom prompt
    custom_prompt = None
    for arg in args[1:]:
        if arg.startswith("prompt="):
            custom_prompt = arg.split("=", 1)[1].strip('"').strip("'")
    
    from utils.paths import validate_name
    valid, error = validate_name(project_name, "project_name")
    if not valid:
         return CommandResult(success=False, message=f"Invalid project name: {error}")

    try:
        # Check if node exists (No node_type filter needed in V4)
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == project_name
        ))
        existing_node = result.scalars().first()
        
        node = None
        if existing_node:
             if existing_node.is_archived:
                 existing_node.is_archived = False
                 node = existing_node
             else:
                 # Already exists
                 return CommandResult(success=False, message=f"Project '{project_name}' already exists")
        else:
            # Create new Node
            node_id = str(uuid.uuid4())
            node = Node(
                id=node_id,
                user_id=user_id,
                name=project_name,
                display_name=project_name.replace('_', ' ').title(),
                # node_type="PROJECT" # default
            )
            session.add(node)
            
            # Create default Profile
            profile = AgentProfile(
                id=str(uuid.uuid4()),
                node_id=node_id,
                system_prompt=custom_prompt or "You are a specialized AI assistant for this project.",
                is_active=True,
                version=1
            )
            session.add(profile)
            
            # Create files/artifacts directory structure
            project_dir = get_project_dir(user_id, project_name)
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "files").mkdir(exist_ok=True)
            (project_dir / "artifacts").mkdir(exist_ok=True)
            (project_dir / "refs").mkdir(exist_ok=True)
            
            await session.commit()
        
        message = f"✅ Created Project: {project_name}"
        if custom_prompt:
            message += " (with custom prompt)"
        
        return CommandResult(
            success=True,
            message=message,
            data={"project_name": project_name, "node_id": node.id, "custom_prompt": bool(custom_prompt)}
        )
    except Exception as e:
        if session: await session.rollback()
        return CommandResult(success=False, message=f"Failed to create Project: {str(e)}")

# Legacy Alias
_registry.register("create_spoke", handle_create_project, "Create new project (alias)", ["hub"])


@register_command("send_message", "Send a message to a Project", ["hub"])
async def handle_send_message(args: List[str], session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Send a message from Hub to a Project's DB history
    """
    if len(args) < 2:
        return CommandResult(success=False, message="Usage: /send_message <project_name> <message>")
    
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    project_name = args[0]
    message_content = " ".join(args[1:])
    
    # Remove quotes if present
    if message_content.startswith('"') and message_content.endswith('"'):
        message_content = message_content[1:-1]
    
    try:
        # 1. Find the Project Node
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == project_name
        ))
        node = result.scalars().first()
        
        if not node:
            return CommandResult(success=False, message=f"Project '{project_name}' does not exist")
        
        # 2. Get active session for that node
        result = await session.execute(select(ChatSession).filter(
            ChatSession.node_id == node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        chat_session = result.scalars().first()
        
        if not chat_session:
            # Create one if missing
            chat_session = ChatSession(
                id=str(uuid.uuid4()),
                node_id=node.id,
                title="New Session via Message",
                is_archived=False
            )
            session.add(chat_session)
            await session.commit()
            
        # 3. Add system message from Hub
        db_message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant", 
            content=f"[Hub -> {project_name}] {message_content}"
        )
        session.add(db_message)
        await session.commit()

        return CommandResult(
            success=True,
            message=f"📨 Message sent to {project_name}",
            data={"project_name": project_name, "node_id": node.id}
        )
    except Exception as e:
        if session: await session.rollback()
        return CommandResult(success=False, message=f"Failed to send message: {str(e)}")


@register_command("delete_project", "Delete a project (archive)", ["hub", "project"])
async def handle_delete_project(args: List[str], context_type: str = "hub", context_name: str = "hub", session: AsyncSession = None, **kwargs) -> CommandResult:
    """
    Delete a project permanently (Archive)
    """
    import shutil
    
    # Determine which project to delete
    if context_type == "project" and context_name != "hub":
        project_name = context_name
    elif args:
        project_name = args[0]
    else:
        return CommandResult(success=False, message="Usage: /delete_project <project_name>")
    
    if project_name == "hub":
         return CommandResult(success=False, message="Cannot delete the Hub/Root project.")

    user_id = kwargs.get("user_id")
    if not user_id:
        return CommandResult(success=False, message="Missing user context")
    
    try:
        # 1. Find and archive DB Node
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == project_name
        )) if session else None
        node = result.scalars().first() if result else None
        
        if node:
            node.is_archived = True
            await session.commit()
            print(f"[DELETE] Archived DB Node for project '{project_name}'")
        else:
            return CommandResult(success=False, message=f"Project '{project_name}' not found")

        # 2. Delete LBS tasks (Legacy) - Keeping for cleanup
        try:
            client = LBSClient(user_id=user_id)
            tasks = await client.get_tasks(context=project_name)
            for t in tasks:
                await client.delete_task(t["task_id"])
        except Exception as lbs_err:
            pass # LBS might not be active
        
        # 3. Handle inbox notification
        if context_type == "project" and session:
            meta_xml = f"""<meta-action type="share_update">
<target>Hub</target>
<timestamp>{datetime.now().isoformat()}</timestamp>
<summary>Project '{project_name}' has been deleted</summary>
<request></request>
</meta-action>"""
            inbox = InboxHandler(session, user_id=user_id)
            await inbox.push_to_inbox(
                source_project=project_name,
                meta_action_xml=meta_xml
            )
        
        # 4. Cleanup directory (Move to archive or delete?)
        # V4 Policy: Archive on disk
        # But user said "Delete".
        # Let's rename folder to avoid name reuse conflict.
        project_dir = get_project_dir(user_id, project_name)
        if project_dir.exists():
             timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
             archive_name = f"{project_name}_archived_{timestamp}"
             try:
                 project_dir.rename(project_dir.parent / archive_name)
             except Exception:
                 pass
        
        return CommandResult(
            success=True,
            message=f"🗑️ Deleted Project: {project_name}",
            data={"project_name": project_name, "deleted": True, "redirect_url": "/projects"}
        )
    except Exception as e:
        if session: await session.rollback()
        return CommandResult(success=False, message=f"Failed to delete Project: {str(e)}")

# Alias
_registry.register("kill", handle_delete_project, "Delete project (alias)", ["hub", "project"])


@register_command("clone", "Clone the current project or a specified project", ["hub", "project"])
async def handle_clone(args: List[str], context_type: str = "hub", context_name: str = "hub", session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Clone a project
    """
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    # Determine source
    if context_type == "project" and context_name != "hub":
        source_name = context_name
        new_name_arg = args[0] if args else None
    elif args:
        source_name = args[0]
        new_name_arg = args[1] if len(args) > 1 else None
    else:
        return CommandResult(success=False, message="Usage: /clone <project_name> [new_name]")

    try:
        # 1. Verify source exists
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == source_name,
            Node.is_archived == False
        ))
        source_node = result.scalars().first()

        if not source_node:
            return CommandResult(success=False, message=f"Source project '{source_name}' not found")

        # 2. Determine new name
        final_new_name = new_name_arg if new_name_arg else f"{source_name}_copy"
        
        # Prevent collision
        base_new_name = final_new_name
        counter = 1
        while (await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == final_new_name))).scalars().first():
            final_new_name = f"{base_new_name}_{counter}"
            counter += 1

        # 3. Create Node (Simplified logic for command)
        # Using get_project_dir
        new_dir = get_project_dir(user_id, final_new_name)
        
        new_node_id = str(uuid.uuid4())
        new_node = Node(
            id=new_node_id,
            user_id=user_id,
            name=final_new_name,
            display_name=f"{source_node.display_name} (Copy)" if source_node.display_name else final_new_name.replace('_', ' ').title(),
            lbs_access_level=source_node.lbs_access_level
        )
        session.add(new_node)
        
        # Copy Profile
        result = await session.execute(select(AgentProfile).filter(AgentProfile.node_id == source_node.id, AgentProfile.is_active == True))
        source_profile = result.scalars().first()
        if source_profile:
            new_profile = AgentProfile(id=str(uuid.uuid4()), node_id=new_node_id, system_prompt=source_profile.system_prompt, is_active=True, version=1)
            session.add(new_profile)
            
        # Copy Sessions
        from models.database import ChatSession, ChatMessage
        result = await session.execute(select(ChatSession).filter(ChatSession.node_id == source_node.id))
        sessions = result.scalars().all()
        for s in sessions:
            new_session_id = str(uuid.uuid4())
            new_session = ChatSession(
                id=new_session_id,
                node_id=new_node_id,
                title=s.title,
                summary=s.summary,
                is_archived=s.is_archived,
                created_at=s.created_at
            )
            session.add(new_session)
            
            result = await session.execute(select(ChatMessage).filter(ChatMessage.session_id == s.id))
            messages = result.scalars().all()
            for msg in messages:
                new_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    session_id=new_session_id,
                    role=msg.role,
                    content=msg.content,
                    meta_payload=msg.meta_payload,
                    is_excluded=msg.is_excluded,
                    created_at=msg.created_at
                )
                session.add(new_msg)
            
        # Copy Physical
        import shutil
        source_dir = get_project_dir(user_id, source_name)
        new_dir.mkdir(parents=True, exist_ok=True)
        if source_dir.exists():
            for sub in ['files', 'artifacts', 'refs']:
                if (source_dir / sub).exists():
                    shutil.copytree(source_dir / sub, new_dir / sub, dirs_exist_ok=True)
        
        await session.commit()
        return CommandResult(success=True, message=f"✅ Project '{source_name}' cloned as '{final_new_name}'", data={"new_project_name": final_new_name})

    except Exception as e:
        if session: await session.rollback()
        return CommandResult(success=False, message=f"Cloning failed: {str(e)}")


@register_command("archive", "Archive conversation and start fresh", ["hub", "project"])
async def handle_archive(args: List[str], context_type: str = "hub", context_name: str = "hub", session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Archive and rotate DB session
    """
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    # 1. Determine target node
    target_name = context_name
    if args:
        target_name = args[0]
        
    try:
        # 2. Find Node
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == target_name
        ))
        node = result.scalars().first()
        
        if not node:
            return CommandResult(success=False, message=f"Node '{target_name}' not found")
        
        # 3. Archive current active session
        result = await session.execute(select(ChatSession).filter(
            ChatSession.node_id == node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if active_session:
            # Summary Logic
            try:
                from services.context_manager import ContextManager
                # context_type is 'hub' or 'project'.
                manager = ContextManager(
                    user_id=user_id,
                    context_type="project", # All are projects
                    context_name=node.name,
                    session=session
                )
                await manager.archive_context(force=True)
            except Exception as summary_err:
                print(f"[Archive] Summary failed: {summary_err}")
            
            active_session.is_archived = True
            await session.commit()
           
        # 4. Create new session
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            node_id=node.id,
            title=f"Session started {datetime.now().strftime('%Y-%m-%d')}",
            is_archived=False
        )
        session.add(new_session)
        await session.commit()
        
        return CommandResult(
            success=True,
            message=f"📦 Archived current session for {target_name}. New session started.",
            data={"node_id": node.id, "new_session_id": new_session.id}
        )
    except Exception as e:
        if session: await session.rollback()
        return CommandResult(success=False, message=f"Failed to archive: {str(e)}")


@register_command("report", "Generate progress report", ["project"])
async def handle_report(args: List[str], context_name: str = None, session: AsyncSession = None, **kwargs) -> CommandResult:
    """
    Generate a progress report (Project to Hub)
    """
    if session is None or context_name is None:
        return CommandResult(success=False, message="Missing context")
    
    user_id = kwargs.get("user_id")
    if not user_id:
        return CommandResult(success=False, message="Missing user context")
    
    summary = " ".join(args) if args else f"Progress update from {context_name}"
    
    try:
        inbox = InboxHandler(session, user_id=user_id)
        
        # Create XML meta-action for inbox
        meta_xml = f"""<meta-action type="share_update">
    <target>Hub</target>
    <timestamp>{datetime.now().isoformat()}</timestamp>
    <summary>{summary}</summary>
    <request></request>
</meta-action>"""
        
        # Push to inbox queue
        await inbox.push_to_inbox(
            source_project=context_name,
            meta_action_xml=meta_xml
        )
        
        return CommandResult(
            success=True,
            message=f"📤 Report sent to Hub inbox",
            data={"project": context_name, "summary": summary}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to send report: {str(e)}")


@register_command("process_inbox", "Process an inbox message", ["hub"])
async def handle_process_inbox(args: List[str], session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
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
        success = await inbox.process_message(msg_id, action)
        
        if success:
            return CommandResult(success=True, message=f"✅ Message {msg_id} {action}ed successfully.")
        else:
            return CommandResult(success=False, message=f"Failed to process message {msg_id}. It may not exist.")
            
    except ValueError:
        return CommandResult(success=False, message="Invalid message ID. Must be an integer.")
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to process inbox: {str(e)}")


@register_command("create_task", "Create a new LBS task", ["hub", "project"])
async def handle_create_task(args: List[str], session: AsyncSession = None, context_name: str = None, **kwargs) -> CommandResult:
    """
    Create a new task in the LBS system
    Usage: /create_task name="<task_name>" project="<project>" workload=<0-10> ...
    """
    if session is None:
        return CommandResult(success=False, message="No database session available")
    
    # Parse key=value arguments
    parsed = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            value = value.strip('"').strip("'")
            parsed[key] = value
    
    if "name" not in parsed:
        return CommandResult(success=False, message="Missing required field: name")
    if "workload" not in parsed:
        return CommandResult(success=False, message="Missing required field: workload")
    
    project = parsed.get("project", parsed.get("spoke", context_name or "general"))
    
    try:
        workload = float(parsed["workload"])
        task_data = {
            "task_name": parsed["name"],
            "context": project,
            "base_load_score": workload,
            "rule_type": parsed.get("rule", "WEEKLY").upper(),
            "active": True,
            "notes": parsed.get("notes")
        }
        
        rule_type = task_data["rule_type"]
        
        if rule_type == "ONCE" and "due" in parsed:
            task_data["due_date"] = parsed["due"]
        elif rule_type == "WEEKLY" and "days" in parsed:
            days = parsed["days"].lower().split(",")
            task_data.update({k: k in days for k in ["mon","tue","wed","thu","fri","sat","sun"]})
        
        client = LBSClient(user_id=kwargs.get("user_id", "dev_user"))
        result = await client.create_task(task_data)
        
        return CommandResult(
            success=True,
            message=f"Created task: {parsed['name']} (ID: {result.get('task_id')}, Project: {project})",
            data={"task_id": result.get("task_id")}
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to create task: {str(e)}")


@register_command("move", "Move to a different chat page", ["hub", "project"])
async def handle_move(args: List[str], session: AsyncSession = None, user_id: str = None, **kwargs) -> CommandResult:
    """
    Navigate between Hub and Projects
    Usage: /move [hub|project_name]
    """
    if not session or not user_id:
        return CommandResult(success=False, message="Missing database session or user context")

    target = args[0].lower() if args else "hub"
    
    if target == "hub":
        return CommandResult(success=True, message="🚀 Moving to Hub page...", data={"redirect_url": "/hub"})
    
    result = await session.execute(select(Node).filter(
        Node.user_id == user_id,
        Node.name == target
    ))
    node = result.scalars().first()
    
    if node:
        # Frontend URL change: /spokes/{target} -> /project/{target}
        # Assuming frontend supports /project route (we will fix frontend next)
        return CommandResult(success=True, message=f"🚀 Moving to {target}...", data={"redirect_url": f"/project/{target}"})
    else:
        return CommandResult(success=False, message=f"❌ Project '{target}' not found.")

# Register alias
_registry.register("mv", handle_move, "Move alias", ["hub", "project"])
