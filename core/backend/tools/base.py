from abc import ABC, abstractmethod
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel

class BaseTool(ABC):
    name: str
    description: str
    args_schema: Type[BaseModel]
    
    # Cache storage for the declaration dict (Singleton-like behavior per class)
    _declaration_cache: Optional[Dict[str, Any]] = None

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
