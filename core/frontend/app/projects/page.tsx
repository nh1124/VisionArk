"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, getFileToken } from "@/lib/api";
import { Search, MoreVertical, Edit2, Trash2, X, Check, ExternalLink, Copy, Download, Send, Loader2, Settings, Rocket, Folder, Sparkles, LayoutGrid, List } from "lucide-react";
import { useNotification } from "@/lib/NotificationContext";

interface Project {
    id: string;
    name: string;
    display_name?: string;
    path: string;
    has_custom_prompt: boolean;
    artifact_count: number;
    ref_count: number;
    queue_count: number;
    created_at?: string;
    updated_at?: string;
    members?: string[];
    latest_activity: string;
    last_activity_time?: string;
    next_task?: { type: string, at: string };
    processing_logs: string[];
}

// WorkspaceStats interface removed

export default function ProjectsPage() {
    const [projects, setProjects] = useState<Project[]>([]);

    const [loading, setLoading] = useState(true);
    const [newProjectPrompt, setNewProjectPrompt] = useState("");
    const [creating, setCreating] = useState(false);
    const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState("");

    // For Context Menu
    const [activeMenu, setActiveMenu] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    // For Renaming
    const [renamingProject, setRenamingProject] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [savingRename, setSavingRename] = useState(false);

    // For navigation after creation
    const router = useRouter();

    const [viewMode, setViewMode] = useState<"tile" | "list">("tile");
    const [systemHealth, setSystemHealth] = useState<"optimal" | "busy" | "degraded">("optimal");

    const { showConfirm, showToast } = useNotification();

    useEffect(() => {
        loadProjects();

        // Polling for live status
        const interval = setInterval(() => {
            loadProjects();
        }, 10000);

        // Close menu on click outside
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setActiveMenu(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
            clearInterval(interval);
        };
    }, []);

    // loadStats removed

    const loadProjects = async () => {
        try {
            const response = await apiFetch("/api/agents/project/list");
            const data = await response.json();
            if (data && data.projects && Array.isArray(data.projects)) {
                setProjects(data.projects);
            } else {
                console.warn("Unexpected projects data format:", data);
                setProjects([]);
            }
        } catch (error) {
            console.error("Error loading projects:", error);
        } finally {
            setLoading(false);
        }
    };

    const createProject = async () => {
        if (!newProjectPrompt.trim()) return;

        setCreating(true);
        try {
            const response = await apiFetch("/api/agents/project/create-from-prompt", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: newProjectPrompt }),
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Failed to create project");
            }

            const data = await response.json();

            // Store the initial prompt so it can be displayed immediately on the project page
            sessionStorage.setItem(`pending_prompt_${data.project_id}`, newProjectPrompt);

            // Redirect to new project with task_id
            router.push(`/projects/${data.project_id}?task_id=${data.task_id}`);
        } catch (error) {
            console.error("Error creating project:", error);
            setCreating(false);
        }
    };


    const toggleSelection = (projectId: string) => {
        const newSelected = new Set(selectedProjects);
        if (newSelected.has(projectId)) {
            newSelected.delete(projectId);
        } else {
            newSelected.add(projectId);
        }
        setSelectedProjects(newSelected);
    };

    const toggleSelectAll = (filteredProjects: Project[]) => {
        if (selectedProjects.size === filteredProjects.length && filteredProjects.length > 0) {
            setSelectedProjects(new Set());
        } else {
            setSelectedProjects(new Set(filteredProjects.map(s => s.id)));
        }
    };

    const cloneProject = async (projectId: string, currentDisplayName: string) => {
        // As per user feedback, start cloning with default name directly
        const newDisplayName = `${currentDisplayName} (Copy)`;

        try {
            const response = await apiFetch(`/api/agents/project/${projectId}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: newDisplayName }),
            });

            if (response.ok) {
                await loadProjects();
                setActiveMenu(null);
            } else {
                const err = await response.json();
                showToast(`Failed to clone project: ${err.detail || 'Unknown error'}`, "error");
            }
        } catch (error) {
            console.error("Error cloning project:", error);
            showToast("Error cloning project", "error");
        }
    };

    const deleteProject = async (projectId: string, displayName: string) => {
        const confirmed = await showConfirm(`Delete project '${displayName}'? This action cannot be undone.`, {
            title: "Delete Project",
            confirmText: "Delete",
            variant: "danger"
        });

        if (!confirmed) return;

        try {
            await apiFetch(`/api/agents/project/${projectId}`, { method: "DELETE" });
            await loadProjects();
            setActiveMenu(null);
        } catch (error) {
            console.error("Error deleting project:", error);
            showToast("Failed to delete project", "error");
        }
    };

    const bulkDelete = async () => {
        if (selectedProjects.size === 0) return;

        const confirmed = await showConfirm(`Delete ${selectedProjects.size} project(s)? This action cannot be undone.`, {
            title: "Bulk Delete",
            confirmText: "Delete All",
            variant: "danger"
        });

        if (!confirmed) return;

        try {
            await Promise.all(
                Array.from(selectedProjects).map(projectId =>
                    apiFetch(`/api/agents/project/${projectId}`, { method: "DELETE" })
                )
            );
            setSelectedProjects(new Set());
            await loadProjects();
        } catch (error) {
            console.error("Error deleting projects:", error);
            showToast("Failed to delete some projects", "error");
        }
    };

    const startRename = (project: Project) => {
        setRenamingProject(project.id);
        setRenameValue(project.display_name || project.name);
        setActiveMenu(null);
    };

    const saveRename = async (projectId: string) => {
        if (!renameValue.trim()) return;
        setSavingRename(true);
        try {
            const response = await apiFetch(`/api/agents/project/${projectId}/rename`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: renameValue }),
            });
            if (response.ok) {
                setRenamingProject(null);
                await loadProjects();
            } else {
                showToast("Failed to rename project", "error");
            }
        } catch (error) {
            console.error("Rename error:", error);
            showToast("Error renaming project", "error");
        } finally {
            setSavingRename(false);
        }
    };

    const handleExportChat = async (projectId: string, displayName: string) => {
        try {
            const token = await getFileToken();
            const exportUrl = `/api/export/chat/project/${projectId}?token=${token}`;

            const link = document.createElement('a');
            link.href = exportUrl;
            link.setAttribute('download', `${displayName}_chat.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            setActiveMenu(null);
        } catch (error) {
            console.error("Export failed:", error);
            showToast("Failed to export chat history.", "error");
        }
    };

    const filteredProjects = projects.filter(s =>
        (s.name && s.name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (s.display_name && s.display_name.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    return (
        <div className="p-8 w-full flex flex-col items-center">
            <div className="w-full max-w-7xl">
                {/* Header Section */}
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
                    <div>
                        <h1 className="text-4xl font-black text-white tracking-tighter mb-2">Workspace</h1>
                    </div>

                    <div className="flex items-center gap-3">
                        <div className="flex bg-gray-900/80 p-1.5 rounded-2xl border border-gray-800 shadow-2xl backdrop-blur-md">
                            <button
                                onClick={() => setViewMode("tile")}
                                className={`p-2.5 rounded-xl transition-all ${viewMode === "tile" ? "bg-cyan-500 text-white shadow-[0_0_20px_rgba(6,182,212,0.4)] scale-105" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"}`}
                                title="Tile View"
                            >
                                <LayoutGrid size={18} />
                            </button>
                            <button
                                onClick={() => setViewMode("list")}
                                className={`p-2.5 rounded-xl transition-all ${viewMode === "list" ? "bg-cyan-500 text-white shadow-[0_0_20px_rgba(6,182,212,0.4)] scale-105" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"}`}
                                title="List View"
                            >
                                <List size={18} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Command Center Stats Removed */}

                {/* Create New Project */}
                <div className="mb-12">
                    <div className="flex flex-col sm:flex-row gap-4">
                        <div className="relative flex-1">
                            <input
                                type="text"
                                value={newProjectPrompt}
                                onChange={(e) => setNewProjectPrompt(e.target.value)}
                                onKeyPress={(e) => e.key === "Enter" && !creating && createProject()}
                                placeholder="What would you like to build today?"
                                className="w-full bg-gray-900/50 border border-gray-800 focus:border-cyan-500/50 rounded-2xl px-6 py-4 text-sm focus:outline-none transition-all shadow-inner"
                                disabled={creating}
                            />
                            {creating && <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-cyan-500" />}
                        </div>
                        <button
                            onClick={createProject}
                            disabled={creating || !newProjectPrompt.trim()}
                            className="bg-white text-black hover:bg-gray-200 disabled:bg-gray-800 disabled:text-gray-500 px-8 py-4 rounded-2xl font-bold text-sm transition-all active:scale-95 shadow-lg whitespace-nowrap"
                        >
                            Create Project
                        </button>
                    </div>
                </div>


                {/* Content Area - Independent of global loading state if filtered projects exist or loading is sub-area */}
                <div className="min-h-[400px]">
                    {/* Bulk Actions Bar */}
                    {!loading && filteredProjects.length > 0 && (
                        <div className="mb-6 flex items-center justify-between border-b border-gray-800 pb-4">
                            <label className="flex items-center gap-3 text-sm text-gray-400 cursor-pointer group hover:text-gray-200 transition-colors">
                                <input
                                    type="checkbox"
                                    checked={selectedProjects.size === filteredProjects.length && filteredProjects.length > 0}
                                    onChange={() => toggleSelectAll(filteredProjects)}
                                    className="w-4 h-4 rounded border-gray-700 bg-gray-900 text-cyan-500 focus:ring-cyan-500/30"
                                />
                                <span className="font-medium">
                                    {selectedProjects.size === filteredProjects.length ? "Deselect All" : "Select All Visible"}
                                    <span className="ml-2 px-1.5 py-0.5 bg-gray-800 rounded text-[10px] text-gray-500">{selectedProjects.size}/{filteredProjects.length}</span>
                                </span>
                            </label>

                            {selectedProjects.size > 0 && (
                                <button
                                    onClick={bulkDelete}
                                    className="flex items-center gap-2 px-4 py-1.5 bg-red-500/10 border border-red-500/30 text-red-500 hover:bg-red-500 hover:text-white rounded-lg text-xs font-bold transition-all shadow-lg"
                                >
                                    <Trash2 size={12} />
                                    DELETE SELECTED
                                </button>
                            )}
                        </div>
                    )}

                    {/* Projects Content: Bento Grid */}
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-32 gap-4">
                            <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin"></div>
                            <p className="text-gray-500 text-sm animate-pulse tracking-wide italic">Retrieving your projects...</p>
                        </div>
                    ) : filteredProjects.length === 0 ? (
                        <div className="text-center py-24 bg-gray-900/10 border border-dashed border-gray-800/50 rounded-3xl backdrop-blur-sm">
                            <div className="w-20 h-20 bg-gray-800/40 rounded-full flex items-center justify-center mx-auto mb-6 text-3xl opacity-50 shadow-inner">
                                {searchQuery ? "🔍" : "💎"}
                            </div>
                            <p className="text-xl font-medium text-gray-400 mb-2">
                                {searchQuery ? `No results found for "${searchQuery}"` : "Your project list is empty"}
                            </p>
                        </div>
                    ) : (
                        <div className={viewMode === 'tile' ? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 auto-rows-min" : "flex flex-col gap-3"}>
                            {filteredProjects.map((project) => {
                                const isSelected = selectedProjects.has(project.id);
                                const isMenuOpen = activeMenu === project.id;
                                const hasActiveTask = project.queue_count > 0;
                                const hasUpcoming = !!project.next_task;

                                // Bento Size Logic
                                let colSpan = "col-span-1";
                                let rowSpan = "row-span-1";
                                if (viewMode === 'tile') {
                                    if (hasActiveTask) {
                                        colSpan = "lg:col-span-2";
                                        rowSpan = "row-span-2";
                                    } else if (hasUpcoming) {
                                        colSpan = "lg:col-span-1";
                                        rowSpan = "row-span-1";
                                    }
                                }

                                if (viewMode === 'list') {
                                    return (
                                        <div
                                            key={project.id}
                                            className={`group flex items-center justify-between bg-gray-900/40 border ${isSelected ? 'border-cyan-500' : 'border-gray-800'} rounded-2xl p-4 hover:bg-gray-800/50 transition-all`}
                                        >
                                            <div className="flex items-center gap-4 flex-1 min-w-0">
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onChange={() => toggleSelection(project.id)}
                                                    className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-cyan-500"
                                                />
                                                <Link href={`/projects/${project.id}`} className="flex-1 min-w-0">
                                                    <h3 className="font-bold text-sm text-gray-100 truncate group-hover:text-cyan-400">
                                                        {project.display_name || project.name}
                                                    </h3>
                                                </Link>
                                            </div>

                                            <div className="flex items-center gap-8 px-6">
                                                <div className="flex flex-col items-center">
                                                    <span className="text-[9px] text-gray-600 font-bold uppercase">Artifacts</span>
                                                    <span className="text-xs font-mono text-gray-300">{project.artifact_count}</span>
                                                </div>
                                                <div className="flex flex-col items-center">
                                                    <span className="text-[9px] text-gray-600 font-bold uppercase">Refs</span>
                                                    <span className="text-xs font-mono text-gray-300">{project.ref_count}</span>
                                                </div>
                                                <div className="flex flex-col items-center w-16">
                                                    <span className="text-[9px] text-gray-600 font-bold uppercase">Queue</span>
                                                    <span className={`text-xs font-mono ${(project as any).queue_count > 0 ? 'text-cyan-400 animate-pulse' : 'text-gray-500'}`}>
                                                        {(project as any).queue_count || 0}
                                                    </span>
                                                </div>
                                            </div>

                                            <div className="relative">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); setActiveMenu(isMenuOpen ? null : project.id); }}
                                                    className="p-2 text-gray-500 hover:text-white"
                                                >
                                                    <MoreVertical size={16} />
                                                </button>
                                                {isMenuOpen && (
                                                    <div ref={menuRef} className="absolute right-0 top-10 w-48 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 py-1">
                                                        <button onClick={() => startRename(project)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                            <Settings size={14} /> Settings
                                                        </button>
                                                        <button onClick={() => cloneProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                            <Copy size={14} /> Clone Project
                                                        </button>
                                                        <button onClick={() => router.push(`/projects/${project.id}`)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                            <Rocket size={14} /> Open Workspace
                                                        </button>
                                                        <button onClick={() => handleExportChat(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                            <Download size={14} /> Export Chat
                                                        </button>
                                                        <div className="border-t border-gray-800 mx-2 my-1"></div>
                                                        <button onClick={() => deleteProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-500 hover:bg-red-500/10 font-medium">
                                                            <Trash2 size={14} /> Delete Project
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                }

                                return (
                                    <div
                                        key={project.id}
                                        className={`group relative bg-gray-900/60 border rounded-3xl p-6 transition-all duration-300 flex flex-col ${colSpan} ${rowSpan} ${isSelected ? "border-cyan-500 ring-1 ring-cyan-500/20" : "border-gray-800 hover:border-cyan-500/30 shadow-xl"}`}
                                    >
                                        <div className="flex items-start justify-between mb-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className={`w-2 h-2 rounded-full ${hasActiveTask ? 'bg-green-500 animate-pulse' : hasUpcoming ? 'bg-blue-500' : 'bg-gray-700'}`}></span>
                                                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest leading-none">
                                                        {hasActiveTask ? 'Processing' : hasUpcoming ? 'Scheduled' : 'Dormant'}
                                                    </span>
                                                </div>
                                                <Link href={`/projects/${project.id}`}>
                                                    <h3 className={`font-black tracking-tight text-white truncate group-hover:text-cyan-400 transition-colors ${hasActiveTask ? 'text-xl' : 'text-base'}`}>
                                                        {project.display_name || project.name}
                                                    </h3>
                                                </Link>
                                            </div>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setActiveMenu(isMenuOpen ? null : project.id); }}
                                                className="p-2 text-gray-600 hover:text-white"
                                            >
                                                <MoreVertical size={18} />
                                            </button>
                                        </div>

                                        {/* Large Card: Terminal Content */}
                                        {hasActiveTask && colSpan.includes("lg:col-span-2") && (
                                            <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-6 mb-6">
                                                <div className="flex-1 bg-black/60 rounded-2xl p-4 font-mono text-[11px] leading-relaxed border border-white/5 overflow-hidden">
                                                    <div className="flex items-center justify-between mb-3 border-b border-white/10 pb-2">
                                                        <span className="text-gray-500 flex items-center gap-1.5 font-bold"><span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> TERMINAL LOGS</span>
                                                        <span className="text-gray-700">v4.0.1</span>
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        {project.processing_logs.length > 0 ? project.processing_logs.map((log, i) => (
                                                            <div key={i} className="text-cyan-400/80 truncate">
                                                                <span className="text-gray-700 mr-2">[{new Date().toLocaleTimeString()}]</span>
                                                                {log}
                                                            </div>
                                                        )) : (
                                                            <div className="text-gray-700 italic">Listening for activity...</div>
                                                        )}
                                                        <div className="text-white animate-pulse">▋</div>
                                                    </div>
                                                </div>
                                                <div className="w-full lg:w-48 flex flex-col gap-4">
                                                    <div className="flex-1 bg-cyan-950/20 rounded-2xl p-4 border border-cyan-500/10">
                                                        <h4 className="text-[9px] font-bold text-cyan-500 uppercase tracking-widest mb-3">System Load</h4>
                                                        <div className="h-2 bg-gray-800 rounded-full overflow-hidden mb-2">
                                                            <div className="h-full bg-cyan-500 w-[75%] shadow-[0_0_10px_rgba(6,182,212,0.5)]"></div>
                                                        </div>
                                                        <div className="text-[10px] text-gray-400">Memory usage optimal</div>
                                                    </div>
                                                    <div className="bg-gray-800/20 rounded-2xl p-4">
                                                        <h4 className="text-[9px] font-bold text-gray-500 uppercase tracking-widest mb-2">Next Sync</h4>
                                                        <div className="text-xs font-bold text-white">14:00 AM</div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Medium/Small Content */}
                                        {(!hasActiveTask || !colSpan.includes("lg:col-span-2")) && (
                                            <div className="mb-6 flex-1">
                                                <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed italic mb-4">
                                                    {project.latest_activity || "Waiting for first interaction..."}
                                                </p>
                                                {hasUpcoming && (
                                                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 flex items-center justify-between">
                                                        <div className="flex flex-col">
                                                            <span className="text-[8px] font-bold text-blue-400 uppercase tracking-widest">Next Task</span>
                                                            <span className="text-[10px] font-bold text-white truncate w-32">{project.next_task?.type}</span>
                                                        </div>
                                                        <span className="text-[10px] font-mono text-blue-500 font-bold">{project.next_task?.at ? new Date(project.next_task.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""}</span>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Footer Stats (Always shown but smaller in focus) */}
                                        <div className="flex items-center justify-between mt-auto pt-4 border-t border-white/5">
                                            <div className="flex gap-4">
                                                <div className="flex items-center gap-1.5" title="Artifacts">
                                                    <Folder size={12} className="text-gray-600" />
                                                    <span className="text-xs font-bold text-gray-400">{project.artifact_count}</span>
                                                </div>
                                                <div className="flex items-center gap-1.5" title="References">
                                                    <Sparkles size={12} className="text-gray-600" />
                                                    <span className="text-xs font-bold text-gray-400">{project.ref_count}</span>
                                                </div>
                                            </div>
                                            <Link href={`/projects/${project.id}`} className="p-2 bg-gray-800/40 rounded-xl text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all">
                                                <ExternalLink size={14} />
                                            </Link>
                                        </div>

                                        {isMenuOpen && (
                                            <div ref={menuRef} className="absolute right-6 top-14 w-48 bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl z-50 py-1 overflow-hidden">
                                                <button onClick={() => startRename(project)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                    <Settings size={14} /> Settings
                                                </button>
                                                <button onClick={() => cloneProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                    <Copy size={14} /> Clone Project
                                                </button>
                                                <button onClick={() => router.push(`/projects/${project.id}`)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                    <Rocket size={14} /> Open Workspace
                                                </button>
                                                <button onClick={() => handleExportChat(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
                                                    <Download size={14} /> Export Chat
                                                </button>
                                                <div className="border-t border-gray-800 mx-2 my-1"></div>
                                                <button onClick={() => deleteProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-500 hover:bg-red-500/10 font-medium">
                                                    <Trash2 size={14} /> Delete Project
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
