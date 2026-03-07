import React, { useCallback, useEffect, useState } from "react"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow } from "@tauri-apps/api/window"
import { invoke, isTauri } from "@tauri-apps/api/core"
export type ProjectSidebarMode = "files" | "automation" | "notes" | "activity" | "settings" | null;
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

export default function App() {
  const [windowLabel] = useState(() => isTauri() ? getCurrentWindow().label : "main")
  const isConsole = windowLabel === "console"
  const isFileViewer = windowLabel.startsWith("fileviewer")
  if (isConsole) return <DaemonConsole />
  if (isFileViewer) return <FileViewerWindow />
  return <MainApp />
}

function MainApp() {
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

  useEffect(() => {
    const bootstrap = async () => {
      // 1. Restore stored server URL
      await initApiBase()
      // 2. Wire bridge (the HTTP client) to desktop's URL/token/refresh management
      configureBridge({ getBaseUrl: getApiBase, getToken, handleRefresh })
      // 3. Now check authentication
      let status = await isLoggedIn()
      if (status) {
        try {
          const profile = await getMe()
          setUsername(profile.username)
          setUserId(profile.user_id)
        } catch (e) {
          console.warn("Failed to fetch user profile, clearing auth state", e)
          status = false
          await logout()
        }
      }
      setLoggedIn(status)
      setAuthChecked(true)
    }
    bootstrap()
  }, [])

  useEffect(() => {
    if (!loggedIn) return
    listProjects().then(setProjects).catch(() => { })
    const startDaemon = async () => {
      // UI responsibility: daemon start trigger only.
      if (isTauri()) {
        const token = await getToken()
        const apiUrl = getApiBase()
        if (!token) {
          console.warn(
            `[daemon-start-skip] apiUrl=${apiUrl} deviceId=(empty) tokenPresent=false`
          )
        } else {
          try {
            await invoke("start_daemon_command", { apiUrl, token, deviceId: "" })
          } catch (e) {
            console.error(
              `[daemon-start-failed] apiUrl=${apiUrl} deviceId=(empty) tokenPresent=true`,
              e
            )
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
        setSelectedSessionId(sessionId || null)
        const project = projects.find((p) => p.id === projectId)
        setSelectedProjectName(project?.display_name || project?.name || "Project")
        setProjectSidebarMode(null) // Reset sidebar when switching projects
      }
    },
    [projects]
  )

  const handleTaskFilterChange = useCallback((filter: TaskFilter, context?: string) => {
    setTaskFilter(filter)
    setTaskFilterContext(context)
  }, [])

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

      bridgeWs.connect(wsUrl, token)

      const dispatch = (data: unknown) => {
        window.dispatchEvent(new CustomEvent("va-realtime-job", { detail: data }))
      }
      offCreated = bridgeWs.on("job.created", dispatch)
      offUpdated = bridgeWs.on("job.updated", dispatch)
      offNotification = bridgeWs.on("notification", dispatch)
    }

    setup()

    return () => {
      disposed = true
      offCreated?.()
      offUpdated?.()
      offNotification?.()
      bridgeWs.disconnect()
    }
  }, [loggedIn, userId])

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

