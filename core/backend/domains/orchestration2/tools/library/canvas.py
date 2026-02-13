"""Canvas tool: update collaborative canvas content."""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import make_result


class UpdateCanvasTool:
    definition = ToolDef(
        name="update_canvas",
        description=(
            "Updates the collaborative canvas on the right side of the screen. "
            "Use for rich text, roadmaps, code snippets, or structured documents. "
            "HOW TO USE: update_canvas(content=\"# My Roadmap\", format=\"markdown\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "New content for the canvas"},
                "file_path": {"type": "string", "description": "Optional path to save as artifact"},
                "format": {"type": "string", "description": "Content format: markdown or code"},
            },
            "required": ["content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        content = call.arguments.get("content", "")
        file_path = call.arguments.get("file_path")
        fmt = call.arguments.get("format", "markdown")

        # Save as artifact if file_path provided
        if file_path:
            from domains.orchestration2.tools.library.files import SaveArtifactTool

            save_call = ToolCallRef(
                tool_name="save_artifact",
                call_id=call.call_id,
                arguments={"file_path": file_path, "content": content, "overwrite": True},
            )
            saver = SaveArtifactTool()
            res = await saver.invoke(save_call, ctx)
            if res.error:
                return res

        return make_result(call, f"Canvas updated with {fmt} content.")
