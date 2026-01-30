from typing import Any, Optional, Dict, List
import json
import jsonschema
from pydantic import BaseModel, Field
from tools.base import BaseTool, NoArgs
from utils.paths import get_project_dir, secure_path_join
from pathlib import Path

class GetProjectRulesTool(BaseTool):
    name = "get_project_rules"
    description = (
        "Retrieve the project-specific governance and organization rules from .visionark/project_rules.json. "
        "Use this to understand naming conventions, directory structures, and metadata requirements."
    )
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        if not user_id or not project_id:
            return {"success": False, "message": "Context error"}

        try:
            from utils.paths import get_project_governance_dir, PROJECT_RULES_FILENAME
            governance_dir = get_project_governance_dir(user_id, project_id)
            rules_path = governance_dir / PROJECT_RULES_FILENAME
            
            if not rules_path.exists():
                return {
                    "success": True, 
                    "message": "No project-specific rules found. Using system defaults.",
                    "data": {"rules": None}
                }
            
            rules = json.loads(rules_path.read_text(encoding='utf-8'))
            return {
                "success": True, 
                "message": "Rules loaded successfully.",
                "data": {"rules": rules}
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to load project rules: {e}"}

class UpdateProjectRulesArgs(BaseModel):
    rules: Dict[str, Any] = Field(..., description="The complete rules object to save.")

class UpdateProjectRulesTool(BaseTool):
    name = "update_project_rules"
    description = (
        "Update the project-specific governance rules in .visionark/project_rules.json. "
        "The rules must follow the project rules schema (naming_convention, directory_structure, etc.)."
    )
    args_schema = UpdateProjectRulesArgs

    async def run(self, rules: Dict[str, Any], **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        if not user_id or not project_id:
            return {"success": False, "message": "Context error"}

        try:
            # 1. Validate against schema
            schema_path = Path(__file__).parent.parent.parent / "assets" / "schemas" / "project_rules_schema.json"
            if schema_path.exists():
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                jsonschema.validate(instance=rules, schema=schema)
            
            # 2. Save
            from utils.paths import get_project_governance_dir, PROJECT_RULES_FILENAME
            governance_dir = get_project_governance_dir(user_id, project_id)
            
            rules_path = governance_dir / PROJECT_RULES_FILENAME
            rules_path.write_text(json.dumps(rules, indent=2), encoding='utf-8')
            
            return {
                "success": True, 
                "message": "Project rules updated successfully.",
                "data": {"path": ".visionark/project_rules.json"}
            }
        except jsonschema.exceptions.ValidationError as ve:
            return {"success": False, "message": f"Rule validation failed: {ve.message}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to update project rules: {e}"}
