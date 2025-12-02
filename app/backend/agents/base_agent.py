"""
Base agent class - now abstract with proper separation of concerns
Removes 10-message limit to use full Gemini context
"""
from abc import ABC, abstractmethod
from typing import List
from pathlib import Path

from llm import get_provider
from models.message import Message, MessageRole, AttachedFile


class BaseAgent(ABC):
    """Abstract base class for all AI agents"""
    
    def __init__(self):
        self.conversation_history: List[Message] = []
        self.llm = get_provider()
        self.system_prompt = None
        
        # Load conversation history from log if exists
        self._load_history_from_log()
    
    @abstractmethod
    def load_system_prompt(self) -> str:
        """
        Each agent type implements its own prompt loading logic
        Hub loads from hub_data/system_prompt.md
        Spoke loads from spokes/{name}/system_prompt.md
        """
        pass
    
    @abstractmethod
    def get_chat_log_path(self) -> Path:
        """
        Each agent defines where to save conversation logs
        Hub: hub_data/chat.log
        Spoke: spokes/{name}/chat.log
        """
        pass
    
    def chat(self, user_message: str, attached_files: List[AttachedFile] = None) -> str:
        """
        Generic chat logic - same for all agents
        NOW SENDS ALL MESSAGES
        """
        # Load system prompt if not loaded
        if not self.system_prompt:
            self.system_prompt = self.load_system_prompt()
        
        # Create structured message
        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            attached_files=attached_files or []
        )
        
        # Add to history
        self.conversation_history.append(msg)
        
        # Convert ALL messages to LLM format (NO LIMIT!)
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        
        # Format for LLM provider
        messages = self.llm.format_messages(
            self.system_prompt,
            llm_messages  # ✅ ALL messages, not just last 10!
        )
        
        # Get response from LLM
        response = self.llm.complete(messages)
        
        # Create assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        
        # Add to history
        self.conversation_history.append(assistant_msg)
        
        # Save both messages to log (metadata only)
        self._save_to_log(msg)
        self._save_to_log(assistant_msg)
        
        return response.content
    
    def _save_to_log(self, message: Message):
        """
        Save message to log file
        Uses format_for_log() which stores metadata only (not file contents)
        """
        log_path = self.get_chat_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(message.format_for_log() + "\n\n")
    
    def _load_history_from_log(self):
        """
        Load conversation history from log file
        Parses log entries back into Message objects
        """
        log_path = self.get_chat_log_path()
        if not log_path.exists():
            return
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by double newline (message separator)
            entries = content.strip().split('\n\n')
            
            for entry in entries:
                if not entry.strip():
                    continue
                
                lines = entry.split('\n')
                if not lines:
                    continue
                
                # Parse first line: "Role [timestamp]:"
                first_line = lines[0]
                if '[' not in first_line or ']:' not in first_line:
                    continue
                
                # Extract role
                role_str = first_line.split('[')[0].strip().lower()
                if role_str == "user":
                    role = MessageRole.USER
                elif role_str == "assistant":
                    role = MessageRole.ASSISTANT
                else:
                    continue
                
                # Extract timestamp
                try:
                    timestamp_str = first_line.split('[')[1].split(']')[0]
                    from datetime import datetime
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = datetime.now()
                
                # Extract content (everything after "Role [timestamp]:")
                content_start = first_line.index(']:') + 2
                content_lines = [first_line[content_start:].strip()] if content_start < len(first_line) else []
                content_lines.extend(lines[1:])
                
                # Filter out file metadata lines (📎)
                message_content = []
                attached_files = []
                
                for line in content_lines:
                    if line.startswith('📎'):
                        # Parse file metadata: "📎 filename.pdf (2.45MB)"
                        # For now, just note that file was attached
                        # Full file reconstruction would need file storage
                        pass
                    else:
                        message_content.append(line)
                
                content = '\n'.join(message_content)
                
                # Create Message object
                msg = Message(
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    attached_files=attached_files  # File contents not in log
                )
                
                self.conversation_history.append(msg)
        
        except Exception as e:
            print(f"Failed to load history from log: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
