import uuid
from typing import List, Type, Any
from sqlalchemy import select, delete
from shared.database import AsyncSessionLocal, Node, Project
from domains.orchestration.nodes.base_node import BaseNode

class MemberNodeRegistry:
    """
    Syncs member node class definitions to the database for each project.
    """
    
    @staticmethod
    def discover_member_nodes() -> List[Type[BaseNode]]:
        """Find all member node classes."""
        import nodes.members.researcher as res
        import nodes.members.planner as plan
        import nodes.members.advocate as adv
        import nodes.members.ruler as rule
        
        return [res.ResearcherNode, plan.PlannerNode, adv.AdvocateNode, rule.RulerNode]

    @classmethod
    async def sync_member_nodes_for_project(cls, project_id: str):
        """Ensure all member nodes exist for a specific project."""
        member_nodes = cls.discover_member_nodes()
        
        async with AsyncSessionLocal() as db:
            for NodeClass in member_nodes:
                role_name = getattr(NodeClass, "role_name", None)
                if not role_name: continue
                    
                display_name = getattr(NodeClass, "display_name", role_name.capitalize())
                description = getattr(NodeClass, "description", "")
                tools = getattr(NodeClass, "default_tools", [])
                
                # Check if exists for THIS project
                res = await db.execute(select(Node).filter(
                    Node.role_name == role_name, 
                    Node.node_type == "MEMBER", 
                    Node.project_id == project_id
                ))
                existing = res.scalars().first()
                
                if existing:
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
                    if existing.status != "active":
                        existing.status = "active"
                        changed = True
                    
                    if changed:
                        print(f"[MemberNodeRegistry] Updating {role_name} for project {project_id}...")
                else:
                    print(f"[MemberNodeRegistry] Creating {role_name} for project {project_id}...")
                    new_node = Node(
                        id=str(uuid.uuid4()),
                        node_type="MEMBER",
                        role_name=role_name,
                        display_name=display_name,
                        description=description,
                        tools=tools,
                        status="active",
                        project_id=project_id
                    )
                    db.add(new_node)
            
            await db.commit()

    @classmethod
    async def sync_member_nodes_for_all_projects(cls):
        """Iterate over all active projects and sync member nodes."""
        print("[MemberNodeRegistry] Syncing all projects...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Project).filter(Project.status == "active"))
            projects = result.scalars().all()
            
        for proj in projects:
            await cls.sync_member_nodes_for_project(proj.id)
            
        # Cleanup: Remove nodes with project_id=None (legacy templates)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Node).filter(Node.node_type == "MEMBER", Node.project_id == None))
            await db.commit()
            
        print("[MemberNodeRegistry] Global sync complete.")

async def sync_member_nodes():
    """convenience wrapper for lifespan."""
    try:
        from domains.orchestration.member_node_registry import MemberNodeRegistry
        await MemberNodeRegistry.sync_member_nodes_for_all_projects()
    except Exception as e:
        print(f"[MemberNodeRegistry] Error during sync: {e}")

async def sync_member_nodes_for_project(project_id: str):
    """convenience wrapper for new project creation."""
    try:
        from domains.orchestration.member_node_registry import MemberNodeRegistry
        await MemberNodeRegistry.sync_member_nodes_for_project(project_id)
    except Exception as e:
        print(f"[MemberNodeRegistry] Error during project sync ({project_id}): {e}")
