import React, { useCallback, useEffect, useState } from "react"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow } from "@tauri-apps/api/window"
import { invoke, isTauri } from "@tauri-apps/api/core"
export type ProjectSidebarMode = "files" | "automation" | "notes" | "activity" | "settings" | null;
import NavSidebar, { type NavView, type TaskFilter } from "./components/NavSidebar"
import TopBar from "./components/TopBar"
import DashboardView from "./components/DashboardView"
import RunCenterView from "./components/RunCenterView"
import ChatView from "./components/ChatView"
import LoginScreen from "./components/LoginScreen"
import NotesView from "./components/NotesView"
import CronTasksView from "./components/CronTasksView"
import WorkspaceView from "./components/WorkspaceView"
import ProjectsView from "./components/ProjectsView"
import AgentsView from "./components/AgentsView"
import TasksView from "./components/TasksView"
import SettingsView from "./components/SettingsView"
import DevicesView from "./components/DevicesView"
import DaemonConsole from "./components/DaemonConsole"
import FileViewerWindow from "./components/FileViewerWindow"
import { isLoggedIn, logout, listProjects, initApiBase, getApiBase, getToken, handleRefresh, type Project } from "./lib/api"
import { listRuns, registerDevice, heartbeatDevice, configure as configureBridge } from "../../bridge/api"

const DEVICE_ID_KEY = "va_device_id"
const HEARTBEAT_INTERVAL_MS = 30_000

function detectPlatform(): string {
  const ua = navigator.userAgent.toLowerCase()
  if (ua.includes("win")) return "windows"
  if (ua.includes("mac")) return "macos"
  if (ua.includes("linux")) return "linux"
  return "other"
}

async function loadStoredDeviceId(): Promise<string | null> {
  try {
    if (isTauri()) {
      const id = await invoke<string>("get_secure_token", { key: DEVICE_ID_KEY })
      return id || null
    }
  } catch { /* ignore */ }
  return localStorage.getItem(DEVICE_ID_KEY)
}

async function saveDeviceId(id: string): Promise<void> {
  try {
    if (isTauri()) {
      await invoke("set_secure_token", { key: DEVICE_ID_KEY, value: id })
      return
    }
  } catch { /* ignore */ }
  localStorage.setItem(DEVICE_ID_KEY, id)
}

export default function App() {
  const [isConsole] = useState(() => isTauri() && getCurrentWindow().label === "console")
  const [isFileViewer] = useState(() => isTauri() && getCurrentWindow().label.startsWith("fileviewer"))
  if (isConsole) return <DaemonConsole />
  if (isFileViewer) return <FileViewerWindow />
  return <MainApp />
}

function MainApp() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [username, setUsername] = useState("")
  const [view, setView] = useState<NavView>("dashboard")
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedProjectName, setSelectedProjectName] = useState("")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [pendingApprovals, setPendingApprovals] = useState(0)
  const [projects, setProjects] = useState<Project[]>([])
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("today")
  const [taskFilterContext, setTaskFilterContext] = useState<string | undefined>(undefined)
  const [projectSidebarMode, setProjectSidebarMode] = useState<ProjectSidebarMode>(null)

  useEffect(() => {
    const bootstrap = async () => {
      // 1. Restore stored server URL
      await initApiBase()
      // 2. Wire bridge (the HTTP client) to desktop's URL/token/refresh management
      configureBridge({ getBaseUrl: getApiBase, getToken, handleRefresh })
      // 3. Now check authentication
      const status = await isLoggedIn()
      setLoggedIn(status)
      setAuthChecked(true)
    }
    bootstrap()
  }, [])

  useEffect(() => {
    if (!loggedIn) return
    listProjects().then(setProjects).catch(() => { })

    // Device registration + heartbeat loop
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null

    const setupDevice = async () => {
      // 1. Try to load an already-registered device_id
      let deviceId = await loadStoredDeviceId()

      // 1.5 Validate if the device still exists on the backend
      if (deviceId) {
        try {
          await heartbeatDevice(deviceId)
        } catch (e: any) {
          const msg = e instanceof Error ? e.message : String(e)
          // If the backend returns 404 (Not Found) or 403 (Forbidden), the device was deleted.
          if (msg.includes("404") || msg.includes("403")) {
            console.warn("Stored device ID is invalid/deleted. Forcing re-registration.", msg)
            await saveDeviceId("")
            deviceId = null
          }
        }
      }

      // 2. If not stored or was deleted, register now and persist the result
      if (!deviceId) {
        const platform = detectPlatform()
        try {
          const device = await registerDevice({
            display_name: `Desktop (${platform})`,
            device_kind: "desktop",
            platform,
            capabilities: ["run_shell", "file_rw", "open_app"],
          })
          deviceId = device.id
          await saveDeviceId(deviceId)
        } catch { /* ignore — best-effort */ }
      }

      // 3. Start daemon if Tauri
      if (isTauri() && deviceId) {
        const token = getToken()
        if (token) {
          try {
            await invoke("start_daemon_command", { apiUrl: getApiBase(), token, deviceId })
          } catch (e) {
            console.error("Failed to start daemon sidecar", e)
          }
        }
      }

      // 4. Heartbeat loop
      if (deviceId) {
        const id = deviceId
        heartbeatDevice(id).catch(() => { })
        heartbeatTimer = setInterval(() => {
          heartbeatDevice(id).catch(() => { })
        }, HEARTBEAT_INTERVAL_MS)
      }
    }

    setupDevice()
    return () => {
      if (heartbeatTimer) clearInterval(heartbeatTimer)
    }
  }, [loggedIn])

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
    await logout()
    setLoggedIn(false)
    setUsername("")
  }, [])

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
        // ignore — not authenticated yet or backend unavailable
      }
    }
    poll()
    const timer = setInterval(poll, 10_000)
    return () => clearInterval(timer)
  }, [loggedIn])

  // Window close → hide to tray; listen for approval events
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

    return () => {
      cleanups.forEach((c) => c.then((unlisten) => unlisten()))
    }
  }, [])

  if (!authChecked) {
    return <div className="h-screen bg-black flex items-center justify-center text-gray-400">Loading...</div>
  }

  if (!loggedIn) {
    return (
      <LoginScreen
        onLogin={(user) => {
          setLoggedIn(true)
          setUsername(user)
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
        isCollapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        taskFilter={taskFilter}
        taskFilterContext={taskFilterContext}
        onTaskFilterChange={handleTaskFilterChange}
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
            {view === "dashboard" && <DashboardView />}
            {view === "run_center" && <RunCenterView />}
            {view === "notes" && <NotesView onOpenProject={(id) => handleNavChange("chat", id)} />}
            {view === "cron" && <CronTasksView />}
            {view === "tasks" && (
              <TasksView filter={taskFilter} filterContext={taskFilterContext} />
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
