"""
Spoke Agent - Project-specific execution agent
Implements spoke-specific prompt loading and log paths
"""
from pathlib import Path
from typing import List
from agents.base_agent import BaseAgent
from utils.paths import get_spoke_dir
from models.message import AttachedFile


class SpokeAgent(BaseAgent):
    """Spoke agent with Spoke-specific logic"""
    
    def __init__(self, spoke_name: str):
        # Set spoke_name and spoke_dir BEFORE calling super().__init__()
        # because _load_history_from_log() needs them
        self.spoke_name = spoke_name
        self.spoke_dir = get_spoke_dir(spoke_name)
"""
Spoke Agent - Project-specific execution agent
Implements spoke-specific prompt loading and log paths
"""
from pathlib import Path
from typing import List
from agents.base_agent import BaseAgent
from utils.paths import get_spoke_dir
from models.message import AttachedFile


class SpokeAgent(BaseAgent):
    """Spoke agent with Spoke-specific logic"""
    
    def __init__(self, spoke_name: str):
        # Set spoke_name and spoke_dir BEFORE calling super().__init__()
        # because _load_history_from_log() needs them
        self.spoke_name = spoke_name
        self.spoke_dir = get_spoke_dir(spoke_name)
        super().__init__()
    
    def load_system_prompt(self) -> str:
        """
        Spoke-specific prompt loading
        Loads from spokes/{spoke_name}/system_prompt.md
        Prepends global system prompt for shared guidelines
        """
        from utils.paths import get_global_prompt
        
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

## Available Commands

**IMPORTANT: You can use these commands DIRECTLY in your responses. Just include the command.**

- `/report "message"` - Send progress updates to Hub
- `/archive` - Archive conversation and start fresh  
- `/kill` - Delete this spoke (use with caution)

## How to Send Messages to Hub

When you complete a milestone or have important updates, **just use the /report command directly**:

**Correct:**
```
I've completed the analysis. Here are the findings...

/report "Analysis phase completed. Key findings: X, Y, Z."
```

**Don't ask permission - just do it when appropriate!**

## Reference Files

Files in your reference library are automatically loaded in your context.
Use them to provide informed, accurate responses.

Work efficiently and communicate proactively with the Hub.
"""
        return global_prompt + separator + spoke_default
    
    def get_chat_log_path(self) -> Path:
        """Spoke-specific log path"""
        return self.spoke_dir / "chat.log"
