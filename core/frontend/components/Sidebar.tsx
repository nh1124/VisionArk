"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useRef, ReactNode, useMemo } from "react";
import { apiFetch, getFileToken } from "@/lib/api";
import { useProjects } from "@/hooks/useProjects";
import { useNotification } from "@/lib/NotificationContext";
import {
    Home,
    Folder,
    ClipboardList,
    Library,
    Bot,
    Monitor,
    Settings as SettingsIcon,
    MessageSquare,
    Plus,
    ChevronLeft,
    Copy,
    ExternalLink,
    Download,
    Trash2,
    MoreVertical,
    Pencil,
    Archive,
    CheckSquare,
    StickyNote,
    FileText,
    Workflow,
    Play,
    ShieldCheck,
    AlarmClock,
    HardDrive,
    Link2,
} from "lucide-react";
import TaskSidebar from "./TaskSidebar";

interface SessionItem {
    id: string;
    title: string | null;
    is_default: boolean;
    last_message_at: string | null;
}

type PrimaryNavId = "home" | "projects" | "tasks" | "knowledge" | "automation" | "devices";

interface PrimaryNavItem {
    id: PrimaryNavId;
    name: string;
    path: string;
    icon: ReactNode;
}

const primaryNavItems: PrimaryNavItem[] = [
    { id: "home", name: "Home", path: "/dashboard", icon: <Home size={18} /> },
    { id: "projects", name: "Projects", path: "/projects", icon: <Folder size={18} /> },
    { id: "tasks", name: "Tasks", path: "/tasks", icon: <ClipboardList size={18} /> },
    { id: "knowledge", name: "Knowledge", path: "/workspace", icon: <Library size={18} /> },
    { id: "automation", name: "Automation", path: "/cron", icon: <Bot size={18} /> },
    { id: "devices", name: "Devices", path: "/settings/devices", icon: <Monitor size={18} /> },
];

function getCurrentPrimaryNav(pathname: string): PrimaryNavId {
    if (pathname.startsWith("/projects")) return "projects";
    if (pathname.startsWith("/tasks")) return "tasks";
    if (pathname.startsWith("/notes") || pathname.startsWith("/workspace")) return "knowledge";
    if (
        pathname.startsWith("/cron") ||
        pathname.startsWith("/agents") ||
        pathname.startsWith("/jobs") ||
        pathname.startsWith("/approvals")
    ) {
        return "automation";
    }
    if (pathname.startsWith("/settings/devices")) return "devices";
    return "home";
}

interface SecondaryLinkProps {
    href: string;
    active: boolean;
    icon?: ReactNode;
    label: string;
    onClick?: () => void;
}

