from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.utils import resolve_project_artifacts_dir, get_project_name_from_id
from utils.paths import secure_path_join, get_project_dir
from sqlalchemy.ext.asyncio import AsyncSession
import os

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
        session: AsyncSession = kwargs.get("session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            d = await resolve_project_artifacts_dir(user_id, project_id, session)
            p = secure_path_join(d, file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and not overwrite:
                return {"success": False, "message": f"File {file_path} already exists and overwrite is False"}
            p.write_text(content, encoding='utf-8')
            return {"success": True, "message": f"Saved artifact to {file_path}"}
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
        session: AsyncSession = kwargs.get("session")
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
                return {"success": True, "message": p.read_text(encoding='utf-8', errors='ignore')}
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
        session: AsyncSession = kwargs.get("session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            d = get_project_dir(user_id, project_id) / sub_dir
            if not d.exists():
                return {"success": True, "message": f"Subdirectory {sub_dir} is empty or doesn't exist.", "data": {"files": []}}
            files = [f.name for f in d.rglob('*') if f.is_file()]
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
        session: AsyncSession = kwargs.get("session")
        project_id: str = kwargs.get("project_id")
        if not user_id: return {"success": False, "message": "Context error"}
        
        try:
            d = await resolve_project_artifacts_dir(user_id, project_id, session)
            p = secure_path_join(d, file_path)
            if p.exists():
                p.unlink()
                return {"success": True, "message": f"Deleted artifact {file_path}"}
            return {"success": False, "message": f"Artifact {file_path} not found"}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete artifact: {e}"}
