"""
Path utilities for the AI TaskManagement OS
User-scoped directories with path validation and traversal protection
"""
from pathlib import Path
import os
import re
from typing import Tuple


def get_project_root() -> Path:
    """Get the project root directory (where BLUEPRINT.md is located)"""
    # From backend/utils/paths.py, go up to project root
    # paths.py -> utils/ -> backend/ -> app/ -> AI_TaskManagement_OS/
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent.parent
    return project_root


# Project paths
PROJECT_ROOT = get_project_root()
SPOKES_DIR = PROJECT_ROOT / "spokes"
HUB_DATA_DIR = PROJECT_ROOT / "hub_data"
GLOBAL_ASSETS_DIR = PROJECT_ROOT / "global_assets"


# ============================================================
# Name Validation
# ============================================================

# Valid characters: alphanumeric, underscore, hyphen, space
# Max length: 50 characters
VALID_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\- ]{1,50}$')


def validate_name(name: str, name_type: str = "name") -> Tuple[bool, str]:
    """
    Validate a name (spoke_name, etc.) for security.
    
    Returns:
        (is_valid, error_message)
    """
    if not name:
        return False, f"{name_type} cannot be empty"
    
    if not VALID_NAME_PATTERN.match(name):
        return False, f"{name_type} can only contain letters, numbers, underscores, hyphens, and spaces (max 50 chars)"
    
    # Block path traversal attempts
    if '..' in name or '/' in name or '\\' in name:
        return False, f"Invalid characters in {name_type}"
    
    # Block hidden files/folders
    if name.startswith('.'):
        return False, f"{name_type} cannot start with a dot"
    
    return True, ""


def validate_user_id(user_id: str) -> Tuple[bool, str]:
    """
    Validate user_id format (UUID expected).
    """
    if not user_id:
        return False, "user_id is required"
    
    # UUID format: 8-4-4-4-12 hex chars
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    
    if not uuid_pattern.match(user_id):
        return False, "Invalid user_id format"
    
    return True, ""


def secure_path_join(base_dir: Path, *parts: str) -> Path:
    """
    Safely join path components with traversal protection.
    
    Raises:
        ValueError: If path traversal is detected
    """
    # Resolve the final path
    target = base_dir
    for part in parts:
        target = target / part
    
    target = target.resolve()
    base_resolved = base_dir.resolve()
    
    # Ensure target is under base directory
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected: {target} is not under {base_resolved}")
    
    return target


# ============================================================
# User-Scoped Directory Functions
# ============================================================

def get_user_spokes_dir(user_id: str) -> Path:
    """
    Get user's spokes directory: /spokes/{user_id}/
    Creates directory if it doesn't exist.
    """
    valid, error = validate_user_id(user_id)
    if not valid:
        raise ValueError(error)
    
    user_dir = secure_path_join(SPOKES_DIR, user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_spoke_dir(user_id: str, spoke_name: str) -> Path:
    """
    Get user's spoke directory: /spokes/{user_id}/{spoke_name}/
    Does NOT auto-create the directory.
    
    Raises:
        ValueError: If spoke_name is invalid or path traversal detected
    """
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise ValueError(error)
    
    user_spokes = get_user_spokes_dir(user_id)
    return secure_path_join(user_spokes, spoke_name)


def get_user_hub_dir(user_id: str) -> Path:
    """
    Get user's hub data directory: /hub_data/{user_id}/
    Creates directory if it doesn't exist.
    """
    valid, error = validate_user_id(user_id)
    if not valid:
        raise ValueError(error)
    
    user_dir = secure_path_join(HUB_DATA_DIR, user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_global_assets_dir(user_id: str) -> Path:
    """
    Get user's global assets directory: /global_assets/{user_id}/
    Creates directory if it doesn't exist.
    """
    valid, error = validate_user_id(user_id)
    if not valid:
        raise ValueError(error)
    
    user_dir = secure_path_join(GLOBAL_ASSETS_DIR, user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


# ============================================================
# Legacy Functions (for backwards compatibility during migration)
# ============================================================

def get_hub_dir() -> Path:
    """
    Get shared hub data directory (legacy, no user scoping).
    DEPRECATED: Use get_user_hub_dir(user_id) instead.
    """
    HUB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return HUB_DATA_DIR


def get_global_prompt() -> str:
    """
    Load the global system prompt shared by all agents.
    Returns empty string if file doesn't exist.
    """
    global_prompt_path = GLOBAL_ASSETS_DIR / "system_prompt_global.md"
    
    if global_prompt_path.exists():
        try:
            return global_prompt_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"⚠️ Failed to load global prompt: {e}")
            return ""
    
    return ""


def get_user_global_prompt(user_id: str) -> str:
    """
    Load user's custom global prompt, falling back to shared prompt.
    """
    # Try user-specific prompt first
    try:
        user_assets = get_user_global_assets_dir(user_id)
        user_prompt_path = user_assets / "system_prompt_global.md"
        
        if user_prompt_path.exists():
            return user_prompt_path.read_text(encoding='utf-8')
    except Exception:
        pass
    
    # Fall back to shared global prompt
    return get_global_prompt()
