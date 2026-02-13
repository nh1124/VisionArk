"""AI generation tools: image generation, mermaid diagrams, code execution."""

from __future__ import annotations

import base64
import hashlib

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import (
    fail,
    get_gemini_client,
    get_project_id,
    get_user_id,
    make_result,
    resolve_artifacts_dir,
)
from shared.paths import get_project_dir


class GenerateImageTool:
    definition = ToolDef(
        name="generate_image",
        description=(
            "Generate an image from a text prompt and save to project artifacts. "
            "HOW TO USE: generate_image(prompt=\"A futuristic city\", filename=\"city.png\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image description"},
                "filename": {"type": "string", "description": "Optional output filename"},
            },
            "required": ["prompt"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        prompt = call.arguments.get("prompt", "")
        filename = call.arguments.get("filename")

        try:
            client = await get_gemini_client(ctx)
            response = client.models.generate_content(
                model="gemini-3-pro-image-preview",
                contents=[prompt],
            )

            image_data = None
            for part in response.parts:
                if part.inline_data is not None:
                    image_data = part.inline_data.data
                    break

            if not image_data:
                return fail(call, "No image generated.")

            if not filename:
                h = hashlib.md5(prompt.encode()).hexdigest()[:8]
                filename = f"generated_{h}.png"
            if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
                filename += ".png"

            artifacts_dir = await resolve_artifacts_dir(ctx)
            file_path = artifacts_dir / filename

            image_bytes = base64.b64decode(image_data) if isinstance(image_data, str) else image_data
            file_path.write_bytes(image_bytes)

            root_dir = get_project_dir(get_user_id(ctx), get_project_id(ctx))
            rel_path = file_path.relative_to(root_dir).as_posix()

            return make_result(call, f"Generated and saved image: {rel_path}")
        except Exception as e:
            return fail(call, f"Image generation failed: {e}")


class MermaidVisualizerTool:
    definition = ToolDef(
        name="generate_mermaid_visualizer",
        description=(
            "Create a Mermaid diagram and save as markdown artifact. "
            "HOW TO USE: generate_mermaid_visualizer(diagram_type=\"flowchart\", data=\"A --> B\", title=\"Flow\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Mermaid diagram data"},
                "diagram_type": {"type": "string", "description": "Diagram type: gantt, flowchart, sequence, class"},
                "title": {"type": "string", "description": "Title for the artifact"},
            },
            "required": ["data"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        data = call.arguments.get("data", "")
        diagram_type = call.arguments.get("diagram_type", "flowchart")
        title = call.arguments.get("title", "Diagram")

        content = f"```mermaid\n{diagram_type}\n{data}\n```"

        # Delegate to SaveArtifactTool
        from domains.orchestration2.tools.library.files import SaveArtifactTool

        save_call = ToolCallRef(
            tool_name="save_artifact",
            call_id=call.call_id,
            arguments={"file_path": f"visuals/{title}.md", "content": content, "overwrite": True},
        )
        saver = SaveArtifactTool()
        return await saver.invoke(save_call, ctx)


class ExecuteCodeTool:
    definition = ToolDef(
        name="execute_code",
        description=(
            "Execute Python code or perform complex calculations via Gemini. "
            "HOW TO USE: execute_code(prompt=\"Calculate standard deviation of [1, 5, 10, 20]\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Code or logic to execute"},
            },
            "required": ["prompt"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        prompt = call.arguments.get("prompt", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(code_execution=types.ToolCodeExecution())]
                ),
            )
            return make_result(call, resp.text or "No output from code execution")
        except Exception as e:
            return fail(call, f"Code execution failed: {e}")
