"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import {
    Plus, Trash2, X, Loader2, Tag,
    ChevronRight, Home, Folder, FileText, File, Save, Lock, Globe, FolderOpen,
    Upload, Download, FolderPlus, Eye, EyeOff, GripVertical,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

interface WorkspaceItem {
    id: string;
    item_type: "note" | "file" | "directory";
    scope: string;
    path: string;
    title: string;
    content: string | null;
    tags: string[];
    version: number;
    mime_type: string | null;
    size_bytes: number | null;
    created_at: string;
    updated_at: string;
}

const SCOPE_OPTIONS = ["private", "org", "project"] as const;
type Scope = typeof SCOPE_OPTIONS[number];

type FolderEntry = { name: string; dirItem: WorkspaceItem | null };

type PendingDelete =
    | { type: "single"; item: WorkspaceItem }
    | { type: "folder"; name: string; folderPath: string; count: number; dirItem: WorkspaceItem | null }
    | null;

type UploadModal = { file: File; path: string; title: string; scope: Scope } | null;
type FolderModal = { name: string; scope: Scope } | null;

type PreviewState =
    | { status: "loading" }
    | { status: "image"; url: string; mimeType: string }
    | { status: "pdf"; url: string }
    | { status: "text"; content: string; mimeType: string }
    | { status: "unsupported"; mimeType: string };

// ─────────────────────────────────────────────
// Pure helpers
// ─────────────────────────────────────────────

function getEntries(items: WorkspaceItem[], currentPath: string): { folders: FolderEntry[]; files: WorkspaceItem[] } {
    const prefix = currentPath ? currentPath + "/" : "";
    const folderMap = new Map<string, WorkspaceItem | null>();
    const files: WorkspaceItem[] = [];

    for (const item of items) {
        if (item.item_type === "directory") {
            if (!item.path.startsWith(prefix)) continue;
            const rest = item.path.slice(prefix.length);
            if (!rest || rest.includes("/")) continue;
            folderMap.set(rest, item);
        } else {
            if (!item.path.startsWith(prefix)) continue;
            const rest = item.path.slice(prefix.length);
            if (!rest) continue;
            const slash = rest.indexOf("/");
            if (slash === -1) files.push(item);
            else { if (!folderMap.has(rest.slice(0, slash))) folderMap.set(rest.slice(0, slash), null); }
        }
    }

    return {
        folders: Array.from(folderMap.entries())
            .map(([name, dirItem]) => ({ name, dirItem }))
            .sort((a, b) => a.name.localeCompare(b.name)),
        files,
    };
}

function breadcrumbs(path: string): string[] { return path ? path.split("/") : []; }

