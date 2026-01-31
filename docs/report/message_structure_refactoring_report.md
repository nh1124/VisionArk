# Report: Message Structure Refactoring & Compatibility

## 1. Problem Overview
The recent refactoring of the `Message` dataclass to support **Structured Thinking Steps** removed the `tool_calls` attribute. This was done to enforce a clean hierarchy where tool executions are stored within `SubMessage` objects, aligning with the new database schema (`chat_sub_messages`).

However, the surrounding LLM pipeline (Providers, Reasoning Engine, Skill Mining) was built with a hard dependency on `Message.tool_calls`. Removing this field caused immediate regressions:
- **`AttributeError`**: When building prompts, providers attempts to access `m.tool_calls` on historical messages.
- **`TypeError`**: When creating new assistant turns, providers attempt to pass `tool_calls` to the `Message` constructor.

## 2. Specific Points of Failure

### A. `GeminiProvider._prepare_history`
The provider iterates through the conversation history to build the prompt. It expects tool calls and their results to be attached directly to the `Message` object:
```python
# current failing logic
if m.tool_calls:
    for tc in m.tool_calls:
        model_parts.append(types.Part.from_function_call(...))
```

### B. `GeminiProvider.complete_async`
When the LLM returns a response, the provider packages it into a `Message` object. It currently tries to pass the detected tool calls via the deprecated argument:
```python
# current failing instantiation
new_msg = Message(
    role=MessageRole.ASSISTANT,
    content=combined_text,
    tool_calls=intents # ERROR: Unexpected keyword argument
)
```

### C. `ReasoningEngine.execute_async`
The reasoning loop relies on `last_turn_msg.tool_calls` to decide whether to continue the loop and to execute tools. It also extracts tool calls from the message to create the `SubMessage` record.
```python
tool_calls = last_turn_msg.tool_calls # ERROR: AttributeError
```

## 3. Recommended Improvements (Without updating `Message`)

To maintain a clean `Message` model while restoring functionality, the following changes are proposed:

### 1. Adaptive History Building in Providers
Providers should be updated to look for tool calls in the `sub_messages` list of a `Message` instead of assuming a `tool_calls` attribute exists. This allows history retrieved from the database to be correctly formatted for the LLM.

### 2. Provider Output Refactoring
`CompletionResponse` should be decoupled from the `Message` constructor for tool storage. The provider can detected tool calls and return them as a separate field or pre-package them into the `sub_messages` list of the returned `Message`.

### 3. Reasoning Engine Update
The `ReasoningEngine` should be updated to treat the `sub_messages` of the `last_turn_msg` as the source of truth for tool calls during the reasoning loop.

## Summary of Fix Strategy
Instead of putting `tool_calls` back into `Message`, we should:
1. Update `gemini_provider.py` and `openai_provider.py` to extract tool history from `m.sub_messages`.
2. Update `complete_async` to Detected detected tool calls and store them in the `sub_messages` list of the newly created `Message`.
3. Update `reasoning_engine.py` to read tool calls from `last_turn_msg.sub_messages`.
