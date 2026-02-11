from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from domains.orchestration.tools.base import BaseTool, NoArgs
from domains.orchestration.tools.library.files import ReadReferenceTool, SaveArtifactTool

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
        from domains.orchestration.tools.base import ToolResult
        # Reuse ReadReferenceTool logic
        reader = ReadReferenceTool()
        res = await reader.run(file_path=file_path, **kwargs)
        if not res.is_success: return res
        
        content = res.content
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
            return ToolResult(content=f"Section '{section_title}' not found in {file_path}", is_success=False)
            
        return ToolResult(content="\n".join(found))

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
        from domains.orchestration.tools.base import ToolResult
        from shared.paths import get_plan_template_path
        
        template_path = get_plan_template_path()
        content = ""
        
        if template_path.exists():
            try:
                template = template_path.read_text(encoding='utf-8')
                content = template.replace("[メインゴールの記述]", goal).replace("[戦略・アプローチの記述]", strategy)
            except Exception as e:
                print(f"[InitPlanTool] Warning: Failed to load template: {e}")
        
        if not content:
            # Fallback to hardcoded default if template fails or doesn't exist
            content = f"# Goal\n{goal}\n\n# Strategy\n{strategy}\n\n# Current Status\nInitializing...\n\n# Log\n- Plan created at {kwargs.get('timestamp', 'unknown')}"
            
        saver = SaveArtifactTool()
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
        from domains.orchestration.tools.base import ToolResult
        # Simple append to end of file for now, or append to # Log section
        reader = ReadReferenceTool()
        res = await reader.run(file_path=CURRENT_PLAN_FILE, **kwargs)
        if not res.is_success:
            return ToolResult(content="PLAN.md not found. Use init_plan first.", is_success=False)
            
        content = res.content
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
        from domains.orchestration.tools.base import ToolResult
        reader = ReadMDSectionTool()
        return await reader.run(file_path=CURRENT_PLAN_FILE, section_title="Current Status", **kwargs)

class UpdateMDSectionArgs(BaseModel):
    file_path: str = Field(..., description="Path to the markdown file")
    section_title: str = Field(..., description="Title of the section to update")
    content: str = Field(..., description="The new content for this section")
    mode: str = Field("overwrite", description="Update mode: 'overwrite' (default) or 'append'")

class UpdateMDSectionTool(BaseTool):
    name = "update_md_section"
    description = (
        "Updates or appends content to a specific section in a markdown file. "
        "The section is identified by its # Heading. "
        "HOW TO USE: 'update_md_section(file_path=\"PLAN.md\", section_title=\"Current Status\", content=\"Working on UI.\", mode=\"overwrite\")'."
    )
    args_schema = UpdateMDSectionArgs

    async def run(self, file_path: str, section_title: str, content: str, mode: str = "overwrite", **kwargs) -> Any:
        from domains.orchestration.tools.base import ToolResult
        reader = ReadReferenceTool()
        res = await reader.run(file_path=file_path, **kwargs)
        
        full_content = ""
        if res.is_success:
            full_content = res.content
        
        lines = full_content.splitlines() if full_content else []
        new_lines = []
        section_found = False
        in_section = False
        section_title_lower = section_title.lower()
        
        # 1. Parse and reconstruct content
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("#") and section_title_lower in line.lower():
                section_found = True
                in_section = True
                new_lines.append(line) # Keep the heading
                
                if mode == "append":
                    # We'll skip existing content and append at the end of section
                    pass 
                else:
                    # Overwrite: we skip lines until next heading
                    i += 1
                    while i < len(lines) and not lines[i].startswith("#"):
                        i += 1
                    
                    # Insert new content
                    new_lines.append(content)
                    in_section = False # Finished overwriting
                    continue # Re-evaluate current line (which is next heading or end)
            
            elif in_section and line.startswith("#"):
                # Hit next section
                if mode == "append":
                    new_lines.append(content)
                in_section = False
                new_lines.append(line)
            else:
                if not in_section:
                    new_lines.append(line)
            i += 1
            
        # 2. Append if section finished at EOF in append mode
        if in_section and mode == "append":
            new_lines.append(content)
            
        # 3. Create section if not found
        if not section_found:
            if new_lines and not new_lines[-1].strip() == "":
                new_lines.append("")
            new_lines.append(f"# {section_title}")
            new_lines.append(content)
            
        final_content = "\n".join(new_lines)
        
        saver = SaveArtifactTool()
        return await saver.run(file_path=file_path, content=final_content, overwrite=True, **kwargs)

# Other MD tools can be added here as needed (QueryMDElements, UpsertMDTable, etc.)
