# ADR: NativeRun Identity Split and Cross-System Tracing

## Status
Accepted and implemented.

## Context
`agent_runs.id` had been overloaded as orchestration identity (`orchestration_runs.run_id`).
This tightly coupled operational run state with orchestration source-of-truth and made cross-system tracing inconsistent.

## Decision
1. Naming is unified to `NativeRun` across backend/native/web.
2. Operational run table is `native_runs` (migrated from `agent_runs` inside `_run_migrations`).
3. `NativeRun.id` is an independent operational UUID; orchestration linkage is stored in nullable `NativeRun.orchestration_run_id`.
4. Run APIs are exposed at `/api/native-runs` (old `/api/runs` path removed).
5. Trace metadata (`trace_id`, `origin_type`, `origin_id`) is persisted on:
`native_runs`, `long_running_jobs`, `monitor_job_runs`, and `scheduled_tasks`.

## Identity Semantics
1. `NativeRun.id`: primary operational identity for run center operations and execution ownership.
2. `NativeRun.orchestration_run_id`: optional foreign-key link to orchestration run (`orchestration_runs.run_id`).
3. Legacy rows that previously used orchestration id as run PK are backfilled by setting `orchestration_run_id = id` when matched.
4. Runtime lookup/update/cancel paths resolve by either `id` or `orchestration_run_id` to keep old rows operable.

## Trace Propagation Rules
1. Chat/agent entrypoint:
worker guarantees a `trace_id` and propagates it to orchestration metadata and `NativeRun` projection.
2. Native standalone entrypoint:
`POST /api/native-runs` generates `trace_id` when absent.
3. Monitor scheduling/execution:
trace metadata is stored on AES scheduled records and propagated to `monitor_job_runs`.
4. Long-running jobs:
trace metadata is accepted and stored on job creation/update.
5. Causally related entities should share one `trace_id` and use hop-specific `origin_type`/`origin_id`.

## Migration Notes
1. Migration is additive and non-destructive:
columns are added conditionally, indexes are created with `IF NOT EXISTS`, and FK add/drop is best-effort.
2. Table rename `agent_runs -> native_runs` is executed in startup migration flow (`init_database` pre-migration and `_run_migrations` safeguard path), not via external one-off SQL.
