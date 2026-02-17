# Tool Specialization Refactoring Report (Revised)

## 1. Goal

Internalize engine-specific specialization into the **Tool Definition itself** to improve cohesion and simplify the architecture perfectly aligning with the "Single Source of Truth" principle.

## 2. Updated Proposal: Single `invoke` Entry Point

Instead of adding a separate `invoke_native` method, we will modify the standard `invoke` method to support engine-aware execution directly.

### Design

1.  **Context Awareness**:
    Ensure `ExecutionContext` (or the `extra` args passed to `invoke`) contains the `engine_kind`.

    ```python
    class ExecutionContext(BaseModel):
        ...
        engine_kind: str | None = None  # Added field
    ```

2.  **Tool Implementation**:
    Tools implement a single `invoke` method that checks the context and dispatches internally.

    ```python
    class ReadReferenceTool(BaseTool):
        async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
            # 1. Engine-specific dispatch
            if ctx.engine_kind == "gemini":
                return await self._invoke_gemini(call, ctx)
            
            # 2. Default (Generic) implementation
            return await self._invoke_generic(call, ctx)

        async def _invoke_gemini(self, call, ctx):
             # ... Gemini specific upload & Part creation ...
             pass
    ```

### Why this is better
*   **Simple Interface**: The `BaseTool` protocol remains unchanged (or minimally changed). Consumers just call `invoke()`.
*   **Encapsulation**: The tool completely owns how it behaves on different engines. The caller (engine/dispatcher) doesn't need to know about "native" vs "generic" invocation.
*   **No Adapter/Dispatcher Logic**: The `ToolDispatcher` becomes a dumb pass-through (or is removed entirely if the engine calls tools directly).

## 3. Change Scope

1.  **`engine/models/execution.py`**: Add `engine_kind` to `ExecutionContext`.
2.  **`engine/registry/tool_dispatcher.py`**: 
    *   Remove `EngineToolAdapter` protocol.
    *   Remove adapter registry logic.
    *   `dispatch()` simply calls `tool.invoke()`.
3.  **`tools/library/files.py`**:
    *   Merge `GeminiFileAdapter` logic back into `ReadReferenceTool.invoke`.
4.  **`engine_runtime/adapters/`**: Delete.
5.  **`engine_setup.py`**: Remove adapter registration.

This approach matches your suggestion: `invoke` is the single entry point that branches to `invoke_gemini` or `invoke_default` internally.
