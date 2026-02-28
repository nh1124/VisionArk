/**
 * Native App API client — talks to the VisionArk backend.
 * In Tauri: direct to http://localhost:8000
 * In browser dev: via Vite proxy (relative /api/... URLs)
 */

// Detect Tauri environment
import { invoke, isTauri } from '@tauri-apps/api/core';

const IS_TAURI = isTauri()
export const BASE_URL = IS_TAURI ? "http://localhost:8000" : "http://localhost:8000" // For local native dev, force 8000

export async function getToken(): Promise<string | null> {
    if (!IS_TAURI) {
        return localStorage.getItem("atmos_access_token")
    }
    try {
        const token = await invoke<string>("get_secure_token", { key: "atmos_access_token" });
        return token || null; // Return null if empty string
    } catch (e) {
        console.error("Keychain GetToken Error:", e);
        return null;
    }
}

export async function getRefreshToken(): Promise<string | null> {
    if (!IS_TAURI) {
        return localStorage.getItem("atmos_refresh_token")
    }
    try {
        const token = await invoke<string>("get_secure_token", { key: "atmos_refresh_token" });
        return token || null; // Return null if empty string
    } catch (e) {
        console.error("Keychain GetRefreshToken Error:", e);
        return null;
    }
}

export async function setToken(token: string): Promise<void> {
    if (!IS_TAURI) {
        localStorage.setItem("atmos_access_token", token)
        return;
    }
    try {
        await invoke("set_secure_token", { key: "atmos_access_token", value: token });
    } catch (e) {
        console.error("Keychain SetToken Error:", e);
        throw e;
    }
}

export async function setRefreshToken(token: string): Promise<void> {
    if (!IS_TAURI) {
        localStorage.setItem("atmos_refresh_token", token)
        return;
    }
    try {
        await invoke("set_secure_token", { key: "atmos_refresh_token", value: token });
    } catch (e) {
        console.error("Keychain SetRefreshToken Error:", e);
        throw e;
    }
}

export async function clearTokens(): Promise<void> {
    if (!IS_TAURI) {
        localStorage.removeItem("atmos_access_token")
        localStorage.removeItem("atmos_refresh_token")
        return;
    }
    try { await invoke("delete_secure_token", { key: "atmos_access_token" }); } catch { }
    try { await invoke("delete_secure_token", { key: "atmos_refresh_token" }); } catch { }
}

let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

function onRefreshed(token: string) {
    refreshSubscribers.forEach(cb => cb(token));
    refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string) => void) {
    refreshSubscribers.push(cb);
}

async function handleRefresh(): Promise<string | null> {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) {
        await clearTokens();
        return null;
    }

    if (isRefreshing) {
        return new Promise(resolve => {
            addRefreshSubscriber(token => resolve(token));
        });
    }

    isRefreshing = true;

    try {
        const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        if (!res.ok) {
            await clearTokens();
            onRefreshed("");
            return null;
        }

        const data = await res.json();
        await setToken(data.access_token);
        if (data.refresh_token) {
            await setRefreshToken(data.refresh_token);
        }

        onRefreshed(data.access_token);
        return data.access_token;
    } catch (e) {
        await clearTokens();
        onRefreshed("");
        return null;
    } finally {
        isRefreshing = false;
    }
}

export async function apiFetch(
    path: string,
    init: RequestInit = {}
): Promise<Response> {
    const headers: Record<string, string> = {
        ...(init.headers as Record<string, string>),
    }
    const token = await getToken()
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }
    // Inject browser/system timezone for LBS date-boundary accuracy
    headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
    console.log(`[AuthDebug] apiFetch ${path} - Token: ${token ? 'Yes' : 'No'}`);
    let res = await fetch(`${BASE_URL}${path}`, { ...init, headers })

    if (res.status === 401 && (await getRefreshToken())) {
        const newToken = await handleRefresh();
        if (newToken) {
            headers["Authorization"] = `Bearer ${newToken}`
            res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
        }
    }

    return res;
}

export async function apiJson<T>(
    path: string,
    init: RequestInit = {}
): Promise<T> {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(init.headers as Record<string, string>),
    }
    const token = await getToken()
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }
    // Inject browser/system timezone for LBS date-boundary accuracy
    headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
    let res = await fetch(`${BASE_URL}${path}`, { ...init, headers })

    if (res.status === 401 && (await getRefreshToken())) {
        const newToken = await handleRefresh();
        if (newToken) {
            headers["Authorization"] = `Bearer ${newToken}`
            res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
        }
    }

    if (!res.ok) {
        const text = await res.text()
        throw new Error(`API ${res.status}: ${text}`)
    }
    return res.json() as Promise<T>
}

