"""
OpenAI LLM Provider
Supports GPT-4, GPT-3.5, and embedding models
"""
from typing import List, Optional, Any, Dict
from .base_provider import BaseLLMProvider, CompletionResponse
from models.message import MessageRole, Message, ToolCall, SubMessage
import asyncio
import uuid

import logging
logger = logging.getLogger(__name__)

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
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        native_context: Optional[Any] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using OpenAI"""
        # Convert Message objects to OpenAI format
        openai_messages = []
        if system_instruction:
            openai_messages.append({"role": "system", "content": system_instruction})
            
        for msg in messages:
            role_val = getattr(msg.role, "value", msg.role)
            openai_messages.append({"role": role_val, "content": msg.content})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        content = response.choices[0].message.content or ""
        
        # Create a SubMessage for this turn
        step = SubMessage(
            sub_id=str(uuid.uuid4()),
            content=content,
            tool_calls=[] # TODO: Implement OpenAI tool parsing if needed
        )

        return CompletionResponse(
            content=content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            step=step
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
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """Stream completion tokens"""
        openai_messages = []
        if system_instruction:
            openai_messages.append({"role": "system", "content": system_instruction})
            
        for msg in messages:
            role_val = getattr(msg.role, "value", msg.role)
            openai_messages.append({"role": role_val, "content": msg.content})
        
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            temperature=temperature,
            stream=True,
            **kwargs
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def stream_chat(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """Streaming chat simulation (not fully implemented for OpenAI yet)"""
        for chunk in self.stream_complete(messages, system_instruction, temperature, **kwargs):
            yield {"type": "content", "data": chunk}

    async def complete_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        native_context: Optional[Any] = None,
        **kwargs
    ) -> CompletionResponse:
        """Asynchronous completion (sync simulation)"""
        return await asyncio.to_thread(
            self.complete, messages, system_instruction, temperature, max_tokens, native_context, **kwargs
        )

    async def stream_chat_async(
        self,
        messages: List[Message],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """Asynchronous streaming chat (sync simulation)"""
        for event in self.stream_chat(messages, system_instruction, temperature, **kwargs):
            yield event
            await asyncio.sleep(0)
