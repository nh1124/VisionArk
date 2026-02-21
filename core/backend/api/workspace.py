"""
Workspace API
REST endpoints for managing shared workspace items, version history, and project bindings.
Supports note, file, and directory item types.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import Response
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
    item_type: str
    scope: str
    path: str
    title: str
    content: Optional[str]
    tags: List[str]
    version: int
    is_deleted: bool
    mime_type: Optional[str]
    size_bytes: Optional[int]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_item(cls, item):
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            item_type=getattr(item, "item_type", "note") or "note",
            scope=item.scope,
            path=item.path,
            title=item.title,
            content=item.content,
            tags=item.tags or [],
            version=item.version,
            is_deleted=item.is_deleted,
            mime_type=getattr(item, "mime_type", None),
            size_bytes=getattr(item, "size_bytes", None),
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


class WorkspaceDirectoryCreate(BaseModel):
    path: str
    title: str
    scope: str = "private"
    tags: List[str] = []


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


# ------------------------------------------------------------------
# Directory endpoints
# ------------------------------------------------------------------

@workspace_router.post("/directories", response_model=WorkspaceItemResponse)
async def create_workspace_directory(
    body: WorkspaceDirectoryCreate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a directory node in the workspace."""
    service = WorkspaceService(db, identity.user_id)
    item = await service.create_directory(
        path=body.path,
        title=body.title,
        scope=body.scope,
        tags=body.tags,
    )
    return WorkspaceItemResponse.from_orm_item(item)


# ------------------------------------------------------------------
# File endpoints
# ------------------------------------------------------------------

@workspace_router.post("/files", response_model=WorkspaceItemResponse)
async def upload_workspace_file(
    path: str = Query(..., description="Logical path, e.g. 'reports/q1.pdf'"),
    title: str = Query(..., description="Human-readable title"),
    scope: str = Query("private"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Upload a file to the workspace (multipart/form-data)."""
    content_bytes = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    service = WorkspaceService(db, identity.user_id)
    item = await service.upload_file(
        path=path,
        title=title,
        content_bytes=content_bytes,
        mime_type=mime_type,
        scope=scope,
        tags=tag_list,
    )
    return WorkspaceItemResponse.from_orm_item(item)


@workspace_router.get("/files/{item_id}/content")
async def download_workspace_file(
    item_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Download the binary content of a workspace file item."""
    service = WorkspaceService(db, identity.user_id)
    content_bytes, mime_type = await service.get_file_content(item_id)
    return Response(content=content_bytes, media_type=mime_type)


@workspace_router.put("/files/{item_id}", response_model=WorkspaceItemResponse)
async def replace_workspace_file(
    item_id: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Replace the content of an existing workspace file."""
    content_bytes = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    service = WorkspaceService(db, identity.user_id)
    item = await service.replace_file(item_id, content_bytes, mime_type)
    return WorkspaceItemResponse.from_orm_item(item)


# ------------------------------------------------------------------
# Tree endpoint
# ------------------------------------------------------------------

@workspace_router.get("/tree", response_model=List[WorkspaceItemResponse])
async def get_workspace_tree(
    path: Optional[str] = Query(None, description="Path prefix to filter (e.g. 'reports/')"),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List all workspace items (notes, files, directories) sorted by path."""
    service = WorkspaceService(db, identity.user_id)
    items = await service.list_tree(path_prefix=path)
    return [WorkspaceItemResponse.from_orm_item(i) for i in items]


# ------------------------------------------------------------------
# Move endpoint
# ------------------------------------------------------------------

@workspace_router.post("/items/{item_id}/move", response_model=WorkspaceItemResponse)
async def move_workspace_item(
    item_id: str,
    new_path: str = Query(..., description="New logical path"),
    new_title: Optional[str] = Query(None, description="New title (optional)"),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Move or rename a workspace item."""
    service = WorkspaceService(db, identity.user_id)
    item = await service.move_item(item_id, new_path, new_title)
    return WorkspaceItemResponse.from_orm_item(item)
