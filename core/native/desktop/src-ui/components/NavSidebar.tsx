import React, { useEffect, useMemo, useRef, useState } from "react"
import {
  Home,
  Folder,
  Bot,
  ClipboardList,
  Activity,
  AlarmClock,
  StickyNote,
  Library,
  Settings,
  Plus,
  MessageSquare,
  MoreVertical,
  Pencil,
  Copy,
  Trash2,
  Download,
  Archive,
  Sun,
  Star,
  Calendar,
  CalendarDays,
  Inbox as InboxIcon,
  LogOut,
  ChevronUp,
  Keyboard,
  Monitor,
  Clock3,
  CheckSquare,
  ShieldCheck,
  FileText,
  HardDrive,
  Menu,
  ChevronLeft,
} from "lucide-react"
import KeyboardShortcutsModal from "./KeyboardShortcutsModal"
import {
  apiFetch,
  listProjects,
  listSessions,
  getFileToken,
  listLBSTasks,
  getOverdueTasks,
  BASE_URL,
  type Project,
  type Session,
} from "../lib/api"

export type NavView =
  | "dashboard"
  | "projects"
  | "agents"
  | "tasks"
  | "calendar"
  | "run_center"
  | "cron"
  | "monitoring"
  | "notes"
  | "workspace"
  | "chat"
  | "settings"
  | "devices"

export type TaskFilter = "today" | "my-day" | "planned" | "overdue" | "inbox" | "project"
export type CalendarStatusFilter = "all" | "open" | "done"
type PrimaryNavId = "home" | "projects" | "tasks" | "knowledge" | "automation" | "devices"

interface Props {
  active: NavView
  onChange: (v: NavView, projectId?: string, sessionId?: string) => void
  selectedProjectId: string | null
  selectedSessionId: string | null
  pendingApprovals: number
  primaryCollapsed: boolean
  onTogglePrimaryCollapsed: () => void
  taskFilter?: TaskFilter
  taskFilterContext?: string
  onTaskFilterChange?: (filter: TaskFilter, context?: string) => void
  calendarStatusFilter?: CalendarStatusFilter
  onCalendarStatusFilterChange?: (filter: CalendarStatusFilter) => void
  username?: string
  onLogout?: () => void
}

const primaryNavItems: { id: PrimaryNavId; icon: React.ElementType; label: string; target: NavView }[] = [
  { id: "home", icon: Home, label: "Home", target: "dashboard" },
  { id: "projects", icon: Folder, label: "Projects", target: "projects" },
  { id: "tasks", icon: ClipboardList, label: "Tasks", target: "tasks" },
  { id: "knowledge", icon: Library, label: "Knowledge", target: "notes" },
  { id: "automation", icon: Bot, label: "Automation", target: "run_center" },
  { id: "devices", icon: Monitor, label: "Devices", target: "devices" },
]

const taskCategories: { id: TaskFilter; label: string; icon: React.ElementType }[] = [
  { id: "today", label: "Today", icon: Sun },
  { id: "my-day", label: "My Day", icon: Star },
  { id: "planned", label: "Planned", icon: Calendar },
  { id: "overdue", label: "Overdue", icon: AlarmClock },
  { id: "inbox", label: "Inbox", icon: InboxIcon },
]

function mapViewToPrimary(view: NavView): PrimaryNavId {
  if (view === "projects" || view === "chat") return "projects"
  if (view === "tasks" || view === "calendar") return "tasks"
  if (view === "notes" || view === "workspace") return "knowledge"
  if (view === "agents" || view === "run_center" || view === "cron" || view === "monitoring") return "automation"
  if (view === "devices") return "devices"
  return "home"
}

function SectionTitle({ title }: { title: string }) {
  return <h3 className="px-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-gray-500">{title}</h3>
}

