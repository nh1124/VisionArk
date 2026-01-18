import sys
import os
from pathlib import Path
import asyncio

# Add backend to sys.path
backend_path = Path("c:/Users/nh112/programming/project/VisionArk/core/backend")
sys.path.append(str(backend_path))

from nodes.system.router_node import RouterNode
from models.database import AsyncSessionLocal

async def test_command_renewal():
    # Mock context
    context = {
        "user_id": "test_user_renew",
        "task_id": "test_task_renew",
        "project_name": "hub"
    }
    
    router = RouterNode(context)
    
    print("--- Testing Command Renewal ---")
    
    # 1. Test /move (Validates MovePageTool)
    print("\n1. Testing /move hub")
    res1 = await router.process("/move hub")
    print(f"Result: {res1}")
    
    # 2. Test /archive (Validates ArchiveChatTool)
    print("\n2. Testing /archive")
    # This might fail in a script due to missing real project setup but let's see the error message
    res2 = await router.process("/archive")
    print(f"Result: {res2}")
    
    # 3. Test positional args (Validates Pydantic mapping)
    print("\n3. Testing /create_project test_name")
    res3 = await router.process("/create_project test_name prompt=\"Test Prompt\"")
    print(f"Result: {res3}")

if __name__ == "__main__":
    asyncio.run(test_command_renewal())
