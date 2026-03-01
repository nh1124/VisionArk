// ─── Auto-generated Rust ↔ TypeScript bindings (Phase 3: ts-rs) ───────────────
//
// Rust-canonical type definitions live in bridge-rs/src/types.rs.
// Run the following to regenerate core/native/shared/bindings/:
//
//   cd core/native && cargo test -p bridge-rs
//
// The interfaces below are the TypeScript-idiomatic versions (more specific
// than the ts-rs output, e.g. Record<string,unknown> instead of unknown).
// They must stay structurally compatible with their counterparts in ./bindings/.
//
// Re-export the generated enum types directly (they match exactly):
export type { JobStatus } from "./bindings/JobStatus"
export type { RiskLevel } from "./bindings/RiskLevel"

// ─── WebSocket event types ─────────────────────────────────────────────────────
// Must stay in sync with the backend notification schema.
export const WsEventType = {
  JOB_CREATED      : "job.created",
  JOB_QUEUED       : "job.queued",
  JOB_UPDATED      : "job.updated",
  JOB_RUNNING      : "job.running",
  JOB_NEEDS_APPROVAL: "job.needs_approval",
  JOB_SUCCEEDED    : "job.succeeded",
  JOB_FAILED       : "job.failed",
  JOB_REJECTED     : "job.rejected",
} as const

export type WsEventType = typeof WsEventType[keyof typeof WsEventType]

export interface WsEvent<T = unknown> {
  type: string
  data: T
}

export interface JobWsEvent extends WsEvent<Job> {
  type: WsEventType
}

// ─── Device types ──────────────────────────────────────────────────────────────

export type DeviceKind = "desktop" | "mobile" | "server" | "other"
export type DevicePlatform = "windows" | "macos" | "linux" | "ios" | "android" | "other"
export type DeviceStatus = "online" | "offline" | "stale"

export interface NativeDevice {
  id: string
  display_name: string
  device_kind: DeviceKind
  platform: DevicePlatform
  client_version?: string
  capabilities: string[]
  is_enabled: boolean
  status: DeviceStatus
  last_seen_at?: string
  created_at: string
}

// ─── Domain types ──────────────────────────────────────────────────────────────
// (JobStatus and RiskLevel re-exported from ./bindings/ above)

export type JobSource = "native" | "web" | "cloud" | "mobile" | string

// JobType is an open string. Known prefix examples:
//   "local.file", "local.app", "local.dev", "integration.email", "integration.ec", "web.search"
export type JobType = string

export const KnownJobTypes = {
  LOCAL_FILE : "local.file",
  LOCAL_APP  : "local.app",
  LOCAL_DEV  : "local.dev",
  INT_EMAIL  : "integration.email",
  INT_EC     : "integration.ec",
} as const

export interface Job {
  id: string
  user_id: string
  project_id?: string
  source: JobSource
  type: JobType
  tags: string[]
  status: JobStatus
  risk_level: RiskLevel
  payload: Record<string, unknown>
  result?: Record<string, unknown>
  approved_by?: string
  error_log?: string
  target_device_id?: string
  claimed_by_device_id?: string
  routing_mode?: string
  device_snapshot?: Record<string, unknown>
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at?: string
}

export interface JobApproval {
  id: string
  job_id: string
  action_type: string
  policy_mode: "manual" | "auto_if_rule"
  expires_at?: string
  decision?: "approved" | "rejected"
  decided_at?: string
  created_at: string
}

export interface NativeApprovalRequest {
  id: string
  job_id: string
  action_type: string
  policy_mode: "manual" | "auto_if_rule"
  expires_at?: string
  decision?: "approved" | "rejected"
}

export interface IntegrationConnection {
  id: string
  provider: string
  account_ref?: string
  scopes: string[]
  health_status: string
  created_at: string
}

export interface AutomationRule {
  id: string
  name: string
  trigger: Record<string, unknown>
  condition?: Record<string, unknown>
  action: Record<string, unknown>
  approval_policy: string
  limit?: Record<string, unknown>
  is_active: boolean
  created_at: string
}
