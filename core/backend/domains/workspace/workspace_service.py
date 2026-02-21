"""
Workspace Service
CRUD, versioning, ACL, and priority resolver for shared workspace items.
Supports three item types: note (text), file (binary/text), directory.
"""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import WorkspaceItem, WorkspaceItemVersion, WorkspaceBinding, WorkspaceACL
from shared.paths import get_workspace_item_path, get_workspace_dir

# 25 MB upload limit for workspace files
MAX_FILE_SIZE = 25 * 1024 * 1024

ALLOWED_MIME_PREFIXES = (
    "text/", "application/pdf", "application/json",
    "application/xml", "application/zip",
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
)


def _validate_path(path: str) -> None:
    """Reject paths with traversal or hidden segments."""
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in ("", ".", "..") or part.startswith("."):
            raise HTTPException(status_code=400, detail=f"Invalid path segment: '{part}'")


def _compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
        _validate_path(path)
        item = WorkspaceItem(
            id=str(uuid4()),
            owner_id=self.user_id,
            item_type="note",
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

    async def create_directory(
        self,
        path: str,
        title: str,
        scope: str = "private",
        tags: Optional[List[str]] = None,
    ) -> WorkspaceItem:
        """Create a directory node in the workspace."""
        _validate_path(path)
        item = WorkspaceItem(
            id=str(uuid4()),
            owner_id=self.user_id,
            item_type="directory",
            scope=scope,
            path=path,
            title=title,
            tags=tags or [],
            version=1,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def upload_file(
        self,
        path: str,
        title: str,
        content_bytes: bytes,
        mime_type: str,
        scope: str = "private",
        tags: Optional[List[str]] = None,
    ) -> WorkspaceItem:
        """Save a file to the workspace and record it in the DB."""
        _validate_path(path)
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB limit")
        if not any(mime_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
            raise HTTPException(status_code=415, detail=f"Unsupported MIME type: {mime_type}")

        # Write to disk
        dest = get_workspace_item_path(self.user_id, path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content_bytes)

        checksum = _compute_checksum(content_bytes)
        item = WorkspaceItem(
            id=str(uuid4()),
            owner_id=self.user_id,
            item_type="file",
            scope=scope,
            path=path,
            title=title,
            storage_path=str(dest),
            mime_type=mime_type,
            size_bytes=len(content_bytes),
            checksum=checksum,
            tags=tags or [],
            version=1,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_file_content(self, item_id: str) -> Tuple[bytes, str]:
        """Return (bytes, mime_type) for a file workspace item."""
        item = await self.get_item(item_id)
        if item.item_type != "file":
            raise HTTPException(status_code=400, detail="Item is not a file")
        dest = Path(item.storage_path) if item.storage_path else get_workspace_item_path(self.user_id, item.path)
        if not dest.exists():
            raise HTTPException(status_code=404, detail="File content not found on disk")
        return dest.read_bytes(), item.mime_type or "application/octet-stream"

    async def replace_file(
        self,
        item_id: str,
        content_bytes: bytes,
        mime_type: str,
    ) -> WorkspaceItem:
        """Replace the content of an existing file workspace item."""
        item = await self.get_item(item_id)
        if item.item_type != "file":
            raise HTTPException(status_code=400, detail="Item is not a file")
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB limit")
        if not any(mime_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
            raise HTTPException(status_code=415, detail=f"Unsupported MIME type: {mime_type}")

        dest = Path(item.storage_path) if item.storage_path else get_workspace_item_path(self.user_id, item.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content_bytes)

        # Snapshot metadata before update
        snapshot = WorkspaceItemVersion(
            id=str(uuid4()),
            item_id=item.id,
            version=item.version,
            content=None,
            created_by=self.user_id,
        )
        self.db.add(snapshot)

        item.mime_type = mime_type
        item.size_bytes = len(content_bytes)
        item.checksum = _compute_checksum(content_bytes)
        item.version = item.version + 1
        item.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def move_item(self, item_id: str, new_path: str, new_title: Optional[str] = None) -> WorkspaceItem:
        """Move/rename a workspace item (updates path and, for files, moves the file on disk)."""
        _validate_path(new_path)
        item = await self.get_item(item_id)

        if item.item_type == "file":
            old_dest = Path(item.storage_path) if item.storage_path else get_workspace_item_path(self.user_id, item.path)
            new_dest = get_workspace_item_path(self.user_id, new_path)
            new_dest.parent.mkdir(parents=True, exist_ok=True)
            if old_dest.exists():
                shutil.move(str(old_dest), str(new_dest))
            item.storage_path = str(new_dest)

        snapshot = WorkspaceItemVersion(
            id=str(uuid4()),
            item_id=item.id,
            version=item.version,
            content=item.content,
            created_by=self.user_id,
        )
        self.db.add(snapshot)

        item.path = new_path
        if new_title is not None:
            item.title = new_title
        item.version = item.version + 1
        item.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_tree(self, path_prefix: Optional[str] = None) -> List[WorkspaceItem]:
        """List all non-deleted items under an optional path prefix."""
        conditions = [
            WorkspaceItem.owner_id == self.user_id,
            WorkspaceItem.is_deleted == False,
        ]
        if path_prefix:
            # Match items whose path starts with the prefix
            from sqlalchemy import String
            conditions.append(WorkspaceItem.path.like(f"{path_prefix}%"))

        result = await self.db.execute(
            select(WorkspaceItem).where(and_(*conditions)).order_by(WorkspaceItem.path)
        )
        return result.scalars().all()

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

        # For directories: recursively soft-delete all children
        if item.item_type == "directory":
            prefix = item.path.rstrip("/") + "/"
            result = await self.db.execute(
                select(WorkspaceItem).where(
                    WorkspaceItem.owner_id == self.user_id,
                    WorkspaceItem.path.like(f"{prefix}%"),
                    WorkspaceItem.is_deleted == False,
                )
            )
            children = result.scalars().all()
            now = datetime.utcnow()
            for child in children:
                child.is_deleted = True
                child.updated_at = now

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
