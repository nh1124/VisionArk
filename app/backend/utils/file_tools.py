"""
File operation tools for Hub and Spoke agents
Implements BLUEPRINT.md Section 5.3.2 - Artifact Management Functions
"""
from pathlib import Path
from typing import Optional, List, Dict
from pydantic.v1 import BaseModel, Field, validator
from langchain_core.tools import tool
import os
import mimetypes
import google.generativeai as genai
from datetime import datetime, timedelta

# Import SPOKES_DIR from paths.py for correct absolute path
from utils.paths import SPOKES_DIR

# File upload cache: {file_path: (uri, upload_time, file_name)}
_file_upload_cache: Dict[str, tuple] = {}
CACHE_EXPIRY_HOURS = 24  # Cache files for 24 hours


def get_mime_type(file_path: Path) -> str:
    """Detect MIME type of a file"""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def is_text_file(mime_type: str) -> bool:
    """Check if MIME type represents a text file"""
    return (
        mime_type.startswith("text/") or
        mime_type in [
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-yaml"
        ]
    )


class SaveArtifactInput(BaseModel):
    """Input schema for save_artifact tool"""
    spoke_name: str = Field(..., description="Name of the spoke (project)")
    file_path: str = Field(..., description="Relative path within artifacts/ directory (e.g., 'draft.md' or 'code/script.py')")
    content: str = Field(..., description="Full content of the file to save")
    overwrite: bool = Field(False, description="Set True to overwrite existing file")
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Prevent path traversal attacks"""
        if '..' in v or v.startswith('/') or v.startswith('\\'):
            raise ValueError("Invalid file path: path traversal not allowed")
        return v


class ReadReferenceInput(BaseModel):
    """Input schema for read_reference tool"""
    spoke_name: str = Field(..., description="Name of the spoke (project)")
    file_path: str = Field(..., description="Relative path within refs/ directory")
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Prevent path traversal attacks"""
        if '..' in v or v.startswith('/') or v.startswith('\\'):
            raise ValueError("Invalid file path: path traversal not allowed")
        return v


class ListDirectoryInput(BaseModel):
    """Input schema for list_directory tool"""
    spoke_name: str = Field(..., description="Name of the spoke (project)")
    sub_dir: str = Field(..., description="Subdirectory to list: 'refs' or 'artifacts'")
    
    @validator('sub_dir', allow_reuse=True)
    def validate_sub_dir(cls, v):
        """Only allow refs or artifacts"""
        if v not in ['refs', 'artifacts']:
            raise ValueError("sub_dir must be either 'refs' or 'artifacts'")
        return v


@tool("save_artifact", args_schema=SaveArtifactInput)
def save_artifact(spoke_name: str, file_path: str, content: str, overwrite: bool = False) -> str:
    """
    Save code or document to the spoke's artifacts directory.
    
    Args:
        spoke_name: Name of the spoke (project)
        file_path: Relative path within artifacts/ (e.g., 'draft.md')
        content: Full text content to save
        overwrite: Whether to overwrite if file exists
        
    Returns:
        Success message with absolute path or error message
    """
    try:
        # Construct full path
        spoke_dir = SPOKES_DIR / spoke_name
        artifacts_dir = spoke_dir / "artifacts"
        full_path = artifacts_dir / file_path
        
        # Create spoke directory if it doesn't exist
        spoke_dir.mkdir(parents=True, exist_ok=True)
        
        # Create artifacts directory if needed
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Create parent directories for file if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file exists
        if full_path.exists() and not overwrite:
            return f"Error: File already exists at {full_path}. Set overwrite=True to replace it."
        
        # Write content
        full_path.write_text(content, encoding='utf-8')
        
        return f"✅ Successfully saved to {full_path.absolute()}"
        
    except Exception as e:
        return f"❌ Error saving artifact: {str(e)}"


