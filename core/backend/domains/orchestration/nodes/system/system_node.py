from typing import Dict, Any, Optional, List
from domains.orchestration.nodes.base_node import BaseNode
from sqlalchemy import select
from shared.database import AsyncSessionLocal, Node, Project, TaskStatus

class SystemNode(BaseNode):
    """
    Base class for system-layer nodes.
    Provides privileged access to cross-project data.
    """
    def __init__(self, context: Dict[str, Any], status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        # System nodes are not scoped to a specific project_id in the same way Project nodes are.
        # They can operate across all projects for a given user.
        
    async def get_all_projects(self) -> List[Project]:
        """Fetch all active projects for the current user."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project).filter(
                    Project.user_id == self.user_id,
                    Project.status == "active"
                )
            )
            return result.scalars().all()

    async def get_all_nodes(self, node_id_exclude: Optional[str] = None) -> List[Node]:
        """Fetch all active nodes across all projects for the current user."""
        async with AsyncSessionLocal() as db:
            # We join with Project to ensure we only get nodes belonging to the current user
            result = await db.execute(
                select(Node).join(Project, Node.project_id == Project.id).filter(
                    Project.user_id == self.user_id,
                    Node.status == "active",
                    Node.id != node_id_exclude if node_id_exclude else True
                )
            )
            return result.scalars().all()
