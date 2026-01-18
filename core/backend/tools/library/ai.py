from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.utils import get_gemini_client, resolve_project_artifacts_dir
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import hashlib

class GenerateImageArgs(BaseModel):
    prompt: str = Field(..., description="The description of the image to generate")
    filename: Optional[str] = Field(None, description="Optional filename for the generated image")

class GenerateImageTool(BaseTool):
    name = "generate_image"
    description = (
        "Generate an image from a text prompt and save it to the project artifacts. "
        "ATTENTION: Image generation can be slow. Ensure the prompt is descriptive for high quality. "
        "HOW TO USE: 'generate_image(prompt=\"A futuristic city in neon lights\", filename=\"city.png\")'."
    )
    args_schema = GenerateImageArgs

    async def run(self, prompt: str, filename: Optional[str] = None, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("session")
        project_name: str = kwargs.get("project_name") or 'hub'
        if not user_id or not session: return {"success": False, "message": "Context error"}
        
        try:
            client = await get_gemini_client(user_id, session)
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
                return {"success": False, "message": "No image generated."}
            
            if not filename:
                hash_suffix = hashlib.md5(prompt.encode()).hexdigest()[:8]
                filename = f"generated_{hash_suffix}.png"
            
            if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                filename += '.png'
            
            artifacts_dir = await resolve_project_artifacts_dir(user_id, project_name, session)
            file_path = artifacts_dir / filename
            
            if isinstance(image_data, str):
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data
                
            file_path.write_bytes(image_bytes)
            
            return {
                "success": True, 
                "message": f"✅ Generated and saved image: `{filename}`",
                "data": {"filename": filename, "embed_path": f"artifacts/{filename}"}
            }
        except Exception as e:
            return {"success": False, "message": f"Image generation failed: {e}"}

class MermaidVisualizerArgs(BaseModel):
    data: str = Field(..., description="The data or structure to visualize")
    diagram_type: str = Field("flowchart", description="The type of Mermaid diagram: gantt, flowchart, sequence, class")
    title: str = Field("Diagram", description="Title for the visualization artifact")

class MermaidVisualizerTool(BaseTool):
    name = "generate_mermaid_visualizer"
    description = (
        "Create a Mermaid diagram (flowchart, sequence, etc.) and save it as a markdown artifact. "
        "HOW TO USE: 'generate_mermaid_visualizer(diagram_type=\"flowchart\", data=\"A --> B\", title=\"LogicFlow\")'."
    )
    args_schema = MermaidVisualizerArgs

    async def run(self, data: str, diagram_type: str = "flowchart", title: str = "Diagram", **kwargs) -> Any:
        from tools.library.files import SaveArtifactTool
        saver = SaveArtifactTool()
        content = f"```mermaid\n{diagram_type}\n{data}\n```"
        return await saver.run(file_path=f"visuals/{title}.md", content=content, overwrite=True, **kwargs)

class ExecuteCodeArgs(BaseModel):
    prompt: str = Field(..., description="The code or logic to execute via Gemini")

class ExecuteCodeTool(BaseTool):
    name = "execute_code"
    description = (
        "Execute Python code snippets or perform complex mathematical calculations. "
        "ATTENTION: Use this for algorithmic tasks where reasoning alone might fail. "
        "HOW TO USE: 'execute_code(prompt=\"Calculate the standard deviation of [1, 5, 10, 20]\")'."
    )
    args_schema = ExecuteCodeArgs

    async def run(self, prompt: str, **kwargs) -> Any:
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("session")
        if not user_id or not session: return {"success": False, "message": "Context error"}
        
        try:
            from google.genai import types
            client = await get_gemini_client(user_id, session)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=prompt, 
                config=types.GenerateContentConfig(tools=[types.Tool(code_execution=types.ToolCodeExecution())])
            )
            return {"success": True, "message": resp.text}
        except Exception as e:
            return {"success": False, "message": f"Code execution failed: {e}"}
