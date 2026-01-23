from __future__ import annotations
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from tools.base import BaseTool, NoArgs
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date

class ListNodesTool(BaseTool):
    name = "list_nodes"
    description = (
        "List all available nodes for communication. "
        "Returns a roster of IDs and descriptions for System Nodes, project specialists, and peer projects."
    )
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        current_node_id: str = kwargs.get("node_id")

        if not db_session or not user_id:
            return {"success": False, "message": "Context error"}

        try:
            from models.database import Node, Project
            from sqlalchemy import select

            # 1. System Nodes
            res_s = await db_session.execute(select(Node).filter(Node.node_type == "SYSTEM", Node.status == "active"))
            systems = res_s.scalars().all()

            # 2. Project Members
            res_m = await db_session.execute(select(Node).filter(Node.project_id == project_id, Node.node_type == "MEMBER", Node.status == "active"))
            members = res_m.scalars().all()

            # 3. Peer Projects
            res_p = await db_session.execute(
                select(Node).join(Project, Node.project_id == Project.id).filter(
                    Project.user_id == user_id,
                    Node.node_type == "PROJECT",
                    Node.id != current_node_id,
                    Node.status == "active"
                )
            )
            peers = res_p.scalars().all()

            nodes = []
            for n in systems + members + peers:
                nodes.append({
                    "id": n.id,
                    "type": n.node_type,
                    "role": n.role_name,
                    "display_name": n.display_name,
                    "description": n.description or "No description available."
                })

            return {"success": True, "message": f"Found {len(nodes)} available nodes.", "data": {"nodes": nodes}}
        except Exception as e:
            return {"success": False, "message": f"Failed to list nodes: {e}"}

class GetNodeProfileArgs(BaseModel):
    node_id: str = Field(..., description="The UUID of the node to inspect")

