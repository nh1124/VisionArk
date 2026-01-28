"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { apiFetch, getFileToken } from "@/lib/api";

import { useProjects } from "@/hooks/useProjects";
import { useNotification } from "@/lib/NotificationContext";
import { LayoutGrid, Folder, Bot, BarChart3, Settings as SettingsIcon, ChevronLeft, Sparkles, ClipboardList, AlarmClock } from "lucide-react";
import TaskSidebar from "./TaskSidebar";

interface SidebarProps {
    isCollapsed: boolean;
    onToggle: () => void;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
    const pathname = usePathname();
    const { projects } = useProjects();
    const [projectsExpanded, setProjectsExpanded] = useState(true);
    const [hoveredProject, setHoveredProject] = useState<string | null>(null);
    const [menuOpen, setMenuOpen] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    const { showConfirm, showToast } = useNotification();

    // Close menu when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setMenuOpen(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const handleExportChat = async (projectId: string, displayName: string) => {
        try {
            const token = await getFileToken();
            const exportUrl = `/api/export/chat/project/${projectId}?token=${token}`;

            // Create a temporary link to trigger download
            const link = document.createElement('a');
            link.href = exportUrl;
            link.setAttribute('download', `${displayName}_chat.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            setMenuOpen(null);
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
                window.location.reload(); // Refresh to show cloned project
            } else {
                const err = await response.json();
                showToast(`Failed to clone project: ${err.detail || 'Unknown error'}`, "error");
            }
        } catch (error) {
            console.error("Clone failed:", error);
            showToast("Failed to clone project.", "error");
        }
    };

    const handleDeleteProject = async (projectId: string, displayName: string) => {
        const confirmed = await showConfirm(`Delete project '${displayName}'? This action cannot be undone.`, {
            title: "Delete Project",
            confirmText: "Delete",
            variant: "danger"
        });

        if (!confirmed) {
            return;
        }

        try {
            await apiFetch(`/api/agents/project/${projectId}`, { method: "DELETE" });
            setMenuOpen(null);
            window.location.href = "/projects"; // Redirect after deletion
        } catch (error) {
            console.error("Delete failed:", error);
            showToast("Failed to delete project.", "error");
        }
    };

    const navItems = [
        { name: "Dashboard", path: "/dashboard", icon: <LayoutGrid size={20} /> },
        { name: "Projects", path: "/projects", icon: <Folder size={20} /> },
        { name: "Tasks", path: "/tasks", icon: <ClipboardList size={20} /> },
        { name: "Skills", path: "/skills", icon: <Sparkles size={20} /> },
        { name: "Cron Tasks", path: "/cron", icon: <AlarmClock size={20} /> },
    ];

    return (
        <div
            id="vision-ark-sidebar"
            className={`bg-gray-950 border-r border-gray-800/50 flex flex-col h-full transition-all duration-200 relative flex-shrink-0 ${isCollapsed ? "w-16" : "w-64"}`}
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
            <nav className="flex-1 py-2 overflow-y-auto">
                {/* Main Nav */}
                <div className="px-3 space-y-1">
                    {navItems.map((item) => {
                        const isActive = pathname === item.path;
                        return (
                            <Link
                                key={item.path}
                                href={item.path}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${isCollapsed ? "justify-center" : ""} ${isActive
                                    ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/20"
                                    : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
                                    }`}
                                title={isCollapsed ? item.name : ""}
                            >
                                <span className={isActive ? "text-white" : "text-gray-500"}>{item.icon}</span>
                                {!isCollapsed && <span>{item.name}</span>}
                            </Link>
                        );
                    })}
                </div>

                {/* Task Context Sidebar or Projects Section */}
                {pathname === "/tasks" ? (
                    <div className="mt-4 pt-4 border-t border-gray-800/50">
                        <TaskSidebar isCollapsed={isCollapsed} />
                    </div>
                ) : (
                    <div className="mt-4 pt-4 border-t border-gray-800/50">
                        <button
                            onClick={() => setProjectsExpanded(!projectsExpanded)}
                            className={`flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors ${isCollapsed ? "justify-center px-2" : ""}`}
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
                            <div className="mt-1 px-2 space-y-0.5">
                                {projects.length === 0 ? (
                                    <div className="px-3 py-2 text-xs text-gray-600 italic">
                                        No projects yet
                                    </div>
                                ) : (
                                    projects.map((project) => {
                                        const projectPath = project.path; // Already /projects/{id}
                                        const isActive = pathname === projectPath || pathname.startsWith(projectPath + "/");
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
                                                <Link
                                                    href={projectPath}
                                                    className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${isActive
                                                        ? "bg-gray-800 text-white"
                                                        : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                                                        }`}
                                                >
                                                    <span className="truncate flex-1">{project.display_name || project.name}</span>
                                                </Link>

                                                {/* Three-dot menu */}
                                                {(isHovered || menuOpen === project.id) && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.preventDefault();
                                                            e.stopPropagation();
                                                            setMenuOpen(menuOpen === project.id ? null : project.id);
                                                        }}
                                                        className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                                                    >
                                                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                                            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                                        </svg>
                                                    </button>
                                                )}

                                                {/* Dropdown Menu */}
                                                {menuOpen === project.id && (
                                                    <div
                                                        ref={menuRef}
                                                        className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[160px] z-50"
                                                    >
                                                        <Link
                                                            href={`/projects/${project.id}/settings`}
                                                            className="flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                            onClick={() => setMenuOpen(null)}
                                                        >
                                                            ⚙️ Settings
                                                        </Link>
                                                        <button
                                                            onClick={() => handleCloneProject(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                        >
                                                            📋 Clone Project
                                                        </button>
                                                        <Link
                                                            href={`/projects/${project.id}`}
                                                            className="flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                            onClick={() => setMenuOpen(null)}
                                                        >
                                                            🚀 Open Workspace
                                                        </Link>
                                                        <button
                                                            onClick={() => handleExportChat(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                        >
                                                            📥 Export Chat
                                                        </button>
                                                        <div className="my-1 border-t border-gray-700"></div>
                                                        <button
                                                            onClick={() => handleDeleteProject(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center px-3 py-2 text-sm text-red-400 hover:bg-red-500/10"
                                                        >
                                                            🗑️ Delete Project
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })
                                )}

                                {/* New Project Button */}
                                <Link
                                    href="/new"
                                    className="flex items-center px-3 py-2 rounded-lg text-sm text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                >
                                    <span className="mr-2">+</span>
                                    <span>New Project</span>
                                </Link>
                            </div>
                        )}
                    </div>
                )}
            </nav>

            {/* AI Manager Entry Removed (Moved to Global Floating Button) */}

            {/* Footer */}
            <div className="p-3 border-t border-gray-800/50">
                <Link
                    href="/settings"
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-bold transition-all ${isCollapsed ? "justify-center" : ""} ${pathname === "/settings"
                        ? "bg-gray-800 text-white"
                        : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
                        }`}
                    title={isCollapsed ? "Settings" : ""}
                >
                    <SettingsIcon size={20} />
                    {!isCollapsed && <span>Settings</span>}
                </Link>
            </div>
        </div>
    );
}
