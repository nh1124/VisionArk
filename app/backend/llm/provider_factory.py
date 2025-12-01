"""
Provider Factory
Creates LLM provider instances based on configuration
"""
import os
from typing import Optional
from dotenv import load_dotenv
from .base_provider import BaseLLMProvider
from .gemini_provider import GeminiProvider

# Load environment variables
load_dotenv()


def get_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None
) -> BaseLLMProvider:
    """
    Factory function to create LLM provider instances
    
    Args:
        provider_name: Provider to use (gemini, openai, anthropic, local)
                      Defaults to LLM_PROVIDER env var or "gemini"
        model_name: Model name to use. Defaults to provider-specific env var
        api_key: API key. Defaults to provider-specific env var
    
    Returns:
        BaseLLMProvider instance
    
    Example:
        # Use defaults from .env
        llm = get_provider()
        
        # Explicit provider
        llm = get_provider("openai", "gpt-4")
    """
    # Determine provider
    if provider_name is None:
        provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    # Create provider instance
    if provider_name == "gemini":
        return _create_gemini_provider(model_name, api_key)
    elif provider_name == "openai":
        return _create_openai_provider(model_name, api_key)
    elif provider_name == "anthropic":
        return _create_anthropic_provider(model_name, api_key)
    elif provider_name == "local":
        return _create_local_provider(model_name, api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}. Supported: gemini, openai, anthropic, local")


def _create_gemini_provider(model_name: Optional[str], api_key: Optional[str]) -> GeminiProvider:
    """Create Gemini provider"""
    if model_name is None:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    if api_key is None:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")
    
    return GeminiProvider(model_name=model_name, api_key=api_key)


def _create_openai_provider(model_name: Optional[str], api_key: Optional[str]):
    """Create OpenAI provider"""
    from .openai_provider import OpenAIProvider
    
    if model_name is None:
        model_name = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment")
    
    return OpenAIProvider(model_name=model_name, api_key=api_key)


def _create_anthropic_provider(model_name: Optional[str], api_key: Optional[str]):
    """Create Anthropic provider"""
    # TODO: Implement when needed
    raise NotImplementedError("Anthropic provider not yet implemented")


def _create_local_provider(model_name: Optional[str], api_key: Optional[str]):
    """Create local model provider (Ollama, LM Studio)"""
    # TODO: Implement when needed
    raise NotImplementedError("Local provider not yet implemented")
