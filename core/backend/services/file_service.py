"""
File Service - Manages file lifecycle with Gemini File API integration

Handles:
- Local file storage (filesystem + database)
- Gemini File API upload/sync/cleanup
- File availability monitoring
"""
import os
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from uuid import uuid4

import google.generativeai as genai
from sqlalchemy.orm import Session

from models.database import UploadedFile, Node
from config import get_settings


# File size limit: 100MB (Gemini supports up to 2GB)
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class FileService:
    """Service for managing files with Gemini File API integration"""
    
    def __init__(self, db: Session, user_id: str, api_key: str = None):
        self.db = db
        self.user_id = user_id
        self.api_key = api_key
        
        if api_key:
            genai.configure(api_key=api_key)
    
    def _get_user_root(self) -> Path:
        """Get user's root data directory"""
        settings = get_settings()
        data_root = Path(settings.user_data_root)
        return data_root / self.user_id
    
    def get_hub_files_dir(self) -> Path:
        """Get Hub files directory for user"""
        path = self._get_user_root() / "hub" / "files"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_spoke_files_dir(self, spoke_name: str) -> Path:
        """Get Spoke files directory for user"""
        path = self._get_user_root() / "spokes" / spoke_name / "files"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_files_dir(self, node_type: str, node_name: str) -> Path:
        """Get files directory based on node type"""
        if node_type.lower() == "hub":
            return self.get_hub_files_dir()
        else:
            return self.get_spoke_files_dir(node_name)
    
    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content"""
        return hashlib.sha256(content).hexdigest()
    
    def _get_node(self, node_type: str, node_name: str) -> Optional[Node]:
        """Get node from database"""
        if node_type.lower() == "hub":
            return self.db.query(Node).filter(
                Node.user_id == self.user_id,
                Node.node_type == "HUB"
            ).first()
        else:
            return self.db.query(Node).filter(
                Node.user_id == self.user_id,
                Node.name == node_name,
                Node.node_type == "SPOKE"
            ).first()
    
    def _get_or_create_node(self, node_type: str, node_name: str) -> Node:
        """Get or create node in database"""
        node = self._get_node(node_type, node_name)
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
        self.db.commit()
        
        # Create default profile
        profile = AgentProfile(
            id=str(uuid4()),
            node_id=node_id,
            system_prompt=None,
            is_active=True
        )
        self.db.add(profile)
        self.db.commit()
        
        print(f"[FileService] Created node: {node_type}/{node_name}")
        return node
    
    def save_file(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        node_type: str,
        node_name: str
    ) -> UploadedFile:
        """
        Save file to filesystem and database.
        
        Args:
            content: File binary content
            filename: Original filename  
            mime_type: MIME type
            node_type: "hub" or "spoke"
            node_name: Node name (spoke name or "hub")
        
        Returns:
            UploadedFile database record
        """
        # Validate file size
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")
        
        # Get existing node (should be created when spoke/hub is created)
        node = self._get_node(node_type, node_name)
        if not node:
            # Log for debugging
            print(f"[FileService] Node not found: {node_type}/{node_name} for user {self.user_id}")
            raise ValueError(f"Node not found: {node_type}/{node_name}. Please create the spoke first.")
        
        # Generate unique filename to avoid collisions
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        
        # Save to filesystem
        files_dir = self.get_files_dir(node_type, node_name)
        file_path = files_dir / safe_filename
        file_path.write_bytes(content)
        
        # Compute hash
        content_hash = self._compute_hash(content)
        
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
        self.db.commit()
        self.db.refresh(uploaded_file)
        
        print(f"[FileService] Saved file: {filename} -> {file_path}")
        return uploaded_file
    
    def upload_to_gemini(self, file_record: UploadedFile) -> Dict[str, str]:
        """
        Upload a file to Gemini File API.
        
        Args:
            file_record: UploadedFile database record
        
        Returns:
            Dict with gemini_file_uri and gemini_file_name
        """
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        
        # Check if file exists locally
        file_path = Path(file_record.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Local file not found: {file_path}")
        
        # Upload to Gemini
        print(f"[FileService] Uploading to Gemini: {file_record.filename}")
        gemini_file = genai.upload_file(
            path=str(file_path),
            mime_type=file_record.mime_type,
            display_name=file_record.filename
        )
        
        # Wait for processing if needed
        import time
        while gemini_file.state.name == "PROCESSING":
            print(f"[FileService] Waiting for Gemini processing: {file_record.filename}")
            time.sleep(2)
            gemini_file = genai.get_file(gemini_file.name)
        
        if gemini_file.state.name == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {file_record.filename}")
        
        # Update database record
        file_record.gemini_file_uri = gemini_file.uri
        file_record.gemini_file_name = gemini_file.name
        self.db.commit()
        
        print(f"[FileService] Uploaded to Gemini: {gemini_file.name}")
        return {
            "gemini_file_uri": gemini_file.uri,
            "gemini_file_name": gemini_file.name
        }
    
    def check_gemini_availability(self, file_record: UploadedFile) -> bool:
        """
        Check if a file is still available in Gemini File API.
        
        Args:
            file_record: UploadedFile with gemini_file_name
        
        Returns:
            True if available, False otherwise
        """
        if not file_record.gemini_file_name:
            return False
        
        if not self.api_key:
            return False
        
        try:
            gemini_file = genai.get_file(file_record.gemini_file_name)
            return gemini_file.state.name == "ACTIVE"
        except Exception as e:
            print(f"[FileService] Gemini file not available: {file_record.gemini_file_name} - {e}")
            return False
    
    def sync_files_for_session(
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
        node = self._get_node(node_type, node_name)
        if not node:
            return []
        
        files = self.db.query(UploadedFile).filter(
            UploadedFile.node_id == node.id
        ).all()
        
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
                if self.check_gemini_availability(file_record):
                    status["gemini_available"] = True
                    status["gemini_file_uri"] = file_record.gemini_file_uri
                else:
                    # Clear stale reference
                    file_record.gemini_file_uri = None
                    file_record.gemini_file_name = None
                    self.db.commit()
            
            # Upload if not available
            if not status["gemini_available"]:
                try:
                    result = self.upload_to_gemini(file_record)
                    status["gemini_available"] = True
                    status["gemini_file_uri"] = result["gemini_file_uri"]
                except Exception as e:
                    print(f"[FileService] Failed to sync file: {file_record.filename} - {e}")
                    status["error"] = str(e)
            
            results.append(status)
        
        return results
    
    def cleanup_gemini_files(self, node_type: str, node_name: str) -> int:
        """
        Delete all Gemini files for a node (preserves local files).
        Called when user leaves the chat page.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            Number of files cleaned up
        """
        node = self._get_node(node_type, node_name)
        if not node:
            return 0
        
        files = self.db.query(UploadedFile).filter(
            UploadedFile.node_id == node.id,
            UploadedFile.gemini_file_name.isnot(None)
        ).all()
        
        cleaned = 0
        for file_record in files:
            try:
                genai.delete_file(file_record.gemini_file_name)
                print(f"[FileService] Deleted from Gemini: {file_record.gemini_file_name}")
            except Exception as e:
                print(f"[FileService] Failed to delete from Gemini: {e}")
            
            # Clear references regardless of delete success
            file_record.gemini_file_uri = None
            file_record.gemini_file_name = None
            cleaned += 1
        
        self.db.commit()
        return cleaned
    
    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from disk, Gemini, and database.
        
        Args:
            file_id: UploadedFile ID
        
        Returns:
            True if deleted successfully
        """
        file_record = self.db.query(UploadedFile).filter(
            UploadedFile.id == file_id
        ).first()
        
        if not file_record:
            return False
        
        # Delete from Gemini if uploaded
        if file_record.gemini_file_name:
            try:
                genai.delete_file(file_record.gemini_file_name)
            except Exception as e:
                print(f"[FileService] Failed to delete from Gemini: {e}")
        
        # Delete from filesystem
        file_path = Path(file_record.storage_path)
        if file_path.exists():
            file_path.unlink()
        
        # Delete from database
        self.db.delete(file_record)
        self.db.commit()
        
        print(f"[FileService] Deleted file: {file_record.filename}")
        return True
    
    def list_files(self, node_type: str, node_name: str) -> List[Dict[str, Any]]:
        """
        List all files for a node.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            List of file metadata dicts
        """
        node = self._get_node(node_type, node_name)
        if not node:
            return []
        
        files = self.db.query(UploadedFile).filter(
            UploadedFile.node_id == node.id
        ).order_by(UploadedFile.uploaded_at.desc()).all()
        
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
    
    def get_gemini_file_parts(self, node_type: str, node_name: str) -> List:
        """
        Get Gemini file parts for all synced files.
        Used when making LLM requests with file context.
        
        Args:
            node_type: "hub" or "spoke"
            node_name: Node name
        
        Returns:
            List of Gemini file objects for API calls
        """
        node = self._get_node(node_type, node_name)
        if not node:
            return []
        
        files = self.db.query(UploadedFile).filter(
            UploadedFile.node_id == node.id,
            UploadedFile.gemini_file_name.isnot(None)
        ).all()
        
        parts = []
        for f in files:
            try:
                gemini_file = genai.get_file(f.gemini_file_name)
                if gemini_file.state.name == "ACTIVE":
                    parts.append(gemini_file)
            except Exception as e:
                print(f"[FileService] Failed to get Gemini file: {f.gemini_file_name} - {e}")
        
        return parts
