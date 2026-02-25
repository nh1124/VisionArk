import os
import hashlib
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from uuid import uuid4
import tempfile

from google.genai import Client, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.database import UploadedFile, Project, AsyncSessionLocal
from shared.paths import get_project_dir, secure_path_join
import shutil
from sqlalchemy import delete

# File size limit: 100MB
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

# Sync exclusion list
IGNORED_DIRS = {
    '.git', '.github', 'node_modules', '__pycache__', 
    '.venv', 'venv', 'env', '.pytest_cache', '.next',
    '.antigravity', '.gemini', 'dist', 'build', '.vscode'
}


def _resolve_portable_path(stored_path: str) -> Path:
    """
    Resolves a stored absolute path to a local physical path.
    Handles Linux absolute paths in a Windows environment if needed.
    """
    from shared.paths import DATA_DIR
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
    
    def get_files_dir(self, project_id: Optional[str] = None, directory: str = "refs") -> Path:
        """Get files directory based on project ID and type (refs/artifacts/files)"""
        if project_id:
            # Map legacy 'root' to 'hub' for project ID
            p_id = project_id
            
            base = get_project_dir(self.user_id, p_id)
        else:
            from shared.paths import get_user_global_assets_dir
            base = get_user_global_assets_dir(self.user_id)
            
        path = base / directory
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
        project_id: Optional[str] = None,
        directory: str = "refs"
    ) -> UploadedFile:
        """
        Save file to filesystem and database.
        """
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds limit of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")
        
        proj = None
        if project_id:
            proj = await self._get_project(project_id)
            if not proj:
                raise ValueError(f"Project '{project_id}' not found.")
        
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        
        # Save to filesystem
        files_dir = self.get_files_dir(project_id, directory)
        file_path = files_dir / safe_filename
        await asyncio.to_thread(file_path.write_bytes, content)
        
        # Create database record
        mime_type = mime_type or "application/octet-stream"
        uploaded_file = UploadedFile(
            id=file_id,
            project_id=proj.id if proj else None,
            filename=filename,
            directory=directory,
            storage_path=str(file_path),
            mime_type=mime_type,
            size_bytes=len(content),
            uploaded_at=datetime.utcnow()
        )
        
        self.db.add(uploaded_file)
        await self.db.commit()
        
        # Trigger Watchers
        if project_id:
            asyncio.create_task(self._trigger_watchers(uploaded_file))
        
        return uploaded_file
    
    async def _trigger_watchers(self, file_record: UploadedFile):
        """
        Check for any nodes or system triggers that should react to this file upload.
        """
        try:
            from shared.database import ProjectAgent, AsyncSessionLocal
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                # Find agents in this project that have 'watcher' metadata
                stmt = select(ProjectAgent).filter(
                    ProjectAgent.project_id == file_record.project_id,
                    ProjectAgent.status == "active"
                )
                result = await session.execute(stmt)
                agents = result.scalars().all()

                for agent in agents:
                    meta = agent.meta_payload or {}
                    watchers = meta.get("watchers", [])

                    for watcher in watchers:
                        # e.g., watcher = {"pattern": "*.pdf", "task_type": "PDF_ANALYSIS"}
                        import fnmatch
                        pattern = watcher.get("pattern", "*")
                        if fnmatch.fnmatch(file_record.filename, pattern):
                            task_type = watcher.get("task_type")
                            if task_type:
                                from domains.automation.aes_dispatcher import AESDispatcher
                                dispatcher = AESDispatcher(lambda: session)
                                await dispatcher.schedule_task(
                                    user_id=self.user_id,
                                    task_type=task_type,
                                    scheduled_at=datetime.utcnow(), # Immediate
                                    project_id=file_record.project_id,
                                    payload={
                                        "file_id": file_record.id,
                                        "filename": file_record.filename,
                                        "project_id": file_record.project_id,
                                        "agent_id": agent.id
                                    }
                                )
                                print(f"[Watcher] Triggered {task_type} for {file_record.filename} via {agent.display_name}")
        except Exception as e:
            print(f"[Watcher] Error in _trigger_watchers: {e}")
    
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
            from shared.mimetype_helper import guess_mime_type
            mime_type = guess_mime_type(filename)

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
        Delete a file or directory from disk and database by UUID.
        """
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.id == file_id
        ))
        file_record = result.scalars().first()
        
        if not file_record:
            return False
        
        try:
            # 1. Physical Deletion
            path = Path(file_record.storage_path)
            if path.exists():
                if file_record.is_directory:
                    import shutil
                    await asyncio.to_thread(shutil.rmtree, str(path))
                else:
                    path.unlink()
            
            # 2. Database Deletion (Recursive if Directory)
            if file_record.is_directory:
                # Find all logical children
                prefix = f"{file_record.filename}/"
                stmt = select(UploadedFile).filter(
                    UploadedFile.project_id == file_record.project_id,
                    UploadedFile.directory == file_record.directory,
                    UploadedFile.filename.like(f"{prefix}%")
                )
                child_results = await self.db.execute(stmt)
                children = child_results.scalars().all()
                for child in children:
                    await self.db.delete(child)
            
            await self.db.delete(file_record)
            await self.db.commit()
            return True
        except Exception as e:
            print(f"[FileService] delete_file failed for {file_id}: {e}")
            await self.db.rollback()
            return False

    async def delete_path(self, project_id: str, directory_type: str, rel_path: str) -> bool:
        """
        Delete a file or directory from the project directory recursively.
        directory_type: 'refs', 'artifacts', or 'files'
        """
        if directory_type not in ["refs", "artifacts", "files"]:
            return False

        proj_dir = get_project_dir(self.user_id, project_id)
        full_path = secure_path_join(proj_dir / directory_type, rel_path)

        if not full_path.exists():
            return False

        # 1. Database Cleanup
        # If it's a directory, delete all files starting with that path
        # If it's a file, delete exactly that path
        search_pattern = rel_path
        if full_path.is_dir():
            if not search_pattern.endswith('/'):
                search_pattern += '/'
            
            await self.db.execute(
                delete(UploadedFile).where(
                    UploadedFile.project_id == project_id,
                    UploadedFile.filename.like(f"{search_pattern}%")
                )
            )
        else:
            await self.db.execute(
                delete(UploadedFile).where(
                    UploadedFile.project_id == project_id,
                    UploadedFile.filename == rel_path
                )
            )

        # 2. Physical Deletion
        try:
            if full_path.is_dir():
                await asyncio.to_thread(shutil.rmtree, full_path)
            else:
                await asyncio.to_thread(full_path.unlink)
            
            await self.db.commit()
            return True
        except Exception as e:
            print(f"[FileService] Delete path failed: {e}")
            await self.db.rollback()
            return False

    async def zip_directory(self, project_id: str, directory_type: str, rel_path: str) -> Optional[Path]:
        """
        Create a ZIP archive of a directory and return the path to the temporary file.
        """
        if directory_type not in ["refs", "artifacts", "files"]:
            return None

        proj_dir = get_project_dir(self.user_id, project_id)
        full_path = secure_path_join(proj_dir / directory_type, rel_path)

        if not full_path.exists() or not full_path.is_dir():
            return None

        print(f"{__name__} Debug : {full_path}")

        try:
            # Create a temporary file
            temp_dir = Path(tempfile.gettempdir())
            zip_base = temp_dir / f"download_{uuid4().hex}"
            

            print(f"{__name__} Debug : {zip_base}")
            # shutil.make_archive adds the extension (.zip) automatically
            zip_path_str = await asyncio.to_thread(
                shutil.make_archive, 
                str(zip_base), 
                'zip', 
                root_dir=str(full_path)
            )
            
            return Path(zip_path_str)
        except Exception as e:
            print(f"[FileService] ZIP generation failed: {e}")
            return None
    
    async def sync_project_directory(self, project_id: str, deep: bool = False, db_override: AsyncSession = None) -> Dict[str, int]:
        """
        Synchronize filesystem with database records.
        Lightweight delta sync using size and mtime.
        """
        # Use provided session or stick with self.db
        db = db_override or self.db
        
        proj = await db.execute(select(Project).filter(
            Project.user_id == self.user_id,
            Project.id == project_id
        ))
        proj = proj.scalars().first()
        
        if not proj:
            return {"added": 0, "removed": 0, "updated": 0}

        proj_dir = get_project_dir(self.user_id, project_id)
        if not proj_dir.exists():
            return {"added": 0, "removed": 0, "updated": 0}

        # 1. Get current DB records and build lookup maps
        result = await db.execute(select(UploadedFile).filter(UploadedFile.project_id == proj.id))
        all_records = result.scalars().all()
        
        db_by_key = {(f.directory, f.filename): f for f in all_records}
        db_by_storage = {}
        
        import re
        UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
        
        for f in all_records:
            if not f.storage_path: continue
            
            # Prefer records with non-UUID filenames as the canonical logical name
            is_uuid_filename = bool(UUID_PATTERN.match(f.filename))
            if f.storage_path not in db_by_storage or not is_uuid_filename:
                db_by_storage[f.storage_path] = f

        from mimetypes import guess_type
        stats = {"added": 0, "removed": 0, "updated": 0}
        found_keys = set()
        claimed_storage = set()

        # 2. Scan Disk (refs, artifacts, files)
        def scan_dir(sub_dir_name: str):
            target_dir = proj_dir / sub_dir_name
            if not target_dir.exists():
                return

            def scan_recursive(current_dir: Path):
                for item in os.scandir(current_dir):
                    if item.name in IGNORED_DIRS:
                        continue
                        
                    p = Path(item.path)
                    spath = str(p)
                    try:
                        # rel_path is relative to the directory root (refs, artifacts, etc.)
                        rel_path = p.relative_to(target_dir).as_posix()
                    except ValueError:
                        continue

                    # 1. Find best match in DB
                    match = db_by_storage.get(spath)
                    if not match:
                        match = db_by_key.get((sub_dir_name, rel_path))
                    
                    is_dir = item.is_dir()
                    
                    if match:
                        key = (match.directory, match.filename)
                        if spath not in claimed_storage and key not in found_keys:
                            found_keys.add(key)
                            claimed_storage.add(spath)
                            
                            # Ensure is_directory is correct for existing records
                            if match.is_directory != is_dir:
                                match.is_directory = is_dir
                                stats["updated"] += 1

                            # Update size for files
                            if not is_dir:
                                file_stat = item.stat()
                                if match.size_bytes != file_stat.st_size:
                                    match.size_bytes = file_stat.st_size
                                    stats["updated"] += 1
                    else:
                        # 2. Register New Disk Item
                        file_stat = item.stat()
                        mime_type = None
                        if not is_dir:
                            mime_type, _ = guess_type(item.name)
                            
                        new_record = UploadedFile(
                            id=str(uuid4()),
                            project_id=proj.id,
                            filename=rel_path,
                            directory=sub_dir_name,
                            storage_path=spath,
                            is_directory=is_dir,
                            mime_type=mime_type or ("inode/directory" if is_dir else "application/octet-stream"),
                            size_bytes=0 if is_dir else file_stat.st_size,
                            uploaded_at=datetime.fromtimestamp(file_stat.st_mtime)
                        )
                        db.add(new_record)
                        found_keys.add((sub_dir_name, rel_path))
                        claimed_storage.add(spath)
                        stats["added"] += 1
                    
                    # 3. Recurse if Directory
                    if is_dir:
                        scan_recursive(p)

            scan_recursive(target_dir)

        await asyncio.to_thread(lambda: [scan_dir(d) for d in ["refs", "artifacts", "files"]])

        # 3. Identify removed OR duplicate records
        for f in all_records:
            key = (f.directory, f.filename)
            if key not in found_keys:
                # This record no longer has a corresponding physical file (or it lost the claim due to deduplication)
                await db.delete(f)
                stats["removed"] += 1
        
        if stats["added"] > 0 or stats["removed"] > 0 or stats["updated"] > 0:
            await db.commit()
            print(f"[FileService] Sync completed for {project_id}: {stats}")

        return stats

    async def sync_project_directory_background(self, project_id: str):
        """
        Background wrapper that uses a fresh database session to avoid concurrency collisions.
        """
        try:
            async with AsyncSessionLocal() as session:
                await self.sync_project_directory(project_id, db_override=session)
        except Exception as e:
            print(f"[FileService] Background sync failed for {project_id}: {e}")

    async def list_files(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List all files for a project entirely from the DB (synchronized in background).
        """
        proj = await self._get_project(project_id)
        if not proj:
            return []
        
        # Trigger background sync (Lazy Sync)
        # Scan all directories
        asyncio.create_task(self.sync_project_directory_background(project_id))

        # 1. Get all DB-registered files
        result = await self.db.execute(select(UploadedFile).filter(
            UploadedFile.project_id == proj.id
        ).order_by(UploadedFile.uploaded_at.desc()))
        db_files = result.scalars().all()
        
        final_list = []
        for f in db_files:
            final_list.append({
                "id": f.id,
                "filename": f.filename,
                "directory": f.directory or "refs",
                "is_directory": f.is_directory,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "source": "database"
            })
            
        return final_list

    async def get_gemini_file_parts(self, project_id: str) -> List:
        """
        Get Gemini file parts for all synced files of a project.
        Used by agents for context.
        Note: With current simplified approach, this returns an empty list as we don't track persistent uploads in DB.
        """
        return []

    @staticmethod
    def compute_hash(p: Path) -> str:
        """SHA-256 hash of a file (with prefix)."""
        return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()

    async def stat_path(self, project_id: str, rel_path: str) -> Optional[Dict[str, Any]]:
        """Return stat info for a project-root-relative path, or None if not found."""
        root = get_project_dir(self.user_id, project_id)
        p = secure_path_join(root, rel_path)
        if not p.exists():
            return None
        st = p.stat()
        return {
            "path": p.relative_to(root).as_posix(),
            "size_bytes": st.st_size if not p.is_dir() else 0,
            "hash": self.compute_hash(p) if p.is_file() else None,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "is_dir": p.is_dir(),
        }

    async def move_file_path(self, project_id: str, src: str, dst: str, overwrite: bool = False) -> bool:
        """Move src to dst within the project root, then sync DB."""
        root = get_project_dir(self.user_id, project_id)
        src_p = secure_path_join(root, src)
        dst_p = secure_path_join(root, dst)

        if not src_p.exists():
            return False
        if dst_p.exists() and not overwrite:
            return False

        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        await self.sync_project_directory(project_id)
        return True

    async def copy_file_path(self, project_id: str, src: str, dst: str, overwrite: bool = False) -> bool:
        """Copy src to dst within the project root, then sync DB."""
        root = get_project_dir(self.user_id, project_id)
        src_p = secure_path_join(root, src)
        dst_p = secure_path_join(root, dst)

        if not src_p.exists():
            return False
        if dst_p.exists() and not overwrite:
            return False

        dst_p.parent.mkdir(parents=True, exist_ok=True)
        if src_p.is_dir():
            if dst_p.exists():
                shutil.rmtree(dst_p)
            shutil.copytree(str(src_p), str(dst_p))
        else:
            shutil.copy2(str(src_p), str(dst_p))
        await self.sync_project_directory(project_id)
        return True

    async def make_directory_path(self, project_id: str, rel_path: str) -> bool:
        """Create a directory (and parents) within the project root, then sync DB."""
        root = get_project_dir(self.user_id, project_id)
        p = secure_path_join(root, rel_path)
        p.mkdir(parents=True, exist_ok=True)
        await self.sync_project_directory(project_id)
        return True
