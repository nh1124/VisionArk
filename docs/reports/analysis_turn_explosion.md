# Analysis Report: Turn Count Explosion

**Date:** 2026-02-17
**Subject:** Analysis of "736 turns" consumed in Visionark Login Automation task.

## Executive Summary
The massive turn count (736 turns) was caused by a **Nested Loop Amplification** issue involving the Orchestrator, the Graph Definition, and the Engine Runtime.

Specifically, the `execute` step in the graph is configured to retry (`next: execute`) on any failure. When the underlying Engine Runtime (Gemini) encounters issues (like Browser timeouts) and exhausts its own turn limit (25 turns), it returns an error. The Orchestrator then re-enters the `execute` step, triggering *another* 25 turns. This repeats until the Orchestrator's own safety limit (75 steps) is reached, creating a theoretical maximum of 1875 turns (75 * 25).

## Root Cause Analysis

### 1. Nested Loops
There are two layers of loop limits that multiply each other:
-   **Inner Loop (Engine Runtime)**: `GeminiEngine` runs a multi-turn inference loop up to `max_turns` (Default: 25).
-   **Outer Loop (Orchestrator)**: `Orchestrator` runs graph steps up to `max_iterations` (Default: 3x `max_turns` = 75).

### 2. Graph Retry Logic
The `project_assistant` graph in `engine_setup.py` defines the `execute` step as:
```yaml
  - id: execute
    type: role
    # ...
    on:
      - when: "event.type == 'done'"
        next: verify
      - when: default
        next: execute  <-- RETRY ON ERROR
```
If `GeminiEngine` returns `EventType.ERROR` (due to tool path failure or max turns exhausted), the `default` transition triggers, causing the Orchestrator to execute the step again.

### 3. Missing Aggregate Limit
While `StepExecutor` delegates limit enforcement to `GeminiEngine` for role steps (`engine_handles_limits = True`), `GeminiEngine` only enforces limits *per invocation*. There is no mechanism tracking the *cumulative* turns consumed by a single logical step across multiple Orchestrator retries.

## Scenario Reconstruction
1.  **Step 1**: Orchestrator enters `execute`. Calls `GeminiEngine`.
2.  **Inner Turn 1-25**: Agent tries "Browser Fill". Tool times out (30s). Agent retries. Repeat until 25 turns exhausted.
3.  **Result**: `GeminiEngine` returns `ERROR: Turn limit exceeded`.
4.  **Transition**: Orchestrator sees `ERROR`. Matches `when: default`. Transitions to `execute`.
5.  **Step 2**: Orchestrator enters `execute` again. Calls `GeminiEngine`.
6.  **Inner Turn 1-25**: `GeminiEngine` starts fresh (0 turns). Agent retries browser actions...
7.  **Repeat**: This cycle continues until Orchestrator hits `max_iterations` (75).

**Calculation**:
-   Observed: 736 turns.
-   Run cycles: 736 / 25 ≈ 29.4 Orchestrator steps.
-   This is well within the Orchestrator's 75-step safety limit.

## Recommendations

### Short Term (Configuration Fix)
1.  **Modify Graph**: Change the `execute` step to transition to a failure state or terminate on error, rather than blindly retrying.
    ```yaml
      - when: default
        next: respond  # Or a dedicated error handler
    ```
2.  **Reduce Orchestrator Safety Limit**: 3x `max_turns` might be too aggressive if nested loops are possible.

### Long Term (Architecture Fix)
1.  **Cumulative Turn Tracking**: `Orchestrator` (or `StepExecutor`) should track cumulative turns for a step *ID* across re-entries, or pass the current `run.context.turn_index` to `GeminiEngine` to enforce a global limit.
2.  **Error Backoff/Circuit Breaker**: If a step fails repeatedly with the same error, stop retrying.

## Conclusion
The system behaved "correctly" according to the configured graph (retry on error) and architecture (isolated runtime scope), but this combination proved dangerous for resource consumption. Breaking the retry loop in the Graph YAML is the most immediate fix.
