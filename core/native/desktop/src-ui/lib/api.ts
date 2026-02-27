/**
 * Native App API client — talks to the VisionArk backend.
 * In Tauri: direct to http://localhost:8000
 * In browser dev: via Vite proxy (relative /api/... URLs)
 */

// Detect Tauri environment
const IS_TAURI = !!(window as any).__TAURI_INTERNALS__ || !!(window as any).__TAURI__
export const BASE_URL = IS_TAURI ? "http://localhost:8000" : "http://localhost:8000" // For local native dev, force 8000

function getToken(): string | null {
    try {
        return localStorage.getItem("atmos_access_token")
    } catch {
        return null
    }
}

export function setToken(token: string) {
    localStorage.setItem("atmos_access_token", token)
}

export async function apiFetch(
    path: string,
    init: RequestInit = {}
): Promise<Response> {
    const headers: Record<string, string> = {
        ...(init.headers as Record<string, string>),
    }
    const token = getToken()
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }
    return fetch(`${BASE_URL}${path}`, { ...init, headers })
}

export async function apiJson<T>(
    path: string,
    init: RequestInit = {}
): Promise<T> {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(init.headers as Record<string, string>),
    }
    const token = getToken()
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }
    const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
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
    if (!res.ok) throw new Error("Login failed")
    const data = await res.json()
    setToken(data.access_token)
    return data
}

export function isLoggedIn(): boolean {
    return !!getToken()
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
