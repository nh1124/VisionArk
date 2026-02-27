import type { Job, IntegrationConnection, AutomationRule } from "../shared/types"

const BASE_URL = "http://localhost:8000"

let _token: string | null = null

export function setToken(token: string) {
  _token = token
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  }
  if (_token) {
    headers["Authorization"] = `Bearer ${_token}`
  }
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ─── Jobs ────────────────────────────────────────────────────────────────────

export async function createJob(payload: {
  type: string
  payload?: Record<string, unknown>
  source?: string
  project_id?: string
  risk_level?: string
  tags?: string[]
}): Promise<Job> {
  return request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) })
}

export async function listJobs(params?: {
  source?: string
  status?: string
  type?: string
  limit?: number
}): Promise<Job[]> {
  const qs = new URLSearchParams()
  if (params?.source) qs.set("source", params.source)
  if (params?.status) qs.set("status", params.status)
  if (params?.type) qs.set("type", params.type)
  if (params?.limit) qs.set("limit", String(params.limit))
  return request<Job[]>(`/api/jobs?${qs.toString()}`)
}

export async function getJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`)
}

export async function updateJobStatus(
  id: string,
  status: string,
  extras?: { error_log?: string; result?: Record<string, unknown> }
): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status, ...extras }),
  })
}

export async function approveJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}/approve`, { method: "POST" })
}

export async function rejectJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}/reject`, { method: "POST" })
}

// ─── Integrations ─────────────────────────────────────────────────────────────

export async function listIntegrations(): Promise<IntegrationConnection[]> {
  return request<IntegrationConnection[]>("/api/native/integrations")
}

export async function createIntegration(payload: {
  provider: string
  account_ref?: string
  scopes?: string[]
}): Promise<IntegrationConnection> {
  return request<IntegrationConnection>("/api/native/integrations", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

// ─── Rules ───────────────────────────────────────────────────────────────────

export async function listRules(): Promise<AutomationRule[]> {
  return request<AutomationRule[]>("/api/native/rules")
}

export async function createRule(payload: {
  name: string
  trigger: Record<string, unknown>
  condition?: Record<string, unknown>
  action: Record<string, unknown>
  approval_policy?: string
  limit?: Record<string, unknown>
}): Promise<AutomationRule> {
  return request<AutomationRule>("/api/native/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
