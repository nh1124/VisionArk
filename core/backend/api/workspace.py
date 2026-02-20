"""
Workspace API
REST endpoints for managing shared workspace items, version history, and project bindings.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from domains.identity.auth import resolve_identity, Identity
from domains.workspace.workspace_service import WorkspaceService
from shared.database import get_async_db

workspace_router = APIRouter(prefix="/api/workspace", tags=["Workspace"])


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class WorkspaceItemCreate(BaseModel):
    path: str
    title: str
    content: Optional[str] = None
    scope: str = "private"
    tags: List[str] = []


class WorkspaceItemUpdate(BaseModel):
    path: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    scope: Optional[str] = None
    tags: Optional[List[str]] = None


class WorkspaceItemResponse(BaseModel):
    id: str
    owner_id: str
    scope: str
    path: str
    title: str
    content: Optional[str]
    tags: List[str]
    version: int
    is_deleted: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_item(cls, item):
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            scope=item.scope,
            path=item.path,
            title=item.title,
            content=item.content,
            tags=item.tags or [],
            version=item.version,
            is_deleted=item.is_deleted,
            created_at=item.created_at.isoformat() if item.created_at else "",
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
        )


class WorkspaceItemVersionResponse(BaseModel):
    id: str
    item_id: str
    version: int
    content: Optional[str]
    created_by: str
    created_at: str

    @classmethod
    def from_orm_version(cls, v):
        return cls(
            id=v.id,
            item_id=v.item_id,
            version=v.version,
            content=v.content,
            created_by=v.created_by,
            created_at=v.created_at.isoformat() if v.created_at else "",
        )


class WorkspaceBindingCreate(BaseModel):
    item_id: str


class WorkspaceBindingResponse(BaseModel):
    id: str
    item_id: str
    project_id: str
    created_by: str
    created_at: str

    @classmethod
    def from_orm_binding(cls, b):
        return cls(
            id=b.id,
            item_id=b.item_id,
            project_id=b.project_id,
            created_by=b.created_by,
            created_at=b.created_at.isoformat() if b.created_at else "",
        )


# ------------------------------------------------------------------
# Items endpoints
# ------------------------------------------------------------------

@workspace_router.post("/items", response_model=WorkspaceItemResponse)
async def create_workspace_item(
    body: WorkspaceItemCreate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a new workspace item."""
    service = WorkspaceService(db, identity.user_id)
    item = await service.create_item(
        path=body.path,
        title=body.title,
        content=body.content,
        scope=body.scope,
        tags=body.tags,
    )
    return WorkspaceItemResponse.from_orm_item(item)


@workspace_router.get("/items", response_model=List[WorkspaceItemResponse])
async def list_workspace_items(
    scope: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tag list"),
    search: Optional[str] = Query(None),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List workspace items owned by the authenticated user."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    service = WorkspaceService(db, identity.user_id)
    items = await service.list_items(scope=scope, tags=tag_list, search=search)
    return [WorkspaceItemResponse.from_orm_item(i) for i in items]


@workspace_router.get("/items/{item_id}", response_model=WorkspaceItemResponse)
async def get_workspace_item(
    item_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Get a single workspace item by ID."""
    service = WorkspaceService(db, identity.user_id)
    item = await service.get_item(item_id)
    return WorkspaceItemResponse.from_orm_item(item)


@workspace_router.patch("/items/{item_id}", response_model=WorkspaceItemResponse)
async def update_workspace_item(
    item_id: str,
    body: WorkspaceItemUpdate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Update a workspace item (creates a version snapshot first)."""
    service = WorkspaceService(db, identity.user_id)
    item = await service.update_item(item_id, **body.model_dump(exclude_none=True))
    return WorkspaceItemResponse.from_orm_item(item)


@workspace_router.delete("/items/{item_id}")
async def delete_workspace_item(
    item_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Soft-delete a workspace item."""
    service = WorkspaceService(db, identity.user_id)
    await service.delete_item(item_id)
    return {"success": True}


@workspace_router.get("/items/{item_id}/versions", response_model=List[WorkspaceItemVersionResponse])
async def list_item_versions(
    item_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List version history for a workspace item."""
    service = WorkspaceService(db, identity.user_id)
    versions = await service.list_versions(item_id)
    return [WorkspaceItemVersionResponse.from_orm_version(v) for v in versions]


# ------------------------------------------------------------------
# Bindings endpoints
# ------------------------------------------------------------------

@workspace_router.post("/projects/{project_id}/bindings", response_model=WorkspaceBindingResponse)
async def bind_item_to_project(
    project_id: str,
    body: WorkspaceBindingCreate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Bind a workspace item to a project."""
    service = WorkspaceService(db, identity.user_id)
    binding = await service.bind_to_project(body.item_id, project_id)
    return WorkspaceBindingResponse.from_orm_binding(binding)


@workspace_router.get("/projects/{project_id}/bindings", response_model=List[WorkspaceItemResponse])
async def list_project_bindings(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List all workspace items bound to a project."""
    service = WorkspaceService(db, identity.user_id)
    items = await service.get_bound_items(project_id)
    return [WorkspaceItemResponse.from_orm_item(i) for i in items]


@workspace_router.delete("/projects/{project_id}/bindings/{item_id}")
async def unbind_item_from_project(
    project_id: str,
    item_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove a workspace item binding from a project."""
    service = WorkspaceService(db, identity.user_id)
    await service.unbind_from_project(item_id, project_id)
    return {"success": True}


@workspace_router.get("/projects/{project_id}/resolve", response_model=List[WorkspaceItemResponse])
async def resolve_project_context(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Return priority-ordered workspace items for a project context."""
    service = WorkspaceService(db, identity.user_id)
    items = await service.resolve_context(project_id)
    return [WorkspaceItemResponse.from_orm_item(i) for i in items]
