"""
Base LLM Provider Interface
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Message:
    """Standard message format across all providers"""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class CompletionResponse:
    """Standard response format"""
    content: str
    model: str
    usage: Optional[Dict] = None  # tokens used, cost, etc.
    metadata: Optional[Dict] = None


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
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion from the LLM
        
        Args:
            messages: List of Message objects (conversation history)
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
        temperature: float = 0.7,
        **kwargs
    ):
        """
        Stream completion tokens as they are generated
        
        Args:
            messages: List of Message objects
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters
        
        Yields:
            String chunks as they are generated
        """
        pass
    
    def format_messages(self, system_prompt: str, conversation: List[Dict[str, str]]) -> List[Message]:
        """
        Helper to convert conversation history to Message format
        
        Args:
            system_prompt: System prompt text
            conversation: List of {"role": str, "content": str} dicts
        
        Returns:
            List of Message objects
        """
        messages = [Message(role="system", content=system_prompt)]
        for msg in conversation:
            messages.append(Message(role=msg["role"], content=msg["content"]))
        return messages
