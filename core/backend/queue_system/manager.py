
import redis
import json
import uuid
from typing import Optional, Dict, Any
from config import settings

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

    def enqueue(self, user_id: str, message: str, context: Optional[Dict] = None, task_type: str = "user_message") -> str:
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
        self.client.rpush("task_queue", json.dumps(payload))
        
        project_id = (context or {}).get("project_id")

        # Set initial status
        self.client.setex(
            f"task:{task_id}", 
            3600, # 1 hour TTL
            json.dumps({
                "status": "queued", 
                "result": None, 
                "task_type": task_type,
                "project_id": project_id
            })
        )

        # Track active task for project recovery if project_id is present
        if project_id:
            self.client.setex(f"active_task:{project_id}", 3600, task_id)
        
        return task_id

    def enqueue_node_task(self, user_id: str, target_node_id: str, message: str, context: Optional[Dict] = None) -> str:
        """New specialized method for async node-to-node communication"""
        ctx = context or {}
        ctx["target_node_id"] = target_node_id
        return self.enqueue(user_id, message, ctx, task_type="node_execution")

    def dequeue(self) -> Dict[str, Any]:
        """Blocking pop from the queue"""
        # BLPOP returns (key, value) tuple
        result = self.client.blpop("task_queue")
        if result:
            return json.loads(result[1])
        return None

    def update_status(self, task_id: str, status: str, result: Any = None):
        """Update task status"""
        # Fetch current status to preserve metadata like project_id
        current_data = self.get_status(task_id)
        project_id = current_data.get("project_id") if current_data else None
        task_type = current_data.get("task_type") if current_data else "user_message"

        payload = {
            "status": status,
            "result": result,
            "task_type": task_type,
            "project_id": project_id
        }

        self.client.setex(
            f"task:{task_id}",
            3600, 
            json.dumps(payload)
        )

        # If terminal state, clear project mapping if it exists
        if status in ["completed", "failed"] and project_id:
            self.clear_active_task(project_id)

    def get_status(self, task_id: str) -> Optional[Dict]:
        """Get task status"""
        data = self.client.get(f"task:{task_id}")
        if data:
            return json.loads(data)
        return None

    def get_active_task_for_project(self, project_id: str) -> Optional[str]:
        """Retrieve active task ID for a project"""
        return self.client.get(f"active_task:{project_id}")

    def clear_active_task(self, project_id: str):
        """Manually clear the active task mapping"""
        self.client.delete(f"active_task:{project_id}")
