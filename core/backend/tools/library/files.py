from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.utils import resolve_project_artifacts_dir
from utils.paths import secure_path_join, get_project_dir
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import UserSettings
import os
from pathlib import Path

class SaveArtifactArgs(BaseModel):
    file_path: str = Field(..., description="Relative path within the artifacts directory (e.g., 'plans/v1.md')")
    content: str = Field(..., description="Content to write to the file")
    overwrite: bool = Field(False, description="Whether to overwrite if the file already exists")

class SaveArtifactTool(BaseTool):
    name = "save_artifact"
    description = (
        "Save content to a file in the project's artifacts directory. "
        "ATTENTION: Overwriting is disabled by default (overwrite=False). If True, existing file content will be replaced. "
        "HOW TO USE: 'save_artifact(file_path=\"docs/analysis.md\", content=\"...\", overwrite=True\")'."
    )
    args_schema = SaveArtifactArgs

    async def run(self, file_path: str, content: str, overwrite: bool = False, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            root_dir = get_project_dir(user_id, project_id)
            # Standardize: If starts with artifacts/, treat as relative to root. Else, relative to artifacts/
            if file_path.startswith("artifacts/"):
                p = secure_path_join(root_dir, file_path)
            else:
                artifacts_dir = await resolve_project_artifacts_dir(user_id, project_id, session)
                p = secure_path_join(artifacts_dir, file_path)
            
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and not overwrite:
                return {"success": False, "message": f"File {file_path} already exists and overwrite is False"}
            p.write_text(content, encoding='utf-8')
            
            # Return path relative to project root
            rel_path = f"artifacts/{p.name}" if not file_path.startswith("artifacts/") else file_path
            # Better: get actual relative path to root
            actual_rel = p.relative_to(root_dir).as_posix()
            
            return {"success": True, "message": f"Saved artifact to {actual_rel}", "data": {"path": actual_rel}}
        except Exception as e:
            return {"success": False, "message": f"Failed to save artifact: {e}"}

class ReadReferenceArgs(BaseModel):
    file_path: str = Field(..., description="Relative path to the file to read")

class ReadReferenceTool(BaseTool):
    name = "read_reference"
    description = (
        "Read a file from the project's storage. It searches in project's root directory and subdirectories. "
        "HOW TO USE: 'read_reference(file_path=\"manual.pdf\")' or 'read_reference(file_path=\"artifacts/result.txt\")'."
    )
    args_schema = ReadReferenceArgs

    async def run(self, file_path: str, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            d = get_project_dir(user_id, project_id)
            p = secure_path_join(d, file_path)
            if not p.exists(): 
                # Try subdirs
                for sub in ["refs", "files", "artifacts"]:
                    try: 
                        p = secure_path_join(d / sub, file_path)
                        if p.exists(): break
                    except: pass
            
            if p.exists():
                text_content = p.read_text(encoding='utf-8', errors='ignore')
                
                # --- Gemini Upload Integration ---
                data = {}
                try:
                    from services.file_service import FileService
                    
                    # Fetch User Settings for API Key
                    result = await session.execute(select(UserSettings).filter(UserSettings.user_id == user_id))
                    user_settings = result.scalars().first()
                    api_key = user_settings.gemini_api_key if user_settings else None
                    
                    if api_key:
                        service = FileService(session, user_id, api_key)
                        gemini_info = await service.ensure_gemini_upload(
                            local_path=p,
                            filename=p.name,
                            project_id=project_id
                        )
                        if gemini_info:
                            data.update(gemini_info)
                except Exception as upload_err:
                    print(f"[ReadReferenceTool] Quietly failed gemini upload: {upload_err}")
                
                if data.get("gemini_file_uri"):
                    message = f"File '{p.name}' is available via Gemini File API for multimodal analysis. (Full text omitted to save context tokens)"
                else:
                    message = text_content
                
                return {
                    "success": True, 
                    "message": message,
                    "data": data
                }
            return {"success": False, "message": f"File {file_path} not found"}
        except Exception as e:
            return {"success": False, "message": f"Failed to read file: {e}"}

class ListFilesArgs(BaseModel):
    sub_dir: str = Field("refs", description="Subdirectory name to list (default 'refs')")

class ListFilesTool(BaseTool):
    name = "list_files"
    description = (
        "List all files within a project subdirectory (default is 'refs'). "
        "HOW TO USE: 'list_files()' to see references, or 'list_files(sub_dir=\"artifacts\")' to see generated files."
    )
    args_schema = ListFilesArgs

    async def run(self, sub_dir: str = "refs", **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            root_dir = get_project_dir(user_id, project_id)
            d = root_dir / sub_dir
            if not d.exists():
                return {"success": True, "message": f"Subdirectory {sub_dir} is empty or doesn't exist.", "data": {"files": []}}
            
            # Return paths relative to project root
            files = [f.relative_to(root_dir).as_posix() for f in d.rglob('*') if f.is_file()]
            return {"success": True, "message": "\n".join(files), "data": {"files": files}}
        except Exception as e:
            return {"success": False, "message": f"Failed to list files: {e}"}

class DeleteArtifactArgs(BaseModel):
    file_path: str = Field(..., description="Relative path to the artifact to delete")

class DeleteArtifactTool(BaseTool):
    name = "delete_artifact"
    description = (
        "Delete a file from the project's artifacts directory permanently. "
        "ATTENTION: This action is IRREVERSIBLE. "
        "HOW TO USE: 'delete_artifact(file_path=\"temp/junk.md\")'."
    )
    args_schema = DeleteArtifactArgs

    async def run(self, file_path: str, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            root_dir = get_project_dir(user_id, project_id)
            if file_path.startswith("artifacts/"):
                p = secure_path_join(root_dir, file_path)
            else:
                artifacts_dir = await resolve_project_artifacts_dir(user_id, project_id, session)
                p = secure_path_join(artifacts_dir, file_path)
                
            if p.exists():
                p.unlink()
                rel_path = p.relative_to(root_dir).as_posix()
                return {"success": True, "message": f"Deleted artifact {rel_path}"}
            return {"success": False, "message": f"Artifact {file_path} not found"}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete artifact: {e}"}

class ImportGitHubRepoArgs(BaseModel):
    repo_url: str = Field(..., description="The HTTPS URL of the GitHub repository to clone")
    branch: Optional[str] = Field(None, description="Specific branch to clone (e.g., 'main', 'develop')")
    token: Optional[str] = Field(None, description="GitHub Personal Access Token for private repos")
    force_update: Optional[bool] = Field(False, description="If True, pulls latest changes if repo exists")

class ImportGitHubRepoTool(BaseTool):
    name = "import_github_repo"
    description = (
        "Import (clone) a GitHub repository into the project's reference sources. "
        "The code will be stored in 'refs/sources/github/[owner]/[repo]'. "
        "Use depth=1 (shallow clone) by default for efficiency. "
        "HOW TO USE: 'import_github_repo(repo_url=\"https://github.com/pallets/flask\", force_update=True)'."
    )
    args_schema = ImportGitHubRepoArgs

    async def run(self, repo_url: str, branch: Optional[str] = None, token: Optional[str] = None, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        force_update: bool = kwargs.get("force_update", False)
        if not user_id: return {"success": False, "message": "Context error"}

        try:
            # 1. Clean URL and extract owner/repo
            # e.g. https://github.com/google/benchmark.git -> google/benchmark
            clean_url = repo_url.rstrip('/').replace('.git', '')
            parts = clean_url.split('/')
            if len(parts) < 2:
                return {"success": False, "message": f"Invalid repo URL: {repo_url}"}
            
            owner = parts[-2]
            repo_name = parts[-1]
            
            # 2. Build target path
            root_dir = get_project_dir(user_id, project_id)
            from pathlib import Path
            target_rel = Path("refs") / "sources" / "github" / owner / repo_name
            target_abs = root_dir / target_rel
            
            # 3. Handle existing repo
            import subprocess
            if target_abs.exists():
                if not force_update:
                    return {
                        "success": True, 
                        "message": f"Repository already exists at {target_rel.as_posix()}",
                        "data": {"path": target_rel.as_posix()}
                    }
                
                # Perform git pull
                print(f"[ImportGitHubRepoTool] Updating existing repo at {target_abs}")
                pull_cmd = ["git", "-C", str(target_abs), "pull"]
                process = subprocess.run(pull_cmd, capture_output=True, text=True)
                
                if process.returncode != 0:
                    return {"success": False, "message": f"Git pull failed: {process.stderr}"}
                
                return {
                    "success": True, 
                    "message": f"Successfully updated (pulled) {owner}/{repo_name} at {target_rel.as_posix()}",
                    "data": {"path": target_rel.as_posix()}
                }

            # 4. Construct clone command
            # Handle token for auth if provided
            if token:
                auth_url = repo_url.replace("https://", f"https://{token}@")
            else:
                auth_url = repo_url

            target_abs.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([auth_url, str(target_abs)])
            
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                return {"success": False, "message": f"Git clone failed: {process.stderr}"}
            
            return {
                "success": True, 
                "message": f"Successfully imported {owner}/{repo_name} to {target_rel.as_posix()}",
                "data": {"path": target_rel.as_posix()}
            }
            
        except Exception as e:
            return {"success": False, "message": f"Import failed: {str(e)}"}
