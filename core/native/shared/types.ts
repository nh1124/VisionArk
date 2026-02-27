export type RiskLevel = "low" | "medium" | "high" | "critical"
export type JobStatus = "queued" | "running" | "needs_approval" | "succeeded" | "failed" | "rejected"
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
