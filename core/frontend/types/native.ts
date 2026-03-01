export type RiskLevel = "low" | "medium" | "high" | "critical"
export type JobStatus = "queued" | "running" | "needs_approval" | "succeeded" | "failed" | "rejected"
export type JobSource = "native" | "web" | "cloud" | "mobile" | string
export type JobType = string

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
  routing_mode: string
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at?: string
}
