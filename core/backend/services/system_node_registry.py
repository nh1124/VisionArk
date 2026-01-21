import asyncio
import uuid
import inspect
from typing import List, Type
from sqlalchemy import select
from models.database import AsyncSessionLocal, Node
from nodes.system.generic_system_node import GenericSystemNode

class SystemNodeRegistry:
    """
    Syncs system node class definitions to the database.
    """
    
    @staticmethod
    def discover_system_nodes() -> List[Type[GenericSystemNode]]:
        """Find all subclasses of GenericSystemNode in the nodes.system package."""
        import nodes.system.global_scheduler as gs
        # In a real dynamic discovery, we would crawl the directory.
        # For now, we explicitly include the known ones.
        return [gs.GlobalScheduler]

    @classmethod
    def get_node_class(cls, role_name: str) -> Type[GenericSystemNode]:
        """Returns the specialized class for a role, or GenericSystemNode as fallback."""
        nodes = cls.discover_system_nodes()
        for NodeClass in nodes:
            if NodeClass.role_name == role_name:
                return NodeClass
        return GenericSystemNode

    @classmethod
    async def sync_to_db(cls):
        """Sync discovered system nodes to the database."""
        print("[SystemNodeRegistry] Starting sync...")
        system_nodes = cls.discover_system_nodes()
        
        async with AsyncSessionLocal() as db:
            for NodeClass in system_nodes:
                # Use metadata from class attributes
                role_name = NodeClass.role_name
                display_name = NodeClass.display_name
                description = NodeClass.description
                tools = NodeClass.default_tools
                
                # Check if exists
                res = await db.execute(select(Node).filter(Node.role_name == role_name))
                existing = res.scalars().first()
                
                if existing:
                    print(f"[SystemNodeRegistry] Updating {role_name}...")
                    existing.display_name = display_name
                    existing.description = description
                    existing.tools = tools
                    existing.status = "active"
                else:
                    print(f"[SystemNodeRegistry] Creating {role_name}...")
                    new_node = Node(
                        id=str(uuid.uuid4()),
                        node_type="SYSTEM",
                        role_name=role_name,
                        display_name=display_name,
                        description=description,
                        tools=tools,
                        status="active"
                    )
                    db.add(new_node)
            
            await db.commit()
            print("[SystemNodeRegistry] Sync complete.")

async def sync_system_nodes():
    """convenience wrapper for lifespan."""
    try:
        await SystemNodeRegistry.sync_to_db()
    except Exception as e:
        print(f"[SystemNodeRegistry] Error during sync: {e}")
