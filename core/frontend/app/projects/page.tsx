"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { apiFetch, getFileToken } from "@/lib/api"
import {
    Search, MoreVertical, Trash2, X, Check, ExternalLink,
    Copy, Download, Settings, Rocket, Folder, Sparkles,
    LayoutGrid, List, FolderKanban
} from "lucide-react"

interface Project {
    id: string
    name: string
    display_name?: string
    path: string
    has_custom_prompt: boolean
    artifact_count: number
    ref_count: number
    queue_count: number
    created_at?: string
    updated_at?: string
    members?: string[]
    latest_activity: string
    last_activity_time?: string
    next_task?: { type: string; at: string }
    processing_logs: string[]
}

export default function ProjectsPage() {
    const [projects, setProjects] = useState<Project[]>([])
    const [loading, setLoading] = useState(true)
    const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set())
    const [searchQuery, setSearchQuery] = useState("")
    const [activeMenu, setActiveMenu] = useState<string | null>(null)
    const menuRef = useRef<HTMLDivElement>(null)
    const [renamingProject, setRenamingProject] = useState<string | null>(null)
    const [renameValue, setRenameValue] = useState("")
    const [savingRename, setSavingRename] = useState(false)
    const [viewMode, setViewMode] = useState<"tile" | "list">("tile")
    const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null)
    const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false)
    const router = useRouter()

    useEffect(() => {
        loadProjects()
        const interval = setInterval(loadProjects, 10000)
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setActiveMenu(null)
            }
        }
        document.addEventListener("mousedown", handleClickOutside)
        return () => {
            document.removeEventListener("mousedown", handleClickOutside)
            clearInterval(interval)
        }
    }, [])

    const loadProjects = async () => {
        try {
            const res = await apiFetch("/api/agents/project/list")
            const data = await res.json()
            if (data?.projects && Array.isArray(data.projects)) {
                setProjects(data.projects)
            }
        } catch (err) {
            console.error("Failed to load projects:", err)
        } finally {
            setLoading(false)
        }
    }

    const toggleSelection = (id: string) => {
        const s = new Set(selectedProjects)
        if (s.has(id)) {
            s.delete(id)
        } else {
            s.add(id)
        }
        setSelectedProjects(s)
    }

    const toggleSelectAll = (filtered: Project[]) => {
        if (selectedProjects.size === filtered.length && filtered.length > 0) {
            setSelectedProjects(new Set())
        } else {
            setSelectedProjects(new Set(filtered.map(p => p.id)))
        }
    }

    const cloneProject = async (id: string, displayName: string) => {
        try {
            const res = await apiFetch(`/api/agents/project/${id}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: `${displayName} (Copy)` }),
            })
            if (res.ok) { await loadProjects(); setActiveMenu(null) }
        } catch (err) { console.error("Clone error:", err) }
    }

    const deleteProjectById = async (id: string) => {
        try {
            await apiFetch(`/api/agents/project/${id}`, { method: "DELETE" })
            await loadProjects()
            setActiveMenu(null)
        } catch (err) { console.error("Delete error:", err) } finally { setDeleteConfirm(null) }
    }

    const bulkDelete = async () => {
        try {
            await Promise.all(
                Array.from(selectedProjects).map(id =>
                    apiFetch(`/api/agents/project/${id}`, { method: "DELETE" })
                )
            )
            setSelectedProjects(new Set())
            await loadProjects()
        } catch (err) { console.error("Bulk delete error:", err) } finally { setBulkDeleteConfirm(false) }
    }

    const startRename = (p: Project) => {
        setRenamingProject(p.id)
        setRenameValue(p.display_name || p.name)
        setActiveMenu(null)
    }

    const saveRename = async (id: string) => {
        if (!renameValue.trim()) return
        setSavingRename(true)
        try {
            const res = await apiFetch(`/api/agents/project/${id}/rename`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: renameValue }),
            })
            if (res.ok) { setRenamingProject(null); await loadProjects() }
        } catch (err) { console.error("Rename error:", err) } finally { setSavingRename(false) }
    }

    const handleExportChat = async (id: string, displayName: string) => {
        try {
            const token = await getFileToken()
            const link = document.createElement("a")
            link.href = `/api/export/chat/project/${id}?token=${token}`
            link.setAttribute("download", `${displayName}_chat.md`)
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            setActiveMenu(null)
        } catch (err) { console.error("Export error:", err) }
    }

    const filteredProjects = projects.filter(p =>
        (p.name?.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (p.display_name?.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    return (
        <div className="flex flex-col h-full bg-[#030712] text-white">
            <div className="flex-1 overflow-y-auto px-8 py-8 custom-scrollbar">
                <div className="max-w-7xl mx-auto">

                    {/* Header */}
                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10">
                        <div>
                            <h1 className="text-4xl font-black text-white tracking-tighter mb-2 flex items-center gap-3">
                                <FolderKanban size={36} className="text-purple-500" />
                                Projects
                            </h1>
                        </div>

                        <div className="flex items-center gap-3">
                            {/* Search */}
                            <div className="relative">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
                                <input
                                    type="text"
                                    placeholder="Search projects..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="pl-9 pr-3 py-2 bg-gray-900/80 border border-gray-800 rounded-xl text-sm text-white focus:outline-none focus:border-cyan-500/50 w-48"
                                />
                            </div>
                            {/* View mode toggle */}
                            <div className="flex bg-gray-900/80 p-1.5 rounded-2xl border border-gray-800">
                                <button
                                    onClick={() => setViewMode("tile")}
                                    className={`p-2 rounded-xl transition-all ${viewMode === "tile" ? "bg-cyan-500 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"}`}
                                    title="Tile View"
                                ><LayoutGrid size={16} /></button>
                                <button
                                    onClick={() => setViewMode("list")}
                                    className={`p-2 rounded-xl transition-all ${viewMode === "list" ? "bg-cyan-500 text-white" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"}`}
                                    title="List View"
                                ><List size={16} /></button>
                            </div>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="min-h-[300px]">
                        {/* Bulk actions */}
                        {!loading && filteredProjects.length > 0 && (
                            <div className="mb-6 flex items-center justify-between border-b border-gray-800 pb-4">
                                <label className="flex items-center gap-3 text-sm text-gray-400 cursor-pointer hover:text-gray-200">
                                    <input
                                        type="checkbox"
                                        checked={selectedProjects.size === filteredProjects.length && filteredProjects.length > 0}
                                        onChange={() => toggleSelectAll(filteredProjects)}
                                        className="w-4 h-4 rounded border-gray-700 bg-gray-900 text-cyan-500"
                                    />
                                    <span className="font-medium">
                                        {selectedProjects.size === filteredProjects.length ? "Deselect All" : "Select All"}
                                        <span className="ml-2 px-1.5 py-0.5 bg-gray-800 rounded text-[10px] text-gray-500">
                                            {selectedProjects.size}/{filteredProjects.length}
                                        </span>
                                    </span>
                                </label>
                                {selectedProjects.size > 0 && (
                                    <button
                                        onClick={() => setBulkDeleteConfirm(true)}
                                        className="flex items-center gap-2 px-4 py-1.5 bg-red-500/10 border border-red-500/30 text-red-500 hover:bg-red-500 hover:text-white rounded-lg text-xs font-bold transition-all"
                                    >
                                        <Trash2 size={12} /> DELETE SELECTED
                                    </button>
                                )}
                            </div>
                        )}

                        {loading ? (
                            <div className="flex flex-col items-center justify-center py-32 gap-4">
                                <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin" />
                                <p className="text-gray-500 text-sm animate-pulse">Retrieving your projects...</p>
                            </div>
                        ) : filteredProjects.length === 0 ? (
                            <div className="text-center py-24 bg-gray-900/10 border border-dashed border-gray-800/50 rounded-3xl">
                                <div className="w-20 h-20 bg-gray-800/40 rounded-full flex items-center justify-center mx-auto mb-6 text-3xl opacity-50">
                                    {searchQuery ? "🔍" : "💎"}
                                </div>
                                <p className="text-xl font-medium text-gray-400 mb-2">
                                    {searchQuery ? `No results for "${searchQuery}"` : "Your project list is empty"}
                                </p>
                                <p className="text-gray-600 text-sm">Use + New Project from the left panel.</p>
                            </div>
                        ) : (
                            <div className={viewMode === "tile" ? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 auto-rows-min" : "flex flex-col gap-3"}>
                                {filteredProjects.map(project => {
                                    const isSelected = selectedProjects.has(project.id)
                                    const isMenuOpen = activeMenu === project.id
                                    const hasActiveTask = project.queue_count > 0
                                    const hasUpcoming = !!project.next_task

                                    if (viewMode === "list") {
                                        return (
                                            <div key={project.id} className={`group flex items-center justify-between bg-gray-900/40 border ${isSelected ? "border-cyan-500" : "border-gray-800"} rounded-2xl p-4 hover:bg-gray-800/50 transition-all`}>
                                                <div className="flex items-center gap-4 flex-1 min-w-0">
                                                    <input type="checkbox" checked={isSelected} onChange={() => toggleSelection(project.id)} className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-cyan-500" />
                                                    {renamingProject === project.id ? (
                                                        <div className="flex items-center gap-2 flex-1">
                                                            <input
                                                                value={renameValue}
                                                                onChange={e => setRenameValue(e.target.value)}
                                                                onKeyPress={e => e.key === "Enter" && saveRename(project.id)}
                                                                autoFocus
                                                                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-sm text-white focus:outline-none focus:border-cyan-500"
                                                            />
                                                            <button onClick={() => saveRename(project.id)} disabled={savingRename} className="p-1.5 text-green-400 hover:text-green-300"><Check size={14} /></button>
                                                            <button onClick={() => setRenamingProject(null)} className="p-1.5 text-gray-500 hover:text-white"><X size={14} /></button>
                                                        </div>
                                                    ) : (
                                                        <button onClick={() => router.push(`/projects/${project.id}`)} className="text-left flex-1 min-w-0">
                                                            <h3 className="font-bold text-sm text-gray-100 truncate group-hover:text-cyan-400">{project.display_name || project.name}</h3>
                                                        </button>
                                                    )}
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
                                                        <span className={`text-xs font-mono ${project.queue_count > 0 ? "text-cyan-400 animate-pulse" : "text-gray-500"}`}>{project.queue_count || 0}</span>
                                                    </div>
                                                </div>
                                                <div className="relative">
                                                    <button onClick={e => { e.stopPropagation(); setActiveMenu(isMenuOpen ? null : project.id) }} className="p-2 text-gray-500 hover:text-white">
                                                        <MoreVertical size={16} />
                                                    </button>
                                                    {isMenuOpen && (
                                                        <div ref={menuRef} className="absolute right-0 top-10 w-48 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 py-1">
                                                            <button onClick={() => startRename(project)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Settings size={14} /> Settings</button>
                                                            <button onClick={() => cloneProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Copy size={14} /> Clone</button>
                                                            <button onClick={() => router.push(`/projects/${project.id}`)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Rocket size={14} /> Open</button>
                                                            <button onClick={() => handleExportChat(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Download size={14} /> Export Chat</button>
                                                            <div className="border-t border-gray-800 mx-2 my-1" />
                                                            <button onClick={() => setDeleteConfirm({ id: project.id, name: project.display_name || project.name })} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-500 hover:bg-red-500/10"><Trash2 size={14} /> Delete</button>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )
                                    }

                                    const colSpan = hasActiveTask ? "lg:col-span-2 row-span-2" : ""

                                    return (
                                        <div
                                            key={project.id}
                                            className={`group relative bg-gray-900/60 border rounded-3xl p-6 transition-all duration-300 flex flex-col ${colSpan} ${isSelected ? "border-cyan-500 ring-1 ring-cyan-500/20" : "border-gray-800 hover:border-cyan-500/30 shadow-xl"}`}
                                        >
                                            <div className="flex items-start justify-between mb-4">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className={`w-2 h-2 rounded-full ${hasActiveTask ? "bg-green-500 animate-pulse" : hasUpcoming ? "bg-blue-500" : "bg-gray-700"}`} />
                                                        <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                                            {hasActiveTask ? "Processing" : hasUpcoming ? "Scheduled" : "Dormant"}
                                                        </span>
                                                    </div>
                                                    {renamingProject === project.id ? (
                                                        <div className="flex items-center gap-2 mt-1">
                                                            <input
                                                                value={renameValue}
                                                                onChange={e => setRenameValue(e.target.value)}
                                                                onKeyPress={e => e.key === "Enter" && saveRename(project.id)}
                                                                autoFocus
                                                                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1 text-sm text-white focus:outline-none focus:border-cyan-500"
                                                            />
                                                            <button onClick={() => saveRename(project.id)} disabled={savingRename} className="p-1 text-green-400"><Check size={14} /></button>
                                                            <button onClick={() => setRenamingProject(null)} className="p-1 text-gray-500"><X size={14} /></button>
                                                        </div>
                                                    ) : (
                                                        <button onClick={() => router.push(`/projects/${project.id}`)} className="text-left w-full">
                                                            <h3 className={`font-black tracking-tight text-white truncate group-hover:text-cyan-400 transition-colors ${hasActiveTask ? "text-xl" : "text-base"}`}>
                                                                {project.display_name || project.name}
                                                            </h3>
                                                        </button>
                                                    )}
                                                </div>
                                                <button onClick={e => { e.stopPropagation(); setActiveMenu(isMenuOpen ? null : project.id) }} className="p-2 text-gray-600 hover:text-white ml-2">
                                                    <MoreVertical size={18} />
                                                </button>
                                            </div>

                                            {/* Large Active Task Content */}
                                            {hasActiveTask && colSpan.includes("lg:col-span-2") && (
                                                <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-6 mb-6">
                                                    <div className="flex-1 bg-black/60 rounded-2xl p-4 font-mono text-[11px] leading-relaxed border border-white/5 overflow-hidden">
                                                        <div className="flex items-center justify-between mb-3 border-b border-white/10 pb-2">
                                                            <span className="text-gray-500 flex items-center gap-1.5 font-bold"><span className="w-1.5 h-1.5 rounded-full bg-green-500" /> TERMINAL</span>
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            {project.processing_logs.length > 0 ? project.processing_logs.map((log, i) => (
                                                                <div key={i} className="text-cyan-400/80 truncate">{log}</div>
                                                            )) : <div className="text-gray-700 italic">Listening for activity...</div>}
                                                            <div className="text-white animate-pulse">▋</div>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Small/Medium content */}
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
                                                            <span className="text-[10px] font-mono text-blue-500 font-bold">
                                                                {project.next_task?.at ? new Date(project.next_task.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Footer */}
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
                                                <button
                                                    onClick={() => router.push(`/projects/${project.id}`)}
                                                    className="p-2 bg-gray-800/40 rounded-xl text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all"
                                                >
                                                    <ExternalLink size={14} />
                                                </button>
                                            </div>

                                            {/* Context menu */}
                                            {isMenuOpen && (
                                                <div ref={menuRef} className="absolute right-6 top-14 w-48 bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl z-50 py-1 overflow-hidden">
                                                    <button onClick={() => startRename(project)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Settings size={14} /> Settings</button>
                                                    <button onClick={() => cloneProject(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Copy size={14} /> Clone</button>
                                                    <button onClick={() => { router.push(`/projects/${project.id}`); setActiveMenu(null) }} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Rocket size={14} /> Open</button>
                                                    <button onClick={() => handleExportChat(project.id, project.display_name || project.name)} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"><Download size={14} /> Export Chat</button>
                                                    <div className="border-t border-gray-800 mx-2 my-1" />
                                                    <button onClick={() => setDeleteConfirm({ id: project.id, name: project.display_name || project.name })} className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-500 hover:bg-red-500/10"><Trash2 size={14} /> Delete</button>
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Delete Confirm */}
            {deleteConfirm && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6">
                        <h3 className="text-base font-bold text-white mb-1.5">Delete project?</h3>
                        <p className="text-gray-400 text-sm mb-5 font-mono">{deleteConfirm.name}</p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirm(null)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={() => deleteProjectById(deleteConfirm.id)} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Bulk Delete Confirm */}
            {bulkDeleteConfirm && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6">
                        <h3 className="text-base font-bold text-white mb-1.5">Delete {selectedProjects.size} project(s)?</h3>
                        <p className="text-gray-400 text-sm mb-5">This action cannot be undone.</p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setBulkDeleteConfirm(false)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={bulkDelete} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete All</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
