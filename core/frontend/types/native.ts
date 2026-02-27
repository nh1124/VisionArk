export type RiskLevel = "low" | "medium" | "high" | "critical"
export type JobStatus = "queued" | "running" | "needs_approval" | "succeeded" | "failed" | "rejected"
export type JobSource = "native" | "web" | "cloud" | "mobile" | string
export type JobType = string

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
