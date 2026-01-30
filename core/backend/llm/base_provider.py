"""
Base LLM Provider Interface
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from models.message import Message, MessageRole


@dataclass
class CompletionResponse:
    """Standard response format"""
    content: str
    model: str
    usage: Optional[Dict] = None  # tokens used, cost, etc.
    new_messages: List[Message] = field(default_factory=list) # List of turns (AI intents & Tool results) during this call


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
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion from the LLM
        
        Args:
            messages: List of Message objects (conversation history)
            system_instruction: Optional system instruction/prompt
            temperature: Sampling temperature (0.0 - 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters
        
        Returns:
            CompletionResponse with generated text
        """
        pass
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        Generate embeddings for text
        
        Args:
            text: Input text to embed
        
        Returns:
            List of floats (embedding vector)
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
        
        Args:
            messages: List of Message objects
            system_instruction: Optional system instruction
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters
        
        Yields:
            String chunks as they are generated
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
    
