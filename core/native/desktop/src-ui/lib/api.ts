/**
 * Native App API client — talks to the VisionArk backend.
 *
 * Responsibilities:
 *   • URL management  : read/write config.toml (Tauri) or localStorage (browser)
 *   • Token management: Tauri secure keychain or localStorage
 *   • Token refresh   : handleRefresh() exported for bridge configuration
 *   • Domain functions: projects, sessions, chat, LBS, files, etc.
 *
 * HTTP mechanics (retry, timeout, auth injection) live in bridge/api.ts.
 * This module imports and re-exports bridge's apiFetch/apiJson so existing
 * component imports from "./lib/api" continue to work without changes.
 */

import { invoke, isTauri } from '@tauri-apps/api/core';
import {
  apiFetch as _apiFetch,
  apiJson as _apiJson,
} from "../../../bridge/api"

const IS_TAURI = isTauri()

// ─── API Base URL (configurable) ───────────────────────────────────────────────
//
//   Tauri  → {config_dir}/visionark/config.toml  (shared with daemon)
//   Browser→ localStorage["va_api_url"]

const API_URL_STORAGE_KEY = "va_api_url"
const DEFAULT_API_URL = "http://localhost:8000"

export let BASE_URL = DEFAULT_API_URL

function normalizeUrl(url: string): string {
    return url.trim().replace(/\/+$/, "") || DEFAULT_API_URL
}

export async function initApiBase(): Promise<string> {
    if (IS_TAURI) {
        try {
            const cfg = await invoke<{ api_url?: string }>("read_app_config")
            if (cfg.api_url) BASE_URL = normalizeUrl(cfg.api_url)
        } catch {
            // Config file not yet created — use compiled-in default
        }
    } else {
        const stored = localStorage.getItem(API_URL_STORAGE_KEY)
        if (stored) BASE_URL = normalizeUrl(stored)
    }
    return BASE_URL
}

export function getApiBase(): string {
    return BASE_URL
}

export async function setApiBase(url: string): Promise<void> {
    BASE_URL = normalizeUrl(url)
    if (IS_TAURI) {
        try {
            await invoke("write_app_config", { config: { api_url: BASE_URL } })
        } catch (e) {
            console.warn("[Config] write_app_config failed:", e)
        }
    } else {
        localStorage.setItem(API_URL_STORAGE_KEY, BASE_URL)
    }
}

// ─── Token management (Tauri keychain / localStorage) ─────────────────────────

export async function getToken(): Promise<string | null> {
    if (!IS_TAURI) return localStorage.getItem("atmos_access_token")
    try {
        const token = await invoke<string>("get_secure_token", { key: "atmos_access_token" })
        return token || null
    } catch (e) {
        console.error("[Token] get error:", e)
        return null
    }
}

export async function getRefreshToken(): Promise<string | null> {
    if (!IS_TAURI) return localStorage.getItem("atmos_refresh_token")
    try {
        const token = await invoke<string>("get_secure_token", { key: "atmos_refresh_token" })
        return token || null
    } catch (e) {
        console.error("[Token] get refresh error:", e)
        return null
    }
}

export async function setToken(token: string): Promise<void> {
    if (!IS_TAURI) { localStorage.setItem("atmos_access_token", token); return }
    try {
        await invoke("set_secure_token", { key: "atmos_access_token", value: token })
    } catch (e) {
        console.error("[Token] set error:", e)
        throw e
    }
}

export async function setRefreshToken(token: string): Promise<void> {
    if (!IS_TAURI) { localStorage.setItem("atmos_refresh_token", token); return }
    try {
        await invoke("set_secure_token", { key: "atmos_refresh_token", value: token })
    } catch (e) {
        console.error("[Token] set refresh error:", e)
        throw e
    }
}

export async function clearTokens(): Promise<void> {
    if (!IS_TAURI) {
        localStorage.removeItem("atmos_access_token")
        localStorage.removeItem("atmos_refresh_token")
        return
    }
    try { await invoke("delete_secure_token", { key: "atmos_access_token" }) } catch { }
    try { await invoke("delete_secure_token", { key: "atmos_refresh_token" }) } catch { }
}

// ─── Token refresh (exported for bridge configuration) ───────────────────────
//
// Bridge calls handleRefresh() when it receives a 401. The function:
//   1. Retrieves the stored refresh token
//   2. Calls POST /api/auth/refresh (without auth — raw fetch)
//   3. Persists the new tokens and returns the new access token
//   4. Deduplicates concurrent refresh attempts via isRefreshing flag

let isRefreshing = false
let refreshSubscribers: ((token: string) => void)[] = []

