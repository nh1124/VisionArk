import sys
import os
from pathlib import Path
import asyncio
from sqlalchemy import select

# Add backend to sys.path
backend_path = Path("c:/Users/nh112/programming/project/VisionArk/core/backend")
sys.path.append(str(backend_path))

from nodes.system.router_node import RouterNode
from models.database import Node, AsyncSessionLocal

async def test_archive_context():
    user_id = "test_user_archive"
    project_name = "archive_test_project"
    
    async with AsyncSessionLocal() as db:
        # 1. Setup: Ensure user and project exist
        from models.database import User
        import uuid
        
        # Check if user exists
        res = await db.execute(select(User).filter(User.username == "test_archive_user"))
        user = res.scalars().first()
        if not user:
            user = User(id=str(uuid.uuid4()), username="test_archive_user", password_hash="dummy")
            db.add(user)
        
        user_id = user.id
        
        # Check if project exists
        res = await db.execute(select(Node).filter(Node.user_id == user_id, Node.name == project_name))
        node = res.scalars().first()
        if not node:
            node = Node(id=str(uuid.uuid4()), user_id=user_id, name=project_name)
            db.add(node)
        
        await db.commit()

        # 2. Test RouterNode
        context = {
            "user_id": user_id,
            "task_id": "test_task_archive",
            "project_name": project_name
        }
        
        router = RouterNode(context)
        
        print(f"Testing /archive command in context: {context['project_name']}")
        result = await router.process("/archive")
        print(f"Result: {result}")
        
        if f"Archived current session for {project_name}" in result:
            print(f"✅ Success: Context correctly identified as {project_name}")
        else:
            print("❌ Failure: Context was not correctly identified")

if __name__ == "__main__":
    asyncio.run(test_archive_context())
