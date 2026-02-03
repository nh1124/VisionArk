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
        import nodes.system.project_manager_node as pmn
        import nodes.system.task_manager_node as tmn
        return [gs.GlobalScheduler, pmn.ProjectManagerNode, tmn.TaskManagerNode]

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
                meta_payload = {"trigger_patterns": getattr(NodeClass, "trigger_patterns", [])}
                
                # Check if exists
                res = await db.execute(select(Node).filter(Node.role_name == role_name))
                existing = res.scalars().first()
                
                if existing:
                    # Check if anything changed to avoid redundant updates
                    changed = False
                    if existing.display_name != display_name:
                        existing.display_name = display_name
                        changed = True
                    if existing.description != description:
                        existing.description = description
                        changed = True
                    if existing.tools != tools:
                        existing.tools = tools
                        changed = True
                    if existing.meta_payload != meta_payload:
                        existing.meta_payload = meta_payload
                        changed = True
                    if existing.status != "active":
                        existing.status = "active"
                        changed = True
                    
                    if changed:
                        print(f"[SystemNodeRegistry] Updating {role_name}...")
                    else:
                        # No changes, skip update
                        pass
                else:
                    print(f"[SystemNodeRegistry] Creating {role_name}...")
                    new_node = Node(
                        id=str(uuid.uuid4()),
                        node_type="SYSTEM",
                        role_name=role_name,
                        display_name=display_name,
                        description=description,
                        tools=tools,
                        meta_payload=meta_payload,
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