// ─── Auth ──────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string) {
    const res = await fetch(`${BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
        console.error("Login API returned non-OK:", res.status);
        throw new Error("Login failed");
    }
    const data = await res.json()
    console.log("[AuthDebug] Login successful, saving tokens...");
    try {
        await setToken(data.access_token)
        console.log("[AuthDebug] Access token saved OK");
        if (data.refresh_token) {
            await setRefreshToken(data.refresh_token)
            console.log("[AuthDebug] Refresh token saved OK");
        }
    } catch (e) {
        console.error("[AuthDebug] Failed to save tokens!", e);
        throw new Error("Failed to save tokens securely");
    }
    return data
}

export async function isLoggedIn(): Promise<boolean> {
    const token = await getToken();
    console.log("[AuthDebug] IS_TAURI:", IS_TAURI);
    console.log("[AuthDebug] Token retrieved:", token ? "Yes (" + token.substring(0, 10) + "...)" : "No");
    return !!token;
}

export async function logout(): Promise<void> {
    await clearTokens();
}

// ─── Projects ──────────────────────────────────────────────────────────────────

export interface Project {
    id: string
    name: string
    display_name?: string | null
    path: string
}

export async function listProjects(): Promise<Project[]> {
    const res = await apiJson<{ projects: Project[] }>("/api/agents/project/list")
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
    const data = await apiJson<{ sessions: Session[] }>(
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
    const res = await apiFetch(`${baseUrl}?limit=50&t=${Date.now()}`)
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
    model?: string
): Promise<{ task_id: string }> {
    const formData = new FormData()
    formData.append("message", message)

    // session_id is computed backend side via default_session selection
    // if needed in the future, we could append it to formData.

    const headers: Record<string, string> = {}
    if (model) {
        headers["X-Preferred-Model"] = model
    }

    const res = await apiFetch(`/api/agents/project/${projectId}/chat`, {
        method: "POST",
        body: formData,
        headers,
    })

    if (!res.ok) {
        const text = await res.text()
        throw new Error(`Chat API ${res.status}: ${text}`)
    }

    return res.json() as Promise<{ task_id: string }>
}

// ─── Task Polling ──────────────────────────────────────────────────────────────

export async function getTaskStatus(
    taskId: string
): Promise<{ status: string; result?: string }> {
    return apiJson<{ status: string; result?: string }>(
        `/api/agents/tasks/${taskId}`
    )
}

// ─── Files & Notes ─────────────────────────────────────────────────────────────

export async function getFileToken(): Promise<string> {
    const res = await apiJson<{ file_token: string; expires_in: number }>("/api/auth/file-token")
    return res.file_token
}


// ─── Dashboard ─────────────────────────────────────────────────────────────────

export async function getDashboard(): Promise<any> {
    return apiJson<any>("/api/lbs/dashboard")
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
    status?: string | null  // "todo" | "done" | "skipped" — present when merged with schedule
    start_time?: string | null
    end_time?: string | null
    meta_payload?: Record<string, any>
}

export async function listLBSTasks(opts?: {
    targetDate?: string  // YYYY-MM-DD — merges schedule status
    active?: boolean
    context?: string
}): Promise<LBSTask[]> {
    const params = new URLSearchParams()
    if (opts?.targetDate) params.set("target_date", opts.targetDate)
    if (opts?.active !== undefined) params.set("active", String(opts.active))
    if (opts?.context) params.set("context", opts.context)
    const qs = params.toString()
    return apiJson<LBSTask[]>(`/api/lbs/tasks${qs ? `?${qs}` : ""}`)
}

export async function completeLBSTask(
    taskId: string,
    targetDate: string,
    status: "done" | "todo" | "skipped" = "done"
): Promise<any> {
    return apiJson<any>(`/api/lbs/tasks/${taskId}/complete`, {
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
    return apiJson<LBSTask>("/api/lbs/tasks", {
        method: "POST",
        body: JSON.stringify(task),
    })
}

export async function getOverdueTasks(): Promise<LBSTask[]> {
    return apiJson<LBSTask[]>("/api/lbs/overdue")
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
    const qs = targetDate ? `?target_date=${targetDate}` : ''
    return apiJson<LBSTaskFull>(`/api/lbs/tasks/${taskId}${qs}`)
}

export async function updateLBSTask(taskId: string, data: Partial<LBSTaskFull>, forceOverride = true): Promise<LBSTaskFull> {
    return apiJson<LBSTaskFull>(`/api/lbs/tasks/${taskId}?force_override=${forceOverride}`, {
        method: "PUT",
        body: JSON.stringify(data),
    })
}

export async function deleteLBSTask(taskId: string): Promise<void> {
    await apiJson<any>(`/api/lbs/tasks/${taskId}?force_override=true`, { method: "DELETE" })
}

export async function getSchedule(startDate: string, endDate: string): Promise<LBSScheduleDay[]> {
    const res = await apiFetch(`/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`)
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
    return apiJson<any>('/api/lbs/exceptions?force_override=true', {
        method: "POST",
        body: JSON.stringify(data),
    })
}
