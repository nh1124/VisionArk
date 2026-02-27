import React, { useEffect, useRef, useState } from "react"
import {
  LayoutGrid, Folder, Bot, ClipboardList, Play, ShieldCheck,
  AlarmClock, StickyNote, Library, Settings, Plus, MessageSquare,
  MoreVertical, Pencil, Copy, Trash2, Download, Archive,
  Sun, Star, Calendar, Inbox as InboxIcon,
} from "lucide-react"
import {
  apiFetch, listProjects, listSessions, getFileToken, listLBSTasks,
  BASE_URL,
  type Project, type Session,
} from "../lib/api"

export type NavView =
  | "dashboard" | "projects" | "agents" | "tasks" | "jobs"
  | "approvals" | "cron" | "notes" | "workspace" | "chat"

export type TaskFilter = "today" | "my-day" | "planned" | "overdue" | "inbox" | "project"

interface Props {
  active: NavView
  onChange: (v: NavView, projectId?: string, sessionId?: string) => void
  selectedProjectId: string | null
  selectedSessionId: string | null
  pendingApprovals: number
  isCollapsed: boolean
  onToggle: () => void
  taskFilter?: TaskFilter
  taskFilterContext?: string
  onTaskFilterChange?: (filter: TaskFilter, context?: string) => void
}

const navItems: { id: NavView; icon: React.ElementType; label: string }[] = [
  { id: "dashboard", icon: LayoutGrid, label: "Dashboard" },
  { id: "projects",  icon: Folder,      label: "Projects"   },
  { id: "agents",    icon: Bot,          label: "Agents"     },
  { id: "tasks",     icon: ClipboardList, label: "Tasks"     },
  { id: "jobs",      icon: Play,         label: "Jobs"       },
  { id: "approvals", icon: ShieldCheck,  label: "Approvals"  },
  { id: "cron",      icon: AlarmClock,   label: "Cron Tasks" },
  { id: "notes",     icon: StickyNote,   label: "Notes"      },
  { id: "workspace", icon: Library,      label: "Workspace"  },
]

const taskCategories: { id: TaskFilter; label: string; icon: React.ElementType }[] = [
  { id: "today",    label: "Today",   icon: Sun      },
  { id: "my-day",   label: "My Day",  icon: Star     },
  { id: "planned",  label: "Planned", icon: Calendar },
  { id: "overdue",  label: "Overdue", icon: AlarmClock },
  { id: "inbox",    label: "Inbox",   icon: InboxIcon },
]

