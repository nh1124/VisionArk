"""
Base LLM Provider Interface
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from domains.orchestration.message import Message, MessageRole, SubMessage


@dataclass
class CompletionResponse:
    """Standard response format"""
    content: str
    model: str
    usage: Optional[Dict] = None  # tokens used, cost, etc.
    step: Optional[SubMessage] = None # The primary thinking step (for single turns)
    native_context: Optional[Any] = None # Provider-specific context for optimization


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, model_name: str, api_key: str, **kwargs):
        self.model_name = model_name
        self.api_key = api_key
        self.kwargs = kwargs
    
    @abstractmethod
    def complete(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        native_context: Optional[Any] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion from the LLM
        """
        pass
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        Generate embeddings for text
        """
        pass
    
    @abstractmethod
    def stream_complete(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Stream completion tokens as they are generated
        """
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Stream chat events including status updates and content chunks.
        """
        pass

    @abstractmethod
    async def complete_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        native_context: Optional[Any] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Asynchronously generate a completion from the LLM
        """
        pass

    @abstractmethod
    async def stream_chat_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Asynchronously stream chat events.
        """
        pass
