import asyncio
from models.database import AsyncSessionLocal, Notification
from sqlalchemy import select

async def check_last_notification():
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Notification).order_by(Notification.created_at.desc()).limit(1)
        )
        n = res.scalars().first()
        if n:
            print(f"Last Notification:")
            print(f"  ID: {n.id}")
            print(f"  Title: {n.title}")
            print(f"  Content: {n.content}")
            print(f"  Type: {n.type}")
            print(f"  Created At: {n.created_at} UTC")
        else:
            print("No notifications found.")

if __name__ == "__main__":
    asyncio.run(check_last_notification())
