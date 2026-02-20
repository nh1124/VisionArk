"""
Workspace Service
CRUD, versioning, ACL, and priority resolver for shared workspace items.
"""
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import WorkspaceItem, WorkspaceItemVersion, WorkspaceBinding, WorkspaceACL


class WorkspaceService:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Item CRUD
    # ------------------------------------------------------------------

    async def create_item(
        self,
        path: str,
        title: str,
        content: Optional[str] = None,
        scope: str = "private",
        tags: Optional[List[str]] = None,
    ) -> WorkspaceItem:
        item = WorkspaceItem(
            id=str(uuid4()),
            owner_id=self.user_id,
            scope=scope,
            path=path,
            title=title,
            content=content,
            tags=tags or [],
            version=1,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_item(self, item_id: str) -> WorkspaceItem:
        result = await self.db.execute(
            select(WorkspaceItem).where(
                WorkspaceItem.id == item_id,
                WorkspaceItem.owner_id == self.user_id,
                WorkspaceItem.is_deleted == False,
            )
        )
        item = result.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Workspace item not found")
        return item

    async def list_items(
        self,
        scope: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
    ) -> List[WorkspaceItem]:
        conditions = [
            WorkspaceItem.owner_id == self.user_id,
            WorkspaceItem.is_deleted == False,
        ]
        if scope:
            conditions.append(WorkspaceItem.scope == scope)

        result = await self.db.execute(
            select(WorkspaceItem).where(and_(*conditions)).order_by(WorkspaceItem.updated_at.desc())
        )
        items = result.scalars().all()

        if tags:
            tag_set = set(tags)
            items = [i for i in items if tag_set.intersection(set(i.tags or []))]

        if search:
            q = search.lower()
            items = [
                i for i in items
                if q in (i.title or "").lower()
                or q in (i.content or "").lower()
                or q in (i.path or "").lower()
            ]

        return items

    async def update_item(self, item_id: str, **fields) -> WorkspaceItem:
        item = await self.get_item(item_id)

        # Snapshot current version before updating
        snapshot = WorkspaceItemVersion(
            id=str(uuid4()),
            item_id=item.id,
            version=item.version,
            content=item.content,
            created_by=self.user_id,
        )
        self.db.add(snapshot)

        # Apply updates
        allowed = {"path", "title", "content", "scope", "tags"}
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(item, key, value)

        item.version = item.version + 1
        item.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_item(self, item_id: str) -> bool:
        item = await self.get_item(item_id)
        item.is_deleted = True
        item.updated_at = datetime.utcnow()
        await self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    async def list_versions(self, item_id: str) -> List[WorkspaceItemVersion]:
        # Ensure item is accessible
        await self.get_item(item_id)
        result = await self.db.execute(
            select(WorkspaceItemVersion)
            .where(WorkspaceItemVersion.item_id == item_id)
            .order_by(WorkspaceItemVersion.version.desc())
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    async def bind_to_project(self, item_id: str, project_id: str) -> WorkspaceBinding:
        # Ensure item is owned by caller
        await self.get_item(item_id)

        # Check if binding already exists
        existing = await self.db.execute(
            select(WorkspaceBinding).where(
                WorkspaceBinding.item_id == item_id,
                WorkspaceBinding.project_id == project_id,
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=409, detail="Binding already exists")

        binding = WorkspaceBinding(
            id=str(uuid4()),
            item_id=item_id,
            project_id=project_id,
            created_by=self.user_id,
        )
        self.db.add(binding)
        await self.db.commit()
        await self.db.refresh(binding)
        return binding

    async def unbind_from_project(self, item_id: str, project_id: str) -> bool:
        result = await self.db.execute(
            select(WorkspaceBinding).where(
                WorkspaceBinding.item_id == item_id,
                WorkspaceBinding.project_id == project_id,
            )
        )
        binding = result.scalars().first()
        if not binding:
            raise HTTPException(status_code=404, detail="Binding not found")
        await self.db.delete(binding)
        await self.db.commit()
        return True

    async def get_bound_items(self, project_id: str) -> List[WorkspaceItem]:
        result = await self.db.execute(
            select(WorkspaceItem)
            .join(WorkspaceBinding, WorkspaceBinding.item_id == WorkspaceItem.id)
            .where(
                WorkspaceBinding.project_id == project_id,
                WorkspaceItem.owner_id == self.user_id,
                WorkspaceItem.is_deleted == False,
            )
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Resolver (§2.4 priority order)
    # ------------------------------------------------------------------

    async def resolve_context(self, project_id: Optional[str]) -> List[WorkspaceItem]:
        """Return priority-ordered, deduplicated workspace items for a project.

        Priority:
        1. Items explicitly bound to project (WorkspaceBinding)
        2. scope='project' items owned by user
        3. scope='org' items owned by user
        4. scope='private' items owned by user
        """
        seen: set = set()
        result: List[WorkspaceItem] = []

        async def _add(items):
            for item in items:
                if item.id not in seen:
                    seen.add(item.id)
                    result.append(item)

        # 1. Bound items
        if project_id:
            bound = await self.get_bound_items(project_id)
            await _add(bound)

        # 2-4. Scoped items in priority order
        for scope in ("project", "org", "private"):
            scoped = await self.db.execute(
                select(WorkspaceItem).where(
                    WorkspaceItem.owner_id == self.user_id,
                    WorkspaceItem.scope == scope,
                    WorkspaceItem.is_deleted == False,
                ).order_by(WorkspaceItem.updated_at.desc())
            )
            await _add(scoped.scalars().all())

        return result
