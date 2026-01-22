import re
import asyncio
from typing import List, Dict, Callable, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import Node, AsyncSessionLocal

class Router:
    """
    Central message router for VisionArk.
    Handles message pattern matching and multicasting to registered nodes.
    """
    _instance = None
    _hooks: List[Dict[str, Any]] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Router, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register_hook(cls, pattern: str, target_node_id: str, description: str = ""):
        """Register a node's interest in a specific message pattern."""
        cls._hooks.append({
            "pattern": pattern,
            "regex": re.compile(pattern, re.IGNORECASE),
            "target_node_id": target_node_id,
            "description": description
        })
        print(f"Router: Registered hook for pattern '{pattern}' -> Node {target_node_id}")

    async def dispatch(self, message: str, context: Dict[str, Any]):
        """
        Check message against registered hooks and trigger background tasks for matches.
        Also triggers AI-based deep analysis via the RouterNode.
        """
        user_id = context.get("user_id")
        if not user_id:
            return

        # 1. FAST ROUTING: Regex Hooks
        matches = []
        for hook in self._hooks:
            if hook["regex"].search(message):
                matches.append(hook)

        from queue_system.manager import QueueManager
        manager = QueueManager()

        if matches:
            print(f"Router: Found {len(matches)} fast-hook matches.")
            for match in matches:
                target_id = match["target_node_id"]
                manager.enqueue_node_task(
                    user_id=user_id,
                    target_node_id=target_id,
                    message=message,
                    context={
                        "triggered_by_hook": True,
                        "hook_pattern": match["pattern"],
                        "original_message": message,
                        "session_id": context.get("session_id"),
                        "project_id": context.get("project_id")
                    }
                )

        # 2. DEEP ROUTING: Trigger RouterNode (AI Analysis)
        # Skip trivial messages (short or common shallow responses)
        msg_clean = message.strip().lower()
        is_trivial = len(msg_clean) < 5 or msg_clean in ["hi", "hello", "ok", "yes", "no", "thanks", "done", "cancel"]
        
        if is_trivial:
            print(f"Router: Skipping deep analysis for trivial message.")
            return

        # We find the RouterNode ID and enqueue a background execution for it
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Node).filter(Node.role_name == "Router")
                res = await session.execute(stmt)
                router_node = res.scalars().first()
                
                if router_node:
                    print(f"Router: Triggering deep AI analysis for message.")
                    manager.enqueue_node_task(
                        user_id=user_id,
                        target_node_id=router_node.id,
                        message=message,
                        context={
                            "deep_analysis": True,
                            "session_id": context.get("session_id"),
                            "project_id": context.get("project_id"),
                            # Pass relevant context for the LLM
                            "original_message": message
                        }
                    )
        except Exception as e:
            print(f"⚠️ Router: Deep analysis trigger failed: {e}")

    @classmethod
    async def initialize_default_hooks(cls):
        """Register hooks from database nodes metadata (trigger_patterns)."""
        cls._hooks = [] # Reset to avoid duplicates on re-init
        
        try:
            async with AsyncSessionLocal() as session:
                # Fetch all nodes with metadata and filter in Python to avoid dialect-specific JSON query issues
                stmt = select(Node).filter(Node.meta_payload.is_not(None))
                res = await session.execute(stmt)
                all_nodes = res.scalars().all()
                
                nodes = [n for n in all_nodes if isinstance(n.meta_payload, dict) and "trigger_patterns" in n.meta_payload]
                
                for node in nodes:
                    patterns = node.meta_payload.get("trigger_patterns", [])
                    if isinstance(patterns, list):
                        for pattern in patterns:
                            cls.register_hook(pattern, node.id, f"Dynamic hook for {node.display_name}")
                
                print(f"Router: Initialized {len(cls._hooks)} dynamic hooks from database.")
        except Exception as e:
            print(f"[ERROR] Router: Dynamic hook initialization failed: {e}")
