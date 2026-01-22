# AskNode Audit Report

An audit of the `ask_node` implementation revealed several critical issues that may lead to inconsistent behavior or silent failures.

## Critical Issues

### 1. Context Inconsistency (Blocking vs. Non-Blocking)
-   **Blocking Mode**: Uses the `db_session` and context of the active process.
-   **Non-Blocking Mode**: The Worker creates a *new* DB session and context.
-   **Problem**: If the initiator node makes local changes to the database or context before calling `ask_node(blocking=False)`, those changes might not be visible to the worker until the current transaction is committed.

### 2. Unreliable Session ID Resolution
-   **Source**: `worker.py` (Lines 177-185)
-   **Problem**: If `session_id` is not in the context, the worker tries to find the "last session" for the project. In a multi-user or multi-session environment, this could lead to callbacks appearing in the wrong chat session.

### 3. Silent Failures in Background Execution
-   **Source**: `worker.py` (Lines 229-233)
-   **Problem**: While the worker logs errors and updates the Redis status, it does **not** notify the user via `CallbackService` if a background task fails. The user will wait indefinitely for a response that never arrives in the chat.

### 4. Circular Dependency Risks
-   **Source**: `AskNodeTool` instantiates nodes directly (e.g., `ProjectNode`, `GenericMemberNode`).
-   **Problem**: As the node graph grows, this direct instantiation pattern is prone to circular imports. Using a factory or the `SystemNodeRegistry` approach for all nodes would be safer.

### 5. Missing Conversation Continuity
-   **Problem**: `ask_node` currently sends a single `message` string. It does not automatically propagate previous conversation history. When a target node receives an `ask_node` call, it lacks the context of "why" it is being called or what was discussed previously, unless explicitly included in the message.

---

## Recommendations
-   **Immediate**: Implement error callbacks in `worker.py` to notify the chat of failed background tasks.
-   **Short-term**: Standardize `session_id` propagation in the queue payload to avoid "guesswork" in the worker.
-   **Long-term**: Create a unified `NodeFactory` to handle instantiation for both tools and workers.
