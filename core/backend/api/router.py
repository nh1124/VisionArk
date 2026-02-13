import re
import asyncio
from typing import List, Dict, Callable, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from shared.database import ProjectAgent, AsyncSessionLocal, TaskType

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
    def register_hook(cls, pattern: str, target_agent_id: str, description: str = ""):
        """Register an agent's interest in a specific message pattern."""
        cls._hooks.append({
            "pattern": pattern,
            "regex": re.compile(pattern, re.IGNORECASE),
            "target_agent_id": target_agent_id,
            "description": description
        })
        print(f"Router: Registered hook for pattern '{pattern}' -> Agent {target_agent_id}")

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

        from infrastructure.queue.manager import QueueManager
        manager = QueueManager()

        if matches:
            print(f"Router: Found {len(matches)} fast-hook matches.")
            for match in matches:
                target_id = match["target_agent_id"]
                await manager.enqueue(
                    user_id=user_id,
                    message=message,
                    context={
                        "triggered_by_hook": True,
                        "hook_pattern": match["pattern"],
                        "original_message": message,
                        "session_id": context.get("session_id"),
                        "project_id": context.get("project_id"),
                        "target_agent_id": target_id,
                    },
                    task_type=TaskType.USER_MESSAGE,
                )

    @classmethod
    async def initialize_default_hooks(cls):
        """Register hooks from database agents metadata (trigger_patterns)."""
        cls._hooks = []  # Reset to avoid duplicates on re-init

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ProjectAgent).filter(ProjectAgent.meta_payload.is_not(None))
                res = await session.execute(stmt)
                all_agents = res.scalars().all()

                agents = [a for a in all_agents if isinstance(a.meta_payload, dict) and "trigger_patterns" in a.meta_payload]

                for agent in agents:
                    patterns = agent.meta_payload.get("trigger_patterns", [])
                    if isinstance(patterns, list):
                        for item in patterns:
                            if isinstance(item, dict) and (pattern := item.get("value")):
                                cls.register_hook(pattern, agent.id, item.get("description") or f"Dynamic hook for {agent.display_name}")

                print(f"Router: Initialized {len(cls._hooks)} dynamic hooks from database.")
        except Exception as e:
            print(f"[ERROR] Router: Dynamic hook initialization failed: {e}")
