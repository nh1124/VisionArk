"""Shared file type definitions."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AttachedFile:
    """
    File attachment with metadata and Gemini File API reference.
    Stores file reference for multimodal LLM calls, not raw content.
    """
    filename: str
    file_type: str
    size_bytes: int
    content: Optional[str] = None
    gemini_file_uri: Optional[str] = None
    gemini_file_name: Optional[str] = None
    storage_path: Optional[str] = None

    def has_gemini_reference(self) -> bool:
        return self.gemini_file_uri is not None

    def format_for_chat(self) -> str:
        if self.gemini_file_uri:
            return f"\n\n**Attached File: {self.filename}** (Gemini File: available for analysis)"
        elif self.content:
            if self.size_bytes < 10000 and self.file_type.startswith("text/"):
                return f"\n\n**Attached File: {self.filename}**\n```\n{self.content}\n```"
            return f"\n\n**Attached File: {self.filename}** (content available)"
        return f"\n\n**File attached: {self.filename}** (type: {self.file_type})"

    def format_for_log(self) -> str:
        size_mb = self.size_bytes / (1024 * 1024)
        if size_mb < 0.01:
            size_kb = self.size_bytes / 1024
            return f"📎 {self.filename} ({size_kb:.1f}KB)"
        return f"📎 {self.filename} ({size_mb:.2f}MB)"

    def format_for_display(self) -> dict:
        return {
            "name": self.filename,
            "type": self.file_type,
            "size": self.size_bytes,
            "has_gemini_ref": self.has_gemini_reference()
        }

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "gemini_file_uri": self.gemini_file_uri,
            "gemini_file_name": self.gemini_file_name,
            "storage_path": self.storage_path,
            "name": self.filename,
            "type": self.file_type,
            "size": self.size_bytes
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AttachedFile':
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
        if self.gemini_file_uri:
            from google.genai import types
            return types.Part.from_uri(
                file_uri=self.gemini_file_uri,
                mime_type=self.file_type
            )
        return None
