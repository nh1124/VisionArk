import React, { useCallback, useEffect, useRef, useState } from "react"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow } from "@tauri-apps/api/window"
import { invoke, isTauri } from "@tauri-apps/api/core"
export type ProjectSidebarMode = "files" | "automation" | "notes" | "settings" | null;
import NavSidebar, { type CalendarStatusFilter, type NavView, type TaskFilter } from "./components/NavSidebar"
import TopBar from "./components/TopBar"
import DashboardView from "./components/DashboardView"
import RunCenterView from "./components/RunCenterView"
import ChatView from "./components/ChatView"
import LoginScreen from "./components/LoginScreen"
import NotesView from "./components/NotesView"
import CronTasksView from "./components/CronTasksView"
import MonitoringJobsView from "./components/MonitoringJobsView"
import WorkspaceView from "./components/WorkspaceView"
import ProjectsView from "./components/ProjectsView"
import AgentsView from "./components/AgentsView"
import TasksView from "./components/TasksView"
import SettingsView from "./components/SettingsView"
import DevicesView from "./components/DevicesView"
import DaemonConsole from "./components/DaemonConsole"
import FileViewerWindow from "./components/FileViewerWindow"
import { isLoggedIn, logout, listProjects, initApiBase, getApiBase, getToken, handleRefresh, getMe, type Project } from "./lib/api"
import { listRuns, configure as configureBridge } from "../../bridge/api"
import * as bridgeWs from "../../bridge/ws"

const daemonStartState = {
  inFlight: false,
  issued: false,
}

export default function App() {
  const [windowLabel] = useState(() => isTauri() ? getCurrentWindow().label : "main")
  const isConsole = windowLabel === "console"
  const isFileViewer = windowLabel.startsWith("fileviewer")
  if (isConsole) return <DaemonConsole />
  if (isFileViewer) return <FileViewerWindow />
  return <MainApp windowLabel={windowLabel} />
}

