from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class CommandResult:
    """Standardized result for all system commands"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class BaseCommand(ABC):
    """
    Abstract base class for all system slash commands.
    Decoupled from AI Tool architecture for better performance and clarity.
    """
    name: str
    description: str
    usage: str # Human-readable usage example
    arg_names: List[str] = [] # List of expected positional argument names

    @abstractmethod
    async def run(self, args: List[str], **kwargs) -> CommandResult:
        """Execute the command logic with raw string arguments."""
        pass

    def parse_args(self, raw_args: List[str]) -> Dict[str, str]:
        """
        Helper to parse raw shlex-split arguments into a dictionary.
        Supports both positional and key=value formats.
        """
        parsed = {}
        for i, arg in enumerate(raw_args):
            if "=" in arg:
                k, v = arg.split("=", 1)
                parsed[k.strip()] = v.strip().strip('"').strip("'")
            elif i < len(self.arg_names):
                parsed[self.arg_names[i]] = arg.strip().strip('"').strip("'")
        return parsed