export default function NavSidebar({
  active,
  onChange,
  selectedProjectId,
  selectedSessionId,
  pendingApprovals,
  primaryCollapsed,
  onTogglePrimaryCollapsed,
  taskFilter = "today",
  taskFilterContext,
  onTaskFilterChange,
  calendarStatusFilter = "all",
  onCalendarStatusFilterChange,
  username,
  onLogout,
}: Props) {
  const [projects, setProjects] = useState<Project[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [taskContexts, setTaskContexts] = useState<string[]>([])
  const [taskFilterCounts, setTaskFilterCounts] = useState<Record<TaskFilter, number>>({
    today: 0,
    "my-day": 0,
    planned: 0,
    overdue: 0,
    inbox: 0,
    project: 0,
  })

  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)

  const [hoveredProject, setHoveredProject] = useState<string | null>(null)
  const [projectMenuOpen, setProjectMenuOpen] = useState<string | null>(null)
  const [projectMenuPos, setProjectMenuPos] = useState<{ top: number; right: number } | null>(null)
  const projectMenuRef = useRef<HTMLDivElement>(null)

  const [hoveredSession, setHoveredSession] = useState<string | null>(null)
  const [sessionMenuOpen, setSessionMenuOpen] = useState<string | null>(null)
  const [sessionMenuPos, setSessionMenuPos] = useState<{ top: number; right: number } | null>(null)
  const sessionMenuRef = useRef<HTMLDivElement>(null)

  const [editingProjectId, setEditingProjectId] = useState<string | null>(null)
  const [editProjectTitle, setEditProjectTitle] = useState("")
  const projectEditRef = useRef<HTMLInputElement>(null)

  const [editingSessionId, setEditingSessionId] = useState<string | null>(null)
  const [editSessionTitle, setEditSessionTitle] = useState("")
  const sessionEditRef = useRef<HTMLInputElement>(null)
  const [projectSearchQuery, setProjectSearchQuery] = useState("")
  const [chatSearchQuery, setChatSearchQuery] = useState("")
  const [dragOverContext, setDragOverContext] = useState<string | null>(null)
  const [selectedSidebarProjectIds, setSelectedSidebarProjectIds] = useState<Set<string>>(new Set())
  const [lastSidebarProjectId, setLastSidebarProjectId] = useState<string | null>(null)
  const [selectedSidebarSessionIds, setSelectedSidebarSessionIds] = useState<Set<string>>(new Set())
  const [lastSidebarSessionId, setLastSidebarSessionId] = useState<string | null>(null)
  const [sidebarBulkMenu, setSidebarBulkMenu] = useState<{ mode: "projects" | "sessions"; top: number; right: number } | null>(null)
  const sidebarBulkMenuRef = useRef<HTMLDivElement>(null)
  const [exportNotice, setExportNotice] = useState<{ type: "success" | "error"; message: string } | null>(null)

  const primaryActive = useMemo(() => mapViewToPrimary(active), [active])
  const todayIso = useMemo(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  }, [])
  const refreshTaskContexts = React.useCallback(() => {
    listLBSTasks({ active: true })
      .then((tasks) => {
        const contexts = Array.from(new Set(tasks.map((t) => t.context).filter(Boolean))).sort() as string[]
        setTaskContexts(contexts)
      })
      .catch(() => {})
  }, [])
  const refreshTaskFilterCounts = React.useCallback(async () => {
    try {
      const [todayTasks, activeTasks, overdueTasks] = await Promise.all([
        listLBSTasks({ targetDate: todayIso }),
        listLBSTasks({ active: true }),
        getOverdueTasks(),
      ])
      const byContext = (t: { context?: string | null }) => !taskFilterContext || t.context === taskFilterContext
      setTaskFilterCounts({
        today: todayTasks.filter(byContext).length,
        "my-day": activeTasks.filter((t) => byContext(t) && !!(t.meta_payload as any)?.is_my_day).length,
        planned: activeTasks.filter((t) => byContext(t) && !!t.due_date && t.due_date > todayIso).length,
        overdue: overdueTasks.filter(byContext).length,
        inbox: activeTasks.filter((t) => byContext(t) && (t.context || "inbox") === "inbox").length,
        project: 0,
      })
    } catch {
      // ignore
    }
  }, [taskFilterContext, todayIso])
  const filteredProjects = useMemo(() => {
    const query = projectSearchQuery.trim().toLowerCase()
    if (!query) return projects
    return projects.filter((project) => {
      const name = (project.display_name || project.name || "").toLowerCase()
      return name.includes(query)
    })
  }, [projects, projectSearchQuery])
  const filteredSessions = useMemo(() => {
    const query = chatSearchQuery.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter((session) => (session.title || "untitled chat").toLowerCase().includes(query))
  }, [sessions, chatSearchQuery])

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedProjectId) {
      setSessions([])
      return
    }
    listSessions(selectedProjectId).then(setSessions).catch(() => {})
  }, [selectedProjectId, selectedSessionId])

  useEffect(() => {
    const onSessionsUpdated = (evt: Event) => {
      const detail = (evt as CustomEvent<any>).detail || {}
      if (!selectedProjectId || detail.project_id !== selectedProjectId) return
      listSessions(selectedProjectId).then(setSessions).catch(() => {})
    }
    window.addEventListener("va-sessions-updated", onSessionsUpdated as EventListener)
    return () => window.removeEventListener("va-sessions-updated", onSessionsUpdated as EventListener)
  }, [selectedProjectId])

  useEffect(() => {
    if (primaryActive !== "tasks") return
    refreshTaskContexts()
    void refreshTaskFilterCounts()
  }, [primaryActive, refreshTaskContexts, refreshTaskFilterCounts])

  useEffect(() => {
    const onRefresh = () => {
      refreshTaskContexts()
      void refreshTaskFilterCounts()
    }
    window.addEventListener("va-task-contexts-refresh", onRefresh as EventListener)
    return () => window.removeEventListener("va-task-contexts-refresh", onRefresh as EventListener)
  }, [refreshTaskContexts, refreshTaskFilterCounts])

  useEffect(() => {
    const onRefresh = () => { void refreshTaskFilterCounts() }
    window.addEventListener("va-tasks-refresh", onRefresh as EventListener)
    return () => window.removeEventListener("va-tasks-refresh", onRefresh as EventListener)
  }, [refreshTaskFilterCounts])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target as Node)) {
        setProjectMenuOpen(null)
        setProjectMenuPos(null)
      }
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
        setSessionMenuOpen(null)
        setSessionMenuPos(null)
      }
      if (sidebarBulkMenuRef.current && !sidebarBulkMenuRef.current.contains(e.target as Node)) {
        setSidebarBulkMenu(null)
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (active !== "chat" || !selectedProjectId || sessions.length === 0) return
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return

      const tag = ((e.target as HTMLElement | null)?.tagName || "").toLowerCase()
      const isTypingTarget =
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        !!(e.target as HTMLElement | null)?.isContentEditable
      if (isTypingTarget) return

      e.preventDefault()
      e.stopPropagation()

      const currentIndex = Math.max(0, sessions.findIndex((s) => s.id === selectedSessionId))
      const offset = e.key === "ArrowUp" ? -1 : 1
      const nextIndex = (currentIndex + offset + sessions.length) % sessions.length
      const next = sessions[nextIndex]
      if (!next) return

      localStorage.setItem(`va_last_session_${selectedProjectId}`, next.id)
      onChange("chat", selectedProjectId, next.id)
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [active, onChange, selectedProjectId, selectedSessionId, sessions])

  useEffect(() => {
    const onDragState = (evt: Event) => {
      const detail = (evt as CustomEvent<{ active?: boolean }>).detail
      const active = !!detail?.active
      if (!active) setDragOverContext(null)
    }
    window.addEventListener("va-task-drag-active", onDragState as EventListener)
    return () => window.removeEventListener("va-task-drag-active", onDragState as EventListener)
  }, [])

  useEffect(() => {
    setSelectedSidebarProjectIds(new Set())
    setSelectedSidebarSessionIds(new Set())
    setLastSidebarProjectId(null)
    setLastSidebarSessionId(null)
    setSidebarBulkMenu(null)
  }, [active, selectedProjectId])

  useEffect(() => {
    if (!exportNotice) return
    const timer = window.setTimeout(() => setExportNotice(null), 3200)
    return () => window.clearTimeout(timer)
  }, [exportNotice])

  async function downloadExportFile(url: string, filename: string) {
    const res = await fetch(url)
    if (!res.ok) {
      const text = await res.text().catch(() => "")
      throw new Error(text || `Export failed (${res.status})`)
    }
    const blob = await res.blob()
    const objectUrl = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = objectUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(objectUrl)
  }

  async function handleTaskDropToContext(context: string, e: React.DragEvent<HTMLButtonElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragOverContext(null)

    const raw = e.dataTransfer.getData("application/x-visionark-task")
    if (!raw) return

    try {
      const parsed = JSON.parse(raw) as { task_id?: string }
      const taskId = parsed.task_id
      if (!taskId) return

      await apiFetch(`/api/lbs/tasks/${taskId}?force_override=true`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context }),
      })

      const tasks = await listLBSTasks({ active: true })
      const contexts = Array.from(new Set(tasks.map((t) => t.context).filter(Boolean))).sort() as string[]
      setTaskContexts(contexts)
      window.dispatchEvent(new Event("va-tasks-refresh"))
      window.dispatchEvent(new Event("va-task-contexts-refresh"))
    } catch (err) {
      console.error("Task drop move failed:", err)
    } finally {
      window.dispatchEvent(new CustomEvent("va-task-drag-active", { detail: { active: false } }))
    }
  }

  function toggleSidebarProjectSelection(projectId: string, shiftKey: boolean) {
    const ids = filteredProjects.map((p) => p.id)
    const next = new Set(selectedSidebarProjectIds)
    if (shiftKey && lastSidebarProjectId) {
      const from = ids.indexOf(lastSidebarProjectId)
      const to = ids.indexOf(projectId)
      if (from !== -1 && to !== -1) {
        const [lo, hi] = from <= to ? [from, to] : [to, from]
        ids.slice(lo, hi + 1).forEach((id) => next.add(id))
        setSelectedSidebarProjectIds(next)
        setLastSidebarProjectId(projectId)
        return
      }
    }
    if (next.has(projectId)) next.delete(projectId)
    else next.add(projectId)
    setSelectedSidebarProjectIds(next)
    setLastSidebarProjectId(projectId)
  }

  function toggleSidebarSessionSelection(sessionId: string, shiftKey: boolean) {
    const ids = filteredSessions.map((s) => s.id)
    const next = new Set(selectedSidebarSessionIds)
    if (shiftKey && lastSidebarSessionId) {
      const from = ids.indexOf(lastSidebarSessionId)
      const to = ids.indexOf(sessionId)
      if (from !== -1 && to !== -1) {
        const [lo, hi] = from <= to ? [from, to] : [to, from]
        ids.slice(lo, hi + 1).forEach((id) => next.add(id))
        setSelectedSidebarSessionIds(next)
        setLastSidebarSessionId(sessionId)
        return
      }
    }
    if (next.has(sessionId)) next.delete(sessionId)
    else next.add(sessionId)
    setSelectedSidebarSessionIds(next)
    setLastSidebarSessionId(sessionId)
  }

  async function handleBulkDeleteSidebarProjects() {
    const ids = Array.from(selectedSidebarProjectIds)
    if (ids.length === 0) return
    try {
      await Promise.all(ids.map((id) => apiFetch(`/api/agents/project/${id}`, { method: "DELETE" })))
      const refreshed = await listProjects()
      setProjects(refreshed)
      setSelectedSidebarProjectIds(new Set())
      setLastSidebarProjectId(null)
      if (selectedProjectId && ids.includes(selectedProjectId)) onChange("projects")
    } catch (e) {
      console.error("Bulk delete projects failed:", e)
    }
  }

  async function handleBulkExportSidebarProjects() {
    const ids = Array.from(selectedSidebarProjectIds)
    if (ids.length === 0) return
    try {
      const token = await getFileToken()
      let successCount = 0
      for (const id of ids) {
        const project = projects.find((p) => p.id === id)
        if (!project) continue
        const fileName = `${project.display_name || project.name}_export.zip`
        const url = `${BASE_URL}/api/export/project/${project.id}?token=${token}`
        await downloadExportFile(url, fileName)
        successCount += 1
      }
      setExportNotice({ type: "success", message: `Exported ${successCount} project${successCount !== 1 ? "s" : ""}.` })
    } catch (e) {
      console.error("Bulk export projects failed:", e)
      setExportNotice({ type: "error", message: "Project export failed." })
    }
  }

  async function handleBulkArchiveSidebarSessions() {
    const ids = Array.from(selectedSidebarSessionIds)
    if (ids.length === 0) return
    try {
      await Promise.all(ids.map((id) =>
        apiFetch(`/api/agents/sessions/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_archived: true }),
        })
      ))
      if (selectedProjectId) {
        const refreshed = await listSessions(selectedProjectId)
        setSessions(refreshed)
      }
      setSelectedSidebarSessionIds(new Set())
      setLastSidebarSessionId(null)
    } catch (e) {
      console.error("Bulk archive sessions failed:", e)
    }
  }

  async function handleBulkExportSidebarSessions() {
    const ids = Array.from(selectedSidebarSessionIds)
    if (ids.length === 0) return
    try {
      const token = await getFileToken()
      let successCount = 0
      for (const id of ids) {
        const session = sessions.find((s) => s.id === id)
        if (!session) continue
        const url = `${BASE_URL}/api/export/chat/session/${session.id}?token=${token}`
        const titleSlug = (session.title || "Untitled").replace(/ /g, "_").toLowerCase()
        await downloadExportFile(url, `chat_export_${titleSlug}.md`)
        successCount += 1
      }
      setExportNotice({ type: "success", message: `Exported ${successCount} session${successCount !== 1 ? "s" : ""}.` })
    } catch (e) {
      console.error("Bulk export sessions failed:", e)
      setExportNotice({ type: "error", message: "Session export failed." })
    }
  }

  function openProjectMenu(e: React.MouseEvent, projectId: string) {
    e.preventDefault()
    e.stopPropagation()
    if (projectMenuOpen === projectId) {
      setProjectMenuOpen(null)
      setProjectMenuPos(null)
      return
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setProjectMenuOpen(projectId)
    setProjectMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
    setSessionMenuOpen(null)
    setSessionMenuPos(null)
  }

  function openSessionMenu(e: React.MouseEvent, sessionId: string) {
    e.preventDefault()
    e.stopPropagation()
    if (sessionMenuOpen === sessionId) {
      setSessionMenuOpen(null)
      setSessionMenuPos(null)
      return
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setSessionMenuOpen(sessionId)
    setSessionMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
  }

  function openSidebarBulkMenu(e: React.MouseEvent, mode: "projects" | "sessions") {
    e.preventDefault()
    e.stopPropagation()
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
    setSessionMenuOpen(null)
    setSessionMenuPos(null)
    setSidebarBulkMenu({
      mode,
      top: e.clientY,
      right: Math.max(8, window.innerWidth - e.clientX),
    })
  }

  function startEditProject(project: Project) {
    setEditingProjectId(project.id)
    setEditProjectTitle(project.display_name || project.name || "")
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
    setTimeout(() => projectEditRef.current?.focus(), 50)
  }

  async function handleRenameProject(projectId: string, newTitle: string) {
    if (!newTitle.trim()) {
      setEditingProjectId(null)
      return
    }
    try {
      await apiFetch(`/api/agents/project/${projectId}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_display_name: newTitle.trim() }),
      })
      setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, display_name: newTitle.trim() } : p)))
    } catch (e) {
      console.error("Rename project failed:", e)
    } finally {
      setEditingProjectId(null)
    }
  }

  async function handleCloneProject(project: Project) {
    try {
      const res = await apiFetch(`/api/agents/project/${project.id}/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_display_name: `${project.display_name || project.name} (Copy)` }),
      })
      if (res.ok) listProjects().then(setProjects).catch(() => {})
    } catch (e) {
      console.error("Clone project failed:", e)
    }
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
  }

  async function handleDeleteProject(project: Project) {
    try {
      await apiFetch(`/api/agents/project/${project.id}`, { method: "DELETE" })
      setProjects((prev) => prev.filter((p) => p.id !== project.id))
      if (selectedProjectId === project.id) onChange("projects")
    } catch (e) {
      console.error("Delete project failed:", e)
    }
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
  }

  async function handleExportChat(project: Project) {
    try {
      const token = await getFileToken()
      const url = `${BASE_URL}/api/export/project/${project.id}?token=${token}`
      await downloadExportFile(url, `${project.display_name || project.name}_export.zip`)
      setExportNotice({ type: "success", message: `Exported project: ${project.display_name || project.name}` })
    } catch (e) {
      console.error("Export chat failed:", e)
      setExportNotice({ type: "error", message: "Project export failed." })
    }
    setProjectMenuOpen(null)
    setProjectMenuPos(null)
  }

  function startEditSession(session: Session) {
    setEditingSessionId(session.id)
    setEditSessionTitle(session.title || "")
    setSessionMenuOpen(null)
    setSessionMenuPos(null)
    setTimeout(() => sessionEditRef.current?.focus(), 50)
  }

  async function handleRenameSession(sessionId: string, newTitle: string) {
    if (!newTitle.trim()) {
      setEditingSessionId(null)
      return
    }
    try {
      const res = await apiFetch(`/api/agents/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim() }),
      })
      const updated = await res.json()
      setSessions((prev) => prev.map((s) => (s.id === sessionId ? { ...s, title: updated.title } : s)))
    } catch (e) {
      console.error("Rename session failed:", e)
    } finally {
      setEditingSessionId(null)
    }
  }

  async function handleArchiveSession(sessionId: string) {
    try {
      await apiFetch(`/api/agents/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_archived: true }),
      })
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    } catch (e) {
      console.error("Archive session failed:", e)
    }
    setSessionMenuOpen(null)
    setSessionMenuPos(null)
  }

  async function handleExportSession(session: Session) {
    try {
      const token = await getFileToken()
      const url = `${BASE_URL}/api/export/chat/session/${session.id}?token=${token}`
      const titleSlug = (session.title || "Untitled").replace(/ /g, "_").toLowerCase()
      await downloadExportFile(url, `chat_export_${titleSlug}.md`)
      setExportNotice({ type: "success", message: `Exported session: ${session.title || "Untitled"}` })
    } catch (e) {
      console.error("Export session failed:", e)
      setExportNotice({ type: "error", message: "Session export failed." })
    }
    setSessionMenuOpen(null)
    setSessionMenuPos(null)
  }

  async function handleNewChat() {
    if (!selectedProjectId) return
    try {
      const res = await apiFetch(`/api/agents/project/${selectedProjectId}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Chat" }),
      })
      const newSession: Session = await res.json()
      setSessions((prev) => [newSession, ...prev])
      localStorage.setItem(`va_last_session_${selectedProjectId}`, newSession.id)
      onChange("chat", selectedProjectId, newSession.id)
    } catch (e) {
      console.error("New chat failed:", e)
    }
  }

  async function handleNewProject() {
    const existingNames = new Set(
      projects.map((p) => (p.display_name || p.name || "").trim().toLowerCase()).filter(Boolean),
    )
    let candidate = "New Project"
    let index = 1
    while (existingNames.has(candidate.toLowerCase())) {
      index += 1
      candidate = `New Project ${index}`
    }

    try {
      const res = await apiFetch("/api/agents/project/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: candidate }),
      })
      if (!res.ok) throw new Error(`Create project failed: ${res.status}`)
      const created = await res.json()
      const projectId = created?.project_id as string | undefined
      if (!projectId) throw new Error("Project ID missing in create response")

      const refreshed = await listProjects()
      setProjects(refreshed)
      const createdProject = refreshed.find((p) => p.id === projectId)
      setEditingProjectId(projectId)
      setEditProjectTitle(createdProject?.display_name || createdProject?.name || candidate)
      onChange("projects", projectId)
      setTimeout(() => projectEditRef.current?.focus(), 50)
    } catch (e) {
      console.error("New project failed:", e)
    }
  }

  const openMenuProject = projects.find((p) => p.id === projectMenuOpen)
  const openMenuSession = sessions.find((s) => s.id === sessionMenuOpen)

  const secondaryTitle: Record<PrimaryNavId, string> = {
    home: "Home Context",
    projects: "Projects",
    tasks: "Tasks",
    knowledge: "Knowledge",
    automation: "Automation",
    devices: "Devices",
  }

  const secondaryDescription: Record<PrimaryNavId, string> = {
    home: "Overview and quick links",
    projects: "Project and chat navigation",
    tasks: "Task views and filters",
    knowledge: "",
    automation: "Runs, agents, and schedules",
    devices: "Device and access context",
  }

  const renderHomeSecondary = () => (
    <div className="space-y-5">
      <section className="space-y-1">
        <SectionTitle title="Overview" />
        <button onClick={() => onChange("dashboard")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "dashboard" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
          <Home size={15} />
          <span>Dashboard</span>
        </button>
        <button onClick={() => onChange("tasks")} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800/70 hover:text-gray-200">
          <CheckSquare size={15} />
          <span>Today</span>
        </button>
      </section>
    </div>
  )

  const renderProjectsSecondary = () =>
    active === "projects" ? (
      <div className="space-y-3">
        <div className="flex items-center gap-2 px-1 py-1 text-gray-300">
          <Folder size={16} />
          <span className="text-lg font-medium">All Projects</span>
        </div>

        <div className="px-1">
          <input
            type="text"
            placeholder="Search projects..."
            value={projectSearchQuery}
            onChange={(e) => setProjectSearchQuery(e.target.value)}
            className="w-full h-10 rounded-xl bg-gray-900/80 border border-gray-800 px-3.5 text-sm text-gray-200 placeholder:text-gray-500 outline-none focus:border-cyan-500/40"
          />
        </div>

        <button
          onClick={handleNewProject}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] font-medium text-cyan-400 hover:bg-cyan-500/10"
        >
          <Plus size={15} />
          <span>New Project</span>
        </button>

        <div className="border-t border-gray-800/60 pt-2">
          <div className="space-y-1 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
            {filteredProjects.length === 0 ? (
              <div className="px-3 py-2 text-xs text-gray-600 italic">No matching projects</div>
            ) : filteredProjects.map((project) => {
              const isHovered = hoveredProject === project.id
              const isSelected = selectedSidebarProjectIds.has(project.id)
              const isActiveProject = selectedProjectId === project.id
              return (
                <div
                  key={`project-${project.id}`}
                  className="relative"
                  onMouseEnter={() => setHoveredProject(project.id)}
                  onMouseLeave={() => { if (projectMenuOpen !== project.id) setHoveredProject(null) }}
                  onContextMenu={(e) => {
                    if (selectedSidebarProjectIds.size > 0 && selectedSidebarProjectIds.has(project.id)) {
                      openSidebarBulkMenu(e, "projects")
                    }
                  }}
                >
                  {editingProjectId === project.id ? (
                    <input
                      ref={projectEditRef}
                      value={editProjectTitle}
                      onChange={(e) => setEditProjectTitle(e.target.value)}
                      onBlur={() => handleRenameProject(project.id, editProjectTitle)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleRenameProject(project.id, editProjectTitle)
                        if (e.key === "Escape") setEditingProjectId(null)
                      }}
                      className="w-full px-3 py-2 text-sm bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                    />
                  ) : (
                    <button
                      onClick={(e) => {
                        if (e.shiftKey) {
                          e.preventDefault()
                          toggleSidebarProjectSelection(project.id, true)
                          return
                        }
                        if (selectedSidebarProjectIds.size > 0) {
                          toggleSidebarProjectSelection(project.id, false)
                          return
                        }
                        const lastSessionId = localStorage.getItem(`va_last_session_${project.id}`)
                        onChange("chat", project.id, lastSessionId || undefined)
                      }}
                      className={`w-full flex items-center px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                        isSelected
                          ? "bg-cyan-500/15 text-cyan-100"
                          : isActiveProject
                            ? "bg-gray-800 text-white"
                            : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                      }`}
                    >
                      <span className="truncate flex-1 text-[13px]">{project.display_name || project.name}</span>
                    </button>
                  )}
                  {(isHovered || projectMenuOpen === project.id) && editingProjectId !== project.id && (
                    <button
                      onClick={(e) => openProjectMenu(e, project.id)}
                      className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                    >
                      <MoreVertical size={14} />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    ) : (
      <div className="space-y-3">
        <button
          onClick={() => onChange("projects")}
          className="w-full flex items-center gap-2 px-1 py-1 text-gray-300 hover:text-white"
        >
          <ChevronLeft size={16} />
          <span className="text-lg font-medium">Projects</span>
        </button>

        <div className="px-1">
          <input
            type="text"
            placeholder="Search chats..."
            value={chatSearchQuery}
            onChange={(e) => setChatSearchQuery(e.target.value)}
            className="w-full h-10 rounded-xl bg-gray-900/80 border border-gray-800 px-3.5 text-sm text-gray-200 placeholder:text-gray-500 outline-none focus:border-cyan-500/40"
          />
        </div>

        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] font-medium text-cyan-400 hover:bg-cyan-500/10"
        >
          <Plus size={15} />
          <span>New Chat</span>
        </button>

        <div className="border-t border-gray-800/60 pt-2">
          <div className="space-y-1 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
            {filteredSessions.length === 0 ? (
              <div className="px-3 py-2 text-xs text-gray-600 italic">No matching chats</div>
            ) : filteredSessions.map((session) => {
              const isActiveSession = selectedSessionId === session.id
              const isHovered = hoveredSession === session.id
              const isSelected = selectedSidebarSessionIds.has(session.id)
              return (
                <div
                  key={`session-${session.id}`}
                  className="relative"
                  onMouseEnter={() => setHoveredSession(session.id)}
                  onMouseLeave={() => { if (sessionMenuOpen !== session.id) setHoveredSession(null) }}
                  onContextMenu={(e) => {
                    if (selectedSidebarSessionIds.size > 0 && selectedSidebarSessionIds.has(session.id)) {
                      openSidebarBulkMenu(e, "sessions")
                    }
                  }}
                >
                  {editingSessionId === session.id ? (
                    <input
                      ref={sessionEditRef}
                      value={editSessionTitle}
                      onChange={(e) => setEditSessionTitle(e.target.value)}
                      onBlur={() => handleRenameSession(session.id, editSessionTitle)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleRenameSession(session.id, editSessionTitle)
                        if (e.key === "Escape") setEditingSessionId(null)
                      }}
                      className="w-full px-3 py-2 text-sm bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                    />
                  ) : (
                    <button
                      onClick={(e) => {
                        if (e.shiftKey) {
                          e.preventDefault()
                          toggleSidebarSessionSelection(session.id, true)
                          return
                        }
                        if (selectedSidebarSessionIds.size > 0) {
                          toggleSidebarSessionSelection(session.id, false)
                          return
                        }
                        if (!selectedProjectId) return
                        localStorage.setItem(`va_last_session_${selectedProjectId}`, session.id)
                        onChange("chat", selectedProjectId, session.id)
                      }}
                      className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                        isSelected
                          ? "bg-cyan-500/15 text-cyan-100"
                          : isActiveSession
                            ? "bg-cyan-500/15 text-white"
                            : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                      }`}
                    >
                      <MessageSquare size={11} className="flex-shrink-0 opacity-40" />
                      <span className="truncate flex-1 text-[13px]">{session.title || "Untitled Chat"}</span>
                    </button>
                  )}
                  {(isHovered || sessionMenuOpen === session.id) && editingSessionId !== session.id && (
                    <button
                      onClick={(e) => openSessionMenu(e, session.id)}
                      className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                    >
                      <MoreVertical size={12} />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    )

  const renderTasksSecondary = () => (
    <div className="space-y-5">
      <section className="space-y-1">
        <button onClick={() => onChange("tasks")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "tasks" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
          <ClipboardList size={15} />
          <span>Task List</span>
        </button>
        <button onClick={() => onChange("calendar")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "calendar" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
          <CalendarDays size={15} />
          <span>Calendar</span>
        </button>
      </section>

      <div className="border-t border-gray-800/60 pt-3 space-y-5">
        {active === "tasks" && (
          <section className="space-y-1">
            <SectionTitle title="Task Filters" />
            {taskCategories.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => onTaskFilterChange?.(id, taskFilterContext)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${taskFilter === id ? "bg-blue-600/10 text-blue-400" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
              >
                <Icon size={15} />
                <span className="flex-1 text-left">{label}</span>
                <span className={`text-[11px] px-1.5 py-0.5 rounded-md ${
                  taskFilter === id ? "bg-blue-500/20 text-blue-300" : "bg-gray-800 text-gray-500"
                }`}>
                  {taskFilterCounts[id]}
                </span>
              </button>
            ))}
          </section>
        )}

        {active === "calendar" && (
          <section className="space-y-1">
            <SectionTitle title="Calendar Status" />
            {([
              { id: "all", label: "All Status" },
              { id: "open", label: "Open Only" },
              { id: "done", label: "Done Only" },
            ] as const).map((item) => (
              <button
                key={item.id}
                onClick={() => onCalendarStatusFilterChange?.(item.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${calendarStatusFilter === item.id ? "bg-blue-600/10 text-blue-400" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
              >
                <span>{item.label}</span>
              </button>
            ))}
          </section>
        )}
      </div>

      {taskContexts.length > 0 && (
        <section className="space-y-1">
          <SectionTitle title="Projects" />
          <button
            onClick={() => onTaskFilterChange?.(taskFilter, undefined)}
            onDragEnter={(e) => {
              if (!Array.from(e.dataTransfer.types).includes("application/x-visionark-task")) return
              e.preventDefault()
            }}
            onDragOver={(e) => {
              if (!Array.from(e.dataTransfer.types).includes("application/x-visionark-task")) return
              e.preventDefault()
              e.dataTransfer.dropEffect = "move"
            }}
            onDrop={(e) => {
              if (!Array.from(e.dataTransfer.types).includes("application/x-visionark-task")) return
              void handleTaskDropToContext("inbox", e)
            }}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${!taskFilterContext ? "bg-gray-800 text-white" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
          >
            <InboxIcon size={15} />
            <span>All Projects</span>
          </button>
          {taskContexts.map((ctx) => (
            <button
              key={ctx}
              onClick={() => onTaskFilterChange?.(taskFilter, ctx)}
              onDragEnter={(e) => {
                if (!Array.from(e.dataTransfer.types).includes("application/x-visionark-task")) return
                e.preventDefault()
                setDragOverContext(ctx)
              }}
              onDragOver={(e) => {
                if (!Array.from(e.dataTransfer.types).includes("application/x-visionark-task")) return
                e.preventDefault()
                e.dataTransfer.dropEffect = "move"
                if (dragOverContext !== ctx) setDragOverContext(ctx)
              }}
              onDragLeave={() => {
                if (dragOverContext === ctx) setDragOverContext(null)
              }}
              onDrop={(e) => { void handleTaskDropToContext(ctx, e) }}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all ${
                dragOverContext === ctx
                  ? "bg-cyan-600/20 text-cyan-300 ring-1 ring-cyan-500/40"
                  : taskFilterContext === ctx
                    ? "bg-gray-800 text-cyan-400"
                    : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"
              }`}
            >
              <Folder size={15} />
              <span className="truncate">{ctx}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  )

  const renderKnowledgeSecondary = () => (
    <div className="space-y-5">
      <section className="space-y-1">
        <button onClick={() => onChange("notes")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "notes" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
          <StickyNote size={15} />
          <span>Notes</span>
        </button>
        <button onClick={() => onChange("workspace")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "workspace" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
          <FileText size={15} />
          <span>Artifacts</span>
        </button>
      </section>
    </div>
  )

  const renderAutomationSecondary = () => (
    <div className="space-y-1">
      <button onClick={() => onChange("run_center")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "run_center" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
        <Activity size={15} />
        <span className="flex-1 text-left">Run Center</span>
        {pendingApprovals > 0 && <span className="text-[10px] px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300">{pendingApprovals}</span>}
      </button>
      <button onClick={() => onChange("agents")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "agents" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
        <Bot size={15} />
        <span>Agents</span>
      </button>
      <button onClick={() => onChange("cron")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "cron" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
        <Clock3 size={15} />
        <span>Cron</span>
      </button>
      <button onClick={() => onChange("monitoring")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "monitoring" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
        <ShieldCheck size={15} />
        <span>Monitoring</span>
      </button>
    </div>
  )

  const renderDevicesSecondary = () => (
    <div className="space-y-1">
      <button onClick={() => onChange("devices")} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${active === "devices" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}>
        <HardDrive size={15} />
        <span>All Devices</span>
      </button>
    </div>
  )

  const renderSecondary = () => {
    if (primaryActive === "projects") return renderProjectsSecondary()
    if (primaryActive === "tasks") return renderTasksSecondary()
    if (primaryActive === "knowledge") return renderKnowledgeSecondary()
    if (primaryActive === "automation") return renderAutomationSecondary()
    if (primaryActive === "devices") return renderDevicesSecondary()
    return renderHomeSecondary()
  }

  return (
    <>
      <div className="h-full flex border-r border-gray-800/50 bg-gray-950 flex-shrink-0">
        <aside className={`${primaryCollapsed ? "w-14" : "w-48"} border-r border-gray-800/50 flex flex-col transition-all duration-200`}>
          <div className={`p-2.5 ${primaryCollapsed ? "flex justify-center" : ""}`}>
            <button
              onClick={onTogglePrimaryCollapsed}
              className="w-8 h-8 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex items-center justify-center"
              title={primaryCollapsed ? "Expand" : "Collapse"}
            >
              <Menu size={18} />
            </button>
          </div>

          <nav className={`flex-1 p-2.5 space-y-1 overflow-y-auto ${primaryCollapsed ? "px-1.5" : ""}`}>
            {primaryNavItems.map(({ id, icon: Icon, label, target }) => {
              const isPrimaryActive = primaryActive === id
              return (
                <button
                  key={id}
                  onClick={() => onChange(target)}
                  title={primaryCollapsed ? label : undefined}
                  className={`w-full flex items-center ${primaryCollapsed ? "justify-center px-1.5" : "gap-2.5 px-3"} py-2 rounded-xl text-[13px] font-medium transition-colors ${isPrimaryActive ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/15" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
                >
                  <Icon size={17} />
                  {!primaryCollapsed && <span>{label}</span>}
                </button>
              )
            })}
          </nav>

          <div className={`p-2.5 border-t border-gray-800/50 relative ${primaryCollapsed ? "px-1.5" : ""}`} ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className={`w-full flex items-center ${primaryCollapsed ? "justify-center px-1.5" : "gap-2.5 px-3"} py-2 rounded-xl text-[13px] font-medium transition-colors ${userMenuOpen ? "bg-gray-800 text-white" : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"}`}
            >
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-md">
                {(username || "U").charAt(0).toUpperCase()}
              </div>
              {!primaryCollapsed && (
                <>
                  <span className="flex-1 text-left truncate">{username || "User"}</span>
                  <ChevronUp size={14} className={`text-gray-500 transition-transform duration-200 ${userMenuOpen ? "" : "rotate-180"}`} />
                </>
              )}
            </button>

            {userMenuOpen && (
              <div className={`absolute bottom-full mb-2 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl py-1.5 z-[9999] ${primaryCollapsed ? "left-0 min-w-[220px]" : "left-3 right-3"}`}>
                <button
                  onClick={() => { onChange("settings"); setUserMenuOpen(false) }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <Settings size={16} /> Settings
                </button>
                <button
                  onClick={() => { setShortcutsOpen(true); setUserMenuOpen(false) }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <Keyboard size={16} /> Keyboard Shortcuts
                </button>
                <div className="my-1 border-t border-gray-700" />
                <button
                  onClick={() => { onLogout?.(); setUserMenuOpen(false) }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                >
                  <LogOut size={16} /> Log out
                </button>
              </div>
            )}
          </div>
        </aside>

        {primaryActive !== "home" && (
          <aside className="w-64 flex flex-col bg-gray-950/80 border-r border-gray-800/40">
            {primaryActive === "tasks" ? (
              <div className="px-5 py-3.5">
                <div className="flex items-center gap-2 text-gray-300">
                  <ClipboardList size={16} />
                  <span className="text-lg font-medium">Tasks</span>
                </div>
              </div>
            ) : primaryActive === "knowledge" ? (
              <div className="px-5 py-3.5">
                <div className="flex items-center gap-2 text-gray-300">
                  <Library size={16} />
                  <span className="text-lg font-medium">Knowledge</span>
                </div>
              </div>
            ) : primaryActive === "automation" ? (
              <div className="px-5 py-3.5">
                <div className="flex items-center gap-2 text-gray-300">
                  <Bot size={16} />
                  <span className="text-lg font-medium">Automation</span>
                </div>
              </div>
            ) : primaryActive === "devices" ? (
              <div className="px-5 py-3.5">
                <div className="flex items-center gap-2 text-gray-300">
                  <Monitor size={16} />
                  <span className="text-lg font-medium">Devices</span>
                </div>
              </div>
            ) : primaryActive !== "projects" && (
              <div className="px-5 py-3.5 border-b border-gray-800/50">
                <h2 className="text-sm font-semibold text-gray-200">{secondaryTitle[primaryActive]}</h2>
                <p className="text-[11px] text-gray-500 mt-1">{secondaryDescription[primaryActive]}</p>
              </div>
            )}
            <div className="flex-1 overflow-y-auto custom-scrollbar p-4">
              {renderSecondary()}
            </div>
          </aside>
        )}
      </div>

      <KeyboardShortcutsModal open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

      {sidebarBulkMenu && (
        <div
          ref={sidebarBulkMenuRef}
          style={{ position: "fixed", top: sidebarBulkMenu.top, right: sidebarBulkMenu.right, zIndex: 9999 }}
          className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[180px]"
        >
          {sidebarBulkMenu.mode === "projects" ? (
            <>
              <div className="px-3 py-1 text-[11px] text-gray-500 border-b border-gray-700/70">
                {selectedSidebarProjectIds.size} selected projects
              </div>
              <button
                onClick={() => {
                  void handleBulkExportSidebarProjects()
                  setSidebarBulkMenu(null)
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
              >
                <Download size={14} /> Export Selected
              </button>
              <button
                onClick={() => {
                  void handleBulkDeleteSidebarProjects()
                  setSidebarBulkMenu(null)
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
              >
                <Trash2 size={14} /> Delete Selected
              </button>
              <div className="my-1 border-t border-gray-700" />
              <button
                onClick={() => {
                  setSelectedSidebarProjectIds(new Set())
                  setLastSidebarProjectId(null)
                  setSidebarBulkMenu(null)
                }}
                className="w-full text-left px-3 py-2 text-xs text-gray-500 hover:text-gray-300"
              >
                Clear Selection
              </button>
            </>
          ) : (
            <>
              <div className="px-3 py-1 text-[11px] text-gray-500 border-b border-gray-700/70">
                {selectedSidebarSessionIds.size} selected sessions
              </div>
              <button
                onClick={() => {
                  void handleBulkExportSidebarSessions()
                  setSidebarBulkMenu(null)
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
              >
                <Download size={14} /> Export Selected
              </button>
              <button
                onClick={() => {
                  void handleBulkArchiveSidebarSessions()
                  setSidebarBulkMenu(null)
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
              >
                <Archive size={14} /> Archive Selected
              </button>
              <div className="my-1 border-t border-gray-700" />
              <button
                onClick={() => {
                  setSelectedSidebarSessionIds(new Set())
                  setLastSidebarSessionId(null)
                  setSidebarBulkMenu(null)
                }}
                className="w-full text-left px-3 py-2 text-xs text-gray-500 hover:text-gray-300"
              >
                Clear Selection
              </button>
            </>
          )}
        </div>
      )}

      {projectMenuOpen && projectMenuPos && openMenuProject && (
        <div
          ref={projectMenuRef}
          style={{ position: "fixed", top: projectMenuPos.top, right: projectMenuPos.right, zIndex: 9999 }}
          className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px]"
        >
          <button onClick={() => startEditProject(openMenuProject)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white">
            <Pencil size={14} /> Rename
          </button>
          <button onClick={() => handleCloneProject(openMenuProject)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white">
            <Copy size={14} /> Clone Project
          </button>
          <button
            onClick={() => {
              const lastSessionId = localStorage.getItem(`va_last_session_${openMenuProject.id}`)
              onChange("chat", openMenuProject.id, lastSessionId || undefined)
              setProjectMenuOpen(null)
              setProjectMenuPos(null)
            }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <MessageSquare size={14} /> Open Chat
          </button>
          <button onClick={() => handleExportChat(openMenuProject)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white">
            <Download size={14} /> Export Project
          </button>
          <div className="my-1 border-t border-gray-700" />
          <button onClick={() => handleDeleteProject(openMenuProject)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10">
            <Trash2 size={14} /> Delete Project
          </button>
        </div>
      )}

      {sessionMenuOpen && sessionMenuPos && openMenuSession && (
        <div
          ref={sessionMenuRef}
          style={{ position: "fixed", top: sessionMenuPos.top, right: sessionMenuPos.right, zIndex: 9999 }}
          className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[140px]"
        >
          <button onClick={() => startEditSession(openMenuSession)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white">
            <Pencil size={14} /> Rename
          </button>
          <button onClick={() => handleExportSession(openMenuSession)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white">
            <Download size={14} /> Export
          </button>
          <div className="my-1 border-t border-gray-700" />
          <button onClick={() => handleArchiveSession(openMenuSession.id)} className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10">
            <Archive size={14} /> Archive
          </button>
        </div>
      )}
      {exportNotice && (
        <div className={`fixed right-6 bottom-6 z-[10000] rounded-lg border px-3 py-2 text-sm shadow-xl ${exportNotice.type === "success" ? "bg-emerald-900/90 border-emerald-700 text-emerald-100" : "bg-red-900/90 border-red-700 text-red-100"}`}>
          {exportNotice.message}
        </div>
      )}
    </>
  )
}