function SecondaryLink({ href, active, icon, label, onClick }: SecondaryLinkProps) {
    return (
        <Link
            href={href}
            onClick={onClick}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                    ? "bg-cyan-500/12 text-cyan-300"
                    : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"
            }`}
        >
            {icon && <span className={active ? "text-cyan-300" : "text-gray-500"}>{icon}</span>}
            <span className="truncate">{label}</span>
        </Link>
    );
}

function SecondarySection({
    title,
    children,
}: {
    title: string;
    children: ReactNode;
}) {
    return (
        <section className="space-y-1">
            <h3 className="px-3 text-[10px] font-black uppercase tracking-[0.16em] text-gray-600">{title}</h3>
            <div className="space-y-1">{children}</div>
        </section>
    );
}

export default function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { projects } = useProjects();
    const currentPrimaryNav = getCurrentPrimaryNav(pathname);

    const [hoveredProject, setHoveredProject] = useState<string | null>(null);
    const [menuOpen, setMenuOpen] = useState<string | null>(null);
    const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    const [sessions, setSessions] = useState<SessionItem[]>([]);
    const [hoveredSession, setHoveredSession] = useState<string | null>(null);
    const [sessionMenuOpen, setSessionMenuOpen] = useState<string | null>(null);
    const [sessionMenuPos, setSessionMenuPos] = useState<{ top: number; right: number } | null>(null);
    const sessionMenuRef = useRef<HTMLDivElement>(null);
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editSessionTitle, setEditSessionTitle] = useState("");
    const sessionEditRef = useRef<HTMLInputElement>(null);
    const [projectSearchQuery, setProjectSearchQuery] = useState("");
    const [chatSearchQuery, setChatSearchQuery] = useState("");

    const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
    const [editProjectTitle, setEditProjectTitle] = useState("");
    const projectEditRef = useRef<HTMLInputElement>(null);

    const { showConfirm, showToast } = useNotification();

    const projectMatch = pathname.match(/^\/projects\/([^\/]+)/);
    const currentProjectId = projectMatch ? projectMatch[1] : null;
    const activeSessionId = searchParams.get("session_id");
    const isAllProjectsMode = pathname === "/projects";

    const filteredProjects = useMemo(() => {
        const query = projectSearchQuery.trim().toLowerCase();
        if (!query) return projects;
        return projects.filter((project) =>
            (project.display_name || project.name || "").toLowerCase().includes(query)
        );
    }, [projects, projectSearchQuery]);

    const filteredSessions = useMemo(() => {
        const query = chatSearchQuery.trim().toLowerCase();
        if (!query) return sessions;
        return sessions.filter((session) =>
            (session.title || "untitled chat").toLowerCase().includes(query)
        );
    }, [sessions, chatSearchQuery]);

    useEffect(() => {
        if (!currentProjectId) {
            setSessions([]);
            return;
        }
        apiFetch(`/api/agents/project/${currentProjectId}/sessions`)
            .then((res) => res.json())
            .then((data) => setSessions(data.sessions || []))
            .catch(() => {});
    }, [currentProjectId]);

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
        } catch (error) {
            console.error("Failed to create session:", error);
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
        if (!newTitle.trim()) {
            setEditingProjectId(null);
            return;
        }

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
        } catch (error) {
            console.error("Rename project failed:", error);
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
        if (!newTitle.trim()) {
            setEditingSessionId(null);
            return;
        }

        try {
            const res = await apiFetch(`/api/agents/sessions/${sessionId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: newTitle.trim() }),
            });
            const updated = await res.json();
            setSessions((prev) =>
                prev.map((session) =>
                    session.id === sessionId ? { ...session, title: updated.title } : session
                )
            );
        } catch (error) {
            console.error("Rename session failed:", error);
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
            setSessions((prev) => prev.filter((session) => session.id !== sessionId));
            if (activeSessionId === sessionId && currentProjectId) {
                router.push(`/projects/${currentProjectId}`);
            }
        } catch (error) {
            console.error("Archive session failed:", error);
        }
        setSessionMenuOpen(null);
        setSessionMenuPos(null);
    };

    const openMenuProject = projects.find((project) => project.id === menuOpen);
    const openMenuSession = sessions.find((session) => session.id === sessionMenuOpen);

    const renderHomeSecondary = () => (
        <div className="space-y-5">
            <SecondarySection title="Overview">
                <SecondaryLink href="/dashboard" active={pathname === "/dashboard"} icon={<Home size={15} />} label="Dashboard" />
                <SecondaryLink href="/tasks" active={pathname.startsWith("/tasks")} icon={<CheckSquare size={15} />} label="Today" />
            </SecondarySection>
        </div>
    );

    const renderProjectsSecondary = () =>
        isAllProjectsMode ? (
            <div className="space-y-4">
                <div className="flex items-center gap-2 px-1 py-1 text-gray-300">
                    <Folder size={16} />
                    <span className="text-[2rem] leading-none font-semibold">All Projects</span>
                </div>

                <div className="px-1">
                    <input
                        type="text"
                        placeholder="Search projects..."
                        value={projectSearchQuery}
                        onChange={(e) => setProjectSearchQuery(e.target.value)}
                        className="w-full h-11 rounded-xl bg-gray-900/80 border border-gray-800 px-4 text-gray-200 placeholder:text-gray-500 outline-none focus:border-cyan-500/40"
                    />
                </div>

                <Link
                    href="/new"
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                >
                    <Plus size={15} />
                    <span>New Project</span>
                </Link>

                <div className="border-t border-gray-800/60 pt-2">
                    <div className="space-y-1 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
                        <SecondaryLink
                            href="/projects"
                            active={pathname === "/projects"}
                            icon={<Folder size={15} />}
                            label="All Projects"
                        />
                        {filteredProjects.length === 0 ? (
                            <div className="px-3 py-2 text-xs text-gray-600 italic">No matching projects</div>
                        ) : filteredProjects.map((project) => {
                            const projectPath = project.path;
                            const isActive = pathname === projectPath || pathname.startsWith(`${projectPath}/`);
                            const isHovered = hoveredProject === project.id;
                            return (
                                <div
                                    key={project.id}
                                    className="relative"
                                    onMouseEnter={() => setHoveredProject(project.id)}
                                    onMouseLeave={() => {
                                        if (menuOpen !== project.id) setHoveredProject(null);
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
                                            className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${
                                                isActive
                                                    ? "bg-gray-800 text-white"
                                                    : "text-gray-400 hover:bg-gray-800/70 hover:text-white"
                                            }`}
                                        >
                                            <span className="truncate flex-1">{project.display_name || project.name}</span>
                                        </Link>
                                    )}

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
                        })}
                    </div>
                </div>
            </div>
        ) : (
            <div className="space-y-4">
                <Link
                    href="/projects"
                    className="w-full flex items-center gap-2 px-1 py-1 text-gray-300 hover:text-white"
                >
                    <ChevronLeft size={16} />
                    <span className="text-[2rem] leading-none font-semibold">Projects</span>
                </Link>

                <div className="px-1">
                    <input
                        type="text"
                        placeholder="Search chats..."
                        value={chatSearchQuery}
                        onChange={(e) => setChatSearchQuery(e.target.value)}
                        className="w-full h-11 rounded-xl bg-gray-900/80 border border-gray-800 px-4 text-gray-200 placeholder:text-gray-500 outline-none focus:border-cyan-500/40"
                    />
                </div>

                <button
                    onClick={handleNewChat}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                >
                    <Plus size={15} />
                    <span>New Chat</span>
                </button>

                <div className="border-t border-gray-800/60 pt-2">
                    <div className="space-y-1 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
                        {filteredSessions.length === 0 ? (
                            <div className="px-3 py-2 text-xs text-gray-600 italic">No matching chats</div>
                        ) : filteredSessions.map((session) => {
                            const isActive = activeSessionId === session.id;
                            const isHovered = hoveredSession === session.id;
                            return (
                                <div
                                    key={session.id}
                                    className="relative"
                                    onMouseEnter={() => setHoveredSession(session.id)}
                                    onMouseLeave={() => {
                                        if (sessionMenuOpen !== session.id) setHoveredSession(null);
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
                                            className="w-full px-3 py-2 text-sm bg-gray-800 text-white rounded-lg border border-cyan-500/50 outline-none"
                                        />
                                    ) : (
                                        <Link
                                            href={`/projects/${currentProjectId}?session_id=${session.id}`}
                                            className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-left ${
                                                isActive
                                                    ? "bg-cyan-500/15 text-white"
                                                    : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                                            }`}
                                        >
                                            <MessageSquare size={11} className="flex-shrink-0 opacity-40" />
                                            <span className="truncate flex-1">{session.title || "Untitled Chat"}</span>
                                        </Link>
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
                            );
                        })}
                    </div>
                </div>
            </div>
        );

    const renderTasksSecondary = () => (
        <div className="space-y-3">
            <TaskSidebar isCollapsed={false} />
        </div>
    );

    const renderKnowledgeSecondary = () => (
        <div className="space-y-5">
            <SecondarySection title="Content">
                <SecondaryLink href="/notes" active={pathname.startsWith("/notes")} icon={<StickyNote size={15} />} label="Notes" />
                <SecondaryLink href="/workspace" active={pathname.startsWith("/workspace")} icon={<FileText size={15} />} label="Artifacts" />
            </SecondarySection>
            <SecondarySection title="Scope">
                <SecondaryLink href="/workspace" active={pathname.startsWith("/workspace")} icon={<Library size={15} />} label="Workspace" />
                <SecondaryLink href="/projects" active={pathname.startsWith("/projects")} icon={<Folder size={15} />} label="Project Context" />
            </SecondarySection>
        </div>
    );

    const renderAutomationSecondary = () => (
        <div className="space-y-5">
            <SecondarySection title="Automation">
                <SecondaryLink href="/cron" active={pathname.startsWith("/cron")} icon={<AlarmClock size={15} />} label="Cron" />
                <SecondaryLink href="/agents" active={pathname.startsWith("/agents")} icon={<Bot size={15} />} label="Agents" />
                <SecondaryLink href="/jobs" active={pathname.startsWith("/jobs")} icon={<Play size={15} />} label="Runs" />
                <SecondaryLink href="/approvals" active={pathname.startsWith("/approvals")} icon={<ShieldCheck size={15} />} label="Approvals" />
            </SecondarySection>
            <SecondarySection title="Operations">
                <SecondaryLink href="/jobs" active={pathname.startsWith("/jobs")} icon={<Workflow size={15} />} label="Queues" />
            </SecondarySection>
        </div>
    );

    const renderDevicesSecondary = () => (
        <div className="space-y-5">
            <SecondarySection title="Devices">
                <SecondaryLink href="/settings/devices" active={pathname.startsWith("/settings/devices")} icon={<HardDrive size={15} />} label="All Devices" />
                <SecondaryLink href="/settings/devices" active={pathname.startsWith("/settings/devices")} icon={<Monitor size={15} />} label="This Device" />
            </SecondarySection>
            <SecondarySection title="Access">
                <SecondaryLink href="/settings" active={pathname === "/settings"} icon={<SettingsIcon size={15} />} label="Permissions" />
                <SecondaryLink href="/settings" active={pathname === "/settings"} icon={<Link2 size={15} />} label="Connections" />
            </SecondarySection>
        </div>
    );

    const renderSecondaryContent = () => {
        if (currentPrimaryNav === "projects") return renderProjectsSecondary();
        if (currentPrimaryNav === "tasks") return renderTasksSecondary();
        if (currentPrimaryNav === "knowledge") return renderKnowledgeSecondary();
        if (currentPrimaryNav === "automation") return renderAutomationSecondary();
        if (currentPrimaryNav === "devices") return renderDevicesSecondary();
        return renderHomeSecondary();
    };

    const secondaryTitles: Record<PrimaryNavId, string> = {
        home: "Home Context",
        projects: "Projects",
        tasks: "Tasks",
        knowledge: "Knowledge",
        automation: "Automation",
        devices: "Devices",
    };

    return (
        <>
            <div id="vision-ark-sidebar" className="flex h-full flex-shrink-0 border-r border-gray-800/50 bg-gray-950">
                <aside className="w-52 border-r border-gray-800/50 flex flex-col">
                    <div className="p-4 border-b border-gray-800/50">
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm">
                                V
                            </div>
                            <span className="text-sm font-semibold text-white">Vision Ark</span>
                        </div>
                    </div>

                    <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
                        {primaryNavItems.map((item) => {
                            const isActive = currentPrimaryNav === item.id;
                            return (
                                <Link
                                    key={item.path}
                                    href={item.path}
                                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                                        isActive
                                            ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/15"
                                            : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"
                                    }`}
                                >
                                    <span className={isActive ? "text-white" : "text-gray-500"}>{item.icon}</span>
                                    <span>{item.name}</span>
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="p-3 border-t border-gray-800/50">
                        <Link
                            href="/settings"
                            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                                pathname === "/settings"
                                    ? "bg-gray-800 text-white"
                                    : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"
                            }`}
                        >
                            <SettingsIcon size={18} />
                            <span>Settings</span>
                        </Link>
                    </div>
                </aside>

                {currentPrimaryNav !== "home" && (
                    <aside className="w-72 flex flex-col bg-gray-950/80">
                        {currentPrimaryNav !== "projects" && (
                            <div className="px-4 py-3 border-b border-gray-800/50">
                                <h2 className="text-sm font-semibold text-gray-200">{secondaryTitles[currentPrimaryNav]}</h2>
                                <p className="text-[11px] text-gray-500 mt-1">Page navigation and filters</p>
                            </div>
                        )}
                        <div className={`flex-1 overflow-y-auto p-3 ${currentPrimaryNav === "projects" ? "pt-6" : ""}`}>
                            {renderSecondaryContent()}
                        </div>
                    </aside>
                )}
            </div>

            {menuOpen && menuPos && openMenuProject && (
                <div
                    ref={menuRef}
                    style={{ position: "fixed", top: menuPos.top, right: menuPos.right, zIndex: 9999 }}
                    className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px]"
                >
                    <Link
                        href={`/projects/${openMenuProject.id}/settings`}
                        className="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                        onClick={() => {
                            setMenuOpen(null);
                            setMenuPos(null);
                        }}
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
                        onClick={() => {
                            setMenuOpen(null);
                            setMenuPos(null);
                        }}
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
        </>
    );
}
