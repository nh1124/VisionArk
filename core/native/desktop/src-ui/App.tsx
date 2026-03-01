import React, { useCallback, useEffect, useState } from "react"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow } from "@tauri-apps/api/window"
export type ProjectSidebarMode = "files" | "automation" | "notes" | "activity" | null;
import NavSidebar, { type NavView, type TaskFilter } from "./components/NavSidebar"
import TopBar from "./components/TopBar"
import DashboardView from "./components/DashboardView"
import JobsView from "./components/JobsView"
import ApprovalsView from "./components/ApprovalsView"
import ChatView from "./components/ChatView"
import LoginScreen from "./components/LoginScreen"
import NotesView from "./components/NotesView"
import CronTasksView from "./components/CronTasksView"
import WorkspaceView from "./components/WorkspaceView"
import ProjectsView from "./components/ProjectsView"
import AgentsView from "./components/AgentsView"
import TasksView from "./components/TasksView"
import SettingsView from "./components/SettingsView"
import { isLoggedIn, logout, listProjects, initApiBase, getApiBase, getToken, type Project } from "./lib/api"
import { listJobs, configure as configureBridge } from "../../bridge/api"

export default function App() {
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
      // 1. Restore stored server URL (also syncs bridge via _setBridgeBaseUrl)
      await initApiBase()
      // 2. Wire bridge to the shared URL and token getters (no more manual syncs)
      configureBridge({ getBaseUrl: getApiBase, getToken })
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

  // Poll for pending approvals count to show badge in NavSidebar
  useEffect(() => {
    if (!loggedIn) return
    const poll = async () => {
      try {
        const jobs = await listJobs({ status: "needs_approval", limit: 50 })
        setPendingApprovals(jobs.length)
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
          setView("approvals")
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
            {view === "jobs" && <JobsView />}
            {view === "approvals" && <ApprovalsView highlightJobId={null} />}
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
          </div>
        </main>
      </div>
    </div>
  )
}
