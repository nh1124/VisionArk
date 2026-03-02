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

# Governance constants
GOVERNANCE_DIR_NAME = ".visionark"
PROJECT_RULES_FILENAME = "project_rules.json"
PLAN_POLICY_FILENAME = "plan_policy.json"
PLAN_FILENAME = "PLAN.md"
PLAN_TEMPLATE_FILENAME = "PLAN_TEMPLATE.md"
PLAN_INJECTION_FILENAME = "project_plan.md"


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

def validate_project_id(project_id: str) -> Tuple[bool, str]:
    """
    Validate project_id format (UUID or special 'hub' expected).
    """
    if not project_id:
        return False, "project_id is required"
    
    # UUID format: 8-4-4-4-12 hex chars
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    
    if not uuid_pattern.match(project_id):
        return False, "Invalid project_id format"
    
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

# ============================================================
# Project Name & Cache Utilities
# ============================================================

# Global cache: (user_id, project_id) -> safe_folder_name
_PROJECT_NAME_CACHE = {}

def update_project_name_cache(user_id: str, project_id: str, display_name: str):
    """
    Explicitly update the folder name cache.
    Called when a project is created or renamed.
    """
    safe_name = "".join(c for c in display_name if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_name = safe_name.replace(' ', '_')
    _PROJECT_NAME_CACHE[(user_id, project_id)] = safe_name

def get_project_name(user_id: str, project_id: str) -> str:
    """
    Get the folder name for a project. 
    First checks cache, then falls back to synchronous DB query.
    """
    cache_key = (user_id, project_id)
    if cache_key in _PROJECT_NAME_CACHE:
        return _PROJECT_NAME_CACHE[cache_key]
    
    # Synchronous DB query fallback
    try:
        from shared.database import Project, get_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        
        engine = get_engine()
        Session = sessionmaker(bind=engine)
        with Session() as session:
            result = session.execute(
                select(Project.name).filter(
                    Project.user_id == user_id,
                    Project.id == project_id
                )
            ).scalar_one_or_none()
            
            if result:
                update_project_name_cache(user_id, project_id, result)
                return _PROJECT_NAME_CACHE[cache_key]
    except Exception as e:
        # Fallback to project_id if DB query fails
        print(f"Warning: Failed to fetch project name for {project_id}: {e}")
        
    return project_id

# ============================================================
# Project Directory Functions (V3 Unified Architecture)
# ============================================================

def get_user_projects_dir(user_id: str) -> Path:
    """
    Get user's projects directory: /data/users/{user_id}/projects/
    Creates directory if it doesn't exist.
    """
    user_root = get_user_root_dir(user_id)
    projects_dir = user_root / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir


def get_project_dir(user_id: str, project_id: str) -> Path:
    """
    Get user's project directory: /data/users/{user_id}/projects/{folder_name}/
    Creates directory if it doesn't exist.
    
    Args:
        user_id: User UUID
        project_id: Project UUID or identifier
    
    Returns:
        Path to the project directory
    
    Raises:
        ValueError: If user_id/project_id is invalid or path traversal detected
    """
    valid, error = validate_project_id(project_id)
    if not valid:
        raise ValueError(error)

    projects_dir = get_user_projects_dir(user_id)

    # 1. Try by display name (cached/DB-fetched)
    folder_name = get_project_name(user_id, project_id)
    project_path = secure_path_join(projects_dir, folder_name)
    
    if project_path.exists():
        return project_path
    
    # 2. Fallback: Try by ID directly if folder name differs
    if folder_name != project_id:
        id_path = secure_path_join(projects_dir, project_id)
        if id_path.exists():
            return id_path

    # 3. Create if not exists (defaulting to display name)
    project_path.mkdir(parents=True, exist_ok=True)
    return project_path


def get_project_governance_dir(user_id: str, project_id: str) -> Path:
    """
    Get the hidden governance directory for a project: project_dir/.visionark/
    """
    project_dir = get_project_dir(user_id, project_id)
    governance_dir = project_dir / GOVERNANCE_DIR_NAME
    governance_dir.mkdir(parents=True, exist_ok=True)
    return governance_dir


def get_user_global_assets_dir(user_id: str) -> Path:
    """
    Get user's global assets directory: /data/users/{user_id}/global_assets/
    Creates directory if it doesn't exist.
    """
    user_root = get_user_root_dir(user_id)
    user_assets = user_root / "global_assets"
    user_assets.mkdir(parents=True, exist_ok=True)
    return user_assets


def get_user_custom_tools_dir(user_id: str, tool_name: str | None = None) -> Path:
    """Get user's custom tools directory: /data/users/{user_id}/custom_tools/

    If tool_name is given, returns the specific tool sub-directory and creates it.
    The tool's code lives at: <returned_path>/__init__.py
    """
    user_root = get_user_root_dir(user_id)
    custom_tools_dir = user_root / "custom_tools"
    custom_tools_dir.mkdir(parents=True, exist_ok=True)

    if tool_name is None:
        return custom_tools_dir

    # tool_name must be a safe identifier (no path traversal)
    tool_dir = secure_path_join(custom_tools_dir, tool_name)
    tool_dir.mkdir(parents=True, exist_ok=True)
    return tool_dir


def get_workspace_dir(user_id: str) -> Path:
    """data/users/{user_id}/workspace/ – user's shared workspace root"""
    user_root = get_user_root_dir(user_id)
    workspace_dir = user_root / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def get_workspace_item_path(user_id: str, item_path: str) -> Path:
    """Resolve and validate a workspace item's filesystem path.
    item_path is the logical path, e.g. 'profile/about.md'
    """
    workspace_dir = get_workspace_dir(user_id)
    return secure_path_join(workspace_dir, item_path)


def get_default_assets_dir() -> Path:
    """
    Get the internal assets directory (source of default prompts/templates).
    Depending on environment, this is either in app/backend/assets or /app/assets.
    """
    current_file = Path(__file__).resolve()
    # In Docker: /app/utils/paths.py -> /app/assets (Mounted top-level assets directory)
    # Locally: .../app/backend/utils/paths.py -> .../VisionArk/assets
    if current_file.parts and 'app' in current_file.parts:
        return Path("/app/assets")
    
    return get_project_root() / "assets"


def get_prompts_dir() -> Path:
    """
    Get the prompts directory: assets/prompts/
    """
    return get_default_assets_dir() / "prompts"


def get_plan_path(user_id: str, project_id: str) -> Path:
    """
    Get the relative path to the project's PLAN.md within artifacts.
    """
    return get_project_dir(user_id, project_id) / "artifacts" / PLAN_FILENAME


def get_plan_template_path() -> Path:
    """
    Get the path to the PLAN.md template in assets.
    """
    return get_default_assets_dir() / "templates" / PLAN_TEMPLATE_FILENAME


def get_plan_injection_prompt_path() -> Path:
    """
    Get the path to the plan injection prompt component.
    """
    return get_prompts_dir() / "components" / PLAN_INJECTION_FILENAME


def get_plan_policy_template_path() -> Path:
    """
    Get the path to the default plan policy template in assets.
    """
    return get_default_assets_dir() / "templates" / PLAN_POLICY_FILENAME


def get_project_plan_policy_path(user_id: str, project_id: str) -> Path:
    """
    Get the path to the project-specific plan policy in .visionark/
    """
    return get_project_governance_dir(user_id, project_id) / PLAN_POLICY_FILENAME


# ============================================================
# Prompt Functions
# ============================================================


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
