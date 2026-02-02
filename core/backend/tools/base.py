from abc import ABC, abstractmethod
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel


from dataclasses import dataclass, field
from typing import List

@dataclass
class ToolAttachment:
    """Standardized multimodal attachment for tool results"""
    type: str  # e.g., "gemini_file_uri", "image_path", etc.
    value: str
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolResult:
    """Standardized result object for all Agent Tools"""
    content: str                          # Text message for the LLM
    data: Optional[Dict[str, Any]] = None  # Raw programmatic data
    attachments: List[ToolAttachment] = field(default_factory=list)
    is_success: bool = True

    def to_log_result(self) -> str:
        """Convert content to a string format suitable for ToolCall.result"""
        return self.content

class NoArgs(BaseModel):
    """Fallback model for tools with no arguments to avoid calling model_json_schema on BaseModel directly."""
    pass

class BaseTool(ABC):
    name: str
    description: str
    args_schema: Type[BaseModel]
    
    # Cache storage for the declaration dict (Singleton-like behavior per class)
    _declaration_cache: Optional[Dict[str, Any]] = None
    _status_callback: Optional[Any] = None

    def set_status_callback(self, callback: Any):
        """Set a callback for progress reporting."""
        self._status_callback = callback

    async def report_status(self, message: str, state: str = "processing"):
        """Report execution status via callback."""
        if self._status_callback:
            await self._status_callback(message, state)

    @classmethod
    def declaration(cls) -> Dict[str, Any]:
        """
        Returns the Gemini function declaration JSON.
        Uses lazy initialization to compute the schema only once (Zero runtime overhead on subsequent calls).
        """
        if cls._declaration_cache is None:
            # Compute schema
            schema = cls.args_schema.model_json_schema()
            
            # Remove unnecessary fields for Gemini
            if "title" in schema: del schema["title"]
            
            # Pydantic's model_json_schema might include 'title' in properties as well
            if "properties" in schema:
                for prop in schema["properties"].values():
                    if "title" in prop:
                        del prop["title"]
            
            # Store in cache
            cls._declaration_cache = {
                "name": cls.name,
                "description": cls.description,
                "parameters": schema
            }
        
        return cls._declaration_cache

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Execute the tool logic."""
        pass
