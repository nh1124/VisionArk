from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool, NoArgs
from tools.library.files import ReadReferenceTool, SaveArtifactTool

CURRENT_PLAN_FILE = "PLAN.md"

class ReadMDSectionArgs(BaseModel):
    file_path: str = Field(..., description="Path to the markdown file")
    section_title: str = Field(..., description="Title of the section to read")

class ReadMDSectionTool(BaseTool):
    name = "read_md_section"
    description = (
        "Extract a specific section from a markdown file based on its heading. "
        "HOW TO USE: 'read_md_section(file_path=\"manual.md\", section_title=\"Installation\")'."
    )
    args_schema = ReadMDSectionArgs

    async def run(self, file_path: str, section_title: str, **kwargs) -> Any:
        # Reuse ReadReferenceTool logic
        reader = ReadReferenceTool()
        res = await reader.run(file_path=file_path, **kwargs)
        if not res.get("success"): return res
        
        content = res.get("message", "")
        lines = content.splitlines()
        found = []
        capture = False
        section_title_lower = section_title.lower()
        
        for line in lines:
            if section_title_lower in line.lower() and line.startswith("#"):
                capture = True
                found.append(line)
            elif capture and line.startswith("#"):
                capture = False
                break # Stop at next heading
            elif capture:
                found.append(line)
        
        if not found:
            return {"success": False, "message": f"Section '{section_title}' not found in {file_path}"}
            
        return {"success": True, "message": "\n".join(found)}

class InitPlanArgs(BaseModel):
    goal: str = Field(..., description="The main goal of the plan")
    strategy: str = Field(..., description="The overarching strategy to achieve the goal")

class InitPlanTool(BaseTool):
    name = "init_plan"
    description = (
        "Initialize the project's primary plan file (PLAN.md). "
        "ATTENTION: This will OVERWRITE any existing PLAN.md. "
        "HOW TO USE: 'init_plan(goal=\"Build a spaceship\", strategy=\"Modular assembly\")'."
    )
    args_schema = InitPlanArgs

    async def run(self, goal: str, strategy: str, **kwargs) -> Any:
        saver = SaveArtifactTool()
        content = f"# Goal\n{goal}\n\n# Strategy\n{strategy}\n\n# Current Status\nInitializing...\n\n# Log\n- Plan created at {kwargs.get('timestamp', 'unknown')}"
        return await saver.run(file_path=CURRENT_PLAN_FILE, content=content, overwrite=True, **kwargs)

class UpdatePlanProgressArgs(BaseModel):
    summary: str = Field(..., description="Summary of the progress made")

class UpdatePlanProgressTool(BaseTool):
    name = "update_plan_progress"
    description = (
        "Add a progress update entry to the Log section of PLAN.md. "
        "HOW TO USE: 'update_plan_progress(summary=\"Phase 1 research complete.\")'."
    )
    args_schema = UpdatePlanProgressArgs

    async def run(self, summary: str, **kwargs) -> Any:
        # Simple append to end of file for now, or append to # Log section
        # For simplicity, we'll use a simplified version of update_artifact
        reader = ReadReferenceTool()
        res = await reader.run(file_path=CURRENT_PLAN_FILE, **kwargs)
        if not res.get("success"):
            # If PLAN.md doesn't exist, maybe they should init_plan first
            return {"success": False, "message": "PLAN.md not found. Use init_plan first."}
            
        content = res.get("message", "")
        new_content = content + f"\n- {summary}"
        
        saver = SaveArtifactTool()
        return await saver.run(file_path=CURRENT_PLAN_FILE, content=new_content, overwrite=True, **kwargs)

class GetCurrentStatusTool(BaseTool):
    name = "get_current_status"
    description = (
        "Retrieve the Current Status section from PLAN.md. "
        "HOW TO USE: 'get_current_status()'."
    )
    args_schema = NoArgs # No args

    async def run(self, **kwargs) -> Any:
        reader = ReadMDSectionTool()
        return await reader.run(file_path=CURRENT_PLAN_FILE, section_title="Current Status", **kwargs)

# Other MD tools can be added here as needed (QueryMDElements, UpsertMDTable, etc.)
