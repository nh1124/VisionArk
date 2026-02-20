
import redis.asyncio as redis
import json
import uuid
from typing import Optional, Dict, Any
from app.config import settings
from shared.database import TaskType

from datetime import datetime, date

class CustomEncoder(json.JSONEncoder):
    """Robust JSON encoder for internal objects"""
    def default(self, obj):
        if hasattr(obj, "format_for_display") and callable(obj.format_for_display):
            return obj.format_for_display()
        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return obj.to_dict()
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # Pydantic support
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            return obj.model_dump()
        if hasattr(obj, "dict") and callable(obj.dict) and not isinstance(obj, dict):
            return obj.dict()
        return super().default(obj)

class QueueManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QueueManager, cls).__new__(cls)
            cls._instance.client = redis.Redis(
                host=settings.redis_host, 
                port=settings.redis_port,
                decode_responses=True
            )
        return cls._instance

    async def enqueue(self, user_id: str, message: str, context: Optional[Dict] = None, task_type: TaskType = TaskType.USER_MESSAGE) -> str:
        """Add a task to the queue"""
        task_id = str(uuid.uuid4())
        payload = {
            "task_id": task_id,
            "user_id": user_id,
            "message": message,
            "task_type": task_type,
            "context": context or {},
            "status": "queued"
        }
        
        # Add to list
        await self.client.rpush("task_queue", json.dumps(payload, cls=CustomEncoder))
        
        project_id = (context or {}).get("project_id")

        # Set initial status
        await self.client.setex(
            f"task:{task_id}", 
            3600, # 1 hour TTL
            json.dumps({
                "status": "queued", 
                "result": None, 
                "task_type": task_type,
                "project_id": project_id
            }, cls=CustomEncoder)
        )

        # Track active task for project recovery if project_id is present
        if project_id:
            await self.client.setex(f"active_task:{project_id}", 3600, task_id)
        
        return task_id

    async def dequeue(self) -> Dict[str, Any]:
        """Blocking pop from the queue"""
        # BLPOP returns (key, value) tuple
        result = await self.client.blpop("task_queue")
        if result:
            return json.loads(result[1])
        return None

    async def update_status(self, task_id: str, status: str, result: Any = None):
        """Update task status"""
        # Fetch current status to preserve metadata like project_id
        current_data = await self.get_status(task_id)
        project_id = current_data.get("project_id") if current_data else None
        task_type = current_data.get("task_type") if current_data else "user_message"

        payload = {
            "status": status,
            "result": result,
            "task_type": task_type,
            "project_id": project_id
        }

        await self.client.setex(
            f"task:{task_id}",
            3600, 
            json.dumps(payload, cls=CustomEncoder)
        )

        # If terminal state, clear project mapping if it exists
        if status in ["completed", "failed"] and project_id:
            await self.clear_active_task(project_id)

    async def get_status(self, task_id: str) -> Optional[Dict]:
        """Get task status"""
        data = await self.client.get(f"task:{task_id}")
        if data:
            return json.loads(data)
        return None

    async def get_active_task_for_project(self, project_id: str) -> Optional[str]:
        """Retrieve active task ID for a project"""
        return await self.client.get(f"active_task:{project_id}")

    async def clear_active_task(self, project_id: str):
        """Manually clear the active task mapping"""
        await self.client.delete(f"active_task:{project_id}")

    async def cancel_task(self, task_id: str):
        """Set task status to cancelled"""
        current_data = await self.get_status(task_id)
        if not current_data:
            return

        current_data["status"] = "cancelled"
        project_id = current_data.get("project_id")

        await self.client.setex(
            f"task:{task_id}",
            3600,
            json.dumps(current_data)
        )

        # Also clear active task mapping if it belongs to this task
        if project_id:
            active_task_id = await self.get_active_task_for_project(project_id)
            if active_task_id == task_id:
                await self.clear_active_task(project_id)

    async def get_all_active_tasks(self) -> list:
        """Get all active task IDs currently tracked"""
        keys = await self.client.keys("active_task:*")
        tasks = []
        for k in keys:
            tid = await self.client.get(k)
            if tid:
                tasks.append(tid)
        return tasks

    async def set_run_for_task(self, task_id: str, run_id: str) -> None:
        """Store the orchestration run_id associated with a task_id."""
        await self.client.setex(f"run_for_task:{task_id}", 3600, run_id)

    async def get_run_for_task(self, task_id: str) -> Optional[str]:
        """Retrieve the orchestration run_id for a given task_id, if available."""
        return await self.client.get(f"run_for_task:{task_id}")