class GetNodeProfileTool(BaseTool):
    name = "get_node_profile"
    description = "Retrieve detailed profile and capabilities for a specific node ID."
    args_schema = GetNodeProfileArgs

    async def run(self, node_id: str, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session")
        if not db_session:
            return {"success": False, "message": "Context error"}
        
        try:
            from models.database import Node
            from sqlalchemy import select
            
            res = await db_session.execute(select(Node).filter(Node.id == node_id))
            node = res.scalars().first()
            if not node:
                return {"success": False, "message": f"Node {node_id} not found."}
            
            return {
                "success": True,
                "data": {
                    "id": node.id,
                    "type": node.node_type,
                    "role": node.role_name,
                    "display_name": node.display_name,
                    "description": node.description,
                    "tools": node.tools or [],
                    "status": node.status
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to get profile: {e}"}

class AskNodeArgs(BaseModel):
    target_id: str = Field(..., description="The UUID (node_id) of the target node. Obtained via 'list_nodes' or active roster.")
    message: str = Field(..., description="The content of the message to send")
    blocking: bool = Field(True, description="If True, waits for the response. If False, returns immediately and executes in background.")
    include_history: bool = Field(False, description="If True, propagates recent conversation history to the target node.")

class AskNodeTool(BaseTool):
    name = "ask_node"
    description = (
        "Send a message or a sub-task to another node. "
        "Allows for sub-delegation or looking up information from other projects/system nodes. "
        "Returns the response from the target node if blocking=True, otherwise returns a status acknowledging the request."
    )
    args_schema = AskNodeArgs

    async def run(self, target_id: str, message: str, blocking: bool = True, include_history: bool = False, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        session_id: str = kwargs.get("session_id")

        if not db_session or not user_id:
            return {"success": False, "message": "Context error: session or user_id missing"}
        
        # Prevent self-recursion
        current_node_id = kwargs.get("node_id")
        if target_id == current_node_id:
            return {"success": False, "message": "Error: You cannot call 'ask_node' on yourself to prevent infinite loops."}
        
        try:
            from models.database import Node
            from sqlalchemy import select
            
            # 1. Lookup node in DB strictly by ID
            result = await db_session.execute(
                select(Node).filter(Node.id == target_id).filter(Node.status == "active")
            )
            node_record = result.scalars().first()
            
            if not node_record:
                return {"success": False, "message": f"Target node ID '{target_id}' not found or inactive. Always use UUIDs from list_nodes."}

            # 1.5. Prepare message with history if requested
            final_message = message
            if include_history and session_id:
                from nodes.system.memory_node import MemoryNode
                memory = MemoryNode(kwargs)
                history = await memory.get_history(session_id)
                # Format last 5 messages as context
                recent = history[-5:] if len(history) > 5 else history
                history_text = "\n".join([f"{m.role}: {m.content}" for m in recent])
                final_message = f"## Conversation History\n{history_text}\n\n## Current Task\n{message}"

            # 2. Non-blocking Mode: Enqueue and return
            if not blocking:
                from queue_system.manager import QueueManager
                manager = QueueManager()
                
                # Pass necessary context for background execution
                # Explicitly include session_id and project_id to avoid ambiguity in worker
                clean_context = {k: v for k, v in kwargs.items() if k not in ["db_session", "session", "background_tasks"]}
                clean_context["project_id"] = node_record.project_id or project_id
                clean_context["session_id"] = session_id
                
                task_id = manager.enqueue_node_task(
                    user_id=user_id,
                    target_node_id=target_id,
                    message=final_message,
                    context=clean_context
                )
                
                return {
                    "success": True, 
                    "message": f"Request sent to {node_record.display_name} for background processing.",
                    "data": {"task_id": task_id, "status": "queued"}
                }

            # 3. Blocking Mode (Use NodeFactory)
            from services.node_factory import NodeFactory
            
            ctx = {
                'user_id': user_id, 
                'db_session': db_session, 
                'project_id': node_record.project_id or project_id,
                'session_id': session_id,
                'api_key': kwargs.get("api_key")
            }
            
            target_node = NodeFactory.get_node(node_record, ctx)
            
            if not target_node:
                return {"success": False, "message": f"Failed to instantiate node: {node_record.display_name}"}

            # 4. Process message
            resp = await target_node.process(final_message)
            return {"success": True, "message": f"Response from {node_record.display_name}: {resp}", "data": {"response": resp}}
            
        except Exception as e:
            return {"success": False, "message": f"Failed to call node {target_id}: {e}"}



class BroadcastMessageArgs(BaseModel):
    message: str = Field(..., description="Message content to broadcast")
    target_project_ids: Optional[list[str]] = Field(None, description="Optional list of project IDs. If None, broadcasts to all.")

class BroadcastSystemMessageTool(BaseTool):
    name = "broadcast_system_message"
    description = (
        "Sends notifications or alerts to active Project Hubs. "
        "Use this to push advice or warnings when global capacity is reached."
    )
    args_schema = BroadcastMessageArgs

    async def run(self, message: str, target_project_ids: Optional[list[str]] = None, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            from models.database import Project, ChatSession, ChatMessage
            from sqlalchemy import select
            import uuid
            
            # 1. Determine target projects
            if target_project_ids:
                res = await db_session.execute(select(Project).filter(Project.id.in_(target_project_ids)))
                projects = res.scalars().all()
            else:
                res = await db_session.execute(select(Project).filter(Project.user_id == user_id, Project.status == "active"))
                projects = res.scalars().all()
            
            count = 0
            for proj in projects:
                # 2. Get/Create a system session for the project
                # We look for a session titled "System Alerts" or similar
                session_res = await db_session.execute(
                    select(ChatSession).filter(
                        ChatSession.project_id == proj.id,
                        ChatSession.title == "System Alerts"
                    )
                )
                chat_session = session_res.scalars().first()
                
                if not chat_session:
                    chat_session = ChatSession(
                        id=str(uuid.uuid4()),
                        project_id=proj.id,
                        title="System Alerts",
                        summary="Global Scheduler automated alerts and advice."
                    )
                    db_session.add(chat_session)
                
                # 3. Add the message
                alert_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    session_id=chat_session.id,
                    role="system",
                    content=f"**[Global Scheduler Alert]**: {message}",
                    meta_payload={"sender": "GlobalScheduler", "type": "SYSTEM_ADVICE"}
                )
                db_session.add(alert_msg)
                count += 1
            
            await db_session.commit()
            return {"success": True, "message": f"Broadcasted alert to {count} projects via System Alerts session."}
        except Exception as e:
            return {"success": False, "message": f"Failed to broadcast message: {e}"}
