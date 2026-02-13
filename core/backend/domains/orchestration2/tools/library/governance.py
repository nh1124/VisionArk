"""Governance tools: project rules management."""

from __future__ import annotations

import json

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_project_id, get_user_id, make_result


class GetProjectRulesTool:
    definition = ToolDef(
        name="get_project_rules",
        description=(
            "Retrieve project governance rules from .visionark/project_rules.json. "
            "Use to understand naming conventions, directory structures, and metadata requirements."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            from shared.paths import get_project_governance_dir, PROJECT_RULES_FILENAME

            governance_dir = get_project_governance_dir(user_id, project_id)
            rules_path = governance_dir / PROJECT_RULES_FILENAME

            if not rules_path.exists():
                return make_result(call, "No project-specific rules found. Using system defaults.")

            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            return make_result(call, json.dumps(rules, indent=2))
        except Exception as e:
            return fail(call, f"Failed to load project rules: {e}")


class UpdateProjectRulesTool:
    definition = ToolDef(
        name="update_project_rules",
        description=(
            "Update project governance rules in .visionark/project_rules.json. "
            "Rules must follow the project rules schema."
        ),
        parameters={
            "type": "object",
            "properties": {
                "rules": {"type": "object", "description": "The complete rules object to save"},
            },
            "required": ["rules"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        rules = call.arguments.get("rules", {})
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            from pathlib import Path

            import jsonschema

            schema_path = Path(__file__).parent.parent.parent / "assets" / "schemas" / "project_rules_schema.json"
            if schema_path.exists():
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                jsonschema.validate(instance=rules, schema=schema)

            from shared.paths import get_project_governance_dir, PROJECT_RULES_FILENAME

            governance_dir = get_project_governance_dir(user_id, project_id)
            rules_path = governance_dir / PROJECT_RULES_FILENAME
            rules_path.write_text(json.dumps(rules, indent=2), encoding="utf-8")

            return make_result(call, "Project rules updated successfully.")
        except Exception as e:
            return fail(call, f"Failed to update project rules: {e}")
