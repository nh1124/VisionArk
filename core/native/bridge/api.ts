import type { Job, IntegrationConnection, AutomationRule } from "../shared/types"

// ─── Configuration ─────────────────────────────────────────────────────────────
//
// Call configure() at application startup to wire bridge to the shared URL and
// token getters. Without configure(), requests are unauthenticated and fall back
// to the compiled-in default URL.
//
// Usage (App.tsx bootstrap):
//   import { configure } from "../../bridge/api"
//   import { getApiBase, getToken } from "./lib/api"
//   configure({ getBaseUrl: getApiBase, getToken })

type TokenGetter = () => Promise<string | null>

interface BridgeConfig {
  getBaseUrl: () => string
  getToken: TokenGetter
}

let _config: BridgeConfig | null = null

/**
 * Wire the bridge to the shared base URL and token getters.
 * Call once at application startup after initApiBase() resolves.
 */
export function configure(config: BridgeConfig): void {
  _config = config
}

// ─── Legacy setters (backward compatibility) ───────────────────────────────────
// Kept so code that calls setBaseUrl() still works. After configure() is called,
// getBaseUrl() prefers the configured getter over _baseUrl.

let _baseUrl = "http://localhost:8000"

/** @deprecated Prefer configure({ getBaseUrl }) so URL is always in sync. */
export function setBaseUrl(url: string): void {
  _baseUrl = url.trim().replace(/\/+$/, "") || _baseUrl
}

export function getBaseUrl(): string {
  return _config ? _config.getBaseUrl() : _baseUrl
}

/** @deprecated Prefer configure({ getToken }) so token refreshes are automatic. */
export function setToken(_token: string) {
  // no-op — tokens are now retrieved per-request via configure()
}

// ─── HTTP client ──────────────────────────────────────────────────────────────

const TIMEOUT_MS = 30_000
const MAX_RETRIES = 2

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const baseUrl = getBaseUrl()
  const token = _config ? await _config.getToken() : null

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  }
  if (token) headers["Authorization"] = `Bearer ${token}`

  let lastError: Error = new Error("Request failed")

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await new Promise<void>((r) => setTimeout(r, 1_000 * attempt))
    }
    try {
      const ctrl = new AbortController()
      const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
      let res: Response
      try {
        res = await fetch(`${baseUrl}${path}`, { ...init, headers, signal: ctrl.signal })
      } finally {
        clearTimeout(tid)
      }
      if (res.ok) return res.json() as Promise<T>
      // 4xx: client error — do not retry
      if (res.status < 500) {
        const text = await res.text()
        throw new Error(`API ${res.status}: ${text}`)
      }
      // 5xx: server error — retry
      lastError = new Error(`API ${res.status}`)
    } catch (e: unknown) {
      const err = e as Error
      if (err.name === "AbortError") {
        lastError = new Error(`Request timed out (${TIMEOUT_MS}ms)`)
      } else {
        lastError = err
      }
    }
  }
  throw lastError
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

export async function retryJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}/retry`, { method: "POST" })
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

export async function deleteIntegration(id: string): Promise<void> {
  await request<void>(`/api/native/integrations/${id}`, { method: "DELETE" })
}

// ─── Rules ───────────────────────────────────────────────────────────────────

export async function listRules(): Promise<AutomationRule[]> {
  return request<AutomationRule[]>("/api/native/rules")
}

export async function deleteRule(id: string): Promise<void> {
  await request<void>(`/api/native/rules/${id}`, { method: "DELETE" })
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
