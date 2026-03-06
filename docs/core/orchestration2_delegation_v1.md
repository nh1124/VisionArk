# orchestration2 Delegation V1

## Scope

This document describes the V1 implementation for parent-child delegation in `orchestration2`:

- Backward-compatible `delegate_task` extension (`mode`, `request_id`, `context_scope`)
- Delivery-safe delegation persistence (`delivery_status`, `delivery_cursor`, `request_id`)
- Poll/receive interfaces (`wait_for_delegation`, `receive_delegation_results`)
- Subagent session continuity (`orchestration_subagent_sessions`)

## Tool Examples

### 1) Existing sync call (backward compatible)

```json
{
  "child_agent": "researcher",
  "task": "Collect the top 3 competitor pricing updates.",
  "timeout_sec": 120
}
```

### 2) Async delegation with idempotency

```json
{
  "child_agent": "researcher",
  "task": "Collect the top 3 competitor pricing updates.",
  "mode": "async",
  "request_id": "pricing-2026-03-06-01",
  "context_scope": "session"
}
```

Expected output contains:

```json
{
  "delegation_id": "<uuid>",
  "status": "pending"
}
```

### 3) Blocking wait for async result

Tool: `wait_for_delegation`

```json
{
  "delegation_id": "<uuid>",
  "timeout_sec": 60,
  "ack": true
}
```

### 4) Cursor-based receive (with optional ack)

Tool: `receive_delegation_results`

```json
{
  "since_cursor": 0,
  "limit": 20,
  "ack": true
}
```

Response shape:

```json
{
  "results": [
    {
      "delegation_id": "<uuid>",
      "child_run_id": "<run_id>",
      "status": "completed",
      "output": "...",
      "error": null,
      "delivery_status": "acknowledged",
      "delivery_cursor": 12
    }
  ],
  "next_cursor": 12,
  "count": 1,
  "acked": 1
}
```

## Design Memo (Engine Change Minimality)

Engine changes are intentionally minimal:

- `AgentEngine.delegate_task(...)` now accepts optional:
  - `mode` (`sync` default, `async` optional)
  - `request_id`
  - `context_scope`
  - `subagent_session_id`
  - `child_history`
- Added `AgentEngine.wait_delegation_result(...)` as a thin wrapper over `DelegationManager.wait_result(...)`.

Non-engine concerns are implemented outside the engine in `DelegationService`:

- Subagent session resolve/create (`orchestration_subagent_sessions`)
- `request_id` idempotency check (`find_delegation_by_request_id`)
- Cursor-based receive and ack orchestration
- Subagent conversation-state persistence and restoration

This keeps engine responsibility focused on run execution (`input -> output`) while moving session/delivery/idempotency concerns to adapter/service and store layers.
