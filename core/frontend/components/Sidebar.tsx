"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { apiFetch, getFileToken } from "@/lib/api";

import { useProjects } from "@/hooks/useProjects";
import { useNotification } from "@/lib/NotificationContext";
import {
    LayoutGrid, Folder, Bot, Settings as SettingsIcon, ClipboardList, AlarmClock, StickyNote,
    Library, MessageSquare, Plus, Copy, ExternalLink, Download, Trash2, MoreVertical, Pencil, Archive,
    Play, ShieldCheck, Monitor,
} from "lucide-react";
import TaskSidebar from "./TaskSidebar";

interface SidebarProps {
    isCollapsed: boolean;
    onToggle: () => void;
}

interface SessionItem {
    id: string;
    title: string | null;
    is_default: boolean;
    last_message_at: string | null;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { projects } = useProjects();
    const [projectsExpanded, setProjectsExpanded] = useState(true);
    const [chatsExpanded, setChatsExpanded] = useState(true);
    const [hoveredProject, setHoveredProject] = useState<string | null>(null);
    const [menuOpen, setMenuOpen] = useState<string | null>(null);
    const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    // Sessions state
    const [sessions, setSessions] = useState<SessionItem[]>([]);
    const [hoveredSession, setHoveredSession] = useState<string | null>(null);
    const [sessionMenuOpen, setSessionMenuOpen] = useState<string | null>(null);
    const [sessionMenuPos, setSessionMenuPos] = useState<{ top: number; right: number } | null>(null);
    const sessionMenuRef = useRef<HTMLDivElement>(null);
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editSessionTitle, setEditSessionTitle] = useState("");
    const sessionEditRef = useRef<HTMLInputElement>(null);

    const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
    const [editProjectTitle, setEditProjectTitle] = useState("");
    const projectEditRef = useRef<HTMLInputElement>(null);

    const { showConfirm, showToast } = useNotification();

    // Extract current projectId from pathname
    const projectMatch = pathname.match(/^\/projects\/([^\/]+)/);
    const currentProjectId = projectMatch ? projectMatch[1] : null;
    const activeSessionId = searchParams.get("session_id");

    // Fetch sessions when on a project page
    useEffect(() => {
        if (!currentProjectId) {
            setSessions([]);
            return;
        }
        apiFetch(`/api/agents/project/${currentProjectId}/sessions`)
            .then((res) => res.json())
            .then((data) => setSessions(data.sessions || []))
            .catch(() => { });
    }, [currentProjectId]);

    // Close menus when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setMenuOpen(null);
                setMenuPos(null);
            }
            if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
                setSessionMenuOpen(null);
                setSessionMenuPos(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const openProjectMenu = (e: React.MouseEvent, projectId: string) => {
        e.preventDefault();
        e.stopPropagation();
        if (menuOpen === projectId) {
            setMenuOpen(null);
            setMenuPos(null);
        } else {
            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
            setMenuOpen(projectId);
            setMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
            setSessionMenuOpen(null);
            setSessionMenuPos(null);
        }
    };

    const openSessionMenu = (e: React.MouseEvent, sessionId: string) => {
        e.preventDefault();
        e.stopPropagation();
        if (sessionMenuOpen === sessionId) {
            setSessionMenuOpen(null);
            setSessionMenuPos(null);
        } else {
            const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
            setSessionMenuOpen(sessionId);
            setSessionMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
            setMenuOpen(null);
            setMenuPos(null);
        }
    };

    const handleNewChat = async () => {
        if (!currentProjectId) return;
        try {
            const res = await apiFetch(`/api/agents/project/${currentProjectId}/sessions`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: "New Chat" }),
            });
            const newSession: SessionItem = await res.json();
            setSessions((prev) => [newSession, ...prev]);
            router.push(`/projects/${currentProjectId}?session_id=${newSession.id}`);
        } catch (e) {
            console.error("Failed to create session:", e);
        }
    };

    const handleExportChat = async (projectId: string, displayName: string) => {
        try {
            const token = await getFileToken();
            const exportUrl = `/api/export/chat/project/${projectId}?token=${token}`;
            const link = document.createElement("a");
            link.href = exportUrl;
            link.setAttribute("download", `${displayName}_chat.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setMenuOpen(null);
            setMenuPos(null);
        } catch (error) {
            console.error("Export failed:", error);
            showToast("Failed to export chat history.", "error");
        }
    };

    const handleCloneProject = async (projectId: string, currentDisplayName: string) => {
        try {
            const response = await apiFetch(`/api/agents/project/${projectId}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: `${currentDisplayName} (Copy)` }),
            });
            if (response.ok) {
                setMenuOpen(null);
                setMenuPos(null);
                window.location.reload();
            } else {
                const err = await response.json();
                showToast(`Failed to clone project: ${err.detail || "Unknown error"}`, "error");
            }
        } catch (error) {
            console.error("Clone failed:", error);
            showToast("Failed to clone project.", "error");
        }
    };

    const handleDeleteProject = async (projectId: string, displayName: string) => {
        const confirmed = await showConfirm(
            `Delete project '${displayName}'? This action cannot be undone.`,
            { title: "Delete Project", confirmText: "Delete", variant: "danger" }
        );
        if (!confirmed) return;
        try {
            await apiFetch(`/api/agents/project/${projectId}`, { method: "DELETE" });
            setMenuOpen(null);
            setMenuPos(null);
            window.location.href = "/projects";
        } catch (error) {
            console.error("Delete failed:", error);
            showToast("Failed to delete project.", "error");
        }
    };

    const startEditProject = (project: { id: string; display_name?: string | null; name: string }) => {
        setEditingProjectId(project.id);
        setEditProjectTitle(project.display_name || project.name || "");
        setMenuOpen(null);
        setMenuPos(null);
        setTimeout(() => projectEditRef.current?.focus(), 50);
    };

    const handleRenameProject = async (projectId: string, newTitle: string) => {
        if (!newTitle.trim()) { setEditingProjectId(null); return; }
        try {
            const res = await apiFetch(`/api/agents/project/${projectId}/rename`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: newTitle.trim() }),
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                showToast(`Failed to rename project: ${err.detail || "Unknown error"}`, "error");
            }
        } catch (e) {
            console.error("Rename project failed:", e);
        } finally {
            setEditingProjectId(null);
        }
    };

    const startEditSession = (session: SessionItem) => {
        setEditingSessionId(session.id);
        setEditSessionTitle(session.title || "");
        setSessionMenuOpen(null);
        setSessionMenuPos(null);
        setTimeout(() => sessionEditRef.current?.focus(), 50);
    };

    const handleRenameSession = async (sessionId: string, newTitle: string) => {
        if (!newTitle.trim()) { setEditingSessionId(null); return; }
        try {
            const res = await apiFetch(`/api/agents/sessions/${sessionId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: newTitle.trim() }),
            });
            const updated = await res.json();
            setSessions((prev) =>
                prev.map((s) => (s.id === sessionId ? { ...s, title: updated.title } : s))
            );
        } catch (e) {
            console.error("Rename session failed:", e);
        } finally {
            setEditingSessionId(null);
        }
    };

    const handleArchiveSession = async (sessionId: string) => {
        try {
            await apiFetch(`/api/agents/sessions/${sessionId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_archived: true }),
            });
            setSessions((prev) => prev.filter((s) => s.id !== sessionId));
            if (activeSessionId === sessionId && currentProjectId) {
                router.push(`/projects/${currentProjectId}`);
            }
        } catch (e) {
            console.error("Archive session failed:", e);
        }
        setSessionMenuOpen(null);
        setSessionMenuPos(null);
    };

    const navItems = [
        { name: "Dashboard", path: "/dashboard", icon: <LayoutGrid size={20} /> },
        { name: "Projects", path: "/projects", icon: <Folder size={20} /> },
        { name: "Agents", path: "/agents", icon: <Bot size={20} /> },
        { name: "Tasks", path: "/tasks", icon: <ClipboardList size={20} /> },
        { name: "Jobs", path: "/jobs", icon: <Play size={20} /> },
        { name: "Approvals", path: "/approvals", icon: <ShieldCheck size={20} /> },
        { name: "Devices", path: "/settings/devices", icon: <Monitor size={20} /> },
        { name: "Cron Tasks", path: "/cron", icon: <AlarmClock size={20} /> },
        { name: "Notes", path: "/notes", icon: <StickyNote size={20} /> },
        { name: "Workspace", path: "/workspace", icon: <Library size={20} /> },
    ];

    const openMenuProject = projects.find((p) => p.id === menuOpen);
    const openMenuSession = sessions.find((s) => s.id === sessionMenuOpen);

    return (
        <div
            id="vision-ark-sidebar"
            className={`bg-gray-950 border-r border-gray-800/50 flex flex-col h-full transition-all duration-200 relative flex-shrink-0 ${isCollapsed ? "w-16" : "w-64"
                }`}
        >
            {/* Toggle Button */}
            <button
                onClick={onToggle}
                className="absolute -right-3 top-5 w-6 h-6 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center text-gray-500 hover:text-white hover:bg-gray-700 transition-all z-10"
            >
                <span className={`text-xs transition-transform duration-200 ${isCollapsed ? "rotate-180" : ""}`}>◀</span>
            </button>

            {/* Header */}
            <div className={`p-3 border-b border-gray-800/50 ${isCollapsed ? "px-2" : ""}`}>
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm flex-shrink-0">
                        V
                    </div>
                    {!isCollapsed && (
                        <span className="text-sm font-semibold text-white">Vision Ark</span>
                    )}
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-2 overflow-y-auto flex flex-col min-h-0">
                {/* Main Nav */}
                <div className="px-3 space-y-1 flex-shrink-0">
                    {navItems.map((item) => {
                        const isActive = pathname === item.path;
                        return (
                            <Link
                                key={item.path}
                                href={item.path}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${isCollapsed ? "justify-center" : ""
                                    } ${isActive
                                        ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/20"
                                        : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
                                    }`}
                                title={isCollapsed ? item.name : ""}
                            >
                                <span className={isActive ? "text-white" : "text-gray-500"}>
                                    {item.icon}
                                </span>
                                {!isCollapsed && <span>{item.name}</span>}
                            </Link>
                        );
                    })}
                </div>

                {/* Task Context Sidebar or Projects + Chats Section */}
                {pathname === "/tasks" ? (
                    <div className="mt-4 pt-4 border-t border-gray-800/50 flex-shrink-0">
                        <TaskSidebar isCollapsed={isCollapsed} />
                    </div>
                ) : (
                    <div className="mt-4 pt-4 border-t border-gray-800/50 flex flex-col min-h-0">
                        {/* ── Projects Section ── */}
                        <button
                            onClick={() => setProjectsExpanded(!projectsExpanded)}
                            className={`flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0 ${isCollapsed ? "justify-center px-2" : ""
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
                            <div className="px-2 flex flex-col min-h-0">
                                {/* New Project – always at top */}
                                <Link
                                    href="/new"
                                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors flex-shrink-0"
                                >
                                    <Plus size={13} />
                                    <span>New Project</span>
                                </Link>

                                {/* Scrollable project list */}
                                <div className="overflow-y-auto max-h-44 space-y-0.5 mt-0.5">
                                    {projects.length === 0 ? (
                                        <div className="px-3 py-2 text-xs text-gray-600 italic">
                                            No projects yet
                                        </div>
                                    ) : (
                                        projects.map((project) => {
                                            const projectPath = project.path;
                                            const isActive =
                                                pathname === projectPath ||
                                                pathname.startsWith(projectPath + "/");
                                            const isHovered = hoveredProject === project.id;
                                            return (
                                                <div
                                                    key={project.id}
                                                    className="relative"
                                                    onMouseEnter={() => setHoveredProject(project.id)}
                                                    onMouseLeave={() => {
                                                        if (menuOpen !== project.id)
                                                            setHoveredProject(null);
                                                    }}
                                                >
                                                    {editingProjectId === project.id ? (
                                                        <input
                                                            ref={projectEditRef}
                                                            value={editProjectTitle}
                                                            onChange={(e) => setEditProjectTitle(e.target.value)}
                                                            onBlur={() => handleRenameProject(project.id, editProjectTitle)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === "Enter") handleRenameProject(project.id, editProjectTitle);
                                                                if (e.key === "Escape") setEditingProjectId(null);
                                                            }}
                                                            className="w-full px-3 py-2 text-sm bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                                                        />
                                                    ) : (
                                                        <Link
                                                            href={projectPath}
                                                            className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${isActive
                                                                    ? "bg-gray-800 text-white"
                                                                    : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                                                                }`}
                                                        >
                                                            <span className="truncate flex-1">
                                                                {project.display_name || project.name}
                                                            </span>
                                                        </Link>
                                                    )}

                                                    {/* Three-dot menu button */}
                                                    {(isHovered || menuOpen === project.id) && editingProjectId !== project.id && (
                                                        <button
                                                            onClick={(e) => openProjectMenu(e, project.id)}
                                                            className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                                                        >
                                                            <MoreVertical size={14} />
                                                        </button>
                                                    )}
                                                </div>
                                            );
                                        })
                                    )}
                                </div>
                            </div>
                        )}

                        {/* ── Chats Section (only on project pages) ── */}
                        {currentProjectId && !isCollapsed && (
                            <div className="mt-3 pt-3 border-t border-gray-800/50 flex flex-col min-h-0">
                                <button
                                    onClick={() => setChatsExpanded(!chatsExpanded)}
                                    className="flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
                                >
                                    <MessageSquare size={11} className="mr-1.5 flex-shrink-0" />
                                    <span className="flex-1 text-left uppercase tracking-wider">Chats</span>
                                    <span className={`transition-transform duration-200 ${chatsExpanded ? "" : "-rotate-90"}`}>▾</span>
                                </button>

                                {chatsExpanded && (
                                    <div className="px-2 flex flex-col min-h-0">
                                        {/* New Chat – always at top */}
                                        <button
                                            onClick={handleNewChat}
                                            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors flex-shrink-0 w-full text-left"
                                        >
                                            <Plus size={13} />
                                            <span>New Chat</span>
                                        </button>

                                        {/* Scrollable sessions list */}
                                        <div className="overflow-y-auto max-h-44 space-y-0.5 mt-0.5">
                                            {sessions.length === 0 ? (
                                                <div className="px-3 py-2 text-xs text-gray-600 italic">
                                                    No chats yet
                                                </div>
                                            ) : (
                                                sessions.map((session) => {
                                                    const isActive = activeSessionId === session.id;
                                                    const isHovered = hoveredSession === session.id;
                                                    return (
                                                        <div
                                                            key={session.id}
                                                            className="relative"
                                                            onMouseEnter={() => setHoveredSession(session.id)}
                                                            onMouseLeave={() => {
                                                                if (sessionMenuOpen !== session.id)
                                                                    setHoveredSession(null);
                                                            }}
                                                        >
                                                            {editingSessionId === session.id ? (
                                                                <input
                                                                    ref={sessionEditRef}
                                                                    value={editSessionTitle}
                                                                    onChange={(e) => setEditSessionTitle(e.target.value)}
                                                                    onBlur={() => handleRenameSession(session.id, editSessionTitle)}
                                                                    onKeyDown={(e) => {
                                                                        if (e.key === "Enter") handleRenameSession(session.id, editSessionTitle);
                                                                        if (e.key === "Escape") setEditingSessionId(null);
                                                                    }}
                                                                    className="w-full px-3 py-2 text-xs bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                                                                />
                                                            ) : (
                                                                <Link
                                                                    href={`/projects/${currentProjectId}?session_id=${session.id}`}
                                                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${isActive
                                                                            ? "bg-cyan-500/15 text-white"
                                                                            : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                                                                        }`}
                                                                >
                                                                    <MessageSquare size={11} className="flex-shrink-0 opacity-40" />
                                                                    <span className="truncate flex-1">
                                                                        {session.title || "Untitled Chat"}
                                                                    </span>
                                                                    {session.is_default && (
                                                                        <span className="text-[9px] text-cyan-500/50 flex-shrink-0">
                                                                            ●
                                                                        </span>
                                                                    )}
                                                                </Link>
                                                            )}

                                                            {/* Three-dot menu button */}
                                                            {(isHovered || sessionMenuOpen === session.id) && editingSessionId !== session.id && (
                                                                <button
                                                                    onClick={(e) => openSessionMenu(e, session.id)}
                                                                    className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                                                                >
                                                                    <MoreVertical size={12} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    );
                                                })
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </nav>

            {/* Footer */}
            <div className="p-3 border-t border-gray-800/50 flex-shrink-0">
                <Link
                    href="/settings"
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${isCollapsed ? "justify-center" : ""
                        } ${pathname === "/settings"
                            ? "bg-gray-800 text-white"
                            : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
                        }`}
                    title={isCollapsed ? "Settings" : ""}
                >
                    <SettingsIcon size={20} />
                    {!isCollapsed && <span>Settings</span>}
                </Link>
            </div>

            {/* Fixed-position Project Dropdown — rendered outside scroll container to avoid clipping */}
            {menuOpen && menuPos && openMenuProject && (
                <div
                    ref={menuRef}
                    style={{ position: "fixed", top: menuPos.top, right: menuPos.right, zIndex: 9999 }}
                    className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px]"
                >
                    <Link
                        href={`/projects/${openMenuProject.id}/settings`}
                        className="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                        onClick={() => { setMenuOpen(null); setMenuPos(null); }}
                    >
                        <SettingsIcon size={14} />
                        Settings
                    </Link>
                    <button
                        onClick={() => startEditProject(openMenuProject)}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                    >
                        <Pencil size={14} />
                        Rename Project
                    </button>
                    <button
                        onClick={() =>
                            handleCloneProject(
                                openMenuProject.id,
                                openMenuProject.display_name || openMenuProject.name
                            )
                        }
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                    >
                        <Copy size={14} />
                        Clone Project
                    </button>
                    <Link
                        href={`/projects/${openMenuProject.id}`}
                        className="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                        onClick={() => { setMenuOpen(null); setMenuPos(null); }}
                    >
                        <ExternalLink size={14} />
                        Open Workspace
                    </Link>
                    <button
                        onClick={() =>
                            handleExportChat(
                                openMenuProject.id,
                                openMenuProject.display_name || openMenuProject.name
                            )
                        }
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                    >
                        <Download size={14} />
                        Export Chat
                    </button>
                    <div className="my-1 border-t border-gray-700" />
                    <button
                        onClick={() =>
                            handleDeleteProject(
                                openMenuProject.id,
                                openMenuProject.display_name || openMenuProject.name
                            )
                        }
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
                    >
                        <Trash2 size={14} />
                        Delete Project
                    </button>
                </div>
            )}

            {/* Fixed-position Session Dropdown — rendered outside scroll container to avoid clipping */}
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
                        <Pencil size={14} />
                        Rename
                    </button>
                    <button
                        onClick={() => handleArchiveSession(openMenuSession.id)}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
                    >
                        <Archive size={14} />
                        Archive
                    </button>
                </div>
            )}
        </div>
    );
}
