"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, getFileToken } from "@/lib/api";
import { Search, MoreVertical, Edit2, Trash2, X, Check, ExternalLink, Copy, FileDown, Send, Loader2 } from "lucide-react";

interface Project {
    id: string;
    name: string;
    display_name?: string;
    path: string;
    has_custom_prompt: boolean;
    artifact_count: number;
    ref_count: number;
    created_at?: string;
    updated_at?: string;
    members?: string[];
}

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

    useEffect(() => {
        loadProjects();

        // Close menu on click outside
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setActiveMenu(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

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
                alert(`Failed to clone project: ${err.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error("Error cloning project:", error);
            alert("Error cloning project");
        }
    };

    const deleteProject = async (projectId: string, displayName: string) => {
        if (!confirm(`Delete project '${displayName}'? This action cannot be undone.`)) {
            return;
        }

        try {
            await apiFetch(`/api/agents/project/${projectId}`, { method: "DELETE" });
            await loadProjects();
            setActiveMenu(null);
        } catch (error) {
            console.error("Error deleting project:", error);
            alert("Failed to delete project");
        }
    };

    const bulkDelete = async () => {
        if (selectedProjects.size === 0) return;

        if (!confirm(`Delete ${selectedProjects.size} project(s)? This action cannot be undone.`)) {
            return;
        }

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
            alert("Failed to delete some projects");
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
                alert("Failed to rename project");
            }
        } catch (error) {
            console.error("Rename error:", error);
            alert("Error renaming project");
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
            alert("Failed to export chat history.");
        }
    };

    const filteredProjects = projects.filter(s =>
        (s.name && s.name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (s.display_name && s.display_name.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    return (
        <div className="p-8 w-full flex flex-col items-center">
            <div className="w-full max-w-7xl">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                    <h1 className="text-3xl font-bold text-cyan-400 whitespace-nowrap">Projects</h1>

                    {/* Search Bar - Fixed width on desktop to prevent shifts */}
                    <div className="relative group w-full md:w-[400px] flex-shrink-0">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-cyan-400 transition-colors" size={18} />
                        <input
                            type="text"
                            placeholder="Search projects by name..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full bg-gray-900/50 border border-gray-800 rounded-xl pl-10 pr-10 py-2.5 text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/30 transition-all font-medium"
                        />
                        {searchQuery && (
                            <button
                                onClick={() => setSearchQuery("")}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white p-1"
                            >
                                <X size={14} />
                            </button>
                        )}
                    </div>
                </div>

                {/* Create New Project - Stable container */}
                <div className="bg-gray-900/40 border border-gray-800/50 backdrop-blur-sm rounded-2xl p-6 mb-10 shadow-xl overflow-hidden relative w-full">
                    <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500/50"></div>
                    <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                        <span className="text-cyan-400 text-lg">✦</span> New Project
                    </h2>
                    <div className="flex flex-col sm:flex-row gap-4">
                        <input
                            type="text"
                            value={newProjectPrompt}
                            onChange={(e) => setNewProjectPrompt(e.target.value)}
                            onKeyPress={(e) => e.key === "Enter" && !creating && createProject()}
                            placeholder="Describe what you want to work on..."
                            className="flex-1 bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/20 transition-all"
                            disabled={creating}
                        />
                        <button
                            onClick={createProject}
                            disabled={creating || !newProjectPrompt.trim()}
                            className="flex items-center justify-center gap-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-800 disabled:text-gray-500 px-6 py-3 rounded-xl font-semibold text-sm transition-all active:scale-95 shadow-lg shadow-cyan-900/20 whitespace-nowrap"
                        >
                            {creating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Creating...
                                </>
                            ) : (
                                <>
                                    <Send className="w-4 h-4" />
                                    Start
                                </>
                            )}
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

                    {/* Projects List */}
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
                            <p className="text-sm text-gray-600 max-w-md mx-auto">
                                {searchQuery ? "Try a different search term or clear the filter" : "Initialize your first project above to begin collaborative task execution"}
                            </p>
                            {searchQuery && (
                                <button onClick={() => setSearchQuery("")} className="mt-6 text-cyan-400 text-sm font-semibold hover:text-cyan-300 transition-colors">
                                    Clear search filter
                                </button>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredProjects.map((project) => {
                                const isSelected = selectedProjects.has(project.id);
                                const isMenuOpen = activeMenu === project.id;
                                const isRenaming = renamingProject === project.id;

                                return (
                                    <div
                                        key={project.id}
                                        className={`group relative bg-gray-900 border rounded-2xl p-6 transition-all duration-300 ${isSelected
                                            ? "border-cyan-500/50 ring-1 ring-cyan-500/20 bg-cyan-500/[0.02]"
                                            : "border-gray-800/80 hover:border-cyan-500/50 hover:bg-gray-850 hover:shadow-2xl hover:shadow-cyan-900/10"
                                            }`}
                                    >
                                        <div className="flex items-start justify-between mb-5">
                                            <div className="flex items-start flex-1 min-w-0 pr-2">
                                                <div className="pt-1 mr-4 flex-shrink-0">
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={(e) => {
                                                            e.stopPropagation();
                                                            toggleSelection(project.id);
                                                        }}
                                                        className="w-5 h-5 rounded border-gray-700 bg-gray-800 text-cyan-500 focus:ring-cyan-500/30 cursor-pointer transition-transform group-hover:scale-110"
                                                    />
                                                </div>

                                                <div className="flex-1 min-w-0">
                                                    {isRenaming ? (
                                                        <div className="flex items-center gap-2 mt-1">
                                                            <input
                                                                type="text"
                                                                value={renameValue}
                                                                onChange={(e) => setRenameValue(e.target.value)}
                                                                className="flex-1 bg-gray-800 border border-cyan-500 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
                                                                autoFocus
                                                                onKeyDown={(e) => {
                                                                    if (e.key === "Enter") saveRename(project.id);
                                                                    if (e.key === "Escape") setRenamingProject(null);
                                                                }}
                                                            />
                                                            <button onClick={() => saveRename(project.id)} disabled={savingRename} className="text-green-500 hover:text-green-400">
                                                                <Check size={18} />
                                                            </button>
                                                            <button onClick={() => setRenamingProject(null)} className="text-red-500 hover:text-red-400">
                                                                <X size={18} />
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <Link href={`/projects/${project.id}`} className="block min-w-0">
                                                            <h3 className="font-bold text-base text-gray-100 truncate group-hover:text-cyan-400 transition-colors" title={project.display_name || project.name}>
                                                                {project.display_name || project.name}
                                                            </h3>
                                                            <p className="text-[9px] text-gray-600 font-mono tracking-tighter uppercase truncate opacity-70">
                                                                # {project.display_name || project.name}
                                                            </p>
                                                            {project.updated_at && (
                                                                <p className="text-[8px] text-gray-500 mt-0.5 flex items-center gap-1 truncate">
                                                                    <span className="w-1 h-1 bg-green-500 rounded-full flex-shrink-0"></span>
                                                                    <span className="truncate">Active: {new Date(project.updated_at).toLocaleDateString()}</span>
                                                                </p>
                                                            )}
                                                        </Link>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Context Menu Button */}
                                            <div className="relative flex-shrink-0 ml-2">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setActiveMenu(isMenuOpen ? null : project.id);
                                                    }}
                                                    className={`p-2 rounded-lg transition-all ${isMenuOpen ? "bg-gray-800 text-cyan-400" : "text-gray-500 hover:text-gray-200 hover:bg-gray-800"}`}
                                                >
                                                    < MoreVertical size={18} />
                                                </button>

                                                {isMenuOpen && (
                                                    <div
                                                        ref={menuRef}
                                                        className="absolute right-0 top-10 w-48 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1 animate-in fade-in slide-in-from-top-2 duration-200"
                                                    >
                                                        <button
                                                            onClick={() => startRename(project)}
                                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                        >
                                                            <Edit2 size={14} /> Rename Project
                                                        </button>
                                                        <button
                                                            onClick={() => cloneProject(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                        >
                                                            <Copy size={14} /> Clone Project
                                                        </button>
                                                        <Link
                                                            href={`/projects/${project.id}`}
                                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                        >
                                                            <ExternalLink size={14} /> Open Workspace
                                                        </Link>
                                                        <button
                                                            onClick={() => handleExportChat(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                        >
                                                            <FileDown size={14} /> Export Chat
                                                        </button>
                                                        <div className="my-1 border-t border-gray-800"></div>
                                                        <button
                                                            onClick={() => deleteProject(project.id, project.display_name || project.name)}
                                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                                                        >
                                                            <Trash2 size={14} /> Delete Project
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4 text-[11px] mb-2">
                                            <div className="bg-gray-950/40 rounded-xl p-3 border border-gray-800/30">
                                                <p className="text-gray-500 uppercase tracking-widest mb-1.5 font-bold">Artifacts</p>
                                                <div className="flex items-end gap-2">
                                                    <p className="text-xl font-bold font-mono text-gray-200 leading-none">{project.artifact_count}</p>
                                                    <span className="text-gray-600 mb-0.5 font-black">FILES</span>
                                                </div>
                                            </div>
                                            <div className="bg-gray-950/40 rounded-xl p-3 border border-gray-800/30">
                                                <p className="text-gray-500 uppercase tracking-widest mb-1.5 font-bold">References</p>
                                                <div className="flex items-end gap-2">
                                                    <p className="text-xl font-bold font-mono text-gray-200 leading-none">{project.ref_count}</p>
                                                    <span className="text-gray-600 mb-0.5 font-black">REFS</span>
                                                </div>
                                            </div>
                                        </div>

                                        {project.has_custom_prompt && (
                                            <div className="flex items-center gap-1.5 mt-4 text-[9px] text-cyan-500 font-black tracking-widest uppercase bg-cyan-500/5 px-3 py-1.5 rounded-full border border-cyan-500/20 w-fit">
                                                <span className="animate-pulse">◈</span> Custom AI Instructions Active
                                            </div>
                                        )}

                                        {project.members && project.members.length > 0 && (
                                            <div className="flex flex-wrap gap-1.5 mt-3">
                                                {project.members.map((member, idx) => (
                                                    <span
                                                        key={idx}
                                                        className="px-2 py-0.5 bg-gray-800/50 border border-gray-700/50 rounded text-[8px] text-gray-400 font-bold uppercase tracking-wider"
                                                    >
                                                        {member}
                                                    </span>
                                                ))}
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
