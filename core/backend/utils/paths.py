"""
Path utilities for the AI TaskManagement OS
User-scoped directories with path validation and traversal protection
"""
from pathlib import Path
import os
import re
from typing import Tuple


def get_project_root() -> Path:
    """
    Get the project root directory.
    
    In Docker: /app (backend code mounted here, data/ is a separate volume)
    Local dev: VisionArk/ (paths.py -> utils -> backend -> core -> VisionArk)
    
    The data/ subdirectory contains: spokes/, hub_data/, users/, global_assets/
    """
    current_file = Path(__file__).resolve()
    
    # In Docker, the codebase from core/backend/ is copied/mounted to /app/
    # paths.py is at /app/utils/paths.py
    # Project root is /app/, and data/ is mounted at /app/data/
    if current_file.parts and 'app' in current_file.parts:
        try:
            app_idx = current_file.parts.index('app')
            potential_root = Path(*current_file.parts[:app_idx+1])
            return potential_root
        except (ValueError, IndexError):
            pass

    # Local development: paths.py -> utils/ -> backend/ -> core/ -> VisionArk/
    return current_file.parent.parent.parent.parent


# Project paths - data directories are under data/ folder (mounted volume in Docker)
PROJECT_ROOT = get_project_root()
DATA_DIR = PROJECT_ROOT / "data"
USERS_DIR = DATA_DIR / "users"


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

def get_user_root_dir(user_id: str) -> Path:
    """
    Get user's root data directory: /data/users/{user_id}/
    """
    valid, error = validate_user_id(user_id)
    if not valid:
        raise ValueError(error)
    
    user_dir = secure_path_join(USERS_DIR, user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_spokes_dir(user_id: str) -> Path:
    """
    Get user's spokes directory: /data/users/{user_id}/spokes/
    Creates directory if it doesn't exist.
    """
    user_root = get_user_root_dir(user_id)
    user_spokes = user_root / "spokes"
    user_spokes.mkdir(parents=True, exist_ok=True)
    return user_spokes


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
    Get user's hub data directory: /data/users/{user_id}/hub_data/
    Creates directory if it doesn't exist.
    """
    user_root = get_user_root_dir(user_id)
    user_hub = user_root / "hub_data"
    user_hub.mkdir(parents=True, exist_ok=True)
    return user_hub


def get_user_global_assets_dir(user_id: str) -> Path:
    """
    Get user's global assets directory: /data/users/{user_id}/global_assets/
    Creates directory if it doesn't exist.
    """
    user_root = get_user_root_dir(user_id)
    user_assets = user_root / "global_assets"
    user_assets.mkdir(parents=True, exist_ok=True)
    return user_assets


def get_default_assets_dir() -> Path:
    """
    Get the internal assets directory (source of default prompts/templates).
    Depending on environment, this is either in app/backend/assets or /app/assets.
    """
    current_file = Path(__file__).resolve()
    # In Docker: /app/utils/paths.py -> /app/assets
    # Locally: .../app/backend/utils/paths.py -> .../app/backend/assets
    return current_file.parent.parent / "assets"


# ============================================================
# Legacy Functions (for backwards compatibility during migration)
# ============================================================

def get_hub_dir() -> Path:
    """
    Get shared hub data directory (legacy, no user scoping).
    DEPRECATED: Use get_user_hub_dir(user_id) instead.
    """
    HUB_DATA_DIR = DATA_DIR / "hub_data"
    HUB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return HUB_DATA_DIR


def get_global_prompt() -> str:
    """
    Load the global system prompt from internal assets.
    """
    default_assets = get_default_assets_dir()
    global_prompt_path = default_assets / "system_prompt_global.md"
    
    if global_prompt_path.exists():
        try:
            return global_prompt_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"⚠️ Failed to load global prompt from {global_prompt_path}: {e}")
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
