from typing import List, Dict, Any, Optional
from tools.base import BaseTool, NoArgs
from pydantic import BaseModel, Field
from queue_system.manager import QueueManager

class MulticastMessageArgs(BaseModel):
    target_ids: List[str] = Field(..., description="List of node IDs to notify.")
    message: str = Field(..., description="The message or instruction to send to all targets.")
    force: bool = Field(False, description="If True, bypass redundancy checks and notify nodes even if they were already triggered by Regex hooks.")

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

    async def run(self, target_ids: List[str], message: str, force: bool = False, **kwargs) -> Any:
        from tools.base import ToolResult
        if not target_ids:
            return ToolResult(content="Error: No target IDs provided.", is_success=False)

        db_session = self.context.get("db_session")
        user_id = self.context.get("user_id")
        project_id = self.context.get("project_id")
        session_id = self.context.get("session_id")
        already_triggered = self.context.get("already_triggered_node_ids", [])

        if not user_id:
            return ToolResult(content="Error: No user_id in context.", is_success=False)
        if not db_session:
            return ToolResult(content="Error: No db_session in context.", is_success=False)

        # 1. Validation and Filtering
        from models.database import Node
        from sqlalchemy import select
        
        # Fetch all valid node IDs in project to prevent hallucination
        res = await db_session.execute(select(Node.id))
        valid_node_ids = set(res.scalars().all())

        filtered_targets = []
        skipped_redundant = []
        invalid_ids = []

        for tid in target_ids:
            if tid not in valid_node_ids:
                invalid_ids.append(tid)
                continue
            
            if not force and tid in already_triggered:
                skipped_redundant.append(tid)
                continue
            
            filtered_targets.append(tid)

        if invalid_ids:
            return ToolResult(content=f"Error: The following Target IDs do not exist: {', '.join(invalid_ids)}. Please check the PROJECT ROSTER and try again with correct IDs.", is_success=False)

        if not filtered_targets:
            if skipped_redundant:
                return ToolResult(content=f"Multicast cancelled: All targets ({', '.join(skipped_redundant)}) were already notified via Tier 1 hooks. Use 'force=True' if a redundant call is intentional.", is_success=False)
            return ToolResult(content="Error: No valid targets identified for multicast.", is_success=False)

        # 2. Enqueue Tasks
        manager = QueueManager()
        current_node_id = self.context.get("node_id")
        count = 0
        
        for target_id in filtered_targets:
            if target_id == current_node_id:
                print(f"[MulticastMessageTool] Skipping self-recursion for node {target_id}")
                continue
            
            manager.enqueue_node_task(
                user_id=user_id,
                target_node_id=target_id,
                message=message,
                context={
                    "triggered_by_multicast": True,
                    "session_id": session_id,
                    "project_id": project_id,
                    "original_message": message,
                    "files": self.context.get("files", []),
                    "attached_files": self.context.get("attached_files", [])
                }
            )
            count += 1
        
        status_msg = f"Successfully multicasted message to {count} agents."
        if skipped_redundant:
            status_msg += f" (Note: {len(skipped_redundant)} nodes were skipped as they were already triggered by Regex hooks)."
        
        return ToolResult(content=status_msg)

class SubscribeIntentArgs(BaseModel):
    pattern: Optional[str] = Field(None, description="Regex pattern for immediate matching (e.g., '.*urgent.*').")
    intent_description: Optional[str] = Field(None, description="Natural language description of your interest for AI-based semantic routing (e.g., 'messages about personal health').")
    description: Optional[str] = Field(None, description="User-facing label for this monitor/hook.")
    session_bound: bool = Field(True, description="If True, this subscription will be automatically removed when the current session is archived (recommended).")

