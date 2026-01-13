"""
Refactored file management API
- Unified /api/files router
- Removed redundant /api/spokes router
- Removed obsolete Gemini sync/cleanup logic
"""
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional
import mimetypes
from uuid import uuid4

from services.auth import resolve_identity, Identity, resolve_identity_for_download
from models.database import UploadedFile, Node, get_async_db, UserSettings
from services.file_service import FileService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# --- Main File Router ---
files_router = APIRouter(prefix="/api/files", tags=["Files"])


async def _get_user_api_key(db: AsyncSession, user_id: str) -> Optional[str]:
    """Get user's Gemini API key from settings"""
    result = await db.execute(select(UserSettings).filter(
        UserSettings.user_id == user_id
    ))
    user_settings = result.scalars().first()
    return user_settings.gemini_api_key if user_settings else None


# --- Specific Routes (IDs or fixed paths) First to avoid shadowing ---
@files_router.post("/{node_type}/{node_name}/upload")
async def upload_node_file(
    node_type: str,
    node_name: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Upload a file to Hub or Spoke storage"""
    if node_type.lower() not in ["hub", "spoke"]:
        raise HTTPException(status_code=400, detail="node_type must be 'hub' or 'spoke'")
    
    # Read file content
    content = await file.read()
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(file.filename)
    mime_type = mime_type or file.content_type or "application/octet-stream"
    
    # FileService handles storage and DB recording
    # Gemini upload is now handled explicitly by agents when needed, 
    # not during the initial upload to the library.
    service = FileService(db, identity.user_id)
    
    db_file = await service.save_file(
        content=content,
        filename=file.filename,
        mime_type=mime_type,
        node_type=node_type,
        node_name=node_name
    )
    
    return {
        "id": db_file.id,
        "filename": db_file.filename,
        "size_bytes": db_file.size_bytes,
        "mime_type": db_file.mime_type
    }


@files_router.get("/{node_type}/{node_name}")
async def list_node_files(
    node_type: str,
    node_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all files for a Hub or Spoke"""
    if node_type.lower() not in ["hub", "spoke"]:
        raise HTTPException(status_code=400, detail="node_type must be 'hub' or 'spoke'")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    files = await service.list_files(node_type, node_name)
    return {"files": files, "count": len(files)}


@files_router.get("/{node_type}/{node_name}/{directory}/{file_path:path}")
async def get_node_file(
    node_type: str,
    node_name: str,
    directory: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Serve a file from Hub or Spoke directory (refs, artifacts, or files) by its path.
    Used for image previews and artifact downloads.
    """
    if node_type.lower() not in ["hub", "spoke"]:
        raise HTTPException(status_code=400, detail="node_type must be 'hub' or 'spoke'")
    
    if directory not in ["refs", "artifacts", "files"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', or 'files'")
    
    user_id = identity.user_id
    
    try:
        if node_type.lower() == "hub":
            from utils.paths import get_user_hub_dir
            base_dir = get_user_hub_dir(user_id)
        else:
            from utils.paths import get_spoke_dir
            base_dir = get_spoke_dir(user_id, node_name)
        
        from utils.paths import secure_path_join
        full_path = secure_path_join(base_dir / directory, file_path)
        
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        return FileResponse(
            full_path, 
            media_type=mime_type, 
            filename=full_path.name
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[FileServing] Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@files_router.get("/meta/{file_id}")
async def get_file_info(
    file_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get metadata for a specific file"""
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check ownership via node
    result = await db.execute(select(Node).filter(Node.id == file_record.node_id))
    node = result.scalars().first()
    if not node or node.user_id != identity.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": file_record.id,
        "filename": file_record.filename,
        "mime_type": file_record.mime_type,
        "size_bytes": file_record.size_bytes,
        "uploaded_at": file_record.uploaded_at,
        "has_gemini_ref": file_record.gemini_file_uri is not None
    }


@files_router.get("/download/{file_id}")
async def download_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Download an uploaded file by its ID (used for References)"""
    # Verify ownership
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check ownership via node
    result = await db.execute(select(Node).filter(Node.id == file_record.node_id))
    node = result.scalars().first()
    if not node or node.user_id != identity.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    file_path = Path(file_record.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing")
    
    return FileResponse(
        file_path,
        media_type=file_record.mime_type,
        filename=file_record.filename
    )


@files_router.delete("/{file_id}")
async def delete_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a file by ID (from disk, database, and Gemini if exists)"""
    # Verify ownership
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check ownership via node
    result = await db.execute(select(Node).filter(Node.id == file_record.node_id))
    node = result.scalars().first()
    if not node or node.user_id != identity.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    if await service.delete_file(file_id):
        return {"message": "File deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete file")

