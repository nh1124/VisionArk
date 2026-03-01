import type { Job, IntegrationConnection, AutomationRule } from "../shared/types"
import { isTauri, invoke } from "@tauri-apps/api/core"

// ─── Configuration ─────────────────────────────────────────────────────────────
//
// bridge/api.ts is the single HTTP client for the Native layer.
// Both desktop (TypeScript) and its components route all backend requests here.
// The Rust daemon uses bridge-rs (Rust crate) for its HTTP/WS communication.
//
// Transport strategy (Phase 2):
//   • Tauri mode : non-FormData requests route through invoke("bridge_request")
//                  which calls bridge-rs::http::raw_request_str in Rust.
//   • Browser/dev: standard fetch() with AbortController timeout.
//   FormData (file uploads) always use fetch() — multipart is not routed via Rust.
//
// Desktop bootstraps this at startup:
//
//   import { configure } from "../../bridge/api"
//   import { getApiBase, getToken, handleRefresh } from "./lib/api"
//   configure({ getBaseUrl: getApiBase, getToken, handleRefresh })
//
// lib/api.ts then re-exports bridge's apiFetch/apiJson so all existing
// component imports (from lib/api) continue to work unchanged.

interface BridgeConfig {
  /** Returns the current API base URL (e.g. "http://localhost:8000"). */
  getBaseUrl: () => string
  /** Returns the current Bearer token, or null if not authenticated. */
  getToken: () => Promise<string | null>
  /**
   * Called when the server returns 401. Should attempt a token refresh and
   * return the new access token, or null if refresh fails / is not supported.
   * Bridge retries the original request exactly once with the new token.
   */
  handleRefresh?: () => Promise<string | null>
}

let _config: BridgeConfig | null = null

/**
 * Wire the bridge to the desktop's URL and token management.
 * Must be called once at application startup before any requests are made.
 */
export function configure(config: BridgeConfig): void {
  _config = config
}

function cfg(): BridgeConfig {
  if (!_config) {
    throw new Error(
      "[Bridge] configure() must be called at app startup before making requests."
    )
  }
  return _config
}

// ─── HTTP client ──────────────────────────────────────────────────────────────
//
// Features:
//   • Per-request token injection (always fresh — no stale-token risk)
//   • 30-second timeout via AbortController
//   • 5xx retry: up to 2 retries with exponential back-off (1s, 2s)
//   • 401 transparent refresh: calls handleRefresh(), retries once with new token
//   • X-Timezone header for LBS date-boundary accuracy

const TIMEOUT_MS = 30_000
const MAX_RETRIES = 2

/**
 * Single attempt: inject token + X-Timezone, then dispatch via the
 * appropriate transport:
 *   • Tauri + non-FormData → invoke("bridge_request") → bridge-rs (Rust)
 *   • Browser or FormData  → fetch() with 30-second AbortController timeout
 */
async function _once(
  path: string,
  init: RequestInit,
  token: string | null
): Promise<Response> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }
  if (token) headers["Authorization"] = `Bearer ${token}`
  headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"

  // FormData (file uploads) must use fetch — multipart isn't handled by bridge_request
  const isFormData = init.body instanceof FormData

  if (!isFormData && isTauri()) {
    // ── Rust transport (bridge-rs) ───────────────────────────────────────────
    const bodyStr =
      init.body != null && typeof init.body === "string" ? init.body : undefined

    const result = await invoke<{ status: number; body: string }>("bridge_request", {
      url: `${cfg().getBaseUrl()}${path}`,
      method: (init.method ?? "GET").toUpperCase(),
      body: bodyStr,
      headers,
    })
    return new Response(result.body, { status: result.status })
  }

  // ── fetch transport (browser dev mode or FormData) ────────────────────────
  const ctrl = new AbortController()
  const tid = setTimeout(() => ctrl.abort(), TIMEOUT_MS)

  // Always use the enriched `headers` (has Authorization + X-Timezone).
  // For FormData the browser automatically appends Content-Type: multipart/form-data
  // with the correct boundary even when custom headers are provided — as long as
  // we don't explicitly set Content-Type ourselves (we don't for FormData callers).

  try {
    const res = await fetch(`${cfg().getBaseUrl()}${path}`, {
      ...init,
      headers,
      signal: ctrl.signal,
    })
    clearTimeout(tid)
    return res
  } catch (e: unknown) {
    clearTimeout(tid)
    const err = e as Error
    if (err.name === "AbortError") {
      throw new Error(`Request timed out after ${TIMEOUT_MS}ms: ${path}`)
    }
    throw err
  }
}