class SubscribeIntentTool(BaseTool):
    """
    Tool for agents to subscribe to specific message patterns or semantic intents.
    When a message matches, the Router will notify this agent.
    Use this for long-term monitoring or to become a 'Subject Matter Expert' for a topic.
    """
    name = "subscribe_to_intent"
    description = (
        "Subscribe to message patterns. You can use regex patterns for exact matching "
        "or natural language descriptions ('intent_description') for semantic AI-based matching. "
        "The System Router will then notify you whenever a relevant message is detected."
    )
    args_schema = SubscribeIntentArgs

    async def run(self, pattern: Optional[str] = None, intent_description: Optional[str] = None, description: Optional[str] = None, session_bound: bool = True, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session = self.context.get("db_session")
        node_id = self.context.get("node_id")
        session_id = self.context.get("session_id") if session_bound else None
        
        if not db_session or not node_id:
            return ToolResult(content="Error: Database session or Node ID missing from context.", is_success=False)

        if not pattern and not intent_description:
            return ToolResult(content="Error: Either 'pattern' or 'intent_description' must be provided.", is_success=False)

        from models.database import Node
        from sqlalchemy import select
        from services.router import Router

        try:
            # 1. Update DB meta_payload
            stmt = select(Node).filter(Node.id == node_id)
            res = await db_session.execute(stmt)
            node = res.scalars().first()
            
            if not node:
                return ToolResult(content=f"Error: Node record {node_id} not found.", is_success=False)

            import copy
            meta = copy.deepcopy(node.meta_payload or {})
            updated = False

            # Handle Regex Path
            import uuid
            def generate_id():
                return f"sub_{str(uuid.uuid4())[:8]}"

            if pattern:
                patterns = meta.get("trigger_patterns", [])
                # Check for existing
                if not any(p.get("value") == pattern for p in patterns if isinstance(p, dict)):
                    sub_id = generate_id()
                    patterns.append({
                        "id": sub_id,
                        "value": pattern, 
                        "session_id": session_id, 
                        "description": description
                    })
                    meta["trigger_patterns"] = patterns
                    updated = True
            
            # Handle Semantic Path
            if intent_description:
                interests = meta.get("semantic_interests", [])
                # Check for existing
                if not any(i.get("value") == intent_description for i in interests if isinstance(i, dict)):
                    sub_id = generate_id()
                    interests.append({
                        "id": sub_id,
                        "value": intent_description, 
                        "session_id": session_id, 
                        "description": description
                    })
                    meta["semantic_interests"] = interests
                    updated = True

            if updated:
                node.meta_payload = meta
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(node, "meta_payload")
                await db_session.commit()
            
            # 2. Register regex in memory for immediate effect (if applicable)
            # We re-initialize the entire hook set to ensure consistency
            await Router.initialize_default_hooks()
            
            # Include the ID in the response if we only added one thing
            msg = "Successfully subscribed to intent."
            if updated:
                added_id = ""
                if pattern: added_id = meta["trigger_patterns"][-1]["id"]
                elif intent_description: added_id = meta["semantic_interests"][-1]["id"]
                msg += f" (Subscription ID: {added_id})"
            
            return ToolResult(content=msg)
        except Exception as e:
            await db_session.rollback()
            return ToolResult(content=f"Error registering subscription: {e}", is_success=False)

class UnsubscribeIntentArgs(BaseModel):
    subscription_id: Optional[str] = Field(None, description="The unique ID of the subscription to remove (e.g., 'sub_abcd1234'). Preferred.")
    pattern: Optional[str] = Field(None, description="The regex pattern to remove (if ID is unknown).")
    intent_description: Optional[str] = Field(None, description="The semantic intent description to remove (if ID is unknown).")

class UnsubscribeIntentTool(BaseTool):
    """
    Tool for agents to unsubscribe from message patterns or semantic intents.
    Removes a previously registered subscription by ID or value.
    """
    name = "unsubscribe_from_intent"
    description = (
        "Remove a subscription to a message pattern or semantic intent. "
        "Use subscription_id if known, otherwise provide the exact pattern/description."
    )
    args_schema = UnsubscribeIntentArgs

    async def run(self, subscription_id: Optional[str] = None, pattern: Optional[str] = None, intent_description: Optional[str] = None, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session = self.context.get("db_session")
        node_id = self.context.get("node_id")
        
        if not db_session or not node_id:
            return ToolResult(content="Error: Database session or Node ID missing from context.", is_success=False)

        if not subscription_id and not pattern and not intent_description:
            return ToolResult(content="Error: Either 'subscription_id', 'pattern', or 'intent_description' must be provided.", is_success=False)

        from models.database import Node
        from sqlalchemy import select

        try:
            stmt = select(Node).filter(Node.id == node_id)
            res = await db_session.execute(stmt)
            node = res.scalars().first()
            
            if not node:
                return ToolResult(content=f"Error: Node record {node_id} not found.", is_success=False)

            import copy
            meta = copy.deepcopy(node.meta_payload or {})
            updated = False

            # Helper to remove from list
            def remove_from_meta(key, value, by_id=False):
                nonlocal updated
                lst = meta.get(key, [])
                if not lst: return lst
                
                new_lst = []
                for item in lst:
                    if not isinstance(item, dict): continue # Should not happen in new system
                    
                    match = False
                    if by_id:
                        if item.get("id") == value: match = True
                    else:
                        if item.get("value") == value: match = True
                    
                    if match:
                        updated = True
                        continue
                    new_lst.append(item)
                return new_lst

            if subscription_id:
                meta["trigger_patterns"] = remove_from_meta("trigger_patterns", subscription_id, by_id=True)
                # If not found in patterns, try interests (checking updated flag)
                was_updated = updated
                meta["semantic_interests"] = remove_from_meta("semantic_interests", subscription_id, by_id=True)
                # updated will be True if either matched
            else:
                if pattern:
                    meta["trigger_patterns"] = remove_from_meta("trigger_patterns", pattern)
                if intent_description:
                    meta["semantic_interests"] = remove_from_meta("semantic_interests", intent_description)

            if updated:
                node.meta_payload = meta
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(node, "meta_payload")
                await db_session.commit()
                
                # Sync Router memory
                from services.router import Router
                await Router.initialize_default_hooks()
                
                return ToolResult(content="Successfully unsubscribed.")
            
            return ToolResult(content="No matching subscription found to remove.", is_success=False)
        except Exception as e:
            await db_session.rollback()
            return ToolResult(content=f"Error removing subscription: {e}", is_success=False)

class ListSubscriptionsTool(BaseTool):
    """
    Tool for agents to list their current active message subscriptions.
    Returns a list of IDs, patterns, interests, and their session-binding status.
    """
    name = "list_my_subscriptions"
    description = "List all active subscriptions (intents and regex hooks) for your node."
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session = self.context.get("db_session")
        node_id = self.context.get("node_id")
        
        if not db_session or not node_id:
            return ToolResult(content="Error: Database session or Node ID missing from context.", is_success=False)

        from models.database import Node
        from sqlalchemy import select

        try:
            stmt = select(Node).filter(Node.id == node_id)
            res = await db_session.execute(stmt)
            node = res.scalars().first()
            
            if not node: return ToolResult(content="Error: Node not found.", is_success=False)

            meta = node.meta_payload or {}
            patterns = meta.get("trigger_patterns", [])
            interests = meta.get("semantic_interests", [])

            if not patterns and not interests:
                return ToolResult(content="You have no active subscriptions.")

            lines = ["### Your Active Subscriptions:"]
            
            if patterns:
                lines.append("\n**Regex Patterns (Tier 1):**")
                for p in patterns:
                    if not isinstance(p, dict): continue
                    bound = f" (Bound to session {p['session_id'][:8]})" if p.get('session_id') else " (Permanent)"
                    desc = f" - {p.get('description')}" if p.get('description') else ""
                    lines.append(f"- ID: `{p.get('id')}` | Pattern: `{p.get('value')}`{bound}{desc}")

            if interests:
                lines.append("\n**Semantic Interests (Tier 2):**")
                for i in interests:
                    if not isinstance(i, dict): continue
                    bound = f" (Bound to session {i['session_id'][:8]})" if i.get('session_id') else " (Permanent)"
                    desc = f" - {i.get('description')}" if i.get('description') else ""
                    lines.append(f"- ID: `{i.get('id')}` | Intent: `{i.get('value')}`{bound}{desc}")

            return ToolResult(content="\n".join(lines))
        except Exception as e:
            return ToolResult(content=f"Error listing subscriptions: {e}", is_success=False)
