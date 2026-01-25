from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.library.files import SaveArtifactTool

class UpdateCanvasArgs(BaseModel):
    content: str = Field(..., description="The new content for the canvas")
    file_path: Optional[str] = Field(None, description="Optional path to a file representing this canvas content (e.g. 'roadmap.md')")
    format: str = Field("markdown", description="The format of the content: 'markdown' or 'code'")

class UpdateCanvasTool(BaseTool):
    name = "update_canvas"
    description = (
        "Updates the content of the collaborative canvas on the right side of the screen. "
        "Use this to provide rich text, roadmaps, code snippets, or structured documents that the user can edit. "
        "HOW TO USE: 'update_canvas(content=\"# My Roadmap\\n- Step 1\", format=\"markdown\")'."
    )
    args_schema = UpdateCanvasArgs

    async def run(self, content: str, file_path: Optional[str] = None, format: str = "markdown", **kwargs) -> Any:
        # 1. Save as an artifact if file_path is provided
        if file_path:
            saver = SaveArtifactTool()
            artifact_res = await saver.run(file_path=file_path, content=content, overwrite=True, **kwargs)
            if not artifact_res.get("success"):
                return artifact_res
            # Update file_path to the official relative path (e.g. artifacts/roadmap.md)
            file_path = artifact_res.get("data", {}).get("path", file_path)

        # 2. Return the result which will be captured in tool_calls for the frontend
        # The frontend will look for 'update_canvas' in tool_calls and update the state.
        return {
            "success": True, 
            "content": content, 
            "format": format, 
            "file_path": file_path,
            "message": f"Canvas updated with {format} content."
        }
