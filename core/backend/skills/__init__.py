from .registry import skill_registry
from datetime import datetime
import uuid

async def init_skills():
    """Initialize skills from file system and register AES mining tasks."""
    await skill_registry.sync_skills()
    
    # 2. Register Daily Skill Mining in AES for each active user if missing
    from models.database import AsyncSessionLocal, ScheduledTask, User
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        # Fetch all active users
        user_stmt = select(User).filter(User.is_active == True)
        u_res = await db.execute(user_stmt)
        users = u_res.scalars().all()
        
        for user in users:
            # Check if this user already has a daily mining task
            stmt = select(ScheduledTask).filter(
                ScheduledTask.task_type == "SYSTEM_SKILL_MINING",
                ScheduledTask.user_id == user.id
            )
            res = await db.execute(stmt)
            existing = res.scalars().first()
            
            if not existing:
                print(f"[Skills] Registering Daily Skill Mining in AES for user {user.username}...")
                new_task = ScheduledTask(
                    id=f"sys-mining-{user.id[:8]}-{uuid.uuid4().hex[:4]}",
                    user_id=user.id,
                    task_type="SYSTEM_SKILL_MINING",
                    payload={"is_batch": True},
                    scheduled_at=datetime.utcnow(),
                    recurring_rule="0 2 * * *", # Daily at 2:00 AM
                    status="pending"
                )
                db.add(new_task)
        
        await db.commit()
