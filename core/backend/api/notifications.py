from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
import json
import asyncio
import redis.asyncio as redis

from models.database import get_async_db, NotificationType
from services.notification_service import NotificationService
from api.auth import get_current_user
from config import settings

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("/")
async def list_notifications(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    service = NotificationService(db)
    notifications = await service.list_notifications(current_user.id, limit=limit, offset=offset)
    unread_count = await service.get_unread_count(current_user.id)
    return {
        "notifications": notifications,
        "unread_count": unread_count
    }

@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    service = NotificationService(db)
    success = await service.mark_as_read(notification_id, current_user.id)
    return {"success": success}

@router.post("/read-all")
async def mark_all_as_read(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    service = NotificationService(db)
    success = await service.mark_all_as_read(current_user.id)
    return {"success": success}

# WebSocket Manager for real-time delivery
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"WebSocket: User {user_id} connected.")

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        print(f"WebSocket: User {user_id} disconnected.")

manager = ConnectionManager()

@router.websocket("/ws/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    
    # Redis for Pub/Sub
    redis_client = redis.Redis(
        host=settings.redis_host, 
        port=settings.redis_port, 
        decode_responses=True
    )
    pubsub = redis_client.pubsub()
    channel = f"notifications:{user_id}"
    
    listener_task = None
    try:
        await pubsub.subscribe(channel)
        print(f"WebSocket: Subscribed to {channel}")
        
        async def redis_listener():
            try:
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        await websocket.send_text(message['data'])
            except Exception as e:
                print(f"WebSocket Redis Listener Error: {e}")

        # Run listener in background
        listener_task = asyncio.create_task(redis_listener())
        
        while True:
            # Keep connection alive
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception as e:
        print(f"WebSocket Error: {e}")
        manager.disconnect(user_id, websocket)
    finally:
        if listener_task:
            listener_task.cancel()
        await pubsub.unsubscribe(channel)
        await redis_client.close()
