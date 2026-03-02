import type {
  NativeDevice, IntegrationConnection, AutomationRule,
  AgentRun, RunExecution, RunApproval,
} from "../shared/types"

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
  /** Returns true if running in a Tauri environment */
  isTauri?: () => boolean
  /** The Tauri invoke function */
  invoke?: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>
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

  if (!isFormData && cfg().isTauri?.()) {
    // ── Rust transport (bridge-rs) ───────────────────────────────────────────
    const bodyStr =
      init.body != null && typeof init.body === "string" ? init.body : undefined

    const invokeFn = cfg().invoke
    if (invokeFn) {
      const result = await invokeFn<{ status: number; body: string }>("bridge_request", {
        url: `${cfg().getBaseUrl()}${path}`,
        method: (init.method ?? "GET").toUpperCase(),
        body: bodyStr,
        headers,
      })
      return new Response(result.body, { status: result.status })
    }
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

// ─── Devices ──────────────────────────────────────────────────────────────────

export async function listDevices(): Promise<NativeDevice[]> {
  return _json<NativeDevice[]>("/api/native/devices")
}

export async function registerDevice(payload: {
  display_name: string
  device_kind?: string
  platform?: string
  client_version?: string
  capabilities?: string[]
}): Promise<NativeDevice> {
  return _json<NativeDevice>("/api/native/devices/register", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function heartbeatDevice(device_id: string): Promise<NativeDevice> {
  return _json<NativeDevice>(`/api/native/devices/${device_id}/heartbeat`, { method: "POST" })
}

export async function patchDevice(
  device_id: string,
  patch: { display_name?: string; is_enabled?: boolean }
): Promise<NativeDevice> {
  return _json<NativeDevice>(`/api/native/devices/${device_id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

export async function deleteDevice(device_id: string): Promise<void> {
  await _void(`/api/native/devices/${device_id}`, { method: "DELETE" })
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

// ─── Runs ─────────────────────────────────────────────────────────────────────

export async function createRun(payload: {
  project_id?: string
  agent_id?: string
  session_id?: string
  summary?: string
}): Promise<AgentRun> {
  return _json<AgentRun>("/api/runs", { method: "POST", body: JSON.stringify(payload) })
}

export async function listRuns(params?: {
  status?: string
  limit?: number
}): Promise<AgentRun[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set("status", params.status)
  if (params?.limit) qs.set("limit", String(params.limit))
  return _json<AgentRun[]>(`/api/runs?${qs.toString()}`)
}

export async function getRun(run_id: string): Promise<AgentRun> {
  return _json<AgentRun>(`/api/runs/${run_id}`)
}

export async function updateRun(run_id: string, status: string, summary?: string): Promise<AgentRun> {
  return _json<AgentRun>(`/api/runs/${run_id}`, {
    method: "PATCH",
    body: JSON.stringify({ status, summary }),
  })
}

export async function addExecution(run_id: string, payload: {
  kind: string
  payload?: Record<string, unknown>
  risk_level?: string
  target_device_id?: string
}): Promise<RunExecution> {
  return _json<RunExecution>(`/api/runs/${run_id}/executions`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function updateExecution(
  run_id: string,
  exec_id: string,
  status: string,
  extras?: { result?: Record<string, unknown>; error_log?: string }
): Promise<RunExecution> {
  return _json<RunExecution>(`/api/runs/${run_id}/executions/${exec_id}`, {
    method: "PATCH",
    body: JSON.stringify({ status, ...extras }),
  })
}

export async function approveExecution(run_id: string, approval_id: string): Promise<RunApproval> {
  return _json<RunApproval>(`/api/runs/${run_id}/approve/${approval_id}`, { method: "POST" })
}

export async function rejectExecution(run_id: string, approval_id: string): Promise<RunApproval> {
  return _json<RunApproval>(`/api/runs/${run_id}/reject/${approval_id}`, { method: "POST" })
}

export async function pullExecutions(params: {
  device_id: string
  limit?: number
}): Promise<RunExecution[]> {
  const qs = new URLSearchParams({ device_id: params.device_id })
  if (params.limit) qs.set("limit", String(params.limit))
  return _json<RunExecution[]>(`/api/runs/pull?${qs.toString()}`)
}

export async function claimExecution(exec_id: string, device_id: string): Promise<RunExecution> {
  return _json<RunExecution>(
    `/api/runs/executions/${exec_id}/claim?device_id=${encodeURIComponent(device_id)}`,
    { method: "POST" }
  )
}
