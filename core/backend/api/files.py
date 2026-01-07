"""
File upload and management endpoints for Spokes
"""
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List, Optional
import shutil
import mimetypes
from uuid import uuid4

from utils.paths import get_spoke_dir, get_user_spokes_dir
from services.auth import resolve_identity, Identity, resolve_identity_for_download
from models.database import UploadedFile, Node, get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles

router = APIRouter(prefix="/api/spokes", tags=["Spokes"])

# File size limit: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes

# MIME types that should be uploaded to Gemini for multimodal processing
GEMINI_SUPPORTED_TYPES = [
    "application/pdf",
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "video/mp4", "video/webm",
    "audio/mp3", "audio/wav", "audio/ogg"
]


@router.post("/{spoke_name}/upload")
async def upload_file(
    spoke_name: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    upload_to_gemini: bool = Query(False, description="Upload to Gemini File API for multimodal processing"),
    db: AsyncSession = Depends(get_async_db)
):
    """Upload a file to a spoke's refs directory (max 100MB)"""
    user_id = identity.user_id
    
    # Get user's spoke directory
    spoke_dir = get_spoke_dir(user_id, spoke_name)
    
    if not spoke_dir.exists():
        # Create it if missing (RDB-first, but we still need local storage)
        spoke_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure refs directory exists
    refs_dir = spoke_dir / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the file
    file_path = refs_dir / file.filename
    
    try:
        # Read and write file in chunks to handle large files
        total_size = 0
        async with aiofiles.open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):  # 8KB chunks
                total_size += len(chunk)
                
                # Check file size limit
                if total_size > MAX_FILE_SIZE:
                    # Clean up partial file
                    await buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is 100MB, got {total_size / 1024 / 1024:.1f}MB"
                    )
                
                await buffer.write(chunk)
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"
        
        # Get or create database session
        try:
            # Find the spoke node
            result = await db.execute(select(Node).filter(
                Node.user_id == user_id,
                Node.name == spoke_name,
                Node.node_type == "SPOKE"
            ))
            node = result.scalars().first()
            
            gemini_file_uri = None
            gemini_file_name = None
            
            # Upload to Gemini if requested and supported
            if upload_to_gemini or mime_type in GEMINI_SUPPORTED_TYPES:
                try:
                    from llm import get_provider
                    from utils.encryption import decrypt_string
                    from models.database import UserSettings
                    
                    # Get user's Gemini API key
                    res = await db.execute(select(UserSettings).filter(
                        UserSettings.user_id == user_id
                    ))
                    settings = res.scalars().first()
                    
                    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
                        api_key = decrypt_string(settings.ai_config["gemini_api_key"])
                        provider = get_provider(api_key=api_key)
                        
                        if hasattr(provider, 'upload_file'):
                            # upload_file is likely sync in current implementation, wrap it?
                            # Actually, FileService is better. Let's use FileService later.
                            # For now, keeping the manual logic but making DB part async.
                            # Wait, provider.upload_file should be async if possible.
                            if asyncio.iscoroutinefunction(provider.upload_file):
                                result = await provider.upload_file(
                                    str(file_path),
                                    mime_type=mime_type,
                                    display_name=file.filename
                                )
                            else:
                                result = await asyncio.to_thread(provider.upload_file,
                                    str(file_path),
                                    mime_type=mime_type,
                                    display_name=file.filename
                                )
                            gemini_file_uri = result["file_uri"]
                            gemini_file_name = result["file_name"]
                except Exception as gemini_err:
                    print(f"[FileUpload] Warning: Failed to upload to Gemini: {gemini_err}")
            
            # Record in database if node exists
            if node:
                db_file = UploadedFile(
                    id=str(uuid4()),
                    node_id=node.id,
                    filename=file.filename,
                    storage_path=str(file_path),
                    mime_type=mime_type,
                    size_bytes=file_path.stat().st_size,
                    gemini_file_uri=gemini_file_uri,
                    gemini_file_name=gemini_file_name
                )
                db.add(db_file)
                await db.commit()
                
                return {
                    "message": f"File '{file.filename}' uploaded successfully",
                    "filename": file.filename,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "file_id": db_file.id,
                    "gemini_uploaded": gemini_file_uri is not None,
                    "gemini_file_uri": gemini_file_uri
                }
            else:
                # Still save to disk but log warning
                print(f"[FileUpload] Warning: Node not found for spoke '{spoke_name}', file not recorded in DB")
                return {
                    "message": f"File '{file.filename}' uploaded successfully",
                    "filename": file.filename,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "warning": "File not recorded in database - spoke node not found"
                }
        except Exception as e:
            await db.rollback()
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        # Clean up partial file on error
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.get("/{spoke_name}/files")
async def list_files(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity)
):
    """List all files in a spoke's refs and artifacts directories"""
    user_id = identity.user_id
    spoke_dir = get_spoke_dir(user_id, spoke_name)
    
    if not spoke_dir.exists():
        # Create directories if missing
        spoke_dir.mkdir(parents=True, exist_ok=True)
        (spoke_dir / "refs").mkdir(exist_ok=True)
        (spoke_dir / "artifacts").mkdir(exist_ok=True)
    
    refs_dir = spoke_dir / "refs"
    artifacts_dir = spoke_dir / "artifacts"
    
    files = {
        "refs": [],
        "artifacts": []
    }
    
    # List refs
    if refs_dir.exists():
        for file_path in refs_dir.glob("*"):
            if file_path.is_file():
                files["refs"].append({
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                })
    
    # List artifacts
    if artifacts_dir.exists():
        for file_path in artifacts_dir.glob("*"):
            if file_path.is_file():
                files["artifacts"].append({
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                })
    
    return files


