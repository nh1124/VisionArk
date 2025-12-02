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
        super().__init__()
        self.spoke_name = spoke_name
        self.spoke_dir = get_spoke_dir(spoke_name)
    
    def load_system_prompt(self) -> str:
        """
        Spoke-specific prompt loading
        Loads from spokes/{spoke_name}/system_prompt.md
        """
        prompt_path = self.spoke_dir / "system_prompt.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        
        # Default Spoke prompt
        return f"""# {self.spoke_name.replace('_', ' ').title()}

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
    
    def get_chat_log_path(self) -> Path:
        """Spoke-specific log path"""
        return self.spoke_dir / "chat.log"
