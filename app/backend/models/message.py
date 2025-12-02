"""
Message models for structured conversation handling
Separates LLM format, log format, and display format
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageRole(Enum):
    """Message role types"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class AttachedFile:
    """
    File attachment with metadata and content
    Separates full content (for LLM) from metadata (for logs)
    """
    filename: str
    file_type: str
    size_bytes: int
    content: Optional[str] = None  # Extracted text content
    
    def format_for_chat(self) -> str:
        """
        Format for LLM - include full content
        """
        if self.content:
            return f"\n\n**Attached File: {self.filename}**\n```\n{self.content}\n```"
        return f"\n\n**File attached: {self.filename}** (type: {self.file_type})"
    
    def format_for_log(self) -> str:
        """
        Format for log - metadata only (compact)
        """
        size_mb = self.size_bytes / (1024 * 1024)
        if size_mb < 0.01:
            size_kb = self.size_bytes / 1024
            return f"📎 {self.filename} ({size_kb:.1f}KB)"
        return f"📎 {self.filename} ({size_mb:.2f}MB)"
    
    def format_for_display(self) -> dict:
        """
        Format for frontend display
        """
        return {
            "name": self.filename,
            "type": self.file_type,
            "size": self.size_bytes
        }


@dataclass
class Message:
    """
    Structured message with clean separation of concerns
    - format_for_chat(): Full content for LLM
    - format_for_log(): Compact metadata for persistence
    - format_for_display(): Clean JSON for frontend
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    attached_files: List[AttachedFile] = field(default_factory=list)
    meta_info: Optional[str] = None  # String provided by agent (e.g., "Load: 7.5/10 | Cap: 10.0")
    
    def format_for_chat(self) -> str:
        """
        Format for LLM - include full file contents and meta_info
        """
        parts = []
        
        # Add meta-info context if present (agent provides formatted string)
        if self.meta_info:
            parts.append(f"[Context: {self.meta_info}]")
        
        # Main message content
        parts.append(self.content)
        
        # Add file contents for LLM
        for file in self.attached_files:
            parts.append(file.format_for_chat())
        
        return "\n\n".join(parts)
    
    def format_for_log(self) -> str:
        """
        Format for persistence - compact with metadata only
        Saves 90%+ space by not storing file contents
        """
        role_label = self.role.value.title()
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [f"{role_label} [{ts}]:", self.content]
        
        # File metadata only (not contents!)
        if self.attached_files:
            files_line = ", ".join(f.format_for_log() for f in self.attached_files)
            lines.append(files_line)
        
        return "\n".join(lines)
    
    def format_for_display(self) -> dict:
        """
        Format for frontend display - clean JSON
        """
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "attached_files": [f.format_for_display() for f in self.attached_files]
        }
    
    def to_llm_message(self) -> dict:
        """
        Convert to LLM provider format
        """
        return {
            "role": self.role.value,
            "content": self.format_for_chat()
        }