function MainApp({ windowLabel }: { windowLabel: string }) {
  const [loggedIn, setLoggedIn] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [username, setUsername] = useState("")
  const [userId, setUserId] = useState("")
  const [view, setView] = useState<NavView>("dashboard")
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedProjectName, setSelectedProjectName] = useState("")
  const [pendingApprovals, setPendingApprovals] = useState(0)
  const [projects, setProjects] = useState<Project[]>([])
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("today")
  const [taskFilterContext, setTaskFilterContext] = useState<string | undefined>(undefined)
  const [calendarStatusFilter, setCalendarStatusFilter] = useState<CalendarStatusFilter>("all")
  const [projectSidebarMode, setProjectSidebarMode] = useState<ProjectSidebarMode>(null)
  const [primaryCollapsed, setPrimaryCollapsed] = useState(false)
  const lastJobEventSigRef = useRef<Map<string, string>>(new Map())
  const lastUiDispatchAtRef = useRef<Map<string, number>>(new Map())
  const lastSeqRef = useRef<Map<string, number>>(new Map())
  const eventQueueRef = useRef<unknown[]>([])
  const eventQueueRunningRef = useRef(false)
  const lastQueueOverflowLogAtRef = useRef(0)

  const appendClientLog = useCallback((level: string, message: string, context?: unknown) => {
    const ctxString = context == null ? undefined : (() => {
      try {
        return JSON.stringify(context)
      } catch {
        return String(context)
      }
    })()
    const appendFallback = (err?: unknown) => {
      try {
        const raw = localStorage.getItem("va_client_log_fallback")
        const prev = raw ? JSON.parse(raw) : []
        const next = Array.isArray(prev) ? prev : []
        next.push({
          ts: new Date().toISOString(),
          level,
          message,
          context: ctxString,
          invoke_error: err ? String(err) : undefined,
        })
        while (next.length > 200) next.shift()
        localStorage.setItem("va_client_log_fallback", JSON.stringify(next))
      } catch {
        // ignore storage failures
      }
    }
    if (isTauri()) {
      invoke("append_client_log", { level, message, context: ctxString }).catch((err) => {
        console.error("[client-log] append_client_log failed", err)
        appendFallback(err)
      })
    } else {
      console[level === "error" ? "error" : "log"](`[client-log][${level}] ${message}`, context ?? "")
      appendFallback()
    }
  }, [])

  useEffect(() => {
    appendClientLog("info", "renderer.mounted", { window_label: windowLabel })
    const onBeforeUnload = () => {
      appendClientLog("info", "renderer.beforeunload", { window_label: windowLabel })
    }
    const onPageHide = () => {
      appendClientLog("info", "renderer.pagehide", { window_label: windowLabel })
    }
    window.addEventListener("beforeunload", onBeforeUnload)
    window.addEventListener("pagehide", onPageHide)
    return () => {
      appendClientLog("info", "renderer.unmounted", { window_label: windowLabel })
      window.removeEventListener("beforeunload", onBeforeUnload)
      window.removeEventListener("pagehide", onPageHide)
    }
  }, [appendClientLog, windowLabel])

  useEffect(() => {
    const bootstrap = async () => {
      // 1. Restore stored server URL
      const bootApiBase = await initApiBase()
      appendClientLog("info", "bootstrap.start", { window_label: windowLabel, api_base: bootApiBase })
      // 2. Wire bridge (the HTTP client) to desktop's URL/token/refresh management
      configureBridge({ getBaseUrl: getApiBase, getToken, handleRefresh })
      // 3. Now check authentication
      let status = await isLoggedIn()
      if (status) {
        try {
          const profile = await getMe()
          setUsername(profile.username)
          setUserId(profile.user_id)
          appendClientLog("info", "bootstrap.authenticated", { user_id: profile.user_id, window_label: windowLabel })
        } catch (e) {
          const errText = e instanceof Error ? e.message : String(e)
          const isAuthFailure = /API\s(401|403)\b/.test(errText)
          if (isAuthFailure) {
            console.warn("Failed to fetch user profile due to auth error, clearing auth state", e)
            appendClientLog("error", "bootstrap.profile_fetch_failed_auth", { error: String(e), window_label: windowLabel })
            status = false
            await logout()
          } else {
            // Keep auth state on transient network errors (e.g. backend reboot).
            console.warn("Failed to fetch user profile (transient), keeping auth state", e)
            appendClientLog("error", "bootstrap.profile_fetch_failed_transient", { error: String(e), window_label: windowLabel })
          }
        }
      }
      setLoggedIn(status)
      setAuthChecked(true)
    }
    bootstrap()
  }, [appendClientLog, windowLabel])

  useEffect(() => {
    if (!loggedIn || userId) return
    let cancelled = false
    const retryLoadProfile = async () => {
      try {
        const profile = await getMe()
        if (cancelled) return
        setUsername(profile.username)
        setUserId(profile.user_id)
        appendClientLog("info", "bootstrap.profile_recovered", { user_id: profile.user_id, window_label: windowLabel })
      } catch (e) {
        appendClientLog("warn", "bootstrap.profile_retry_failed", { error: String(e), window_label: windowLabel })
      }
    }
    retryLoadProfile()
    const timer = setInterval(retryLoadProfile, 15_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [loggedIn, userId, appendClientLog, windowLabel])

  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      const payload = {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      }
      localStorage.setItem("va_last_renderer_error", JSON.stringify(payload))
      appendClientLog("error", "renderer.error", payload)
    }
    const onUnhandled = (event: PromiseRejectionEvent) => {
      const reason = event.reason instanceof Error ? event.reason.stack || event.reason.message : String(event.reason)
      const payload = { reason }
      localStorage.setItem("va_last_renderer_unhandled_rejection", JSON.stringify(payload))
      appendClientLog("error", "renderer.unhandled_rejection", payload)
    }
    window.addEventListener("error", onError)
    window.addEventListener("unhandledrejection", onUnhandled)
    return () => {
      window.removeEventListener("error", onError)
      window.removeEventListener("unhandledrejection", onUnhandled)
    }
  }, [appendClientLog])

  useEffect(() => {
    if (!loggedIn) return
    listProjects().then(setProjects).catch(() => { })
    const startDaemon = async () => {
      // UI responsibility: daemon start trigger only.
      if (isTauri()) {
        if (daemonStartState.inFlight || daemonStartState.issued) {
          return
        }
        daemonStartState.inFlight = true
        const token = await getToken()
        const apiUrl = getApiBase()
        if (!token) {
          daemonStartState.inFlight = false
          console.warn(
            `[daemon-start-skip] apiUrl=${apiUrl} deviceId=(empty) tokenPresent=false`
          )
        } else {
          try {
            await invoke("start_daemon_command", { apiUrl, token, deviceId: "" })
            daemonStartState.issued = true
          } catch (e) {
            console.error(
              `[daemon-start-failed] apiUrl=${apiUrl} deviceId=(empty) tokenPresent=true`,
              e
            )
          } finally {
            daemonStartState.inFlight = false
          }
        }
      }
    }

    startDaemon()
  }, [loggedIn])

  useEffect(() => {
    if (selectedProjectId) {
      localStorage.setItem("va_active_project_id", selectedProjectId)
    } else {
      localStorage.removeItem("va_active_project_id")
    }
  }, [selectedProjectId])

  const handleNavChange = useCallback(
    (newView: NavView, projectId?: string, sessionId?: string) => {
      setView(newView)
      if (projectId) {
        setSelectedProjectId(projectId)
        setSelectedSessionId((prev) => {
          const hasExplicitSession = !!(sessionId && sessionId.trim().length > 0)
          // Guard: do not drop current session on same-project navigation
          // when caller omitted sessionId.
          if (!hasExplicitSession && selectedProjectId === projectId) {
            return prev
          }
          return hasExplicitSession ? sessionId! : null
        })
        const project = projects.find((p) => p.id === projectId)
        setSelectedProjectName(project?.display_name || project?.name || "Project")
        setProjectSidebarMode(null) // Reset sidebar when switching projects
      }
    },
    [projects, selectedProjectId]
  )

  useEffect(() => {
    const onNotificationOpen = (evt: Event) => {
      const detail = (evt as CustomEvent<any>).detail || {}
      const view = String(detail.view || "")

      if (view === "monitoring") {
        setView("monitoring")
        return
      }
      if (view === "run_center") {
        setView("run_center")
        return
      }
      if (view === "chat" && detail.project_id) {
        handleNavChange("chat", String(detail.project_id), detail.session_id ? String(detail.session_id) : undefined)
      }
    }

    window.addEventListener("va-open-notification", onNotificationOpen as EventListener)
    return () => window.removeEventListener("va-open-notification", onNotificationOpen as EventListener)
  }, [handleNavChange])

  const handleTaskFilterChange = useCallback((filter: TaskFilter, context?: string) => {
    setTaskFilter(filter)
    setTaskFilterContext(context)
  }, [])

  useEffect(() => {
    const onGlobalNavShortcut = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || !e.shiftKey || e.altKey) return
      const key = e.key.toLowerCase()

      if (key === "h") {
        e.preventDefault()
        e.stopPropagation()
        setView("dashboard")
        return
      }
      if (key === "t") {
        e.preventDefault()
        e.stopPropagation()
        setView("tasks")
        return
      }
      if (key === "p") {
        e.preventDefault()
        e.stopPropagation()
        setView("projects")
        return
      }
      if (key === "n") {
        e.preventDefault()
        e.stopPropagation()
        setView("notes")
        return
      }
      if (key === "s") {
        e.preventDefault()
        e.stopPropagation()
        const raw = localStorage.getItem("va_last_command_session")
        if (!raw) return
        try {
          const parsed = JSON.parse(raw) as { project_id?: string; session_id?: string | null }
          if (!parsed.project_id) return
          handleNavChange("chat", parsed.project_id, parsed.session_id || undefined)
        } catch {
          // ignore malformed cache
        }
      }
    }

    window.addEventListener("keydown", onGlobalNavShortcut, { capture: true })
    return () => window.removeEventListener("keydown", onGlobalNavShortcut, { capture: true })
  }, [handleNavChange])

  const handleLogout = useCallback(async () => {
    bridgeWs.disconnect()
    await logout()
    setLoggedIn(false)
    setUsername("")
    setUserId("")
  }, [])

  // Real-time sync via backend notification WebSocket (job.* events).
  useEffect(() => {
    if (!loggedIn || !userId) return
    let offCreated: (() => void) | null = null
    let offUpdated: (() => void) | null = null
    let offNotification: (() => void) | null = null
    let disposed = false

    const setup = async () => {
      const token = await getToken()
      if (!token || disposed) return

      const apiBase = getApiBase()
      const wsBase = apiBase.replace("http://", "ws://").replace("https://", "wss://")
      const wsUrl = `${wsBase}/api/notifications/ws/${userId}`
      appendClientLog("info", "ws.connecting", { window_label: windowLabel, ws_url: wsUrl })

      bridgeWs.connect(wsUrl, token)

      const enqueueRealtimeEvent = (detail: unknown) => {
        const MAX_EVENT_QUEUE = 400
        if (eventQueueRef.current.length >= MAX_EVENT_QUEUE) {
          // Keep most recent events when burst traffic arrives.
          eventQueueRef.current.shift()
          const now = Date.now()
          if (now - lastQueueOverflowLogAtRef.current > 5000) {
            appendClientLog("warn", "ws.event_queue_overflow", { queue_len: eventQueueRef.current.length })
            lastQueueOverflowLogAtRef.current = now
          }
        }
        eventQueueRef.current.push(detail)
        if (eventQueueRunningRef.current) return
        eventQueueRunningRef.current = true

        const pump = () => {
          const next = eventQueueRef.current.shift()
          if (next === undefined) {
            eventQueueRunningRef.current = false
            return
          }
          window.dispatchEvent(new CustomEvent("va-realtime-job", { detail: next }))
          if (typeof window.requestAnimationFrame === "function") {
            window.requestAnimationFrame(() => pump())
          } else {
            setTimeout(pump, 16)
          }
        }
        pump()
      }

      const dispatch = (eventType: string) => (data: unknown) => {
        let detail = data as any
        if (eventType === "job.updated" && detail && typeof detail === "object") {
          const taskId = String(detail.task_id || "")
          const status = String(detail.status || "")
          const phase = String(detail.phase || "")
          const step = String(detail.step || "")
          const msg = String(detail.message || "")
          const seq = Number(detail.seq ?? 0)

          if (taskId && Number.isFinite(seq) && seq > 0) {
            const prevSeq = lastSeqRef.current.get(taskId) || 0
            if (seq <= prevSeq) {
              return
            }
            lastSeqRef.current.set(taskId, seq)
            if (lastSeqRef.current.size > 500) {
              const firstKey = lastSeqRef.current.keys().next().value
              if (firstKey) lastSeqRef.current.delete(firstKey)
            }
          }

          const signature = `${status}|${phase}|${step}|${msg.slice(0, 120)}`
          if (taskId) {
            const prev = lastJobEventSigRef.current.get(taskId)
            if (prev === signature) {
              return
            }
            lastJobEventSigRef.current.set(taskId, signature)
            if (lastJobEventSigRef.current.size > 200) {
              const firstKey = lastJobEventSigRef.current.keys().next().value
              if (firstKey) lastJobEventSigRef.current.delete(firstKey)
            }
          }

          const statusLower = status.toLowerCase()
          const isTerminal = ["completed", "failed", "cancelled"].includes(statusLower)

          // Avoid passing very large status strings through UI event bus
          detail = {
            ...detail,
            message: msg.length > 500 ? `${msg.slice(0, 500)}...` : msg,
          }

          if (isTerminal) {
            const payload = { event_type: eventType, data: detail }
            localStorage.setItem("va_last_realtime_event", JSON.stringify(payload))
            appendClientLog("info", "ws.job_updated", payload)
          }

          // Generic sampling for high-churn "processing" updates.
          if (taskId && statusLower === "processing") {
            const now = Date.now()
            const prev = lastUiDispatchAtRef.current.get(taskId) || 0
            if (now - prev < 800) {
              return
            }
            lastUiDispatchAtRef.current.set(taskId, now)
            if (lastUiDispatchAtRef.current.size > 500) {
              const firstKey = lastUiDispatchAtRef.current.keys().next().value
              if (firstKey) lastUiDispatchAtRef.current.delete(firstKey)
            }
          }
        }
        enqueueRealtimeEvent(detail)
      }
      offCreated = bridgeWs.on("job.created", dispatch("job.created"))
      offUpdated = bridgeWs.on("job.updated", dispatch("job.updated"))
      offNotification = bridgeWs.on("notification", dispatch("notification"))
    }

    setup()

    return () => {
      disposed = true
      offCreated?.()
      offUpdated?.()
      offNotification?.()
      bridgeWs.disconnect()
    }
  }, [loggedIn, userId, appendClientLog])

  // Poll for pending approvals count (from run_approvals) to show badge in NavSidebar
  useEffect(() => {
    if (!loggedIn) return
    const poll = async () => {
      try {
        const runs = await listRuns({ status: "waiting_approval", limit: 50 })
        // Count pending approvals across all waiting runs
        let count = 0
        for (const run of runs) {
          for (const exec of run.executions) {
            count += exec.approvals.filter(a => a.status === "pending").length
          }
        }
        setPendingApprovals(count)
      } catch {
        // ignore - not authenticated yet or backend unavailable
      }
    }
    poll()
    const timer = setInterval(poll, 10_000)
    return () => clearInterval(timer)
  }, [loggedIn])

  // Window close -> hide to tray; listen for approval events; Ctrl+N for new window
  useEffect(() => {
    const cleanups: Array<Promise<() => void>> = []
    try {
      const appWindow = getCurrentWindow()
      cleanups.push(
        appWindow.onCloseRequested((event) => {
          event.preventDefault()
          appWindow.hide()
        }).catch((e) => {
          console.warn("Could not attach onCloseRequested:", e);
          return () => { };
        })
      )
    } catch {
      // Not in Tauri (browser dev mode)
    }

    try {
      cleanups.push(
        listen<{ job_id: string }>("show-approval", () => {
          setView("run_center")
        }).catch((e) => {
          console.warn("Could not listen to show-approval:", e);
          return () => { };
        })
      )
    } catch {
      // Not in Tauri
    }

    // Ctrl+N -> new window (capture phase to intercept before WebView2)
    const handleKeyDown = async (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "n" && !e.shiftKey && !e.altKey) {
        // Don't trigger if user is typing in an input/textarea
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
        if (tag === "input" || tag === "textarea" || tag === "select") return
        e.preventDefault()
        e.stopImmediatePropagation()
        if (isTauri()) {
          try {
            const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
            const label = `main-${Date.now()}`
            new WebviewWindow(label, {
              url: "/",
              title: "VisionArk",
              width: 1100,
              height: 700,
              minWidth: 800,
              minHeight: 520,
              resizable: true,
              decorations: true,
            })
          } catch (err) {
            console.error("Failed to create new window:", err)
          }
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown, { capture: true })

    return () => {
      cleanups.forEach((c) => c.then((unlisten) => unlisten()))
      window.removeEventListener("keydown", handleKeyDown, { capture: true })
    }
  }, [])

  if (!authChecked) {
    return <div className="h-screen bg-black flex items-center justify-center text-gray-400">Loading...</div>
  }

  if (!loggedIn) {
    return (
      <LoginScreen
        onLogin={async (user) => {
          setLoggedIn(true)
          setUsername(user)
          try {
            const profile = await getMe()
            setUserId(profile.user_id)
          } catch {
            // best-effort: WS sync may start after next bootstrap if this fails
          }
        }}
      />
    )
  }

  const topBarProjectName = view === "chat" ? selectedProjectName : undefined

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-white select-none">
      {/* Left: Sidebar */}
      <NavSidebar
        active={view}
        onChange={handleNavChange}
        selectedProjectId={selectedProjectId}
        selectedSessionId={selectedSessionId}
        pendingApprovals={pendingApprovals}
        primaryCollapsed={primaryCollapsed}
        onTogglePrimaryCollapsed={() => setPrimaryCollapsed((v) => !v)}
        taskFilter={taskFilter}
        taskFilterContext={taskFilterContext}
        onTaskFilterChange={handleTaskFilterChange}
        calendarStatusFilter={calendarStatusFilter}
        onCalendarStatusFilterChange={setCalendarStatusFilter}
        username={username}
        onLogout={handleLogout}
      />

      {/* Right: Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar
          projectName={topBarProjectName}
          username={username}
          sidebarMode={projectSidebarMode}
          setSidebarMode={setProjectSidebarMode}
        />

        <main className="flex-1 min-w-0 flex overflow-hidden">
          <div className="flex-1 overflow-hidden">
            {view === "dashboard" && <DashboardView onNavigate={handleNavChange} />}
            {view === "run_center" && <RunCenterView />}
            {view === "notes" && <NotesView onOpenProject={(id) => handleNavChange("chat", id)} />}
            {view === "cron" && <CronTasksView />}
            {view === "monitoring" && <MonitoringJobsView />}
            {view === "tasks" && (
              <TasksView mode="tasks" filter={taskFilter} filterContext={taskFilterContext} />
            )}
            {view === "calendar" && (
              <TasksView
                mode="calendar"
                filter={taskFilter}
                filterContext={taskFilterContext}
                calendarStatusFilter={calendarStatusFilter}
              />
            )}
            {view === "chat" && selectedProjectId && (
              <ChatView
                projectId={selectedProjectId}
                sessionId={selectedSessionId}
                projectName={selectedProjectName}
                sidebarMode={projectSidebarMode}
                setSidebarMode={setProjectSidebarMode}
                onSessionChange={(next) => {
                  // Ignore accidental null/empty session updates while staying on chat.
                  if (!next) return
                  setSelectedSessionId(next)
                }}
              />
            )}
            {view === "workspace" && <WorkspaceView />}
            {view === "projects" && <ProjectsView onOpenProject={(id) => handleNavChange("chat", id)} />}
            {view === "agents" && <AgentsView />}
            {view === "settings" && <SettingsView />}
            {view === "devices" && <DevicesView />}
          </div>
        </main>
      </div>
    </div>
  )
}

