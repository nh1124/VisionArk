"""
Gemini LLM Provider  
Supports Gemini 1.5 and 2.0 models
"""
import google.generativeai as genai
from typing import List, Optional
from .base_provider import BaseLLMProvider, Message, CompletionResponse


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider"""
    
    def __init__(self, model_name: str = "gemini-2.5-flash-lite", api_key: str = None, **kwargs):
        super().__init__(model_name, api_key, **kwargs)
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
    
    def complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using Gemini"""
        # Build prompt from messages
        full_prompt = self._build_prompt(messages)
        
        # Generate config
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        # Generate response
        response = self.model.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        
        # Extract token usage
        total_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0)
        
        return CompletionResponse(
            content=response.text,
            model=self.model_name,
            usage={"total_tokens": total_tokens} if total_tokens > 0 else None
        )
    
    def embed(self, text: str) -> List[float]:
        """Generate embeddings using Gemini Embedding API"""
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]
    
    def stream_complete(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ):
        """Stream completion tokens"""
        full_prompt = self._build_prompt(messages)
        
        generation_config = {
            "temperature": temperature,
        }
        
        response = self.model.generate_content(
            full_prompt,
            generation_config=generation_config,
            stream=True
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
    def _build_prompt(self, messages: List[Message]) -> str:
        """Convert Message list to Gemini prompt format"""
        prompt_parts = []
        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"System: {msg.content}\n\n")
            elif msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n\n")
        return "".join(prompt_parts)
