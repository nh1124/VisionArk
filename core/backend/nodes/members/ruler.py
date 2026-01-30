from typing import Any, Dict, Optional, List
import json
import os
from pathlib import Path
from nodes.members.generic_member_node import GenericMemberNode
from utils.paths import get_project_dir

class RulerNode(GenericMemberNode):
    """
    The Organizer.
    Focus: File organization and Indexing.
    """
    role_name = "ruler"
    display_name = "Ruler"
    description = "Task management, scheduling, and file orchestration."
    default_tools = [
        "list_tasks",
        "create_task",
        "update_task",
        "complete_lbs_task",
        "get_lbs_schedule",
        "get_load_on_day",
        "save_artifact",
        "read_reference",
        "list_files",
        "get_project_rules",
        "update_project_rules"
    ]
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)
        self.project_rules = self._load_project_rules()

    def _load_project_rules(self) -> Dict[str, Any]:
        """Load project-specific rules from .visionark/project_rules.json"""
        project_id = self.context.get("project_id")
        user_id = self.user_id
        
        if not project_id or not user_id:
            return self._get_default_rules()
            
        try:
            project_dir = get_project_dir(user_id, project_id)
            rules_path = project_dir / ".visionark" / "project_rules.json"
            
            if rules_path.exists():
                with open(rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[RulerNode] Error loading project rules: {e}")
            
        return self._get_default_rules()

    def _get_default_rules(self) -> Dict[str, Any]:
        """Default fallback rules if no project-specific config exists."""
        return {
            "naming_convention": "snake_case",
            "required_metadata": ["title", "date", "status"],
            "directory_structure": {
                "docs/plans": "Implementation plans",
                "docs/reports": "Research reports",
                "docs/specs": "Technical specs"
            },
            "auto_archive_days": 30
        }

    async def on_exit(self, result: Any):
        pass
