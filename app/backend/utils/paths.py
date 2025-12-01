"""
Path utilities for the AI TaskManagement OS
Ensures all paths are relative to project root
"""
from pathlib import Path
import os


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


def get_spoke_dir(spoke_name: str) -> Path:
    """Get spoke directory path (does NOT auto-create)"""
    return SPOKES_DIR / spoke_name


def get_hub_dir() -> Path:
    """Get hub data directory path"""
    HUB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return HUB_DATA_DIR
