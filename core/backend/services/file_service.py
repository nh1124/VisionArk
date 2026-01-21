import os
import hashlib
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from uuid import uuid4

from google.genai import Client, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import UploadedFile, Project
from utils.paths import get_project_dir

# File size limit: 100MB
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


def _resolve_portable_path(stored_path: str) -> Path:
    """
    Resolves a stored absolute path to a local physical path.
    Handles Linux absolute paths in a Windows environment if needed.
    """
    from utils.paths import DATA_DIR
    p = Path(stored_path)
    if p.exists():
        return p
    
    path_str = str(p).replace('\\', '/')
    if '/data/' in path_str:
        relative_part = path_str.split('/data/', 1)[1]
        portable_path = DATA_DIR / relative_part.replace('/', os.sep)
        return portable_path
        
    return p


class FileService:
    """
    Service for managing file storage and database records.
    Handles local storage and Gemini File API uploads for chat context.
    """
    
    def __init__(self, db: AsyncSession, user_id: str, api_key: str = None):
        self.db = db
        self.user_id = user_id
        self.api_key = api_key
        self.client = None
        if api_key:
            self.client = Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
            
    def _ensure_client(self):
        """Ensure the Gemini client is initialized"""
        if self.api_key and self.client is None:
            self.client = Client(api_key=self.api_key, http_options={'api_version': 'v1alpha'})
        return self.client
    
    def get_files_dir(self, project_id: str) -> Path:
        """Get files directory (refs) based on project ID"""
        # Map legacy 'root' to 'hub' for project ID
        p_id = project_id
        
        base = get_project_dir(self.user_id, p_id)
        
        path = base / "refs"  # Default to refs for library uploads
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    async def _get_project(self, project_id: str) -> Optional[Project]:
        """Get project from database by ID"""
        result = await self.db.execute(select(Project).filter(
            Project.user_id == self.user_id,
            Project.id == project_id
        ))
        return result.scalars().first()
    
    async def save_file(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        project_id: str
    ) -> UploadedFile:
        """
        Save file to filesystem and database.
        """
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")
        
        proj = await self._get_project(project_id)
        if not proj:
            raise ValueError(f"Project '{project_id}' not found.")
        
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        
        # Save to filesystem
        files_dir = self.get_files_dir(project_id)
        file_path = files_dir / safe_filename
        await asyncio.to_thread(file_path.write_bytes, content)
        
        # Create database record
        uploaded_file = UploadedFile(
            id=file_id,
            project_id=proj.id,
            filename=filename,
            storage_path=str(file_path),
            mime_type=mime_type,
            size_bytes=len(content),
            uploaded_at=datetime.utcnow()
        )
        
        self.db.add(uploaded_file)
        await self.db.commit()
        return uploaded_file
    
    async def upload_to_gemini(self, file_record: UploadedFile) -> Dict[str, str]:
        """
        Explicitly upload a file to Gemini File API for LLM context.
        """
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        
        file_path = _resolve_portable_path(file_record.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Local file not found: {file_path}")
        
        client = self._ensure_client()
        gemini_file = await asyncio.to_thread(
            client.files.upload,
            file=str(file_path),
            config=types.UploadFileConfig(
                mime_type=file_record.mime_type,
                display_name=file_record.filename
            )
        )
        
        while gemini_file.state == "PROCESSING":
            await asyncio.sleep(2)
            gemini_file = await asyncio.to_thread(client.files.get, name=gemini_file.name)
        
        if gemini_file.state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {file_record.filename}")
        
        return {
            "gemini_file_uri": gemini_file.uri,
            "gemini_file_name": gemini_file.name
        }
    
    async def ensure_gemini_upload(
        self,
        local_path: Path,
        filename: str = None,
        mime_type: str = None,
        project_id: str = None
    ) -> Dict[str, str]:
        """
        Ensures a file is uploaded to Gemini File API.
        Always uploads to ensure reliability as cloud files are temporary.
        """
        if not self.api_key:
            return {}

        abs_path = str(local_path.resolve())
        filename = filename or local_path.name
        
        if not mime_type:
            from mimetypes import guess_type
            mime_type, _ = guess_type(abs_path)
            mime_type = mime_type or "application/octet-stream"

        try:
            client = self._ensure_client()
            gemini_file = await asyncio.to_thread(
                client.files.upload,
                file=abs_path,
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=filename
                )
            )
            
            while gemini_file.state == "PROCESSING":
                await asyncio.sleep(1)
                gemini_file = await asyncio.to_thread(client.files.get, name=gemini_file.name)
            
            if gemini_file.state == "FAILED":
                return {}

            return {
                "gemini_file_uri": gemini_file.uri,
                "mime_type": mime_type
            }
        except Exception as e:
            print(f"[FileService] ensure_gemini_upload failed: {e}")
            return {}

    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from disk, database, and Gemini if exists.
        """
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.id == file_id
        ))
        file_record = result.scalars().first()
        
        if not file_record:
            return False
        
        # Delete from filesystem
        file_path = Path(file_record.storage_path)
        if file_path.exists():
            file_path.unlink()
        
        # Delete from database
        await self.db.delete(file_record)
        await self.db.commit()
        return True
    
    async def list_files(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List all files for a project (Hybrid: DB + Disk).
        Includes files registered in DB and those physically in the 'refs' directory.
        """
        proj = await self._get_project(project_id)
        if not proj:
            return []
        
        # 1. Get DB-registered files
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.project_id == proj.id
        ).order_by(UploadedFile.uploaded_at.desc()))
        db_files = result.scalars().all()
        
        db_file_map = {Path(f.storage_path).resolve(): f for f in db_files}
        
        # 2. Scan Disk for additional files (e.g., GitHub imports)
        final_list = []
        
        # Add DB files first
        for f in db_files:
            final_list.append({
                "id": f.id,
                "filename": f.filename,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "source": "database"
            })
            
        # 3. Add Disk-only files from 'refs' directory
        try:
            refs_dir = self.get_files_dir(project_id)
            if refs_dir.exists():
                from mimetypes import guess_type
                for p in refs_dir.rglob('*'):
                    if p.is_file():
                        resolved_p = p.resolve()
                        if resolved_p not in db_file_map:
                            # Relative path for display/identification
                            rel_path = p.relative_to(refs_dir).as_posix()
                            
                            # Determine mime type
                            mime_type, _ = guess_type(str(p))
                            stat = p.stat()
                            
                            final_list.append({
                                "id": f"disk:refs/{rel_path}", # Virtual ID
                                "filename": rel_path,
                                "mime_type": mime_type or "application/octet-stream",
                                "size_bytes": stat.st_size,
                                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "has_gemini_ref": False,
                                "source": "disk"
                            })
        except Exception as e:
            print(f"[FileService] Error scanning disk for files: {e}")
            
        return final_list

    async def get_gemini_file_parts(self, project_id: str) -> List:
        """
        Get Gemini file parts for all synced files of a project.
        Used by agents for context.
        Note: With current simplified approach, this returns an empty list as we don't track persistent uploads in DB.
        """
        return []
