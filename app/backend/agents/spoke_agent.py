"""
Spoke Agent - Project-specific execution agent
Implements spoke-specific prompt loading and log paths
"""
from pathlib import Path
from typing import List
from agents.base_agent import BaseAgent
from utils.paths import get_spoke_dir, get_global_prompt
from models.message import AttachedFile
from utils.file_tools import ARTIFACT_TOOLS


class SpokeAgent(BaseAgent):
    """Spoke agent with Spoke-specific logic and file operation tools"""
    
    def __init__(self, spoke_name: str):
        # Set spoke_name and spoke_dir BEFORE calling super().__init__()
        # because _load_history_from_log() needs them
        self.spoke_name = spoke_name
        self.spoke_dir = get_spoke_dir(spoke_name)
        super().__init__()
        
        # Add file operation tools after base initialization
        self._setup_tools()
    
    def _setup_tools(self):
        """Setup and bind file operation tools to LLM"""
        from functools import partial
        
        # Create spoke-specific versions of tools
        spoke_tools = []
        for tool in ARTIFACT_TOOLS:
            # Create a partial function with spoke_name pre-filled
            # This way the AI doesn't need to specify spoke_name
            if tool.name == "save_artifact":
                from langchain_core.tools import tool as tool_decorator
                from pydantic.v1 import BaseModel, Field, validator
                
                # Schema WITHOUT spoke_name since it's pre-filled
                class SpokeArtifactInput(BaseModel):
                    file_path: str = Field(..., description="Relative path within artifacts/ (e.g., 'draft.md')")
                    content: str = Field(..., description="Full content of the file")
                    overwrite: bool = Field(False, description="Set True to overwrite existing file")
                    
                    @validator('file_path', allow_reuse=True)
                    def validate_file_path(cls, v):
                        if '..' in v or v.startswith('/'):
                            raise ValueError("Path traversal not allowed")
                        return v
                
                @tool_decorator("save_artifact", args_schema=SpokeArtifactInput)
                def save_artifact_bound(file_path: str, content: str, overwrite: bool = False):
                    """Save code or document to artifacts directory"""
                    from utils.file_tools import save_artifact
                    # Call original function with spoke_name filled in
                    return save_artifact.func(self.spoke_name, file_path, content, overwrite)
                
                spoke_tools.append(save_artifact_bound)
            
            elif tool.name == "read_reference":
                from langchain_core.tools import tool as tool_decorator
                from pydantic.v1 import BaseModel, Field, validator
                
                # Schema WITHOUT spoke_name
                class SpokeReferenceInput(BaseModel):
                    file_path: str = Field(..., description="Relative path within refs/")
                    
                    @validator('file_path', allow_reuse=True)
                    def validate_file_path(cls, v):
                        if '..' in v or v.startswith('/'):
                            raise ValueError("Path traversal not allowed")
                        return v
                
                @tool_decorator("read_reference", args_schema=SpokeReferenceInput)
                def read_reference_bound(file_path: str):
                    """Read a file from refs directory"""
                    from utils.file_tools import read_reference
                    # Call original function with spoke_name filled in
                    return read_reference.func(self.spoke_name, file_path)
                
                spoke_tools.append(read_reference_bound)
            
            elif tool.name == "list_directory":
                from langchain_core.tools import tool as tool_decorator
                from pydantic.v1 import BaseModel, Field, validator
                
                # Schema WITHOUT spoke_name
                class SpokeListInput(BaseModel):
                    sub_dir: str = Field(..., description="Either 'refs' or 'artifacts'")
                    
                    @validator('sub_dir', allow_reuse=True)
                    def validate_sub_dir(cls, v):
                        if v not in ['refs', 'artifacts']:
                            raise ValueError("Must be 'refs' or 'artifacts'")
                        return v
                
                @tool_decorator("list_directory", args_schema=SpokeListInput)
                def list_directory_bound(sub_dir: str):
                    """List files in refs or artifacts directory"""
                    from utils.file_tools import list_directory
                    # Call original function with spoke_name filled in
                    return list_directory.func(self.spoke_name, sub_dir)
                
                spoke_tools.append(list_directory_bound)
        
        # Set tools on the LLM provider
        if hasattr(self.llm, 'set_tools'):
            self.llm.set_tools(spoke_tools)
    
    def load_system_prompt(self) -> str:
        """
        Spoke-specific prompt loading
        Loads from spokes/{spoke_name}/system_prompt.md
        Prepends global system prompt for shared guidelines
        """
        # Start with global prompt
        global_prompt = get_global_prompt()
        separator = f"\n\n---\n\n# {self.spoke_name.replace('_', ' ').title()} (Role-Specific Instructions)\n\n" if global_prompt else ""
        
        # Load Spoke-specific prompt
        prompt_path = self.spoke_dir / "system_prompt.md"
        if prompt_path.exists():
            spoke_specific = prompt_path.read_text(encoding='utf-8')
            return global_prompt + separator + spoke_specific
        
        # Default Spoke prompt
        spoke_default = f"""# {self.spoke_name.replace('_', ' ').title()}

You are a specialized execution agent for the {self.spoke_name} project.
Focus on delivering high-quality work within this context.

## Available Tools

You have access to these tools via Function Calling:
- `save_artifact(file_path, content, overwrite=False)` - Save code/docs to artifacts/ 
- `read_reference(file_path)` - Read files from refs/
- `list_directory(sub_dir)` - List files in 'refs' or 'artifacts'

**Use these tools to CREATE FILES instead of just showing code!**

## Available Commands

**IMPORTANT: You can use these commands DIRECTLY in your responses.**

- `/report "message"` - Send progress updates to Hub
- `/archive` - Archive conversation and start fresh  
- `/kill` - Delete this spoke (use with caution)

## How to Send Messages to Hub

When you complete a milestone, **use /report directly**:

```
I've completed the analysis. Here are the findings...

/report "Analysis phase completed. Key findings: X, Y, Z."
```

## Reference Files

Files in your reference library are automatically loaded in your context.
Use them to provide informed, accurate responses.

Work efficiently and communicate proactively with the Hub.
"""
        return global_prompt + separator + spoke_default
    
    def get_chat_log_path(self) -> Path:
        """Spoke-specific log path"""
        return self.spoke_dir / "chat.log"