@router.get("/{spoke_name}/files/{directory}/{filename}")
async def download_file(
    spoke_name: str,
    directory: str,
    filename: str,
    identity: Identity = Depends(resolve_identity)
):
    """Download a file from spoke's refs or artifacts directory"""
    user_id = identity.user_id
    spoke_dir = get_spoke_dir(user_id, spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    if directory not in ["refs", "artifacts"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs' or 'artifacts'")
    
    file_path = spoke_dir / directory / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path, filename=filename)


@router.delete("/{spoke_name}/files/{directory}/{filename}")
async def delete_file(
    spoke_name: str,
    directory: str,
    filename: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a file from spoke's refs or artifacts directory"""
    user_id = identity.user_id
    spoke_dir = get_spoke_dir(user_id, spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    if directory not in ["refs", "artifacts"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs' or 'artifacts'")
    
    file_path = spoke_dir / directory / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Also remove from database
        result = await db.execute(select(UploadedFile).filter(
            UploadedFile.storage_path == str(file_path)
        ))
        db_file = result.scalars().first()
        if db_file:
            await db.delete(db_file)
            await db.commit()
        
        file_path.unlink()
        return {"message": f"File '{filename}' deleted successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


# ============================================================================
# NEW: Generic File Management Endpoints (Hub + Spoke)
# ============================================================================

from services.file_service import FileService
from utils.encryption import decrypt_string
from models.database import UserSettings


async def _get_user_api_key(db: AsyncSession, user_id: str) -> Optional[str]:
    """Get user's Gemini API key from settings"""
    result = await db.execute(select(UserSettings).filter(
        UserSettings.user_id == user_id
    ))
    settings = result.scalars().first()
    
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        return decrypt_string(settings.ai_config["gemini_api_key"])
    return None


# Create a separate router for generic file management
files_router = APIRouter(prefix="/api/files", tags=["Files"])


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
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    try:
        uploaded_file = await service.save_file(
            content=content,
            filename=file.filename,
            mime_type=mime_type,
            node_type=node_type,
            node_name=node_name
        )
        
        return {
            "id": uploaded_file.id,
            "filename": uploaded_file.filename,
            "size_bytes": uploaded_file.size_bytes,
            "mime_type": uploaded_file.mime_type,
            "message": f"File '{file.filename}' uploaded successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@files_router.post("/{node_type}/{node_name}/sync-gemini")
async def sync_gemini_files(
    node_type: str,
    node_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Sync all files for a node to Gemini File API.
    Call this when opening the chat page.
    """
    if node_type.lower() not in ["hub", "spoke"]:
        raise HTTPException(status_code=400, detail="node_type must be 'hub' or 'spoke'")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    if not api_key:
        raise HTTPException(status_code=400, detail="Gemini API key not configured")
    
    service = FileService(db, identity.user_id, api_key)
    
    results = await service.sync_files_for_session(node_type, node_name)
    
    synced = sum(1 for r in results if r.get("gemini_available"))
    failed = sum(1 for r in results if r.get("error"))
    
    return {
        "synced_count": synced,
        "failed_count": failed,
        "files": results
    }


@files_router.post("/{node_type}/{node_name}/cleanup-gemini")
async def cleanup_gemini_files(
    node_type: str,
    node_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete all Gemini files for a node (preserves local files).
    Call this when leaving the chat page.
    """
    if node_type.lower() not in ["hub", "spoke"]:
        raise HTTPException(status_code=400, detail="node_type must be 'hub' or 'spoke'")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    cleaned = await service.cleanup_gemini_files(node_type, node_name)
    
    return {
        "cleaned_count": cleaned,
        "message": f"Cleaned up {cleaned} Gemini files"
    }


@files_router.delete("/{file_id}")
async def delete_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a file by ID (from disk, Gemini, and database)"""
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


@files_router.get("/download/{file_id}")
async def download_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Download an uploaded file by its ID (References)"""
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
    Serve a file from Hub or Spoke directory (refs, artifacts, or files).
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
        
        # Determine filename for download
        filename = full_path.name
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        return FileResponse(
            full_path, 
            media_type=mime_type, 
            filename=filename
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Traversal or validation error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[FileServing] Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