/**
 * Make an authenticated HTTP request.
 * Returns the raw Response so callers can inspect status / read body themselves.
 */
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  let lastRes: Response | null = null

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await new Promise<void>((r) => setTimeout(r, 1_000 * attempt))
    }

    const token = await cfg().getToken() // fresh token every attempt
    const res = await _once(path, init, token)

    // 401 → try refresh once (first attempt only)
    if (res.status === 401 && attempt === 0) {
      const { handleRefresh } = cfg()
      if (handleRefresh) {
        const newToken = await handleRefresh()
        if (newToken) return _once(path, init, newToken)
      }
    }

    // Non-5xx (2xx / 3xx / 4xx): return immediately
    if (res.status < 500) return res

    // 5xx: schedule retry
    lastRes = res
  }

  return lastRes!
}

/**
 * Make an authenticated JSON request.
 * Throws on non-2xx responses.
 */
export async function apiJson<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  }
  const res = await apiFetch(path, { ...init, headers })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ─── Internal helpers for domain functions ────────────────────────────────────

async function _json<T>(path: string, init?: RequestInit): Promise<T> {
  return apiJson<T>(path, init)
}

/** For endpoints that return 204 No Content (DELETE etc.). */
async function _void(path: string, init?: RequestInit): Promise<void> {
  const res = await apiFetch(path, init ?? {})
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`API ${res.status}: ${text}`)
  }
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
  return _json<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) })
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
  return _json<Job[]>(`/api/jobs?${qs.toString()}`)
}

export async function getJob(id: string): Promise<Job> {
  return _json<Job>(`/api/jobs/${id}`)
}

export async function updateJobStatus(
  id: string,
  status: string,
  extras?: { error_log?: string; result?: Record<string, unknown> }
): Promise<Job> {
  return _json<Job>(`/api/jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status, ...extras }),
  })
}

export async function approveJob(id: string): Promise<Job> {
  return _json<Job>(`/api/jobs/${id}/approve`, { method: "POST" })
}

export async function rejectJob(id: string): Promise<Job> {
  return _json<Job>(`/api/jobs/${id}/reject`, { method: "POST" })
}

export async function retryJob(id: string): Promise<Job> {
  return _json<Job>(`/api/jobs/${id}/retry`, { method: "POST" })
}

// ─── Integrations ─────────────────────────────────────────────────────────────

export async function listIntegrations(): Promise<IntegrationConnection[]> {
  return _json<IntegrationConnection[]>("/api/native/integrations")
}

export async function createIntegration(payload: {
  provider: string
  account_ref?: string
  scopes?: string[]
}): Promise<IntegrationConnection> {
  return _json<IntegrationConnection>("/api/native/integrations", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function deleteIntegration(id: string): Promise<void> {
  await _void(`/api/native/integrations/${id}`, { method: "DELETE" })
}

// ─── Rules ───────────────────────────────────────────────────────────────────

export async function listRules(): Promise<AutomationRule[]> {
  return _json<AutomationRule[]>("/api/native/rules")
}

export async function deleteRule(id: string): Promise<void> {
  await _void(`/api/native/rules/${id}`, { method: "DELETE" })
}

export async function createRule(payload: {
  name: string
  trigger: Record<string, unknown>
  condition?: Record<string, unknown>
  action: Record<string, unknown>
  approval_policy?: string
  limit?: Record<string, unknown>
}): Promise<AutomationRule> {
  return _json<AutomationRule>("/api/native/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
