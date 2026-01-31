"""
Message models for structured conversation handling
Separates LLM format, log format, and display format
"""
from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict
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
    File attachment with metadata and Gemini File API reference
    Stores file reference for multimodal LLM calls, not raw content
    """
    filename: str
    file_type: str
    size_bytes: int
    content: Optional[str] = None  # Legacy: extracted text (for fallback only)
    gemini_file_uri: Optional[str] = None  # Gemini File API URI
    gemini_file_name: Optional[str] = None  # Gemini file reference name
    storage_path: Optional[str] = None  # Local storage path
    
    def has_gemini_reference(self) -> bool:
        """Check if file was uploaded to Gemini"""
        return self.gemini_file_uri is not None
    
    def format_for_chat(self) -> str:
        """
        Format for LLM - show file reference, NOT content
        Use Gemini File API for actual content when available
        """
        if self.gemini_file_uri:
            return f"\n\n**Attached File: {self.filename}** (Gemini File: available for analysis)"
        elif self.content:
            # Fallback for text files only (small files < 10KB)
            if self.size_bytes < 10000 and self.file_type.startswith("text/"):
                return f"\n\n**Attached File: {self.filename}**\n```\n{self.content}\n```"
            return f"\n\n**Attached File: {self.filename}** (content available)"
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
        Format for frontend display - metadata only, no content
        """
        return {
            "name": self.filename,
            "type": self.file_type,
            "size": self.size_bytes,
            "has_gemini_ref": self.has_gemini_reference()
        }
    
    def to_dict(self) -> dict:
        """
        Full serialization for DB persistence (meta_payload)
        Contains both internal keys and frontend-friendly keys.
        """
        return {
            "filename": self.filename,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "gemini_file_uri": self.gemini_file_uri,
            "gemini_file_name": self.gemini_file_name,
            "storage_path": self.storage_path,
            # Keys expected by frontend (compatibility)
            "name": self.filename,
            "type": self.file_type,
            "size": self.size_bytes
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AttachedFile':
        """
        Reconstruct AttachedFile from dictionary, handling various key mappings.
        """
        if not data:
            return None
            
        return cls(
            filename=data.get("filename") or data.get("name") or "unknown_file",
            file_type=data.get("file_type") or data.get("type") or "application/octet-stream",
            size_bytes=data.get("size_bytes") or data.get("size") or 0,
            gemini_file_uri=data.get("gemini_file_uri"),
            gemini_file_name=data.get("gemini_file_name"),
            storage_path=data.get("storage_path")
        )
    
    def to_gemini_part(self):
        """
        Convert to Gemini content part for multimodal API calls.
        """
        if self.gemini_file_uri:
            from google.genai import types
            return types.Part.from_uri(
                file_uri=self.gemini_file_uri,
                mime_type=self.file_type
            )
        return None


@dataclass
class ToolCall:
    """Structured record of a tool/function call and its result"""
    name: str
    args: dict
    call_id: Optional[str] = None
    result: Optional[str] = None
    is_success: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "call_id": self.call_id,
            "result": self.result,
            "is_success": self.is_success
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ToolCall':
        if not data:
            return None
        return cls(
            name=data.get("name"),
            args=data.get("args") or {},
            call_id=data.get("call_id"),
            result=data.get("result"),
            is_success=data.get("is_success", True)
        )


@dataclass
class SubMessage:
    """Structured record of an intermediate thinking turn and its tools"""
    sub_id: str
    content: str  # Thought/Text
    tool_calls: List[ToolCall] = field(default_factory=list)
    meta_info: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "sub_id": self.sub_id,
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "meta_info": self.meta_info,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SubMessage':
        if not data: return None
        ts = data.get("timestamp")
        if isinstance(ts, str): ts = datetime.fromisoformat(ts)
        
        return cls(
            sub_id=data.get("sub_id"),
            content=data.get("content") or "",
            tool_calls=[ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])],
            meta_info=data.get("meta_info") or {},
            timestamp=ts or datetime.now()
        )


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
    sub_messages: List[SubMessage] = field(default_factory=list) # Structured history
    meta_info: Optional[Any] = None  # Can be string or dict for tool metadata
    
    def format_for_chat(self) -> str:
        """
        Format for LLM - include full file contents but EXCLUDE technical meta_info
        to prevent LLM from mimicking internal JSON/log formats.
        """
        parts = []
        
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
            "attached_files": [f.format_for_display() for f in self.attached_files],
            "sub_messages": [sm.to_dict() for sm in self.sub_messages]
        }
    
    def to_dict(self) -> dict:
        """
        Full serialization for DB persistence
        """
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "attached_files": [f.to_dict() for f in self.attached_files],
            "sub_messages": [sm.to_dict() for sm in self.sub_messages],
            "meta_info": self.meta_info
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Message':
        if not data: return None
        ts = data.get("timestamp")
        if isinstance(ts, str): ts = datetime.fromisoformat(ts)
        
        return cls(
            role=MessageRole(data.get("role", "user")),
            content=data.get("content") or "",
            timestamp=ts or datetime.now(),
            attached_files=[AttachedFile.from_dict(f) for f in data.get("attached_files", [])],
            sub_messages=[SubMessage.from_dict(sm) for sm in data.get("sub_messages", [])],
            meta_info=data.get("meta_info")
        )

    def to_llm_message(self) -> dict:
        """
        Convert to LLM provider format
        """
        return {
            "role": self.role.value,
            "content": self.format_for_chat()
        }
