import os
import hashlib
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from uuid import uuid4

from google.genai import Client, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from models.database import UploadedFile, Node
from config import get_settings
from utils.paths import get_user_hub_dir, get_spoke_dir

# File size limit: 100MB (Gemini supports up to 2GB)
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


def _resolve_portable_path(stored_path: str) -> Path:
    """
    Resolves a stored absolute path to a local physical path.
    Handles Linux absolute paths (/app/data/...) in a Windows environment.
    """
    from utils.paths import DATA_DIR
    p = Path(stored_path)
    if p.exists():
        return p
    
    # If not exists, check if it's a Linux absolute path containing 'data'
    path_str = str(p).replace('\\', '/')
    if '/data/' in path_str:
        relative_part = path_str.split('/data/', 1)[1]
        portable_path = DATA_DIR / relative_part.replace('/', os.sep)
        return portable_path
        
    return p


class FileService:
    """Service for managing files with Gemini File API integration (New SDK)"""
    
    def __init__(self, db: AsyncSession, user_id: str, api_key: str = None):
        self.db = db
        self.user_id = user_id
        self.api_key = api_key
        
        # Initialize the new SDK client
        self.client = None
        if api_key:
            self.client = Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
            
    def _ensure_client(self):
        """Ensure the client is initialized"""
        if self.api_key and self.client is None:
            self.client = Client(api_key=self.api_key, http_options={'api_version': 'v1alpha'})
        return self.client
    
    def get_files_dir(self, node_type: str, node_name: str) -> Path:
        """Get files directory based on node type"""
        if node_type.lower() == "hub":
            base = get_user_hub_dir(self.user_id)
        else:
            base = get_spoke_dir(self.user_id, node_name)
        
        path = base / "files"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content"""
        return hashlib.sha256(content).hexdigest()
    
    async def _get_node(self, node_type: str, node_name: str) -> Optional[Node]:
        """Get node from database asynchronously"""
        if node_type.lower() == "hub":
            result = await self.db.execute(select(Node).filter(
                Node.user_id == self.user_id,
                Node.node_type == "HUB"
            ))
            return result.scalars().first()
        else:
            result = await self.db.execute(select(Node).filter(
                Node.user_id == self.user_id,
                Node.name == node_name,
                Node.node_type == "SPOKE"
            ))
            return result.scalars().first()
    
    async def _get_or_create_node(self, node_type: str, node_name: str) -> Node:
        """Get or create node in database asynchronously"""
        node = await self._get_node(node_type, node_name)
        if node:
            return node
        
        # Create node if it doesn't exist
        print(f"[FileService] Creating node for user_id={self.user_id}, {node_type}/{node_name}")
        from models.database import AgentProfile
        node_id = str(uuid4())
        
        if node_type.lower() == "hub":
            node = Node(
                id=node_id,
                user_id=self.user_id,
                name="hub",
                display_name="Central Hub",
                node_type="HUB",
                lbs_access_level="WRITE"
            )
        else:
            node = Node(
                id=node_id,
                user_id=self.user_id,
                name=node_name,
                display_name=node_name.replace('_', ' ').title(),
                node_type="SPOKE",
                lbs_access_level="READ_ONLY"
            )
        
        self.db.add(node)
        await self.db.commit()
        
        # Create default profile
        profile = AgentProfile(
            id=str(uuid4()),
            node_id=node_id,
            system_prompt=None,
            is_active=True
        )
        self.db.add(profile)
        await self.db.commit()
        
        print(f"[FileService] Created node: {node_type}/{node_name}")
        return node
    
    async def save_file(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        node_type: str,
        node_name: str
    ) -> UploadedFile:
        """
        Save file to filesystem and database asynchronously.
        """
        # Validate file size
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")
        
        # Get existing node
        node = await self._get_node(node_type, node_name)
        if not node:
            print(f"[FileService] Node not found: {node_type}/{node_name} for user {self.user_id}")
            raise ValueError(f"Node not found: {node_type}/{node_name}. Please create the spoke first.")
        
        # Generate unique filename
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        
        # Save to filesystem
        files_dir = self.get_files_dir(node_type, node_name)
        file_path = files_dir / safe_filename
        await asyncio.to_thread(file_path.write_bytes, content)
        
        # Create database record
        uploaded_file = UploadedFile(
            id=file_id,
            node_id=node.id,
            filename=filename,
            storage_path=str(file_path),
            mime_type=mime_type,
            size_bytes=len(content),
            vector_status="PENDING",
            kc_sync_status="PENDING",
            uploaded_at=datetime.utcnow()
        )
        
        self.db.add(uploaded_file)
        await self.db.commit()
        
        print(f"[FileService] Saved file: {filename} -> {file_path}")
        return uploaded_file
    
    async def upload_to_gemini(self, file_record: UploadedFile) -> Dict[str, str]:
        """
        Upload a file to Gemini File API.
        """
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        
        # Check if file exists locally
        file_path = _resolve_portable_path(file_record.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Local file not found: {file_path}")
        
        # Upload to Gemini
        print(f"[FileService] Uploading to Gemini: {file_record.filename}")
        client = self._ensure_client()
        
        # Run upload in a thread pool to avoid blocking the event loop
        gemini_file = await asyncio.to_thread(
            client.files.upload,
            file=str(file_path),
            config=types.UploadFileConfig(
                mime_type=file_record.mime_type,
                display_name=file_record.filename
            )
        )
        
        # Wait for processing asynchronously
        while gemini_file.state == "PROCESSING":
            print(f"[FileService] Waiting for Gemini processing: {file_record.filename}")
            await asyncio.sleep(2)
            gemini_file = await asyncio.to_thread(client.files.get, name=gemini_file.name)
        
        if gemini_file.state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {file_record.filename}")
        
        # Update database record
        file_record.gemini_file_uri = gemini_file.uri
        file_record.gemini_file_name = gemini_file.name
        await self.db.commit()
        
        print(f"[FileService] Uploaded to Gemini: {gemini_file.name}")
        return {
            "gemini_file_uri": gemini_file.uri,
            "gemini_file_name": gemini_file.name
        }
    
    async def check_gemini_availability(self, file_record: UploadedFile) -> bool:
        """
        Check if a file is still available in Gemini File API.
        """
        if not file_record.gemini_file_name or not self.api_key:
            return False
        
        try:
            client = self._ensure_client()
            gemini_file = await asyncio.to_thread(client.files.get, name=file_record.gemini_file_name)
            return gemini_file.state == "ACTIVE"
        except Exception as e:
            print(f"[FileService] Gemini file not available: {file_record.gemini_file_name} - {e}")
            return False
    
    async def sync_files_for_session(
        self,
        node_type: str,
        node_name: str
    ) -> List[Dict[str, Any]]:
        """
        Ensure all files for a node are uploaded to Gemini.
        Re-uploads if files are not available.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            List of file status dicts
        """
        node = await self._get_node(node_type, node_name)
        if not node:
            return []
        
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.node_id == node.id
        ))
        files = result.scalars().all()
        
        results = []
        for file_record in files:
            status = {
                "id": file_record.id,
                "filename": file_record.filename,
                "size_bytes": file_record.size_bytes,
                "mime_type": file_record.mime_type,
                "gemini_available": False,
                "gemini_file_uri": None
            }
            
            # Check if already uploaded and available
            if file_record.gemini_file_name:
                if await self.check_gemini_availability(file_record):
                    status["gemini_available"] = True
                    status["gemini_file_uri"] = file_record.gemini_file_uri
                else:
                    # Clear stale reference
                    file_record.gemini_file_uri = None
                    file_record.gemini_file_name = None
                    await self.db.commit()
            
            # Upload if not available
            if not status["gemini_available"]:
                try:
                    # Check if local file actually exists before trying to upload
                    resolved_path = _resolve_portable_path(file_record.storage_path)
                    if not resolved_path.exists():
                        print(f"[FileService] Warning: Local file missing, skipping sync: {file_record.filename}")
                        status["error"] = "Local file missing"
                        continue
                        
                    result = await self.upload_to_gemini(file_record)
                    status["gemini_available"] = True
                    status["gemini_file_uri"] = result["gemini_file_uri"]
                except Exception as e:
                    print(f"[FileService] Failed to sync file: {file_record.filename} - {e}")
                    status["error"] = str(e)
            
            results.append(status)
        
        return results
    
    async def cleanup_gemini_files(self, node_type: str, node_name: str) -> int:
        """
        Delete all Gemini files for a node (preserves local files).
        Called when user leaves the chat page.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            Number of files cleaned up
        """
        node = await self._get_node(node_type, node_name)
        if not node:
            return 0
        
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.node_id == node.id,
            UploadedFile.gemini_file_name.isnot(None)
        ))
        files = result.scalars().all()
        
        cleaned = 0
        client = self._ensure_client()
        for file_record in files:
            try:
                await asyncio.to_thread(client.files.delete, name=file_record.gemini_file_name)
                print(f"[FileService] Deleted from Gemini: {file_record.gemini_file_name}")
            except Exception as e:
                print(f"[FileService] Failed to delete from Gemini: {e}")
            
            # Clear references regardless of delete success
            file_record.gemini_file_uri = None
            file_record.gemini_file_name = None
            cleaned += 1
        
        await self.db.commit()
        return cleaned
    
    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from disk, Gemini, and database asynchronously.
        """
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.id == file_id
        ))
        file_record = result.scalars().first()
        
        if not file_record:
            return False
        
        # Delete from Gemini if uploaded
        if file_record.gemini_file_name:
            try:
                client = self._ensure_client()
                client.files.delete(name=file_record.gemini_file_name)
            except Exception as e:
                print(f"[FileService] Failed to delete from Gemini: {e}")
        
        # Delete from filesystem
        file_path = Path(file_record.storage_path)
        if file_path.exists():
            file_path.unlink()
        
        # Delete from database
        await self.db.delete(file_record)
        await self.db.commit()
        
        print(f"[FileService] Deleted file: {file_record.filename}")
        return True
    
    async def list_files(self, node_type: str, node_name: str) -> List[Dict[str, Any]]:
        """
        List all files for a node asynchronously.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            List of file metadata dicts
        """
        node = await self._get_node(node_type, node_name)
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
    
    async def get_gemini_file_parts(self, node_type: str, node_name: str) -> List:
        """
        Get Gemini file parts for all synced files.
        Used when making LLM requests with file context.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            List of Gemini file objects for API calls
        """
        node = await self._get_node(node_type, node_name)
        if not node:
            return []
        
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.node_id == node.id,
            UploadedFile.gemini_file_name.isnot(None)
        ))
        files = result.scalars().all()
        
        parts = []
        client = self._ensure_client()
        for f in files:
            try:
                gemini_file = await asyncio.to_thread(client.files.get, name=f.gemini_file_name)
                if gemini_file.state == "ACTIVE":
                    parts.append(gemini_file)
            except Exception as e:
                print(f"[FileService] Failed to get Gemini file: {f.gemini_file_name} - {e}")
        
        return parts