function formatSize(bytes: number | null): string {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isTextMime(mime: string): boolean {
    return mime.startsWith("text/") || ["application/json", "application/xml", "application/javascript", "application/x-yaml"].includes(mime);
}

function tryFormatJson(text: string): string {
    try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
}

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

const EMPTY_FORM = { title: "", scope: "private" as Scope, content: "", tags: [] as string[] };
const DND_KEY = "application/x-workspace-ids";

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

export default function WorkspacePage() {
    const [items, setItems]           = useState<WorkspaceItem[]>([]);
    const [loading, setLoading]       = useState(true);
    const [currentPath, setCurrentPath] = useState("");

    // right-panel single-item state
    const [selectedItem, setSelectedItem] = useState<WorkspaceItem | null>(null);
    const [isCreating, setIsCreating]     = useState(false);
    const [form, setForm]                 = useState({ ...EMPTY_FORM });
    const [newPath, setNewPath]           = useState("");
    const [tagInput, setTagInput]         = useState("");
    const [dirty, setDirty]               = useState(false);
    const [saving, setSaving]             = useState(false);

    // multi-selection
    const [selectedIds, setSelectedIds]     = useState<Set<string>>(new Set());
    const [lastClickedId, setLastClickedId] = useState<string | null>(null);
    const [pendingBulkDelete, setPendingBulkDelete] = useState(false);

    // drag & drop
    const [draggingIds, setDraggingIds]     = useState<Set<string>>(new Set());
    const [dragOverTarget, setDragOverTarget] = useState<string | null>(null);
    const [moving, setMoving]               = useState(false);

    // misc
    const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);
    const [hoveredEntry, setHoveredEntry]   = useState<string | null>(null);
    const fileInputRef                      = useRef<HTMLInputElement>(null);
    const [uploadModal, setUploadModal]     = useState<UploadModal>(null);
    const [uploading, setUploading]         = useState(false);
    const [folderModal, setFolderModal]     = useState<FolderModal>(null);
    const [creatingFolder, setCreatingFolder] = useState(false);
    const [downloading, setDownloading]     = useState(false);
    const [preview, setPreview]             = useState<PreviewState | null>(null);
    const [showPreview, setShowPreview]     = useState(true);

    const { folders, files } = useMemo(() => getEntries(items, currentPath), [items, currentPath]);
    const crumbs              = useMemo(() => breadcrumbs(currentPath), [currentPath]);

    // ── fetch ──────────────────────────────────

    const fetchItems = async () => {
        setLoading(true);
        try {
            const res = await apiFetch("/api/workspace/tree");
            if (res.ok) setItems(await res.json());
        } finally { setLoading(false); }
    };

    useEffect(() => { fetchItems(); }, []);

    // ── preview ────────────────────────────────

    useEffect(() => {
        if (!selectedItem || selectedItem.item_type !== "file") { setPreview(null); return; }
        let cancelled = false;
        let blobUrl: string | null = null;

        (async () => {
            setPreview({ status: "loading" });
            const mime = selectedItem.mime_type || "";
            try {
                const res = await apiFetch(`/api/workspace/files/${selectedItem.id}/content`);
                if (cancelled || !res.ok) { if (!cancelled) setPreview({ status: "unsupported", mimeType: mime }); return; }
                if (mime.startsWith("image/")) {
                    const blob = await res.blob(); if (cancelled) return;
                    blobUrl = URL.createObjectURL(blob);
                    setPreview({ status: "image", url: blobUrl, mimeType: mime });
                } else if (mime === "application/pdf") {
                    const blob = await res.blob(); if (cancelled) return;
                    blobUrl = URL.createObjectURL(blob);
                    setPreview({ status: "pdf", url: blobUrl });
                } else if (isTextMime(mime)) {
                    const text = await res.text(); if (cancelled) return;
                    setPreview({ status: "text", content: mime === "application/json" ? tryFormatJson(text) : text, mimeType: mime });
                } else {
                    setPreview({ status: "unsupported", mimeType: mime });
                }
            } catch { if (!cancelled) setPreview({ status: "unsupported", mimeType: selectedItem.mime_type || "" }); }
        })();

        return () => { cancelled = true; if (blobUrl) URL.revokeObjectURL(blobUrl); };
    }, [selectedItem?.id]);

    // ── navigation ─────────────────────────────

    const navigateTo = (path: string) => {
        setCurrentPath(path);
        setSelectedItem(null);
        setSelectedIds(new Set());
        setLastClickedId(null);
        setIsCreating(false);
        setDirty(false);
    };

    const navigateUp = () => {
        const parts = currentPath.split("/"); parts.pop();
        navigateTo(parts.join("/"));
    };

    // ── selection helpers ──────────────────────

    /** Load a single item into the right panel. */
    const loadItem = (item: WorkspaceItem) => {
        setSelectedItem(item);
        setIsCreating(false);
        setForm({ title: item.title, scope: item.scope as Scope, content: item.item_type === "note" ? (item.content ?? "") : "", tags: item.tags ?? [] });
        setTagInput("");
        setDirty(false);
    };

    const handleFileClick = (item: WorkspaceItem, e: React.MouseEvent) => {
        if (item.item_type === "directory") { setSelectedIds(new Set()); setLastClickedId(null); navigateTo(item.path); return; }

        let nextIds: Set<string>;

        if (e.shiftKey && lastClickedId) {
            const allIds = files.map(f => f.id);
            const lo = allIds.indexOf(lastClickedId), hi = allIds.indexOf(item.id);
            if (lo !== -1 && hi !== -1) {
                const [a, b] = [Math.min(lo, hi), Math.max(lo, hi)];
                nextIds = new Set([...selectedIds, ...allIds.slice(a, b + 1)]);
            } else { nextIds = new Set([item.id]); }
            // lastClickedId intentionally unchanged on shift+click
        } else if (e.ctrlKey || e.metaKey) {
            nextIds = new Set(selectedIds);
            nextIds.has(item.id) ? nextIds.delete(item.id) : nextIds.add(item.id);
            setLastClickedId(item.id);
        } else {
            nextIds = new Set([item.id]);
            setLastClickedId(item.id);
        }

        setSelectedIds(nextIds);

        if (nextIds.size === 1) {
            const [id] = [...nextIds];
            const found = items.find(i => i.id === id);
            if (found) loadItem(found);
        } else {
            setSelectedItem(null);
            setIsCreating(false);
        }
    };

    const openCreate = () => {
        setSelectedItem(null);
        setSelectedIds(new Set());
        setIsCreating(true);
        setForm({ ...EMPTY_FORM });
        setNewPath(currentPath ? currentPath + "/" : "");
        setTagInput("");
        setDirty(false);
    };

    // ── save ───────────────────────────────────

    const handleSave = async () => {
        setSaving(true);
        try {
            if (isCreating) {
                if (!form.title.trim() || !newPath.trim()) return;
                const res = await apiFetch("/api/workspace/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, path: newPath }) });
                if (res.ok) { const created = await res.json(); setItems(prev => [created, ...prev]); setIsCreating(false); setSelectedIds(new Set([created.id])); loadItem(created); }
            } else if (selectedItem) {
                const payload = selectedItem.item_type === "note" ? form : { title: form.title, scope: form.scope, tags: form.tags };
                const res = await apiFetch(`/api/workspace/items/${selectedItem.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
                if (res.ok) { const updated = await res.json(); setItems(prev => prev.map(i => i.id === updated.id ? updated : i)); setSelectedItem(updated); setDirty(false); }
            }
        } finally { setSaving(false); }
    };

    // ── delete ─────────────────────────────────

    const handleDelete = async () => {
        if (!pendingDelete) return;
        if (pendingDelete.type === "single") {
            const res = await apiFetch(`/api/workspace/items/${pendingDelete.item.id}`, { method: "DELETE" });
            if (res.ok) {
                setItems(prev => prev.filter(i => i.id !== pendingDelete.item.id));
                if (selectedItem?.id === pendingDelete.item.id) { setSelectedItem(null); setSelectedIds(new Set()); }
            }
        } else {
            if (pendingDelete.dirItem) {
                await apiFetch(`/api/workspace/items/${pendingDelete.dirItem.id}`, { method: "DELETE" });
            } else {
                await Promise.all(items.filter(i => i.path.startsWith(pendingDelete.folderPath + "/")).map(i => apiFetch(`/api/workspace/items/${i.id}`, { method: "DELETE" })));
            }
            const fp = pendingDelete.folderPath;
            setItems(prev => prev.filter(i => !i.path.startsWith(fp + "/") && i.path !== fp));
            if (selectedItem && (selectedItem.path.startsWith(fp + "/") || selectedItem.path === fp)) { setSelectedItem(null); setSelectedIds(new Set()); }
        }
        setPendingDelete(null);
    };

    const handleBulkDelete = async () => {
        const ids = [...selectedIds];
        setPendingBulkDelete(false);
        await Promise.all(ids.map(id => apiFetch(`/api/workspace/items/${id}`, { method: "DELETE" })));
        setItems(prev => prev.filter(i => !selectedIds.has(i.id)));
        setSelectedIds(new Set());
        setSelectedItem(null);
    };

    // ── drag & drop ────────────────────────────

    const handleMove = async (ids: string[], targetFolderPath: string) => {
        if (ids.length === 0) return;
        setMoving(true);
        try {
            const results = await Promise.all(ids.map(async id => {
                const item = items.find(i => i.id === id);
                if (!item || item.item_type === "directory") return null;
                const filename = item.path.split("/").pop() || item.title;
                const newPath = targetFolderPath ? `${targetFolderPath}/${filename}` : filename;
                if (newPath === item.path) return item;
                const params = new URLSearchParams({ new_path: newPath });
                const res = await apiFetch(`/api/workspace/items/${id}/move?${params}`, { method: "POST" });
                return res.ok ? await res.json() : null;
            }));
            setItems(prev => {
                const map = new Map(prev.map(i => [i.id, i]));
                for (const r of results) if (r) map.set(r.id, r);
                return Array.from(map.values());
            });
        } finally {
            setMoving(false);
            setDraggingIds(new Set());
            setDragOverTarget(null);
        }
    };

    const onDragStart = (item: WorkspaceItem, e: React.DragEvent) => {
        if (item.item_type === "directory") { e.preventDefault(); return; }
        const ids = selectedIds.has(item.id) ? [...selectedIds].filter(id => { const it = items.find(i => i.id === id); return it && it.item_type !== "directory"; }) : [item.id];
        setDraggingIds(new Set(ids));
        e.dataTransfer.setData(DND_KEY, JSON.stringify(ids));
        e.dataTransfer.effectAllowed = "move";
    };

    const onDragEnd = () => { setDraggingIds(new Set()); setDragOverTarget(null); };

    const onFolderDragOver = (e: React.DragEvent, targetKey: string) => {
        if (!e.dataTransfer.types.includes(DND_KEY)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setDragOverTarget(targetKey);
    };

    const onFolderDragLeave = (e: React.DragEvent) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOverTarget(null);
    };

    const onFolderDrop = (e: React.DragEvent, targetFolderPath: string) => {
        e.preventDefault();
        try {
            const ids: string[] = JSON.parse(e.dataTransfer.getData(DND_KEY) || "[]");
            handleMove(ids, targetFolderPath);
        } catch { /* ignore */ }
        setDragOverTarget(null);
    };

    // ── upload ─────────────────────────────────

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        setUploadModal({ file, path: currentPath ? `${currentPath}/${file.name}` : file.name, title: file.name, scope: "private" });
        e.target.value = "";
    };

    const handleUpload = async () => {
        if (!uploadModal) return;
        setUploading(true);
        try {
            const fd = new FormData(); fd.append("file", uploadModal.file);
            const params = new URLSearchParams({ path: uploadModal.path, title: uploadModal.title, scope: uploadModal.scope });
            const res = await apiFetch(`/api/workspace/files?${params}`, { method: "POST", body: fd });
            if (res.ok) { const created = await res.json(); setItems(prev => [...prev, created]); setUploadModal(null); }
        } finally { setUploading(false); }
    };

    // ── folder creation ────────────────────────

    const handleCreateFolder = async () => {
        if (!folderModal?.name.trim()) return;
        setCreatingFolder(true);
        try {
            const path = currentPath ? `${currentPath}/${folderModal.name.trim()}` : folderModal.name.trim();
            const res = await apiFetch("/api/workspace/directories", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, title: folderModal.name.trim(), scope: folderModal.scope }) });
            if (res.ok) { const created = await res.json(); setItems(prev => [...prev, created]); setFolderModal(null); }
        } finally { setCreatingFolder(false); }
    };

    // ── download ───────────────────────────────

    const handleDownload = async (item: WorkspaceItem) => {
        setDownloading(true);
        try {
            const res = await apiFetch(`/api/workspace/files/${item.id}/content`);
            if (res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a"); a.href = url; a.download = item.title; a.click();
                URL.revokeObjectURL(url);
            }
        } finally { setDownloading(false); }
    };

    // ── form helpers ───────────────────────────

    const patchForm = (patch: Partial<typeof form>) => { setForm(f => ({ ...f, ...patch })); setDirty(true); };
    const addTag = () => { const t = tagInput.trim(); if (t && !form.tags.includes(t)) patchForm({ tags: [...form.tags, t] }); setTagInput(""); };

    // ── render ─────────────────────────────────

    const multiSelected = selectedIds.size > 1;

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />

            {/* ── Top bar ── */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/60 flex-shrink-0 bg-gray-950">
                <h1 className="text-base font-bold text-white tracking-tight">Workspace</h1>
                <div className="flex items-center gap-2">
                    {moving && <span className="text-[10px] text-cyan-500 font-bold uppercase tracking-wider flex items-center gap-1"><Loader2 size={10} className="animate-spin" />Moving…</span>}
                    <button onClick={() => setFolderModal({ name: "", scope: "private" })} className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-lg text-xs font-bold transition-all active:scale-95 border border-gray-700/50">
                        <FolderPlus size={13} /> New Folder
                    </button>
                    <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-lg text-xs font-bold transition-all active:scale-95 border border-gray-700/50">
                        <Upload size={13} /> Upload
                    </button>
                    <button onClick={openCreate} className="flex items-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 text-black px-3 py-1.5 rounded-lg text-xs font-bold transition-all active:scale-95 shadow-md shadow-cyan-500/20">
                        <Plus size={14} /> New Note
                    </button>
                </div>
            </div>

            {/* ── Two-panel body ── */}
            <div className="flex flex-1 min-h-0 overflow-hidden">

                {/* ── LEFT: tree ── */}
                <div className="w-64 flex-shrink-0 border-r border-gray-800/60 flex flex-col bg-gray-950/60">

                    {/* breadcrumb */}
                    <div className="flex items-center gap-1 px-3 py-2 border-b border-gray-800/40 flex-wrap min-h-[36px]">
                        <button onClick={() => navigateTo("")} className="text-gray-500 hover:text-cyan-400 transition-colors" title="Root"><Home size={13} /></button>
                        {crumbs.map((crumb, idx) => {
                            const crumbPath = crumbs.slice(0, idx + 1).join("/");
                            const isLast = idx === crumbs.length - 1;
                            return (
                                <span key={crumbPath} className="flex items-center gap-1">
                                    <ChevronRight size={10} className="text-gray-700" />
                                    <button
                                        onClick={() => navigateTo(crumbPath)}
                                        className={`text-xs transition-colors ${isLast ? "text-gray-200 font-semibold" : "text-gray-500 hover:text-cyan-400"}`}
                                    >{crumb}</button>
                                </span>
                            );
                        })}
                    </div>

                    {/* tree list */}
                    {loading ? (
                        <div className="flex flex-1 items-center justify-center"><Loader2 size={18} className="text-cyan-500 animate-spin" /></div>
                    ) : (
                        <div
                            className="flex-1 overflow-y-auto py-0.5"
                            onClick={e => { if (e.target === e.currentTarget) { setSelectedIds(new Set()); setSelectedItem(null); setIsCreating(false); } }}
                        >
                            {/* parent (..) – also a drop target */}
                            {currentPath && (
                                <button
                                    onClick={navigateUp}
                                    onDragOver={e => onFolderDragOver(e, "parent")}
                                    onDragLeave={onFolderDragLeave}
                                    onDrop={e => { const parent = currentPath.split("/").slice(0, -1).join("/"); onFolderDrop(e, parent); }}
                                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs transition-colors rounded
                                        ${dragOverTarget === "parent" ? "bg-cyan-500/15 text-cyan-400 ring-1 ring-inset ring-cyan-500/30" : "text-gray-600 hover:text-gray-300 hover:bg-gray-900/50"}`}
                                >
                                    <span className="font-mono">..</span>
                                    {dragOverTarget === "parent" && <span className="text-[10px] text-cyan-500 ml-auto">Drop here</span>}
                                </button>
                            )}

                            {/* folders */}
                            {folders.map(({ name, dirItem }) => {
                                const folderPath = currentPath ? `${currentPath}/${name}` : name;
                                const hovered = hoveredEntry === `folder:${name}`;
                                const isDropTarget = dragOverTarget === `folder:${name}`;
                                return (
                                    <div
                                        key={name}
                                        onMouseEnter={() => setHoveredEntry(`folder:${name}`)}
                                        onMouseLeave={() => setHoveredEntry(null)}
                                        onDragOver={e => onFolderDragOver(e, `folder:${name}`)}
                                        onDragLeave={onFolderDragLeave}
                                        onDrop={e => onFolderDrop(e, folderPath)}
                                        className={`flex items-center px-3 py-1.5 text-sm text-gray-300 transition-colors rounded mx-0.5
                                            ${isDropTarget ? "bg-cyan-500/15 ring-1 ring-inset ring-cyan-500/30" : "hover:bg-gray-900/50"}`}
                                    >
                                        <button onClick={() => navigateTo(folderPath)} className="flex items-center gap-2 flex-1 min-w-0">
                                            <Folder size={15} className="text-yellow-500/70 flex-shrink-0" />
                                            <span className="truncate text-left text-xs">{name}</span>
                                            {isDropTarget && <span className="text-[10px] text-cyan-500 ml-auto flex-shrink-0">Drop</span>}
                                        </button>
                                        {hovered && !isDropTarget && (
                                            <button
                                                onClick={e => { e.stopPropagation(); const count = items.filter(i => i.path.startsWith(folderPath + "/") || i.path === folderPath).length; setPendingDelete({ type: "folder", name, folderPath, count, dirItem }); }}
                                                className="p-0.5 text-gray-600 hover:text-red-500 transition-colors flex-shrink-0"
                                                title="Delete folder"
                                            ><Trash2 size={12} /></button>
                                        )}
                                    </div>
                                );
                            })}

                            {/* files + notes */}
                            {files.map(item => {
                                const isSelected = selectedIds.has(item.id);
                                const hovered = hoveredEntry === `file:${item.id}`;
                                const isDragging = draggingIds.has(item.id);
                                const isFile = item.item_type === "file";
                                return (
                                    <div
                                        key={item.id}
                                        draggable
                                        onDragStart={e => onDragStart(item, e)}
                                        onDragEnd={onDragEnd}
                                        onMouseEnter={() => setHoveredEntry(`file:${item.id}`)}
                                        onMouseLeave={() => setHoveredEntry(null)}
                                        onClick={e => handleFileClick(item, e)}
                                        className={`flex items-center px-2 py-1.5 text-sm transition-colors select-none rounded mx-0.5 cursor-pointer
                                            ${isSelected ? "bg-cyan-500/10 text-cyan-300" : "text-gray-400 hover:bg-gray-900/50 hover:text-gray-200"}
                                            ${isDragging ? "opacity-30" : ""}`}
                                    >
                                        {/* drag handle (visible on hover) */}
                                        <span className={`flex-shrink-0 transition-opacity mr-0.5 ${hovered ? "opacity-40" : "opacity-0"}`}>
                                            <GripVertical size={12} className="text-gray-500" />
                                        </span>

                                        {isFile
                                            ? <File size={14} className={`flex-shrink-0 mr-1.5 ${isSelected ? "text-cyan-400" : "text-blue-500/70"}`} />
                                            : <FileText size={14} className={`flex-shrink-0 mr-1.5 ${isSelected ? "text-cyan-400" : "text-gray-600"}`} />
                                        }

                                        <span className="truncate text-xs flex-1">{item.title}</span>

                                        {hovered && !isDragging ? (
                                            <button
                                                onClick={e => { e.stopPropagation(); setPendingDelete({ type: "single", item }); }}
                                                className="p-0.5 text-gray-600 hover:text-red-500 transition-colors flex-shrink-0"
                                                title="Delete"
                                            ><Trash2 size={12} /></button>
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

                    {/* selection action bar */}
                    {selectedIds.size > 0 && (
                        <div className="border-t border-gray-800/60 px-3 py-2 flex items-center justify-between flex-shrink-0 bg-gray-950/80">
                            <span className="text-xs text-gray-500">
                                {selectedIds.size} selected
                                <span className="text-gray-700 ml-1">· Shift/Ctrl+click</span>
                            </span>
                            <div className="flex items-center gap-2">
                                <button onClick={() => { setSelectedIds(new Set()); setSelectedItem(null); }} className="text-[11px] text-gray-600 hover:text-gray-400 transition-colors">Clear</button>
                                {selectedIds.size > 1 && (
                                    <button onClick={() => setPendingBulkDelete(true)} className="text-[11px] text-red-500 hover:text-red-400 transition-colors flex items-center gap-0.5">
                                        <Trash2 size={11} /> Delete
                                    </button>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* ── RIGHT: detail / multi-select / empty ── */}
                <div className="flex-1 overflow-y-auto">

                    {/* multi-select panel */}
                    {multiSelected && (
                        <div className="flex flex-col items-center justify-center h-full gap-5 p-8 text-center">
                            <div>
                                <p className="text-4xl font-black text-gray-700">{selectedIds.size}</p>
                                <p className="text-gray-400 text-sm mt-1">items selected</p>
                            </div>
                            <div className="flex flex-wrap justify-center gap-1.5 max-w-xs">
                                {[...selectedIds].slice(0, 6).map(id => {
                                    const it = items.find(i => i.id === id);
                                    return it ? <span key={id} className="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs truncate max-w-[130px]">{it.title}</span> : null;
                                })}
                                {selectedIds.size > 6 && <span className="text-gray-600 text-xs">+{selectedIds.size - 6} more</span>}
                            </div>
                            <p className="text-gray-700 text-xs">Drag items in the tree to move them</p>
                            <div className="flex gap-3">
                                <button onClick={() => { setSelectedIds(new Set()); setSelectedItem(null); }} className="px-4 py-2 rounded-xl text-xs text-gray-500 hover:text-gray-300 border border-gray-800 hover:border-gray-700 transition-all">
                                    Clear
                                </button>
                                <button onClick={() => setPendingBulkDelete(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition-all font-bold">
                                    <Trash2 size={12} /> Delete {selectedIds.size} items
                                </button>
                            </div>
                        </div>
                    )}

                    {/* single item / create panel */}
                    {!multiSelected && (selectedItem || isCreating) && (
                        <div className="flex flex-col h-full p-6 gap-4">

                            {/* header */}
                            <div className="flex items-center justify-between flex-shrink-0">
                                <div className="flex items-center gap-2 text-xs text-gray-500 font-mono">
                                    {selectedItem?.item_type === "file" ? <File size={13} className="text-blue-500" /> : <FileText size={13} className="text-gray-600" />}
                                    <span>{isCreating ? (newPath || "new note") : selectedItem?.path}</span>
                                    {selectedItem && <span className="text-gray-700">v{selectedItem.version}</span>}
                                </div>
                                <div className="flex items-center gap-2">
                                    {selectedItem?.item_type === "file" && (
                                        <button onClick={() => handleDownload(selectedItem)} disabled={downloading} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs font-bold transition-all active:scale-95 border border-gray-700/50 disabled:opacity-40">
                                            {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} Download
                                        </button>
                                    )}
                                    {dirty && <span className="text-[10px] text-yellow-500 font-bold uppercase tracking-wider">Unsaved</span>}
                                    {selectedItem && (
                                        <button onClick={() => setPendingDelete({ type: "single", item: selectedItem })} className="p-1.5 text-gray-600 hover:text-red-500 transition-colors" title="Delete">
                                            <Trash2 size={14} />
                                        </button>
                                    )}
                                    <button onClick={handleSave} disabled={saving || (!dirty && !isCreating)} className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-black rounded-lg text-xs font-bold transition-all active:scale-95">
                                        {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                        {isCreating ? "Create" : "Save"}
                                    </button>
                                </div>
                            </div>

                            {/* path (new items only) */}
                            {isCreating && (
                                <div>
                                    <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Path *</label>
                                    <input type="text" placeholder="e.g. profile/about.md" value={newPath} onChange={e => setNewPath(e.target.value)}
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 font-mono text-sm" />
                                </div>
                            )}

                            {/* title */}
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Title *</label>
                                <input type="text" placeholder="e.g. About Me" value={form.title} onChange={e => patchForm({ title: e.target.value })}
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50" />
                            </div>

                            {/* scope */}
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Scope</label>
                                <div className="flex gap-2">
                                    {SCOPE_OPTIONS.map(s => (
                                        <button key={s} onClick={() => patchForm({ scope: s })} className={`flex-1 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${scopeButtonClass(s, form.scope === s)}`}>{s}</button>
                                    ))}
                                </div>
                            </div>

                            {/* file metadata + preview */}
                            {selectedItem?.item_type === "file" && (
                                <>
                                    <div className="bg-gray-900/60 rounded-xl border border-gray-800/80 px-4 py-3 flex items-center gap-6 text-xs flex-shrink-0">
                                        <div className="min-w-0 flex-1">
                                            <p className="text-gray-600 uppercase tracking-widest font-bold text-[10px]">MIME</p>
                                            <p className="text-gray-300 font-mono mt-0.5 truncate">{selectedItem.mime_type || "—"}</p>
                                        </div>
                                        <div className="flex-shrink-0">
                                            <p className="text-gray-600 uppercase tracking-widest font-bold text-[10px]">Size</p>
                                            <p className="text-gray-300 mt-0.5">{formatSize(selectedItem.size_bytes)}</p>
                                        </div>
                                    </div>

                                    <div className="flex flex-col flex-1 min-h-0">
                                        <div className="flex items-center justify-between mb-1.5">
                                            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Preview</label>
                                            <button onClick={() => setShowPreview(v => !v)} className="flex items-center gap-1 text-[10px] text-gray-600 hover:text-gray-400 transition-colors">
                                                {showPreview ? <EyeOff size={11} /> : <Eye size={11} />}{showPreview ? "Hide" : "Show"}
                                            </button>
                                        </div>

                                        {showPreview && (
                                            <div className="flex-1 min-h-[280px] rounded-xl border border-gray-800 overflow-hidden bg-gray-950">
                                                {(!preview || preview.status === "loading") && (
                                                    <div className="flex h-full items-center justify-center"><Loader2 size={20} className="text-cyan-500 animate-spin" /></div>
                                                )}
                                                {preview?.status === "image" && (
                                                    <div className="flex h-full items-center justify-center p-4 overflow-auto">
                                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                                        <img src={preview.url} alt={selectedItem.title} className="max-w-full max-h-full object-contain rounded" />
                                                    </div>
                                                )}
                                                {preview?.status === "pdf" && (
                                                    <iframe src={preview.url} className="w-full h-full border-0" title={selectedItem.title} />
                                                )}
                                                {preview?.status === "text" && (
                                                    <pre className="h-full overflow-auto p-4 text-xs text-gray-300 font-mono leading-relaxed whitespace-pre-wrap break-words">{preview.content}</pre>
                                                )}
                                                {preview?.status === "unsupported" && (
                                                    <div className="flex flex-col h-full items-center justify-center gap-2 text-center p-6">
                                                        <File size={32} className="text-gray-700" />
                                                        <p className="text-gray-600 text-xs">{preview.mimeType ? `Preview not available for ${preview.mimeType}` : "Preview not available"}</p>
                                                        <button onClick={() => handleDownload(selectedItem)} disabled={downloading} className="flex items-center gap-1 text-xs text-cyan-500 hover:text-cyan-400 mt-1 transition-colors disabled:opacity-40">
                                                            <Download size={12} /> Download to view
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </>
                            )}

                            {/* content (note only) */}
                            {(isCreating || selectedItem?.item_type === "note") && (
                                <div className="flex flex-col flex-1 min-h-0">
                                    <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Content (Markdown)</label>
                                    <textarea placeholder="Write your content here…" value={form.content} onChange={e => patchForm({ content: e.target.value })}
                                        className="flex-1 min-h-[180px] w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 resize-none font-mono text-sm leading-relaxed" />
                                </div>
                            )}

                            {/* tags */}
                            <div>
                                <label className="flex items-center gap-1 text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5"><Tag size={10} /> Tags</label>
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                    {form.tags.map(tag => (
                                        <span key={tag} className="flex items-center gap-1 px-2 py-0.5 bg-cyan-500/10 text-cyan-400 rounded-md text-xs border border-cyan-500/20">
                                            {tag}<X size={10} className="cursor-pointer hover:text-white" onClick={() => patchForm({ tags: form.tags.filter(t => t !== tag) })} />
                                        </span>
                                    ))}
                                </div>
                                <input type="text" placeholder="Add tag, press Enter" value={tagInput} onChange={e => setTagInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 text-sm" />
                            </div>
                        </div>
                    )}

                    {/* empty state */}
                    {!multiSelected && !selectedItem && !isCreating && (
                        <div className="flex flex-col items-center justify-center h-full gap-3 text-center p-8">
                            <FileText size={36} className="text-gray-800" />
                            <p className="text-gray-600 text-sm">Select an item to view or edit</p>
                            <p className="text-gray-700 text-xs">Shift+click or Ctrl+click for multi-select<br />Drag items onto folders to move them</p>
                            <div className="flex items-center gap-3 mt-1">
                                <button onClick={openCreate} className="text-xs text-cyan-500 hover:text-cyan-400 flex items-center gap-1 transition-colors"><Plus size={13} /> New note</button>
                                <span className="text-gray-800">·</span>
                                <button onClick={() => fileInputRef.current?.click()} className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors"><Upload size={13} /> Upload file</button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Delete single ── */}
            {pendingDelete && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-150">
                        <h3 className="text-base font-bold text-white mb-1.5">{pendingDelete.type === "folder" ? "Delete folder?" : "Delete item?"}</h3>
                        {pendingDelete.type === "folder" ? (
                            <p className="text-gray-400 text-sm mb-5">Delete <span className="font-mono text-gray-200">{pendingDelete.name}</span> and <span className="text-red-400 font-bold">{pendingDelete.count}</span> item(s) inside?</p>
                        ) : (
                            <p className="text-gray-400 text-sm mb-5 font-mono">{pendingDelete.item.path}</p>
                        )}
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setPendingDelete(null)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={handleDelete} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete</button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Delete bulk ── */}
            {pendingBulkDelete && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-150">
                        <h3 className="text-base font-bold text-white mb-1.5">Delete {selectedIds.size} items?</h3>
                        <p className="text-gray-400 text-sm mb-5">This cannot be undone.</p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setPendingBulkDelete(false)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={handleBulkDelete} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete</button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Upload modal ── */}
            {uploadModal && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-gray-700 w-full max-w-md rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-150">
                        <h3 className="text-base font-bold text-white mb-1 flex items-center gap-2"><Upload size={15} className="text-cyan-400" /> Upload File</h3>
                        <p className="text-[11px] text-gray-500 mb-5 font-mono truncate">{uploadModal.file.name} · {formatSize(uploadModal.file.size)}</p>
                        <div className="flex flex-col gap-3">
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Path *</label>
                                <input type="text" value={uploadModal.path} onChange={e => setUploadModal(m => m ? { ...m, path: e.target.value } : m)}
                                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 font-mono text-sm" />
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Title *</label>
                                <input type="text" value={uploadModal.title} onChange={e => setUploadModal(m => m ? { ...m, title: e.target.value } : m)}
                                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 text-sm" />
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Scope</label>
                                <div className="flex gap-2">
                                    {SCOPE_OPTIONS.map(s => <button key={s} onClick={() => setUploadModal(m => m ? { ...m, scope: s } : m)} className={`flex-1 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${scopeButtonClass(s, uploadModal.scope === s)}`}>{s}</button>)}
                                </div>
                            </div>
                        </div>
                        <div className="flex gap-3 justify-end mt-6">
                            <button onClick={() => setUploadModal(null)} disabled={uploading} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={handleUpload} disabled={uploading || !uploadModal.path.trim() || !uploadModal.title.trim()} className="flex items-center gap-1.5 px-5 py-1.5 rounded-lg text-sm bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-black font-bold">
                                {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} Upload
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── New Folder modal ── */}
            {folderModal !== null && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-gray-700 w-full max-w-sm rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-150">
                        <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2"><FolderPlus size={15} className="text-yellow-400" /> New Folder</h3>
                        <div className="flex flex-col gap-3">
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Folder Name *</label>
                                <input type="text" placeholder="e.g. reports" value={folderModal.name}
                                    onChange={e => setFolderModal(m => m ? { ...m, name: e.target.value } : m)}
                                    onKeyDown={e => { if (e.key === "Enter") handleCreateFolder(); }}
                                    autoFocus
                                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-cyan-500/50 font-mono text-sm" />
                                {currentPath && folderModal.name && <p className="text-[10px] text-gray-600 mt-1 font-mono">{currentPath}/{folderModal.name}</p>}
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">Scope</label>
                                <div className="flex gap-2">
                                    {SCOPE_OPTIONS.map(s => <button key={s} onClick={() => setFolderModal(m => m ? { ...m, scope: s } : m)} className={`flex-1 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${scopeButtonClass(s, folderModal.scope === s)}`}>{s}</button>)}
                                </div>
                            </div>
                        </div>
                        <div className="flex gap-3 justify-end mt-6">
                            <button onClick={() => setFolderModal(null)} disabled={creatingFolder} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={handleCreateFolder} disabled={creatingFolder || !folderModal.name.trim()} className="flex items-center gap-1.5 px-5 py-1.5 rounded-lg text-sm bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-black font-bold">
                                {creatingFolder ? <Loader2 size={12} className="animate-spin" /> : <FolderPlus size={12} />} Create
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
