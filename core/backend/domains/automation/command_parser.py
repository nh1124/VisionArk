from typing import Optional, Dict, List, Type, Any
from dataclasses import dataclass
import shlex

from domains.automation.commands.base import CommandResult, BaseCommand


@dataclass
class Command:
    """Parsed command structure"""
    name: str
    args: List[str]
    raw_input: str


def parse_command(text: str) -> Optional[Command]:
    """
    Parse a slash command into a Command object
    """
    if not text.startswith('/'):
        return None
    
    try:
        parts = shlex.split(text[1:])
    except ValueError:
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


def _get_command_map() -> Dict[str, Type[BaseCommand]]:
    """Central mapping of slash commands to BaseCommand classes"""
    # Import here to avoid circular dependencies
    from domains.automation.commands.library import (
        ArchiveCommand, MoveCommand, CreateProjectCommand, DeleteProjectCommand, CloneProjectCommand,
        SendMessageCommand, ResendCommand, UndoCommand, TimerCommand, NoteCommand
    )
    
    return {
        "archive": ArchiveCommand,
        "move": MoveCommand,
        "mv": MoveCommand,
        "create_project": CreateProjectCommand,
        "delete_project": DeleteProjectCommand,
        "kill": DeleteProjectCommand,
        "clone": CloneProjectCommand,
        "send_message": SendMessageCommand,
        "resend": ResendCommand,
        "undo": UndoCommand,
        "timer": TimerCommand,
        "note": NoteCommand,
    }


async def execute_command(
    command: Command,
    scope: str = "main",
    **kwargs
) -> CommandResult:
    """
    Execute a parsed command using the new dedicated BaseCommand architecture
    """
    command_map = _get_command_map()
    command_cls = command_map.get(command.name)

    if not command_cls:
        return CommandResult(success=False, message=f"Unknown command: /{command.name}")

    try:
        command_instance = command_cls()
        # Execute the command logic
        return await command_instance.run(command.args, **kwargs)

    except Exception as e:
        return CommandResult(success=False, message=f"Command execution failed: {str(e)}")


def get_command_help() -> str:
    """Generate help text for all dedicated commands"""
    command_map = _get_command_map()
    
    help_text = "## Available Commands\n\n"
    # Deduplicate aliases
    shown_classes = set()
    
    for name, command_cls in sorted(command_map.items()):
        if command_cls in shown_classes:
            continue
            
        instance = command_cls()
        desc = instance.description or "No description available."
        
        # Find aliases
        aliases = [n for n, t in command_map.items() if t == command_cls and n != name]
        alias_str = f" (aliases: {', '.join(['/' + a for a in aliases])})" if aliases else ""
        
        help_text += f"- `/{name}` - {desc}{alias_str}\n"
        shown_classes.add(command_cls)
    
    return help_text
