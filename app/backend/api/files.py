"""
File upload and management endpoints for Spokes
"""
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
import shutil

from utils.paths import get_spoke_dir

router = APIRouter(prefix="/api/spokes", tags=["Spokes"])

# File size limit: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes


@router.post("/{spoke_name}/upload")
async def upload_file(spoke_name: str, file: UploadFile = File(...)):
    """Upload a file to a spoke's refs directory (max 100MB)"""
    spoke_dir = get_spoke_dir(spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    # Ensure refs directory exists
    refs_dir = spoke_dir / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the file
    file_path = refs_dir / file.filename
    
    try:
        # Read and write file in chunks to handle large files
        total_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):  # 8KB chunks
                total_size += len(chunk)
                
                # Check file size limit
                if total_size > MAX_FILE_SIZE:
                    # Clean up partial file
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is 100MB, got {total_size / 1024 / 1024:.1f}MB"
                    )
                
                buffer.write(chunk)
        
        return {
            "message": f"File '{file.filename}' uploaded successfully",
            "filename": file.filename,
            "path": str(file_path),
            "size": file_path.stat().st_size
        }
    except HTTPException:
        raise
    except Exception as e:
        # Clean up partial file on error
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.get("/{spoke_name}/files")
def list_files(spoke_name: str):
    """List all files in a spoke's refs and artifacts directories"""
    spoke_dir = get_spoke_dir(spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
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
def download_file(spoke_name: str, directory: str, filename: str):
    """Download a file from spoke's refs or artifacts directory"""
    spoke_dir = get_spoke_dir(spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    if directory not in ["refs", "artifacts"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs' or 'artifacts'")
    
    file_path = spoke_dir / directory / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path, filename=filename)


@router.delete("/{spoke_name}/files/{directory}/{filename}")
def delete_file(spoke_name: str, directory: str, filename: str):
    """Delete a file from spoke's refs or artifacts directory"""
    spoke_dir = get_spoke_dir(spoke_name)
    
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    if directory not in ["refs", "artifacts"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs' or 'artifacts'")
    
    file_path = spoke_dir / directory / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        file_path.unlink()
        return {"message": f"File '{filename}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")
