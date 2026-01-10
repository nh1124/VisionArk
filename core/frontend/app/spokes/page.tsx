"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { apiFetch, getFileToken } from "@/lib/api";
import { Search, MoreVertical, Edit2, Trash2, X, Check, ExternalLink, Copy, FileDown } from "lucide-react";

interface Spoke {
    name: string;
    display_name?: string;
    path: string;
    has_custom_prompt: boolean;
    artifact_count: number;
    ref_count: number;
}

export default function SpokesPage() {
    const [spokes, setSpokes] = useState<Spoke[]>([]);
    const [loading, setLoading] = useState(true);
    const [newSpokeName, setNewSpokeName] = useState("");
    const [creating, setCreating] = useState(false);
    const [selectedSpokes, setSelectedSpokes] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState("");

    // For Context Menu
    const [activeMenu, setActiveMenu] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    // For Renaming
    const [renamingSpoke, setRenamingSpoke] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [savingRename, setSavingRename] = useState(false);

    useEffect(() => {
        loadSpokes();

        // Close menu on click outside
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setActiveMenu(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const loadSpokes = async () => {
        try {
            const response = await apiFetch("/api/agents/spoke/list");
            const data = await response.json();
            if (data && data.spokes && Array.isArray(data.spokes)) {
                setSpokes(data.spokes);
            } else {
                console.warn("Unexpected spokes data format:", data);
                setSpokes([]);
            }
        } catch (error) {
            console.error("Error loading spokes:", error);
        } finally {
            setLoading(false);
        }
    };

    const createSpoke = async () => {
        if (!newSpokeName.trim()) return;

        setCreating(true);
        try {
            await apiFetch("/api/agents/spoke/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ spoke_name: newSpokeName }),
            });
            setNewSpokeName("");
            await loadSpokes();
        } catch (error) {
            console.error("Error creating spoke:", error);
        } finally {
            setCreating(false);
        }
    };

    const toggleSelection = (spokeName: string) => {
        const newSelected = new Set(selectedSpokes);
        if (newSelected.has(spokeName)) {
            newSelected.delete(spokeName);
        } else {
            newSelected.add(spokeName);
        }
        setSelectedSpokes(newSelected);
    };

    const toggleSelectAll = (filteredSpokes: Spoke[]) => {
        if (selectedSpokes.size === filteredSpokes.length && filteredSpokes.length > 0) {
            setSelectedSpokes(new Set());
        } else {
            setSelectedSpokes(new Set(filteredSpokes.map(s => s.name)));
        }
    };

    const cloneSpoke = async (name: string) => {
        // As per user feedback, start cloning with default name directly
        const newName = `${name}_copy`;

        try {
            const response = await apiFetch(`/api/agents/spoke/${name}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_name: newName }),
            });

            if (response.ok) {
                await loadSpokes();
                setActiveMenu(null);
            } else {
                const err = await response.json();
                alert(`Failed to clone project: ${err.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error("Error cloning spoke:", error);
            alert("Error cloning project");
        }
    };

    const deleteSpoke = async (name: string) => {
        if (!confirm(`Delete project '${name}'? This action cannot be undone.`)) {
            return;
        }

        try {
            await apiFetch(`/api/agents/spoke/${name}`, { method: "DELETE" });
            await loadSpokes();
            setActiveMenu(null);
        } catch (error) {
            console.error("Error deleting spoke:", error);
            alert("Failed to delete project");
        }
    };

    const bulkDelete = async () => {
        if (selectedSpokes.size === 0) return;

        if (!confirm(`Delete ${selectedSpokes.size} project(s)? This action cannot be undone.`)) {
            return;
        }

        try {
            await Promise.all(
                Array.from(selectedSpokes).map(name =>
                    apiFetch(`/api/agents/spoke/${name}`, { method: "DELETE" })
                )
            );
            setSelectedSpokes(new Set());
            await loadSpokes();
        } catch (error) {
            console.error("Error deleting spokes:", error);
            alert("Failed to delete some projects");
        }
    };

    const startRename = (spoke: Spoke) => {
        setRenamingSpoke(spoke.name);
        setRenameValue(spoke.display_name || spoke.name);
        setActiveMenu(null);
    };

    const saveRename = async (spokeName: string) => {
        if (!renameValue.trim()) return;
        setSavingRename(true);
        try {
            const response = await apiFetch(`/api/agents/spoke/${spokeName}/rename`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: renameValue }),
            });
            if (response.ok) {
                setRenamingSpoke(null);
                await loadSpokes();
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

    const handleExportChat = async (name: string) => {
        try {
            const token = await getFileToken();
            const exportUrl = `/api/export/chat/${name}?token=${token}`;

            const link = document.createElement('a');
            link.href = exportUrl;
            link.setAttribute('download', `${name}_chat.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            setActiveMenu(null);
        } catch (error) {
            console.error("Export failed:", error);
            alert("Failed to export chat history.");
        }
    };

    const filteredSpokes = spokes.filter(s =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (s.display_name && s.display_name.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                <h1 className="text-3xl font-bold text-cyan-400">Projects (Spokes)</h1>

                {/* Search Bar */}
                <div className="relative group min-w-[300px]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-cyan-400 transition-colors" size={18} />
                    <input
                        type="text"
                        placeholder="Search projects by name..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-gray-900/50 border border-gray-800 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/30 transition-all"
                    />
                    {searchQuery && (
                        <button
                            onClick={() => setSearchQuery("")}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>
            </div>

            {/* Create New Spoke */}
            <div className="bg-gray-900/40 border border-gray-800/50 backdrop-blur-sm rounded-2xl p-6 mb-10 shadow-xl overflow-hidden relative">
                <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500/50"></div>
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                    <span className="text-cyan-400 text-lg">✦</span> Create New Project
                </h2>
                <div className="flex flex-col sm:flex-row gap-4">
                    <input
                        type="text"
                        value={newSpokeName}
                        onChange={(e) => setNewSpokeName(e.target.value)}
                        onKeyPress={(e) => e.key === "Enter" && !creating && createSpoke()}
                        placeholder="Project identifier (e.g., research_ai)"
                        className="flex-1 bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/20 transition-all"
                        disabled={creating}
                    />
                    <button
                        onClick={createSpoke}
                        disabled={creating || !newSpokeName.trim()}
                        className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-800 disabled:text-gray-500 px-8 py-3 rounded-xl font-semibold text-sm transition-all active:scale-95 shadow-lg shadow-cyan-900/20"
                    >
                        {creating ? "Creating..." : "Initialize Spoke"}
                    </button>
                </div>
                <p className="text-[10px] text-gray-500 mt-3 uppercase tracking-widest font-medium opacity-60">
                    * Names should use underscores for spaces
                </p>
            </div>

            {/* Bulk Actions Bar */}
            {filteredSpokes.length > 0 && (
                <div className="mb-6 flex items-center justify-between border-b border-gray-800 pb-4">
                    <label className="flex items-center gap-3 text-sm text-gray-400 cursor-pointer group hover:text-gray-200 transition-colors">
                        <input
                            type="checkbox"
                            checked={selectedSpokes.size === filteredSpokes.length && filteredSpokes.length > 0}
                            onChange={() => toggleSelectAll(filteredSpokes)}
                            className="w-4 h-4 rounded border-gray-700 bg-gray-900 text-cyan-500 focus:ring-cyan-500/30"
                        />
                        <span className="font-medium">
                            {selectedSpokes.size === filteredSpokes.length ? "Deselect All" : "Select All Visible"}
                            <span className="ml-2 px-1.5 py-0.5 bg-gray-800 rounded text-[10px] text-gray-500">{selectedSpokes.size}/{filteredSpokes.length}</span>
                        </span>
                    </label>

                    {selectedSpokes.size > 0 && (
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

            {/* Spokes List */}
            {loading ? (
                <div className="flex flex-col items-center justify-center py-20 gap-4">
                    <div className="w-10 h-10 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin"></div>
                    <p className="text-gray-500 text-sm animate-pulse">Loading project data...</p>
                </div>
            ) : filteredSpokes.length === 0 ? (
                <div className="text-center py-24 bg-gray-900/20 border border-dashed border-gray-800 rounded-3xl">
                    <div className="w-20 h-20 bg-gray-800/40 rounded-full flex items-center justify-center mx-auto mb-6 text-3xl opacity-50 gray-shadow-lg">
                        {searchQuery ? "🔍" : "💎"}
                    </div>
                    <p className="text-xl font-medium text-gray-400 mb-2">
                        {searchQuery ? `No results found for "${searchQuery}"` : "Your project list is empty"}
                    </p>
                    <p className="text-sm text-gray-600">
                        {searchQuery ? "Try a different search term or clear the filter" : "Initialize your first project above to begin collaborative task execution"}
                    </p>
                    {searchQuery && (
                        <button onClick={() => setSearchQuery("")} className="mt-4 text-cyan-400 text-sm font-semibold hover:underline">
                            Clear search filter
                        </button>
                    )}
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredSpokes.map((spoke) => {
                        const isSelected = selectedSpokes.has(spoke.name);
                        const isMenuOpen = activeMenu === spoke.name;
                        const isRenaming = renamingSpoke === spoke.name;

                        return (
                            <div
                                key={spoke.name}
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
                                                    toggleSelection(spoke.name);
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
                                                            if (e.key === "Enter") saveRename(spoke.name);
                                                            if (e.key === "Escape") setRenamingSpoke(null);
                                                        }}
                                                    />
                                                    <button onClick={() => saveRename(spoke.name)} disabled={savingRename} className="text-green-500 hover:text-green-400">
                                                        <Check size={18} />
                                                    </button>
                                                    <button onClick={() => setRenamingSpoke(null)} className="text-red-500 hover:text-red-400">
                                                        <X size={18} />
                                                    </button>
                                                </div>
                                            ) : (
                                                <Link href={`/spokes/${spoke.name}`} className="block min-w-0">
                                                    <h3 className="font-bold text-lg text-gray-100 truncate group-hover:text-cyan-400 transition-colors" title={spoke.display_name || spoke.name}>
                                                        {spoke.display_name || spoke.name}
                                                    </h3>
                                                    <p className="text-[10px] text-gray-600 font-mono tracking-tighter uppercase truncate opacity-70">
                                                        #{spoke.name}
                                                    </p>
                                                </Link>
                                            )}
                                        </div>
                                    </div>

                                    {/* Context Menu Button */}
                                    <div className="relative flex-shrink-0 ml-2">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setActiveMenu(isMenuOpen ? null : spoke.name);
                                            }}
                                            className={`p-2 rounded-lg transition-all ${isMenuOpen ? "bg-gray-800 text-cyan-400" : "text-gray-500 hover:text-gray-200 hover:bg-gray-800"}`}
                                        >
                                            <MoreVertical size={18} />
                                        </button>

                                        {isMenuOpen && (
                                            <div
                                                ref={menuRef}
                                                className="absolute right-0 top-10 w-48 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1 animate-in fade-in slide-in-from-top-2 duration-200"
                                            >
                                                <button
                                                    onClick={() => startRename(spoke)}
                                                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                >
                                                    <Edit2 size={14} /> Rename Project
                                                </button>
                                                <button
                                                    onClick={() => cloneSpoke(spoke.name)}
                                                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                >
                                                    <Copy size={14} /> Clone Project
                                                </button>
                                                <Link
                                                    href={`/spokes/${spoke.name}`}
                                                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                >
                                                    <ExternalLink size={14} /> Open Workspace
                                                </Link>
                                                <button
                                                    onClick={() => handleExportChat(spoke.name)}
                                                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-cyan-500/10 hover:text-cyan-400 transition-colors"
                                                >
                                                    <FileDown size={14} /> Export Chat
                                                </button>
                                                <div className="my-1 border-t border-gray-800"></div>
                                                <button
                                                    onClick={() => deleteSpoke(spoke.name)}
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
                                            <p className="text-xl font-bold font-mono text-gray-200 leading-none">{spoke.artifact_count}</p>
                                            <span className="text-gray-600 mb-0.5 font-black">FILES</span>
                                        </div>
                                    </div>
                                    <div className="bg-gray-950/40 rounded-xl p-3 border border-gray-800/30">
                                        <p className="text-gray-500 uppercase tracking-widest mb-1.5 font-bold">References</p>
                                        <div className="flex items-end gap-2">
                                            <p className="text-xl font-bold font-mono text-gray-200 leading-none">{spoke.ref_count}</p>
                                            <span className="text-gray-600 mb-0.5 font-black">REFS</span>
                                        </div>
                                    </div>
                                </div>

                                {spoke.has_custom_prompt && (
                                    <div className="flex items-center gap-1.5 mt-4 text-[9px] text-cyan-500 font-black tracking-widest uppercase bg-cyan-500/5 px-3 py-1.5 rounded-full border border-cyan-500/20 w-fit">
                                        <span className="animate-pulse">◈</span> Custom AI Instructions Active
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
