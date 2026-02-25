# LLM Provider System

VisionArk supports multiple LLM providers (Gemini, OpenAI, Anthropic) through a unified provider abstraction. This document explains the architecture and how to add new models or providers.

---

## Architecture Overview

```
User picks model in ChatInput (e.g. "openai:gpt-4.1")
    ↓
model_router.parse_model_spec()   →  ("openai", "gpt-4.1")
    ↓
model_router.get_api_key_for_provider()  →  decrypted API key from UserSettings
    ↓
project_engine_builder.py  →  selects OpenAIEngine / AnthropicEngine / GeminiEngine
    ↓
Engine.run(EngineRunInput) → multi-turn inference loop with tool calling
```

---

## Key Files

| File | Purpose |
|------|---------|
| [`infrastructure/llm/model_router.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/infrastructure/llm/model_router.py) | Parse `provider:model` spec, resolve API key, list configured providers |
| [`infrastructure/llm/provider_registry.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/infrastructure/llm/provider_registry.py) | Factory: given provider ID → returns correct `LLMProvider` instance |
| [`infrastructure/llm/openai_provider.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/infrastructure/llm/openai_provider.py) | `LLMProvider` thin wrapper for OpenAI (used by lightweight callers) |
| [`infrastructure/llm/anthropic_provider.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/infrastructure/llm/anthropic_provider.py) | `LLMProvider` thin wrapper for Anthropic |
| [`engine_runtime/openai_engine.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/domains/orchestration2/engine_runtime/openai_engine.py) | Full `LLMEngine` multi-turn loop for OpenAI (tool calling, cancellation) |
| [`engine_runtime/anthropic_engine.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/domains/orchestration2/engine_runtime/anthropic_engine.py) | Full `LLMEngine` multi-turn loop for Anthropic (tool_use/tool_result blocks) |
| [`engine_runtime/gemini_engine.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/domains/orchestration2/engine_runtime/gemini_engine.py) | Full `LLMEngine` for Gemini — uses native `Content/Part` types |
| [`bootstrap/project_engine_builder.py`](file:///c:/Users/nh112/programming/project/VisionArk/core/backend/domains/orchestration2/bootstrap/project_engine_builder.py) | Engine factory — reads selected model, picks correct engine class |
| [`frontend/lib/ModelContext.tsx`](file:///c:/Users/nh112/programming/project/VisionArk/core/frontend/lib/ModelContext.tsx) | React context — `MODEL_OPTIONS` list, `configuredProviders` state |

---

## Model Spec Format

Models are stored and transmitted as `provider:model` strings:

```
gemini-2.5-flash              # Legacy Gemini (no prefix — backward compat)
openai:gpt-4.1-mini           # OpenAI GPT-4.1 Mini
openai:o4-mini                # OpenAI o4-mini (reasoning)
openai:o3                     # OpenAI o3 (reasoning)
anthropic:claude-opus-4-5-20251101  # Anthropic Claude Opus 4.5
anthropic:claude-sonnet-4-20250514  # Anthropic Claude Sonnet 4
anthropic:claude-haiku-4-5          # Anthropic Claude Haiku 4.5
```

`parse_model_spec()` in `model_router.py` handles parsing:
1. If spec contains `:` → split on first `:` → `(provider, model)`
2. Else → match `_PREFIX_MAP` prefixes (e.g. `gpt-` → `openai`)
3. Fallback → `("gemini", spec)`

---

## Current Model List (as of Feb 2026)

### Gemini
| Model ID | Display Name | Notes |
|----------|-------------|-------|
| `gemini-3-pro-preview` | Gemini 3 Pro | Most capable |
| `gemini-3-flash-preview` | Gemini 3 Flash | Fast |
| `gemini-2.5-pro` | Gemini 2.5 Pro | Stable |
| `gemini-2.5-flash` | Gemini 2.5 Flash | Stable, fast |

### OpenAI
| Model ID | Display Name | Notes |
|----------|-------------|-------|
| `openai:gpt-5` | GPT-5 | Latest flagship |
| `openai:gpt-5-mini` | GPT-5 Mini | Balanced |
| `openai:gpt-5-nano` | GPT-5 Nano | Fast/cheap |
| `openai:gpt-5.1` | GPT-5.1 | Updated flagship |
| `openai:gpt-4.1` | GPT-4.1 | 1M context, coding |
| `openai:gpt-4.1-mini` | GPT-4.1 Mini | Default |
| `openai:o4-mini` | o4 Mini | Reasoning |
| `openai:o3` | o3 | Advanced reasoning |

### Anthropic
| Model ID | Display Name | Notes |
|----------|-------------|-------|
| `anthropic:claude-opus-4-6-20260220` | Claude Opus 4.6 | **Latest**, 1M context, default |
| `anthropic:claude-opus-4-5-20251101` | Claude Opus 4.5 | High capability |
| `anthropic:claude-sonnet-4-20250514` | Claude Sonnet 4 | Balanced |
| `anthropic:claude-haiku-4-5` | Claude Haiku 4.5 | Fast, cheap |

---

## Adding a New Model

Models only need to be updated in **2 places**:

### 1. Frontend: `ModelContext.tsx`

Add to the `MODEL_OPTIONS` array in the appropriate provider group:

```tsx
// In MODEL_OPTIONS:
{
    group: "OpenAI", provider: "openai", models: [
        // ... existing models ...
        { id: "openai:gpt-5", name: "GPT-5" },   // ← ADD HERE
    ]
}
```

### 2. Backend: `model_router.py`

Only needed if the new model uses a **new name prefix** not already in `_PREFIX_MAP`.
For `gpt-*`, `claude-*`, `gemini-*`, `o3*`, `o4-*` — no changes needed.

```python
# _PREFIX_MAP in model_router.py — add only if new prefix needed:
_PREFIX_MAP = {
    "gpt-": "openai",
    "o3":   "openai",   # exact match for "o3"
    "o3-":  "openai",   # prefix match for "o3-pro" etc.
    "o4-":  "openai",
    "claude-": "anthropic",
    "gemini-": "gemini",
    # "new-prefix-": "provider",  ← add here
}
```

No changes needed in the engine, settings, or worker for new models within an existing provider.

---

## Adding a New Provider

Adding a completely new provider (e.g. `mistral`) requires changes in 6 places:

### 1. `shared/database.py` — `UserSettings`
Add a new property and `_decrypt_ai_key` call:
```python
@property
def mistral_api_key(self) -> Optional[str]:
    return self._decrypt_ai_key("mistral_api_key")
```

### 2. `infrastructure/llm/model_router.py`
Add prefix to `_PREFIX_MAP`, add to `get_api_key_for_provider`, add to `get_configured_providers`:
```python
_PREFIX_MAP = { ..., "mistral-": "mistral" }

def get_api_key_for_provider(settings, provider_id):
    key_map = {
        ...,
        "mistral": settings.mistral_api_key,
    }
    return key_map.get(provider_id)

def get_configured_providers(settings):
    ...
    if settings.mistral_api_key:
        providers.append("mistral")
```

### 3. `engine_runtime/mistral_engine.py` — NEW FILE
Copy `openai_engine.py` as a template and adapt the SDK calls.
Key differences: message format, tool calling format, response parsing.

```python
class MistralEngine(LLMEngine):
    def __init__(self, api_key: str, tool_registry: ToolRegistry, *, model=None):
        from mistralai import AsyncMistral
        self._client = AsyncMistral(api_key=api_key)
        self._model = model or "mistral-large-latest"
        ...

    @property
    def kind(self) -> str:
        return "mistral"
```

### 4. `bootstrap/project_engine_builder.py`
Add a case in the engine factory:
```python
elif provider == "mistral":
    from ..engine_runtime.mistral_engine import MistralEngine
    engine = MistralEngine(api_key=api_key, tool_registry=tool_registry, model=model_id)
```

### 5. `api/settings.py` — `AIConfigUpdate` and save endpoint
```python
class AIConfigUpdate(BaseModel):
    ...
    mistral_api_key: Optional[str] = None

# In the save loop:
for key_name in ["gemini_api_key", "openai_api_key", "anthropic_api_key", "mistral_api_key"]:
    ...
```

### 6. Frontend — 3 files

**`ModelContext.tsx`** — add to `MODEL_OPTIONS` and `getProviderForModel`:
```tsx
{ group: "Mistral", provider: "mistral", models: [
    { id: "mistral:mistral-large-latest", name: "Mistral Large" },
]}
```

**`settings/page.tsx`** — add API key input field in the AI Providers tab.

**`signup/page.tsx`** — optionally add API key field (or skip; at-least-one requirement already met).

---

## Tool Integration

Tools detect the engine and can provide engine-specific behavior via `ctx.engine_kind`:

```python
# Example from files.py:
async def invoke(self, call, ctx):
    if ctx.engine_kind == "gemini":
        return await self._invoke_gemini(call, ctx)   # Uses Gemini Files API
    return await self._invoke_generic(call, ctx)       # Text-based fallback
```

`provider_parts` in `ToolResult` is **Gemini-only** — allows injecting native `types.Part` (e.g. file URIs) directly into Gemini's history. OpenAI/Anthropic use text-only `output`.

---

## API Key Storage

Keys are stored encrypted (AES) in `UserSettings.ai_config` JSON:
```json
{
  "gemini_api_key": "<encrypted>",
  "openai_api_key": "<encrypted>",
  "anthropic_api_key": "<encrypted>"
}
```

`UserSettings._decrypt_ai_key(key_name)` handles transparent decryption.

The frontend receives `"********"` for existing keys (never the plaintext). Sending `"********"` back means "keep existing" — only non-masked values trigger updates.
