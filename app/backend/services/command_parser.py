"""
Command Parser
Handles slash commands in chat input (/check_inbox, /archive, etc.)
"""
import re
import shlex
from typing import Optional, Dict, Callable, Any, List
from dataclasses import dataclass


@dataclass
class Command:
    """Parsed command structure"""
    name: str
    args: List[str]
    raw_input: str


@dataclass
class CommandResult:
    """Command execution result"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class CommandRegistry:
    """Registry of available commands"""
    
    def __init__(self):
        self._commands: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}
        self._contexts: Dict[str, List[str]] = {}  # hub, spoke, both
    
    def register(
        self,
        name: str,
        handler: Callable,
        description: str,
        context: List[str] = None
    ):
        """
        Register a command handler
        
        Args:
            name: Command name (without /)
            handler: Function to execute (async or sync)
            description: Help text
            context: Which contexts this command is available in (hub, spoke, both)
        """
        if context is None:
            context = ["both"]
        
        self._commands[name] = handler
        self._descriptions[name] = description
        self._contexts[name] = context
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """Get command handler by name"""
        return self._commands.get(name)
    
    def list_commands(self, context: str = None) -> Dict[str, str]:
        """
        List available commands
        
        Args:
            context: Filter by context (hub, spoke)
        
        Returns:
            Dict of command_name: description
        """
        if context is None:
            return self._descriptions
        
        return {
            name: desc
            for name, desc in self._descriptions.items()
            if "both" in self._contexts[name] or context in self._contexts[name]
        }


# Global registry instance
_registry = CommandRegistry()


def register_command(name: str, description: str, context: List[str] = None):
    """
    Decorator to register command handlers
    
    Example:
        @register_command("archive", "Archive and rotate context", ["spoke", "hub"])
        def handle_archive(args: List[str]) -> CommandResult:
            # Implementation
            return CommandResult(success=True, message="Archived")
    """
    def decorator(func: Callable):
        _registry.register(name, func, description, context)
        return func
    return decorator


def parse_command(text: str) -> Optional[Command]:
    """
    Parse a slash command into a Command object
    
    Uses shlex for proper handling of quoted strings.
    
    Example:
        /create_task name="Dummy Task 1" spoke="test" workload=1.0
        -> Command(name="create_task", args=['name=Dummy Task 1', 'spoke=test', 'workload=1.0'])
    """
    if not text.startswith('/'):
        return None
    
    # Use shlex to properly handle quoted strings
    try:
        parts = shlex.split(text[1:])  # Remove leading '/' and split
    except ValueError:
        # If shlex fails (e.g., unclosed quote), fall back to simple split
        parts = text[1:].split()
    
    if not parts:
        return None
    
    command_name = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    
    return Command(
        name=command_name,
        args=args,
        raw_input=text
    )


async def execute_command(
    command: Command,
    context: str = "hub",
    **kwargs
) -> CommandResult:
    """
    Execute a parsed command
    
    Args:
        command: Parsed Command object
        context: Execution context (hub or spoke)
        **kwargs: Additional context (session, agent, etc.)
    
    Returns:
        CommandResult with success status and message
    """
    handler = _registry.get_handler(command.name)
    
    if handler is None:
        available = list(_registry.list_commands(context).keys())
        return CommandResult(
            success=False,
            message=f"Unknown command: /{command.name}. Available: {', '.join(available)}"
        )
    
    # Check context availability
    allowed_contexts = _registry._contexts.get(command.name, ["both"])
    if "both" not in allowed_contexts and context not in allowed_contexts:
        return CommandResult(
            success=False,
            message=f"Command /{command.name} not available in {context} context"
        )
    
    try:
        # Execute handler (support both async and sync)
        import inspect
        if inspect.iscoroutinefunction(handler):
            result = await handler(command.args, **kwargs)
        else:
            result = handler(command.args, **kwargs)
        
        return result
    except Exception as e:
        return CommandResult(
            success=False,
            message=f"Command execution failed: {str(e)}"
        )


def get_command_help() -> str:
    """
    Generate help text for all commands
    
    Returns:
        Formatted help string
    """
    commands = _registry.list_commands()
    
    if not commands:
        return "No commands registered."
    
    help_text = "## Available Commands\n\n"
    for name, description in sorted(commands.items()):
        contexts = _registry._contexts.get(name, ["both"])
        context_str = " | ".join(contexts)
        help_text += f"- `/{name}` - {description} ({context_str})\n"
    
    return help_text
