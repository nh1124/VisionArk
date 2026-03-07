from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from domains.orchestration2.engine.models.execution import ExecutionContext
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.execution import ToolResult as OrchToolResult
from domains.orchestration2.tools.base import make_result, fail as orch_fail
from va_sdk import BaseTool, IntegrationContext, ToolResult as SDKToolResult

logger = logging.getLogger(__name__)

class IntegrationToolAdapter:
    """Adapts a va_sdk.BaseTool to the orchestration2 tool interface.
    
    Acts as a bridge between the new orchestration engine and the existing
    integration tools living in `integrations/`.
    """

    def __init__(self, sdk_tool: BaseTool) -> None:
        self.sdk_tool = sdk_tool
        self.definition = self._build_definition()

    def _build_definition(self) -> ToolDef:
        """Convert va_sdk tool metadata to orchestration2 ToolDef."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        if self.sdk_tool.args_schema and issubclass(self.sdk_tool.args_schema, BaseModel):
            try:
                # Generate JSON schema from Pydantic model
                model_schema = self.sdk_tool.args_schema.model_json_schema()
                schema = {
                    "type": "object",
                    "properties": model_schema.get("properties", {}),
                    "required": model_schema.get("required", []),
                }
            except Exception as e:
                logger.warning(
                    "Failed to generate schema for tool '%s': %s. Falling back to empty schema.",
                    self.sdk_tool.name, e
                )

        return ToolDef(
            name=self.sdk_tool.name,
            description=self.sdk_tool.description,
            parameters=schema,
        )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> OrchToolResult:
        """Execute the wrapped SDK tool."""
        # 1. Build IntegrationContext
        try:
            integration_ctx = IntegrationContext(
                user_id=ctx.metadata["user_id"],
                db=ctx.metadata["db_session"],
                project_id=ctx.metadata.get("project_id"),
                session_id=ctx.metadata.get("session_id"),
                api_key=ctx.metadata.get("api_key"),
                user_settings=ctx.metadata.get("user_settings", {}),
                # Merge ctx.metadata and inject run_id so CLI tools can create RunExecutions.
                metadata={**ctx.metadata, "run_id": ctx.run_id},
            )
        except KeyError as e:
            return orch_fail(call, f"Missing required context for integration tool: {e}")

        # 2. Invoke tool
        try:
            # va_sdk tools expect arguments as kwargs or a Pydantic model.
            # BaseTool.run signature is run(self, ctx: IntegrationContext, **kwargs)
            
            # If args_schema is present, validate/parse args (optional, but good practice)
            tool_args = call.arguments or {}
            
            # Pass context as keyword argument 'ctx' to support flexible signatures
            # (e.g. run(self, arg1, ctx=None) vs run(self, ctx, **kwargs))
            result: Any = await self.sdk_tool.run(ctx=integration_ctx, **tool_args)

            # 3. Handle result
            if isinstance(result, SDKToolResult):
                if result.is_success:
                    return make_result(call, result.content)
                else:
                    return orch_fail(call, result.content or "Tool execution failed")
            
            # Fallback for non-SDKToolResult returns (str, dict, etc.)
            return make_result(call, str(result))

        except Exception as e:
            logger.exception("Integration tool '%s' execution failed", self.sdk_tool.name)
            return orch_fail(call, f"Tool execution error: {str(e)}")
