from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import ServiceRegistry
from queue_system.manager import QueueManager
from va_sdk.registry import sync_registry

class SyncCoordinator:
    """
    Coordinates synchronization between LBS and external calendars.
    Triggered by LBS operations (create/update/delete/complete).
    """
    
    @staticmethod
    async def trigger_export(db_session: AsyncSession, user_id: str, reason: str = "LBS change"):
        """
        Identify active calendar services for the user and enqueue export tasks.
        """
        # Find active calendar integrations
        active_sync_services = list(sync_registry.get_all().keys())
        if not active_sync_services:
            return

        stmt = select(ServiceRegistry).filter(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name.in_(active_sync_services),
            ServiceRegistry.is_active == True
        )
        result = await db_session.execute(stmt)
        services = result.scalars().all()
        
        if not services:
            return
            
        queue = QueueManager()
        for service in services:
            task_type = f"export_to_{service.service_name}"
            queue.enqueue(
                user_id=user_id,
                message=f"Export triggered by {reason}",
                context={"service_name": service.service_name, "triggered_by": "sync_coordinator"},
                task_type=task_type
            )
            print(f"[SyncCoordinator] Enqueued {task_type} for user {user_id}")

    @staticmethod
    async def trigger_import(db_session: AsyncSession, user_id: str, reason: str = "Manual sync"):
        """
        Identify active calendar services for the user and enqueue import (sync) tasks.
        """
        active_sync_services = list(sync_registry.get_all().keys())
        if not active_sync_services:
            return

        stmt = select(ServiceRegistry).filter(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name.in_(active_sync_services),
            ServiceRegistry.is_active == True
        )
        result = await db_session.execute(stmt)
        services = result.scalars().all()
        
        queue = QueueManager()
        for service in services:
            task_type = f"sync_{service.service_name}"
            queue.enqueue(
                user_id=user_id,
                message=f"Sync triggered by {reason}",
                context={"service_name": service.service_name},
                task_type=task_type
            )
