
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
        
        # Set initial status
        self.client.setex(
            f"task:{task_id}", 
            3600, # 1 hour TTL
            json.dumps({"status": "queued", "result": None, "task_type": task_type})
        )
        
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
        self.client.setex(
            f"task:{task_id}",
            3600, 
            json.dumps({"status": status, "result": result})
        )

    def get_status(self, task_id: str) -> Optional[Dict]:
        """Get task status"""
        data = self.client.get(f"task:{task_id}")
        if data:
            return json.loads(data)
        return None
