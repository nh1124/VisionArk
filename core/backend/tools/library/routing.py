from typing import List, Dict, Any, Optional
from tools.base import BaseTool
from pydantic import BaseModel, Field
from queue_system.manager import QueueManager

class MulticastMessageArgs(BaseModel):
    target_ids: List[str] = Field(..., description="List of node IDs to notify.")
    message: str = Field(..., description="The message or instruction to send to all targets.")

class MulticastMessageTool(BaseTool):
    """
    Tool to send a single message to multiple target nodes simultaneously.
    This is more efficient than calling ask_node multiple times.
    """
    name = "multicast_message"
    description = (
        "Send a fire-and-forget message to multiple target IDs at once. "
        "Use this for routing a single intent to multiple specialized agents."
    )
    args_schema = MulticastMessageArgs

    async def run(self, target_ids: List[str], message: str) -> str:
        if not target_ids:
            return "Error: No target IDs provided."

        user_id = self.context.get("user_id")
        project_id = self.context.get("project_id")
        session_id = self.context.get("session_id")

        if not user_id:
            return "Error: No user_id in context."

        manager = QueueManager()
        for target_id in target_ids:
            manager.enqueue_node_task(
                user_id=user_id,
                target_node_id=target_id,
                message=message,
                context={
                    "triggered_by_multicast": True,
                    "session_id": session_id,
                    "project_id": project_id,
                    "original_message": message
                }
            )
        
        return f"Successfully multicasted message to {len(target_ids)} agents."

class RegisterRoutingHookArgs(BaseModel):
    pattern: Optional[str] = Field(None, description="Regex pattern for Fast-Path monitoring (e.g., '.*urgent.*').")
    intent_description: Optional[str] = Field(None, description="Natural language description of your interest for AI-based semantic routing (e.g., 'messages about budget concerns').")
    description: Optional[str] = Field(None, description="User-facing label for this hook.")

class RegisterRoutingHookTool(BaseTool):
    """
    Tool for agents to dynamically register interest in specific message patterns.
    When a message matching the pattern is detected, the Router will notify this agent.
    """
    name = "register_routing_hook"
    description = (
        "Subscribe to message patterns. You can use regex patterns for exact matching "
        "or natural language descriptions ('intent_description') for semantic AI-based matching."
    )
    args_schema = RegisterRoutingHookArgs

    async def run(self, pattern: Optional[str] = None, intent_description: Optional[str] = None, description: Optional[str] = None) -> str:
        db_session = self.context.get("db_session")
        node_id = self.context.get("node_id")
        
        if not db_session or not node_id:
            return "Error: Database session or Node ID missing from context."

        if not pattern and not intent_description:
            return "Error: Either 'pattern' or 'intent_description' must be provided."

        from models.database import Node
        from sqlalchemy import select
        from services.router import Router

        try:
            # 1. Update DB meta_payload
            stmt = select(Node).filter(Node.id == node_id)
            res = await db_session.execute(stmt)
            node = res.scalars().first()
            
            if not node:
                return f"Error: Node record {node_id} not found."

            meta = node.meta_payload or {}
            updated = False

            # Handle Regex Path
            if pattern:
                patterns = meta.get("trigger_patterns", [])
                if pattern not in patterns:
                    patterns.append(pattern)
                    meta["trigger_patterns"] = patterns
                    updated = True
            
            # Handle Semantic Path
            if intent_description:
                interests = meta.get("semantic_interests", [])
                if intent_description not in interests:
                    interests.append(intent_description)
                    meta["semantic_interests"] = interests
                    updated = True

            if updated:
                node.meta_payload = meta
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(node, "meta_payload")
                await db_session.commit()
            
            # 2. Register regex in memory for immediate effect (if applicable)
            if pattern:
                router = Router()
                router.register_hook(pattern, node_id, description or f"Dynamic hook from {node.display_name}")
            
            return f"Successfully registered interest. (Pattern: {pattern}, Intent: {intent_description})"
        except Exception as e:
            await db_session.rollback()
            return f"Error registering hook: {e}"
