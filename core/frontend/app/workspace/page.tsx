"use client";

import { useEffect, useState, useMemo } from "react";
import {
    Plus, Trash2, X, Loader2, Tag,
    ChevronRight, Home, Folder, FileText, Save, Lock, Globe, FolderOpen,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface WorkspaceItem {
    id: string;
    scope: string;
    path: string;
    title: string;
    content: string | null;
    tags: string[];
    version: number;
    created_at: string;
    updated_at: string;
}

const SCOPE_OPTIONS = ["private", "org", "project"] as const;
type Scope = typeof SCOPE_OPTIONS[number];

// ---------- path helpers ----------

function getEntries(items: WorkspaceItem[], currentPath: string) {
    const prefix = currentPath ? currentPath + "/" : "";
    const folderSet = new Set<string>();
    const files: WorkspaceItem[] = [];

    for (const item of items) {
        if (!item.path.startsWith(prefix)) continue;
        const rest = item.path.slice(prefix.length);
        if (!rest) continue;
        const slash = rest.indexOf("/");
        if (slash === -1) files.push(item);
        else folderSet.add(rest.slice(0, slash));
    }

    return { folders: Array.from(folderSet).sort(), files };
}

function breadcrumbs(path: string): string[] {
    return path ? path.split("/") : [];
}

// ---------- scope helpers ----------

function ScopeIcon({ scope }: { scope: string }) {
    if (scope === "org") return <Globe size={11} className="text-blue-400 flex-shrink-0" />;
    if (scope === "project") return <FolderOpen size={11} className="text-purple-400 flex-shrink-0" />;
    return <Lock size={11} className="text-gray-600 flex-shrink-0" />;
}

function scopeButtonClass(s: Scope, active: boolean) {
    if (!active) return "bg-black/20 border-gray-800 text-gray-600 hover:text-gray-400";
    if (s === "org") return "bg-blue-500/20 border-blue-500/40 text-blue-300";
    if (s === "project") return "bg-purple-500/20 border-purple-500/40 text-purple-300";
    return "bg-gray-700 border-gray-600 text-white";
}

// ---------- component ----------

const EMPTY_FORM = { title: "", scope: "private" as Scope, content: "", tags: [] as string[] };

type PendingDelete =
    | { type: "file"; item: WorkspaceItem }
    | { type: "folder"; name: string; folderPath: string; count: number }
    | null;

export default function WorkspacePage() {
    const [items, setItems] = useState<WorkspaceItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [currentPath, setCurrentPath] = useState("");

    // right-panel mode
    const [selectedItem, setSelectedItem] = useState<WorkspaceItem | null>(null);
    const [isCreating, setIsCreating] = useState(false);

    // form
    const [form, setForm] = useState({ ...EMPTY_FORM });
    const [newPath, setNewPath] = useState("");
    const [tagInput, setTagInput] = useState("");
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);
    const [hoveredEntry, setHoveredEntry] = useState<string | null>(null);

    const { folders, files } = useMemo(() => getEntries(items, currentPath), [items, currentPath]);
    const crumbs = useMemo(() => breadcrumbs(currentPath), [currentPath]);

    // ---------- fetch ----------

    const fetchItems = async () => {
        setLoading(true);
        try {
            const res = await apiFetch("/api/workspace/items");
            if (res.ok) setItems(await res.json());
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchItems(); }, []);

    // ---------- navigation ----------

    const navigateTo = (path: string) => {
        setCurrentPath(path);
        setSelectedItem(null);
        setIsCreating(false);
        setDirty(false);
    };

    const navigateUp = () => {
        const parts = currentPath.split("/");
        parts.pop();
        navigateTo(parts.join("/"));
    };

    // ---------- selection ----------

    const selectItem = (item: WorkspaceItem) => {
        setSelectedItem(item);
        setIsCreating(false);
        setForm({ title: item.title, scope: item.scope as Scope, content: item.content ?? "", tags: item.tags ?? [] });
        setTagInput("");
        setDirty(false);
    };

    const openCreate = () => {
        setSelectedItem(null);
        setIsCreating(true);
        setForm({ ...EMPTY_FORM });
        setNewPath(currentPath ? currentPath + "/" : "");
        setTagInput("");
        setDirty(false);
    };

    // ---------- save / delete ----------

    const handleSave = async () => {
        setSaving(true);
        try {
            if (isCreating) {
                if (!form.title.trim() || !newPath.trim()) return;
                const res = await apiFetch("/api/workspace/items", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ...form, path: newPath }),
                });
                if (res.ok) {
                    const created = await res.json();
                    setItems(prev => [created, ...prev]);
                    setIsCreating(false);
                    selectItem(created);
                }
            } else if (selectedItem) {
                const res = await apiFetch(`/api/workspace/items/${selectedItem.id}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(form),
                });
                if (res.ok) {
                    const updated = await res.json();
                    setItems(prev => prev.map(i => i.id === updated.id ? updated : i));
                    setSelectedItem(updated);
                    setDirty(false);
                }
            }
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!pendingDelete) return;

        if (pendingDelete.type === "file") {
            const res = await apiFetch(`/api/workspace/items/${pendingDelete.item.id}`, { method: "DELETE" });
            if (res.ok) {
                setItems(prev => prev.filter(i => i.id !== pendingDelete.item.id));
                if (selectedItem?.id === pendingDelete.item.id) setSelectedItem(null);
            }
        } else {
            const toDelete = items.filter(i => i.path.startsWith(pendingDelete.folderPath + "/"));
            await Promise.all(toDelete.map(i => apiFetch(`/api/workspace/items/${i.id}`, { method: "DELETE" })));
            setItems(prev => prev.filter(i => !i.path.startsWith(pendingDelete.folderPath + "/")));
            if (selectedItem && selectedItem.path.startsWith(pendingDelete.folderPath + "/")) setSelectedItem(null);
        }

        setPendingDelete(null);
    };

    // ---------- form helpers ----------

    const patchForm = (patch: Partial<typeof form>) => {
        setForm(f => ({ ...f, ...patch }));
        setDirty(true);
    };

    const addTag = () => {
        const t = tagInput.trim();
        if (t && !form.tags.includes(t)) patchForm({ tags: [...form.tags, t] });
        setTagInput("");
    };

    // ---------- render ----------

    return (
        <div className="flex flex-col h-full overflow-hidden">

            {/* ── Top bar ── */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/60 flex-shrink-0 bg-gray-950">
                <h1 className="text-base font-bold text-white tracking-tight">Workspace</h1>
                <button
                    onClick={openCreate}
                    className="flex items-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 text-black px-3 py-1.5 rounded-lg text-xs font-bold transition-all active:scale-95 shadow-md shadow-cyan-500/20"
                >
                    <Plus size={14} /> New Item
                </button>
            </div>

            {/* ── Two-panel body ── */}
            <div className="flex flex-1 min-h-0 overflow-hidden">

                {/* ── LEFT: file browser ── */}
                <div className="w-64 flex-shrink-0 border-r border-gray-800/60 flex flex-col bg-gray-950/60">

                    {/* breadcrumb */}
                    <div className="flex items-center gap-1 px-3 py-2 border-b border-gray-800/40 flex-wrap min-h-[36px]">
                        <button
                            onClick={() => navigateTo("")}
                            className="text-gray-500 hover:text-cyan-400 transition-colors"
                            title="Root"
                        >
                            <Home size={13} />
                        </button>
                        {crumbs.map((crumb, idx) => {
                            const crumbPath = crumbs.slice(0, idx + 1).join("/");
                            const isLast = idx === crumbs.length - 1;
                            return (
                                <span key={crumbPath} className="flex items-center gap-1">
                                    <ChevronRight size={10} className="text-gray-700" />
                                    <button
                                        onClick={() => navigateTo(crumbPath)}
                                        className={`text-xs transition-colors ${isLast ? "text-gray-200 font-semibold" : "text-gray-500 hover:text-cyan-400"}`}
                                    >
                                        {crumb}
                                    </button>
                                </span>
                            );
                        })}
                    </div>

                    {/* tree */}
                    {loading ? (
                        <div className="flex flex-1 items-center justify-center">
                            <Loader2 size={18} className="text-cyan-500 animate-spin" />
                        </div>
                    ) : (
                        <div className="flex-1 overflow-y-auto py-0.5">
                            {/* parent entry */}
                            {currentPath && (
                                <button
                                    onClick={navigateUp}
                                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-600 hover:text-gray-300 hover:bg-gray-900/50 transition-colors"
                                >
                                    <span className="text-gray-700 font-mono">..</span>
                                </button>
                            )}

                            {/* folders */}
                            {folders.map(folder => {
                                const folderPath = currentPath ? `${currentPath}/${folder}` : folder;
                                const hovered = hoveredEntry === `folder:${folder}`;
                                return (
                                    <div
                                        key={folder}
                                        onMouseEnter={() => setHoveredEntry(`folder:${folder}`)}
                                        onMouseLeave={() => setHoveredEntry(null)}
                                        className="flex items-center px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-900/50 transition-colors"
                                    >
                                        <button
                                            onClick={() => navigateTo(folderPath)}
                                            className="flex items-center gap-2 flex-1 min-w-0"
                                        >
                                            <Folder size={15} className="text-yellow-500/70 flex-shrink-0" />
                                            <span className="truncate text-left">{folder}</span>
                                        </button>
                                        {hovered && (
                                            <button
                                                onClick={e => {
                                                    e.stopPropagation();
                                                    const count = items.filter(i => i.path.startsWith(folderPath + "/")).length;
                                                    setPendingDelete({ type: "folder", name: folder, folderPath, count });
                                                }}
                                                className="p-0.5 text-gray-600 hover:text-red-500 transition-colors flex-shrink-0"
                                                title="Delete folder"
                                            >
                                                <Trash2 size={12} />
                                            </button>
                                        )}
                                    </div>
                                );
                            })}

                            {/* files */}
                            {files.map(item => {
                                const active = selectedItem?.id === item.id;
                                const hovered = hoveredEntry === `file:${item.id}`;
                                return (
                                    <div
                                        key={item.id}
                                        onMouseEnter={() => setHoveredEntry(`file:${item.id}`)}
                                        onMouseLeave={() => setHoveredEntry(null)}
                                        className={`flex items-center px-3 py-1.5 text-sm transition-colors ${active ? "bg-cyan-500/10 text-cyan-300" : "text-gray-400 hover:bg-gray-900/50 hover:text-gray-200"}`}
                                    >
                                        <button
                                            onClick={() => selectItem(item)}
                                            className="flex items-center gap-2 flex-1 min-w-0"
                                        >
                                            <FileText size={14} className={active ? "text-cyan-400 flex-shrink-0" : "text-gray-600 flex-shrink-0"} />
                                            <span className="truncate text-left text-xs">{item.title}</span>
                                        </button>
                                        {hovered ? (
                                            <button
                                                onClick={e => {
                                                    e.stopPropagation();
                                                    setPendingDelete({ type: "file", item });
                                                }}
                                                className="p-0.5 text-gray-600 hover:text-red-500 transition-colors flex-shrink-0"
                                                title="Delete item"
                                            >
                                                <Trash2 size={12} />
                                            </button>
                                        ) : (
                                            <ScopeIcon scope={item.scope} />
                                        )}
                                    </div>
                                );
                            })}

                            {folders.length === 0 && files.length === 0 && (
                                <p className="px-4 py-6 text-center text-xs text-gray-700 italic">Empty</p>
                            )}
                        </div>
                    )}
                </div>

                {/* ── RIGHT: detail / edit ── */}
                <div className="flex-1 overflow-y-auto">
                    {selectedItem || isCreating ? (
                        <div className="flex flex-col h-full p-6 gap-4">

                            {/* panel header */}
                            <div className="flex items-center justify-between flex-shrink-0">
                                <div className="flex items-center gap-2 text-xs text-gray-500 font-mono">
                                    <FileText size={13} className="text-gray-600" />
                                    <span>{isCreating ? (newPath || "new item") : selectedItem?.path}</span>
                                    {selectedItem && <span className="text-gray-700">v{selectedItem.version}</span>}
                                </div>
                                <div className="flex items-center gap-2">
                                    {dirty && <span className="text-[10px] text-yellow-500 font-bold uppercase tracking-wider">Unsaved</span>}
                                    {selectedItem && (
                                        <button
                                            onClick={() => setPendingDelete({ type: "file", item: selectedItem })}
                                            className="p-1.5 text-gray-600 hover:text-red-500 transition-colors"
                                            title="Delete"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    )}
                                    <button
                                        onClick={handleSave}
                                        disabled={saving || (!dirty && !isCreating)}
                                        className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-black rounded-lg text-xs font-bold transition-all active:scale-95"
                                    >
                                        {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                        {isCreating ? "Create" : "Save"}
                                    </button>
                                </div>
                            </div>

                            {/* path (new items only) */}
                            {isCreating && (
                                <div>
                                    <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Path *</label>
                                    <input
                                        type="text"
                                        placeholder="e.g. profile/about.md"
                                        value={newPath}
                                        onChange={e => setNewPath(e.target.value)}
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 font-mono text-sm"
                                    />
                                </div>
                            )}

                            {/* title */}
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Title *</label>
                                <input
                                    type="text"
                                    placeholder="e.g. About Me"
                                    value={form.title}
                                    onChange={e => patchForm({ title: e.target.value })}
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50"
                                />
                            </div>

                            {/* scope */}
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Scope</label>
                                <div className="flex gap-2">
                                    {SCOPE_OPTIONS.map(s => (
                                        <button
                                            key={s}
                                            onClick={() => patchForm({ scope: s })}
                                            className={`flex-1 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${scopeButtonClass(s, form.scope === s)}`}
                                        >
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* content */}
                            <div className="flex flex-col flex-1 min-h-0">
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Content (Markdown)</label>
                                <textarea
                                    placeholder="Write your content here..."
                                    value={form.content}
                                    onChange={e => patchForm({ content: e.target.value })}
                                    className="flex-1 min-h-[180px] w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 resize-none font-mono text-sm leading-relaxed"
                                />
                            </div>

                            {/* tags */}
                            <div>
                                <label className="flex items-center gap-1 text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5"><Tag size={10} /> Tags</label>
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                    {form.tags.map(tag => (
                                        <span key={tag} className="flex items-center gap-1 px-2 py-0.5 bg-cyan-500/10 text-cyan-400 rounded-md text-xs border border-cyan-500/20">
                                            {tag}
                                            <X size={10} className="cursor-pointer hover:text-white" onClick={() => patchForm({ tags: form.tags.filter(t => t !== tag) })} />
                                        </span>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    placeholder="Add tag, press Enter"
                                    value={tagInput}
                                    onChange={e => setTagInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 text-sm"
                                />
                            </div>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center h-full gap-3 text-center p-8">
                            <FileText size={36} className="text-gray-800" />
                            <p className="text-gray-600 text-sm">Select a file to view or edit</p>
                            <button onClick={openCreate} className="text-xs text-cyan-500 hover:text-cyan-400 flex items-center gap-1 transition-colors">
                                <Plus size={13} /> New item
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Delete confirmation ── */}
            {pendingDelete && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-150">
                        <h3 className="text-base font-bold text-white mb-1.5">
                            {pendingDelete.type === "folder" ? "Delete folder?" : "Delete item?"}
                        </h3>
                        {pendingDelete.type === "folder" ? (
                            <p className="text-gray-400 text-sm mb-5">
                                Delete folder <span className="font-mono text-gray-200">{pendingDelete.name}</span> and all{" "}
                                <span className="text-red-400 font-bold">{pendingDelete.count}</span> item(s) inside?
                            </p>
                        ) : (
                            <p className="text-gray-400 text-sm mb-5 font-mono">{pendingDelete.item.path}</p>
                        )}
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setPendingDelete(null)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
                            <button onClick={handleDelete} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold transition-all active:scale-95">Delete</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