function onRefreshed(token: string) {
    refreshSubscribers.forEach(cb => cb(token))
    refreshSubscribers = []
}

export async function handleRefresh(): Promise<string | null> {
    const refreshToken = await getRefreshToken()
    if (!refreshToken) { await clearTokens(); return null }

    if (isRefreshing) {
        return new Promise(resolve => {
            refreshSubscribers.push(token => resolve(token || null))
        })
    }

    isRefreshing = true
    try {
        const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!res.ok) { await clearTokens(); onRefreshed(""); return null }

        const data = await res.json()
        await setToken(data.access_token)
        if (data.refresh_token) await setRefreshToken(data.refresh_token)
        onRefreshed(data.access_token)
        return data.access_token
    } catch {
        await clearTokens(); onRefreshed(""); return null
    } finally {
        isRefreshing = false
    }
}

// ─── HTTP primitives (re-exported from bridge) ────────────────────────────────
//
// Components that import apiFetch/apiJson from "./lib/api" transparently use
// bridge's single HTTP client (retry + timeout + auth injection).

export const apiFetch = _apiFetch
export const apiJson = _apiJson

// ─── Auth ──────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string) {
    // Raw fetch — no auth header needed for login
    const res = await fetch(`${BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    })
    if (!res.ok) throw new Error("Login failed")
    const data = await res.json()
    try {
        await setToken(data.access_token)
        if (data.refresh_token) await setRefreshToken(data.refresh_token)
    } catch (e) {
        console.error("[Auth] Failed to save tokens:", e)
        throw new Error("Failed to save tokens securely")
    }
    return data
}

export async function isLoggedIn(): Promise<boolean> {
    return !!(await getToken())
}

export async function logout(): Promise<void> {
    await clearTokens()
}

// ─── Projects ──────────────────────────────────────────────────────────────────

export interface Project {
    id: string
    name: string
    display_name?: string | null
    path: string
}

export async function listProjects(): Promise<Project[]> {
    const res = await _apiJson<{ projects: Project[] }>("/api/agents/project/list")
    return res.projects
}

// ─── Sessions ──────────────────────────────────────────────────────────────────

export interface Session {
    id: string
    title: string | null
    is_default: boolean
    last_message_at: string | null
}

export async function listSessions(projectId: string): Promise<Session[]> {
    const data = await _apiJson<{ sessions: Session[] }>(
        `/api/agents/project/${projectId}/sessions`
    )
    return data.sessions || []
}

// ─── Chat History ──────────────────────────────────────────────────────────────

export interface ChatMessage {
    role: "user" | "assistant"
    content: string
    tool_calls?: any[]
    sub_messages?: any[]
    meta_payload?: any
    attached_files?: { name: string; size: number; type: string }[]
}

export async function fetchHistory(
    projectId: string,
    sessionId?: string | null
): Promise<ChatMessage[]> {
    const baseUrl = sessionId
        ? `/api/agents/sessions/${sessionId}/history`
        : `/api/agents/project/${projectId}/history`
    const res = await _apiFetch(`${baseUrl}?limit=50&t=${Date.now()}`)
    if (!res.ok) return []
    const data = await res.json()
    const rawItems: any[] = data.items ?? data.history ?? []
    return rawItems.map((m: any) => ({
        role: m.role,
        content: m.content,
        attached_files: m.meta_payload?.attached_files || [],
        tool_calls: m.meta_payload?.tool_calls || [],
        sub_messages: m.sub_messages || [],
        meta_payload: m.meta_payload || {},
    }))
}

// ─── Send Message ──────────────────────────────────────────────────────────────

export async function sendChat(
    projectId: string,
    message: string,
    sessionId?: string | null,
    model?: string,
    files?: File[]
): Promise<{ task_id: string; session_id?: string }> {
    const formData = new FormData()
    formData.append("message", message)
    if (sessionId) formData.append("session_id", sessionId)
    if (files?.length) {
        for (const file of files) formData.append("files", file, file.name)
    }

    const headers: Record<string, string> = {}
    if (model) headers["X-Preferred-Model"] = model

    const res = await _apiFetch(`/api/agents/project/${projectId}/chat`, {
        method: "POST",
        body: formData,
        headers,
    })
    if (!res.ok) {
        const text = await res.text()
        throw new Error(`Chat API ${res.status}: ${text}`)
    }
    return res.json() as Promise<{ task_id: string; session_id?: string }>
}

// ─── Task Polling ──────────────────────────────────────────────────────────────

export async function getTaskStatus(
    taskId: string
): Promise<{ status: string; result?: string; phase?: string; step?: string }> {
    return _apiJson<{ status: string; result?: string; phase?: string; step?: string }>(`/api/agents/tasks/${taskId}`)
}

export async function cancelTask(taskId: string): Promise<void> {
    await _apiFetch(`/api/agents/tasks/${taskId}`, { method: "DELETE" })
}

// ─── Files ─────────────────────────────────────────────────────────────────────

export async function getFileToken(): Promise<string> {
    const res = await _apiJson<{ file_token: string; expires_in: number }>("/api/auth/file-token")
    return res.file_token
}

// ─── Dashboard ─────────────────────────────────────────────────────────────────

export async function getDashboard(): Promise<any> {
    return _apiJson<any>("/api/lbs/dashboard")
}

// ─── LBS Tasks ─────────────────────────────────────────────────────────────────

export interface LBSTask {
    task_id: string
    task_name: string
    context: string
    base_load_score: number
    active: boolean
    rule_type: string
    due_date?: string | null
    notes?: string | null
    status?: string | null
    start_time?: string | null
    end_time?: string | null
    meta_payload?: Record<string, any>
}

export async function listLBSTasks(opts?: {
    targetDate?: string
    active?: boolean
    context?: string
}): Promise<LBSTask[]> {
    const params = new URLSearchParams()
    if (opts?.targetDate) params.set("target_date", opts.targetDate)
    if (opts?.active !== undefined) params.set("active", String(opts.active))
    if (opts?.context) params.set("context", opts.context)
    const qs = params.toString()
    return _apiJson<LBSTask[]>(`/api/lbs/tasks${qs ? `?${qs}` : ""}`)
}

export async function completeLBSTask(
    taskId: string,
    targetDate: string,
    status: "done" | "todo" | "skipped" = "done"
): Promise<any> {
    return _apiJson<any>(`/api/lbs/tasks/${taskId}/complete`, {
        method: "POST",
        body: JSON.stringify({ target_date: targetDate, status }),
    })
}

export interface LBSTaskCreate {
    task_name: string
    context: string
    base_load_score: number
    rule_type: string
    due_date?: string | null
    notes?: string | null
    timezone?: string | null
}

export async function createLBSTask(task: LBSTaskCreate): Promise<LBSTask> {
    return _apiJson<LBSTask>("/api/lbs/tasks", {
        method: "POST",
        body: JSON.stringify(task),
    })
}

export async function getOverdueTasks(): Promise<LBSTask[]> {
    return _apiJson<LBSTask[]>("/api/lbs/overdue")
}

export interface LBSTaskFull extends LBSTask {
    mon?: boolean
    tue?: boolean
    wed?: boolean
    thu?: boolean
    fri?: boolean
    sat?: boolean
    sun?: boolean
    interval_days?: number
    anchor_date?: string | null
    month_day?: number
    nth_in_month?: number
    weekday_mon1?: number
    start_date?: string | null
    end_date?: string | null
    is_locked?: boolean
    timezone?: string | null
    meta_payload?: {
        steps?: { id: string; text: string; done: boolean }[]
        is_my_day?: boolean
        [key: string]: any
    }
}

export interface LBSScheduleDay {
    date: string
    total_load: number
    tasks: Array<{
        task_id: string
        task_name: string
        context: string
        load: number
        status: string
        start_time: string | null
        end_time: string | null
        has_exception: boolean
        is_locked: boolean
    }>
}

export async function getLBSTask(taskId: string, targetDate?: string): Promise<LBSTaskFull> {
    const qs = targetDate ? `?target_date=${targetDate}` : ""
    return _apiJson<LBSTaskFull>(`/api/lbs/tasks/${taskId}${qs}`)
}

export async function updateLBSTask(
    taskId: string,
    data: Partial<LBSTaskFull>,
    forceOverride = true
): Promise<LBSTaskFull> {
    return _apiJson<LBSTaskFull>(`/api/lbs/tasks/${taskId}?force_override=${forceOverride}`, {
        method: "PUT",
        body: JSON.stringify(data),
    })
}

export async function deleteLBSTask(taskId: string): Promise<void> {
    await _apiJson<any>(`/api/lbs/tasks/${taskId}?force_override=true`, { method: "DELETE" })
}

export async function getSchedule(startDate: string, endDate: string): Promise<LBSScheduleDay[]> {
    const res = await _apiFetch(`/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`)
    if (!res.ok) throw new Error(`Schedule API ${res.status}`)
    return res.json()
}

export async function createLBSException(data: {
    task_id: string
    target_date: string
    exception_type: string
    override_load_value?: number
    start_time?: string | null
    end_time?: string | null
    notes?: string | null
}): Promise<any> {
    return _apiJson<any>("/api/lbs/exceptions?force_override=true", {
        method: "POST",
        body: JSON.stringify(data),
    })
}
