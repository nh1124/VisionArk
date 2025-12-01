"""
OpenAI LLM Provider
Supports GPT-4, GPT-3.5, and embedding models
"""
from typing import List, Optional
from .base_provider import BaseLLMProvider, Message, CompletionResponse

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider"""
    
    def __init__(self, model_name: str = "gpt-4-turbo-preview", api_key: str = None, **kwargs):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
        
        super().__init__(model_name, api_key, **kwargs)
        self.client = OpenAI(api_key=self.api_key)
    
    def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using OpenAI"""
        # Convert Message objects to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return CompletionResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        )
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI"""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    
    def stream_complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ):
        """Stream completion tokens"""
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            temperature=temperature,
            stream=True,
            **kwargs
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
