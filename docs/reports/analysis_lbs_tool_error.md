# Analysis Report: LBS Tool Execution Errors

**Date:** 2026-02-17
**Subject:** Analysis of "Argument Error" and "Context Error" in LBS tools.

## Executive Summary
The errors observed (`TypeError: ... got multiple values for argument 'start_date'`) were caused by a calling convention mismatch between the `IntegrationToolAdapter` and the LBS tools. The Adapter was passing the `IntegrationContext` as the **first positional argument**, whereas LBS tools define specific positional arguments (e.g., `start_date`, `end_date`) and expect the context as a **keyword argument** (`ctx=...`).

## Root Cause Analysis

### 1. Adapter Implementation
The `IntegrationToolAdapter.invoke` method was implemented as:
```python
# integratons/adapter.py
result = await self.sdk_tool.run(integration_ctx, **tool_args)
```
This forces `integration_ctx` into the first positional slot of the wrapper `run` method.

### 2. Tool Signature (LBS)
LBS tools (e.g., `GetLBSScheduleTool`) are defined as:
```python
# integrations/lbs/agent_tools.py
async def run(self, start_date: str, end_date: str, ctx: IntegrationContext = None, **kwargs):
    ...
```
-   **Positional Arg 1**: `start_date`
-   **Positional Arg 2**: `end_date`
-   **Keyword Arg**: `ctx`

### 3. The Conflict
When the Adapter calls `run(integration_ctx, start_date="...", end_date="...")`:
1.  Python assigns `integration_ctx` to the first positional parameter: `start_date`.
2.  Python sees `start_date` again in `**kwargs` (from `tool_args`).
3.  Result: `TypeError: run() got multiple values for argument 'start_date'`.

For tools like `ListTasksTool` which take `context` (string) as first arg:
1.  `integration_ctx` is assigned to `context`.
2.  `ctx` remains `None` (default).
3.  The tool checks `if not ctx:` and returns "Context error".

## Solution

The fix was applied to `integrations/adapter.py` to pass the context explicitly as a **keyword argument**:

```python
# Fixed invocation
result = await self.sdk_tool.run(ctx=integration_ctx, **tool_args)
```

This ensures `ctx` targets the `ctx` parameter regardless of position, and leaves positional slots available for the tool's actual arguments.

## Verification
A reproduction script `scripts/reproduce_lbs_error_mocked.py` was created to simulate both LBS-style tools (arguments first) and Google-style tools (context first).
-   **Before Fix**: LBS-style tools failed with TypeError.
-   **After Fix**: Both tool styles executed successfully.