@tool("read_reference", args_schema=ReadReferenceInput)
def read_reference(spoke_name: str, file_path: str) -> str:
    """
    Read a file from the spoke's refs directory.
    Supports text files, PDFs, and images via Gemini File API.
    
    Args:
        spoke_name: Name of the spoke (project)
        file_path: Relative path within refs/ directory
        
    Returns:
        File content (text) or multimodal reference object (PDF/images)
    """
    try:
        # Construct full path
        spoke_dir = SPOKES_DIR / spoke_name
        refs_dir = spoke_dir / "refs"
        full_path = refs_dir / file_path
        
        # Validate spoke exists
        if not spoke_dir.exists():
            return f"Error: Spoke '{spoke_name}' does not exist."
        
        # Validate file exists
        if not full_path.exists():
            return f"Error: File not found at {full_path}"
        
        # Validate it's within refs directory (security check)
        if not str(full_path.resolve()).startswith(str(refs_dir.resolve())):
            return "Error: Path traversal attempt detected"
        
        # Detect MIME type
        mime_type = get_mime_type(full_path)
        
        # Handle text files - read directly
        if is_text_file(mime_type):
            encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
            
            for encoding in encodings_to_try:
                try:
                    content = full_path.read_text(encoding=encoding)
                    return f"📄 Content of {file_path}:\n\n{content}"
                except UnicodeDecodeError:
                    continue
            
            return f"❌ Unable to read file as text: {file_path}"
        
        # Handle binary files (PDF, images) - upload to Gemini File API
        cache_key = str(full_path.resolve())
        
        # Check cache
        if cache_key in _file_upload_cache:
            uri, upload_time, cached_name = _file_upload_cache[cache_key]
            # Check if cache is still valid (within 24 hours)
            if datetime.now() - upload_time < timedelta(hours=CACHE_EXPIRY_HOURS):
                # Return multimodal reference
                return str({
                    "__type__": "multimodal_ref",
                    "mime_type": mime_type,
                    "file_uri": uri,
                    "file_name": file_path,
                    "cached": True
                })
        
        # Upload file to Gemini File API
        try:
            uploaded_file = genai.upload_file(path=str(full_path), mime_type=mime_type)
            
            # Cache the upload
            _file_upload_cache[cache_key] = (uploaded_file.uri, datetime.now(), file_path)
            
            # Return multimodal reference
            return str({
                "__type__": "multimodal_ref",
                "mime_type": mime_type,
                "file_uri": uploaded_file.uri,
                "file_name": file_path,
                "cached": False
            })
        
        except Exception as upload_error:
            return f"❌ Failed to upload {file_path} to Gemini API: {str(upload_error)}"
        
    except Exception as e:
        return f"❌ Error reading reference: {str(e)}"


@tool("list_directory", args_schema=ListDirectoryInput)
def list_directory(spoke_name: str, sub_dir: str) -> str:
    """
    List files in the spoke's refs or artifacts directory.
    
    Args:
        spoke_name: Name of the spoke (project)
        sub_dir: Either 'refs' or 'artifacts'
        
    Returns:
        Formatted list of files and directories
    """
    try:
        # Construct full path
        spoke_dir = SPOKES_DIR / spoke_name
        target_dir = spoke_dir / sub_dir
        
        # Create spoke directory if it doesn't exist
        if not spoke_dir.exists():
            return f"Error: Spoke '{spoke_name}' does not exist."
        
        # Create target directory if it doesn't exist
        if not target_dir.exists():
            return f"Error: Directory '{sub_dir}' does not exist."
        
        # List files
        files = []
        dirs = []
        
        for item in sorted(target_dir.rglob('*')):
            relative_path = item.relative_to(target_dir)
            if item.is_file():
                size = item.stat().st_size
                files.append(f"  📄 {relative_path} ({size} bytes)")
            elif item.is_dir():
                dirs.append(f"  📁 {relative_path}/")
        
        if not files and not dirs:
            return f"📁 {sub_dir}/ (empty)"
        
        result = [f"📁 {sub_dir}/"]
        result.extend(dirs)
        result.extend(files)
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ Error listing directory: {str(e)}"


# Export all tools
ARTIFACT_TOOLS = [save_artifact, read_reference, list_directory]
