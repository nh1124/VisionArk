# Multi-LLM Provider System

## Overview

The AI TaskManagement OS now supports multiple LLM providers through a clean abstraction layer. You can easily switch between Gemini, OpenAI, Anthropic, or local models without changing code.

## Architecture

```
llm/
├── base_provider.py       # Abstract interface
├── gemini_provider.py     # Google Gemini implementation
├── openai_provider.py     # OpenAI implementation  
├── provider_factory.py    # Factory pattern for instantiation
└── __init__.py           # Package exports
```

## Configuration

Edit your `.env` file:

```bash
# Choose your provider
LLM_PROVIDER=gemini  # or openai, anthropic, local

# Model selection
GEMINI_MODEL=gemini-2.0-flash-exp
OPENAI_MODEL=gpt-4-turbo-preview

# API Keys
GEMINI_API_KEY=your_key
OPENAI_API_KEY=your_key  # if using OpenAI
```

## Usage

The `base_agent.py` now automatically uses the configured provider:

```python
from llm import get_provider

# Automatically uses env vars
llm = get_provider()

# Or explicit
llm = get_provider("openai", "gpt-4")

# Same interface for all providers
response = llm.complete(messages)
embeddings = llm.embed(text)
```

## Supported Providers

| Provider | Status | Models |
|----------|--------|--------|
| Gemini | ✅ Implemented | gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp |
| OpenAI | ✅ Implemented | gpt-4-turbo, gpt-3.5-turbo, gpt-4 |
| Anthropic | 🔜 Planned | claude-3-opus, claude-3-sonnet |
| Local | 🔜 Planned | Ollama, LM Studio |

## Benefits

- **Hot-swappable**: Change providers without code changes
- **Cost optimization**: Use cheaper models for simple tasks
- **Fallback support**: Switch if one provider is down
- **Vendor independence**: Not locked into one provider
- **Easy testing**: Mock providers for unit

 tests

## Next Steps

To add a new provider:

1. Create `llm/your_provider.py` extending `BaseLLMProvider`
2. Implement `complete()`, `embed()`, `stream_complete()`
3. Add factory method in `provider_factory.py`
4. Update `.env.template`
