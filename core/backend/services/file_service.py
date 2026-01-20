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
        
        file_record.gemini_file_uri = gemini_file.uri
        file_record.gemini_file_name = gemini_file.name
        await self.db.commit()
        
        return {
            "gemini_file_uri": gemini_file.uri,
            "gemini_file_name": gemini_file.name
        }
    
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
        
        # Delete from Gemini if uploaded
        if file_record.gemini_file_name and self.api_key:
            try:
                client = self._ensure_client()
                await asyncio.to_thread(client.files.delete, name=file_record.gemini_file_name)
            except Exception as e:
                print(f"[FileService] Failed to delete from Gemini: {e}")
        
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
        List all files for a project.
        """
        node = await self._get_node(project_id)
        if not node:
            return []
        
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.node_id == node.id
        ).order_by(UploadedFile.uploaded_at.desc()))
        files = result.scalars().all()
        
        return [
            {
                "id": f.id,
                "filename": f.filename,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "has_gemini_ref": f.gemini_file_uri is not None
            }
            for f in files
        ]

    async def get_gemini_file_parts(self, node_id: str) -> List:
        """
        Get Gemini file parts for all synced files of a node.
        Used by agents for context.
        """
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.node_id == node_id,
            UploadedFile.gemini_file_name.isnot(None)
        ))
        files = result.scalars().all()
        
        parts = []
        client = self._ensure_client()
        if not client:
            return []

        for f in files:
            try:
                gemini_file = await asyncio.to_thread(client.files.get, name=f.gemini_file_name)
                if gemini_file.state == "ACTIVE":
                    parts.append(gemini_file)
            except Exception as e:
                print(f"[FileService] Failed to get Gemini file: {f.gemini_file_name} - {e}")
        
        return parts