export default function NavSidebar({
  active, onChange, selectedProjectId, selectedSessionId,
  pendingApprovals, isCollapsed, onToggle,
  taskFilter = "today", taskFilterContext, onTaskFilterChange,
}: Props) {
  const [projects, setProjects]             = useState<Project[]>([])
  const [sessions, setSessions]             = useState<Session[]>([])
  const [projectsExpanded, setProjectsExpanded] = useState(true)
  const [chatsExpanded, setChatsExpanded]   = useState(true)
  const [taskContexts, setTaskContexts]     = useState<string[]>([])

  // Hover / dropdown states
  const [hoveredProject, setHoveredProject]           = useState<string | null>(null)
  const [projectMenuOpen, setProjectMenuOpen]         = useState<string | null>(null)
  const [projectMenuPos, setProjectMenuPos]           = useState<{ top: number; right: number } | null>(null)
  const projectMenuRef                                 = useRef<HTMLDivElement>(null)

  const [hoveredSession, setHoveredSession]           = useState<string | null>(null)
  const [sessionMenuOpen, setSessionMenuOpen]         = useState<string | null>(null)
  const [sessionMenuPos, setSessionMenuPos]           = useState<{ top: number; right: number } | null>(null)
  const sessionMenuRef                                 = useRef<HTMLDivElement>(null)

  // Inline edit states
  const [editingProjectId, setEditingProjectId]   = useState<string | null>(null)
  const [editProjectTitle, setEditProjectTitle]   = useState("")
  const projectEditRef                             = useRef<HTMLInputElement>(null)

  const [editingSessionId, setEditingSessionId]   = useState<string | null>(null)
  const [editSessionTitle, setEditSessionTitle]   = useState("")
  const sessionEditRef                             = useRef<HTMLInputElement>(null)

  // Data fetching
  useEffect(() => { listProjects().then(setProjects).catch(() => {}) }, [])

  useEffect(() => {
    if (!selectedProjectId) { setSessions([]); return }
    listSessions(selectedProjectId).then(setSessions).catch(() => {})
  }, [selectedProjectId])

  useEffect(() => {
    if (active !== "tasks") return
    listLBSTasks({ active: true })
      .then((tasks) => {
        const ctxs = Array.from(new Set(tasks.map((t) => t.context).filter(Boolean))).sort() as string[]
        setTaskContexts(ctxs)
      })
      .catch(() => {})
  }, [active])

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target as Node)) {
        setProjectMenuOpen(null); setProjectMenuPos(null)
      }
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
        setSessionMenuOpen(null); setSessionMenuPos(null)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  // ── Project actions ───────────────────────────────────────────────────────

  function openProjectMenu(e: React.MouseEvent, projectId: string) {
    e.preventDefault(); e.stopPropagation()
    if (projectMenuOpen === projectId) {
      setProjectMenuOpen(null); setProjectMenuPos(null)
    } else {
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      setProjectMenuOpen(projectId)
      setProjectMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
      setSessionMenuOpen(null); setSessionMenuPos(null)
    }
  }

  function startEditProject(project: Project) {
    setEditingProjectId(project.id)
    setEditProjectTitle(project.display_name || project.name || "")
    setProjectMenuOpen(null); setProjectMenuPos(null)
    setTimeout(() => projectEditRef.current?.focus(), 50)
  }

  async function handleRenameProject(projectId: string, newTitle: string) {
    if (!newTitle.trim()) { setEditingProjectId(null); return }
    try {
      await apiFetch(`/api/agents/project/${projectId}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_display_name: newTitle.trim() }),
      })
      setProjects((prev) =>
        prev.map((p) => p.id === projectId ? { ...p, display_name: newTitle.trim() } : p)
      )
    } catch (e) { console.error("Rename project failed:", e) }
    finally { setEditingProjectId(null) }
  }

  async function handleCloneProject(project: Project) {
    try {
      const res = await apiFetch(`/api/agents/project/${project.id}/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_display_name: `${project.display_name || project.name} (Copy)` }),
      })
      if (res.ok) listProjects().then(setProjects).catch(() => {})
    } catch (e) { console.error("Clone project failed:", e) }
    setProjectMenuOpen(null); setProjectMenuPos(null)
  }

  async function handleDeleteProject(project: Project) {
    const name = project.display_name || project.name
    if (!window.confirm(`Delete project '${name}'? This cannot be undone.`)) return
    try {
      await apiFetch(`/api/agents/project/${project.id}`, { method: "DELETE" })
      setProjects((prev) => prev.filter((p) => p.id !== project.id))
      if (selectedProjectId === project.id) onChange("projects")
    } catch (e) { console.error("Delete project failed:", e) }
    setProjectMenuOpen(null); setProjectMenuPos(null)
  }

  async function handleExportChat(project: Project) {
    try {
      const token = await getFileToken()
      const url   = `${BASE_URL}/api/export/chat/project/${project.id}?token=${token}`
      const a     = document.createElement("a")
      a.href = url
      a.download = `${project.display_name || project.name}_chat.md`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
    } catch (e) { console.error("Export chat failed:", e) }
    setProjectMenuOpen(null); setProjectMenuPos(null)
  }

  // ── Session actions ───────────────────────────────────────────────────────

  function openSessionMenu(e: React.MouseEvent, sessionId: string) {
    e.preventDefault(); e.stopPropagation()
    if (sessionMenuOpen === sessionId) {
      setSessionMenuOpen(null); setSessionMenuPos(null)
    } else {
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      setSessionMenuOpen(sessionId)
      setSessionMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
      setProjectMenuOpen(null); setProjectMenuPos(null)
    }
  }

  function startEditSession(session: Session) {
    setEditingSessionId(session.id)
    setEditSessionTitle(session.title || "")
    setSessionMenuOpen(null); setSessionMenuPos(null)
    setTimeout(() => sessionEditRef.current?.focus(), 50)
  }

  async function handleRenameSession(sessionId: string, newTitle: string) {
    if (!newTitle.trim()) { setEditingSessionId(null); return }
    try {
      const res = await apiFetch(`/api/agents/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim() }),
      })
      const updated = await res.json()
      setSessions((prev) =>
        prev.map((s) => s.id === sessionId ? { ...s, title: updated.title } : s)
      )
    } catch (e) { console.error("Rename session failed:", e) }
    finally { setEditingSessionId(null) }
  }

  async function handleArchiveSession(sessionId: string) {
    try {
      await apiFetch(`/api/agents/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_archived: true }),
      })
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    } catch (e) { console.error("Archive session failed:", e) }
    setSessionMenuOpen(null); setSessionMenuPos(null)
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
      onChange("chat", selectedProjectId, newSession.id)
    } catch (e) { console.error("New chat failed:", e) }
  }

  const openMenuProject = projects.find((p) => p.id === projectMenuOpen)
  const openMenuSession = sessions.find((s) => s.id === sessionMenuOpen)

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className={`bg-gray-950 border-r border-gray-800/50 flex flex-col h-full transition-all duration-200 relative flex-shrink-0 ${
        isCollapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Toggle Button */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-5 w-6 h-6 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center text-gray-500 hover:text-white hover:bg-gray-700 transition-all z-10"
      >
        <span className={`text-xs transition-transform duration-200 ${isCollapsed ? "rotate-180" : ""}`}>◀</span>
      </button>

      {/* ── Header (fixed) ────────────────────────────────────────────────── */}
      <div className={`p-3 border-b border-gray-800/50 flex-shrink-0 ${isCollapsed ? "px-2" : ""}`}>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm flex-shrink-0">
            V
          </div>
          {!isCollapsed && <span className="text-sm font-semibold text-white">Vision Ark</span>}
        </div>
      </div>

      {/* ── Nav Items (fixed — never pushed off screen) ───────────────────── */}
      <div className="flex-shrink-0 px-3 py-2 space-y-1">
        {navItems.map(({ id, icon: Icon, label }) => {
          const isActive = active === id
          const badge    = id === "approvals" && pendingApprovals > 0
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${
                isCollapsed ? "justify-center" : ""
              } ${
                isActive
                  ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/20"
                  : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
              }`}
              title={isCollapsed ? label : ""}
            >
              <span className={isActive ? "text-white" : "text-gray-500"}>
                <Icon size={20} />
              </span>
              {!isCollapsed && <span>{label}</span>}
              {badge && !isCollapsed && (
                <span className="ml-auto w-2 h-2 rounded-full bg-yellow-400" />
              )}
            </button>
          )
        })}
      </div>

      {/* ── Scrollable bottom section (Projects+Chats or Task Filter) ─────── */}
      {/*   flex-1 + overflow-y-auto → always reachable by scrolling         */}
      <div className="flex-1 min-h-0 overflow-y-auto border-t border-gray-800/50 flex flex-col custom-scrollbar">

        {active === "tasks" ? (
          /* ─ Task Filter Sidebar ──────────────────────────────────────── */
          <div className="py-2">
            <div className="space-y-1 px-3">
              {taskCategories.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => onTaskFilterChange?.(id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-bold transition-all ${
                    isCollapsed ? "justify-center" : ""
                  } ${
                    taskFilter === id
                      ? "bg-blue-600/10 text-blue-400"
                      : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                  }`}
                  title={isCollapsed ? label : ""}
                >
                  <span className={taskFilter === id ? "text-blue-400" : "text-gray-500"}>
                    <Icon size={18} />
                  </span>
                  {!isCollapsed && <span className="flex-1 text-left">{label}</span>}
                </button>
              ))}
            </div>

            {/* Context (Projects) list for task filter */}
            {!isCollapsed && taskContexts.length > 0 && (
              <div className="mt-4 px-3">
                <h4 className="px-3 text-[10px] font-black text-gray-600 uppercase tracking-widest mb-2">
                  Projects
                </h4>
                <button
                  onClick={() => onTaskFilterChange?.("inbox")}
                  className={`w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    taskFilter !== "project"
                      ? "bg-gray-800 text-white"
                      : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/40"
                  }`}
                >
                  <InboxIcon
                    size={14}
                    className={taskFilter !== "project" ? "text-blue-400" : "text-gray-600"}
                  />
                  <span className="truncate flex-1 text-left">All Tasks</span>
                </button>
                {taskContexts.map((ctx) => (
                  <button
                    key={ctx}
                    onClick={() => onTaskFilterChange?.("project", ctx)}
                    className={`w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      taskFilter === "project" && taskFilterContext === ctx
                        ? "bg-gray-800 text-cyan-400"
                        : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/40"
                    }`}
                  >
                    <Folder
                      size={14}
                      className={
                        taskFilter === "project" && taskFilterContext === ctx
                          ? "text-cyan-400" : "text-gray-600"
                      }
                    />
                    <span className="truncate flex-1 text-left">{ctx}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* ─ Projects + Chats ─────────────────────────────────────────── */
          <div className="py-2">
            {/* Projects header */}
            <button
              onClick={() => setProjectsExpanded(!projectsExpanded)}
              className={`flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors ${
                isCollapsed ? "justify-center px-2" : ""
              }`}
            >
              {isCollapsed ? (
                <span>P</span>
              ) : (
                <>
                  <span className="flex-1 text-left uppercase tracking-wider">Projects</span>
                  <span className={`transition-transform duration-200 ${projectsExpanded ? "" : "-rotate-90"}`}>▾</span>
                </>
              )}
            </button>

            {projectsExpanded && !isCollapsed && (
              <div className="px-2 mt-1">
                {/* New Project */}
                <button
                  onClick={() => onChange("projects")}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors w-full text-left"
                >
                  <Plus size={13} />
                  <span>New Project</span>
                </button>

                {/* Project list */}
                <div className="space-y-0.5 mt-0.5">
                  {projects.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-gray-600 italic">No projects yet</div>
                  ) : (
                    projects.map((project) => {
                      const isActive  = selectedProjectId === project.id && active === "chat"
                      const isHovered = hoveredProject === project.id
                      return (
                        <div
                          key={project.id}
                          className="relative"
                          onMouseEnter={() => setHoveredProject(project.id)}
                          onMouseLeave={() => { if (projectMenuOpen !== project.id) setHoveredProject(null) }}
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
                              onClick={() => onChange("chat", project.id)}
                              className={`w-full flex items-center px-3 py-2 rounded-lg text-sm transition-colors text-left ${
                                isActive
                                  ? "bg-gray-800 text-white"
                                  : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                              }`}
                            >
                              <span className="truncate flex-1">
                                {project.display_name || project.name}
                              </span>
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
                    })
                  )}
                </div>
              </div>
            )}

            {/* Chats section — shown when a project is selected */}
            {selectedProjectId && !isCollapsed && (
              <div className="mt-3 pt-3 border-t border-gray-800/50">
                <button
                  onClick={() => setChatsExpanded(!chatsExpanded)}
                  className="flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors"
                >
                  <MessageSquare size={11} className="mr-1.5 flex-shrink-0" />
                  <span className="flex-1 text-left uppercase tracking-wider">Chats</span>
                  <span className={`transition-transform duration-200 ${chatsExpanded ? "" : "-rotate-90"}`}>▾</span>
                </button>

                {chatsExpanded && (
                  <div className="px-2 mt-1">
                    {/* New Chat */}
                    <button
                      onClick={handleNewChat}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors w-full text-left"
                    >
                      <Plus size={13} />
                      <span>New Chat</span>
                    </button>

                    {/* Session list */}
                    <div className="space-y-0.5 mt-0.5">
                      {sessions.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-gray-600 italic">No chats yet</div>
                      ) : (
                        sessions.map((session) => {
                          const isActiveSession = selectedSessionId === session.id
                          const isHovered       = hoveredSession === session.id
                          return (
                            <div
                              key={session.id}
                              className="relative"
                              onMouseEnter={() => setHoveredSession(session.id)}
                              onMouseLeave={() => { if (sessionMenuOpen !== session.id) setHoveredSession(null) }}
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
                                  className="w-full px-3 py-2 text-xs bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                                />
                              ) : (
                                <button
                                  onClick={() => onChange("chat", selectedProjectId, session.id)}
                                  className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs transition-colors text-left ${
                                    isActiveSession
                                      ? "bg-cyan-500/15 text-white"
                                      : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                                  }`}
                                >
                                  <MessageSquare size={11} className="flex-shrink-0 opacity-40" />
                                  <span className="truncate flex-1">
                                    {session.title || "Untitled Chat"}
                                  </span>
                                  {session.is_default && (
                                    <span className="text-[9px] text-cyan-500/50 flex-shrink-0">●</span>
                                  )}
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
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Footer (fixed) ────────────────────────────────────────────────── */}
      <div className="p-3 border-t border-gray-800/50 flex-shrink-0">
        <button
          onClick={() => onChange("dashboard")}
          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${
            isCollapsed ? "justify-center" : ""
          } text-gray-500 hover:bg-gray-800/50 hover:text-gray-300`}
          title={isCollapsed ? "Settings" : ""}
        >
          <Settings size={20} />
          {!isCollapsed && <span>Settings</span>}
        </button>
      </div>

      {/* ── Project dropdown (fixed-position) ─────────────────────────────── */}
      {projectMenuOpen && projectMenuPos && openMenuProject && (
        <div
          ref={projectMenuRef}
          style={{ position: "fixed", top: projectMenuPos.top, right: projectMenuPos.right, zIndex: 9999 }}
          className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px]"
        >
          <button
            onClick={() => startEditProject(openMenuProject)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <Pencil size={14} /> Rename
          </button>
          <button
            onClick={() => handleCloneProject(openMenuProject)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <Copy size={14} /> Clone Project
          </button>
          <button
            onClick={() => { onChange("chat", openMenuProject.id); setProjectMenuOpen(null); setProjectMenuPos(null) }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <MessageSquare size={14} /> Open Chat
          </button>
          <button
            onClick={() => handleExportChat(openMenuProject)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <Download size={14} /> Export Chat
          </button>
          <div className="my-1 border-t border-gray-700" />
          <button
            onClick={() => handleDeleteProject(openMenuProject)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
          >
            <Trash2 size={14} /> Delete Project
          </button>
        </div>
      )}

      {/* ── Session dropdown (fixed-position) ─────────────────────────────── */}
      {sessionMenuOpen && sessionMenuPos && openMenuSession && (
        <div
          ref={sessionMenuRef}
          style={{ position: "fixed", top: sessionMenuPos.top, right: sessionMenuPos.right, zIndex: 9999 }}
          className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[140px]"
        >
          <button
            onClick={() => startEditSession(openMenuSession)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            <Pencil size={14} /> Rename
          </button>
          <button
            onClick={() => handleArchiveSession(openMenuSession.id)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
          >
            <Archive size={14} /> Archive
          </button>
        </div>
      )}
    </div>
  )
}
