import React, { useCallback, useEffect, useRef, useState } from "react"
import { Search, Plus, Trash2, Edit2, Music, StickyNote, Filter, ExternalLink, Loader2, X, Pencil, Mic, Undo2 } from "lucide-react"
import { listProjects, Project, apiFetch, apiJson, getFileToken, BASE_URL } from "../lib/api"
import AudioRecorder from "./AudioRecorder"

interface Note {
    id: string
    project_id: string | null
    title: string | null
    content: string | null
    audio_file_id: string | null
    tags: string[]
    created_at: string
    updated_at: string
}

// ── Undo stack types ───────────────────────────────────────────────────────────
type UndoAction =
    | { type: "delete"; notes: Note[] }
    | { type: "create"; noteId: string }

const MAX_UNDO = 20

export default function NotesView({ onOpenProject }: { onOpenProject: (projectId: string) => void }) {
    const [notes, setNotes] = useState<Note[]>([])
    const [projects, setProjects] = useState<Project[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState("")
    const [selectedProject, setSelectedProject] = useState<string>("all")

    // Selection
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
    const lastClickedId = useRef<string | null>(null)

    // Undo
    const [undoStack, setUndoStack] = useState<UndoAction[]>([])
    const [undoToast, setUndoToast] = useState<string | null>(null)
    const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Context menu
    const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; noteId: string } | null>(null)

    // Modals
    const [isCreating, setIsCreating] = useState(false)
    const [isCreatingAudio, setIsCreatingAudio] = useState(false)
    const [isUploading, setIsUploading] = useState(false)

    // Forms
    const [editingNote, setEditingNote] = useState<Note | null>(null)
    const [newNote, setNewNote] = useState({ title: "", content: "", project_id: "", tags: [] as string[] })
    const [tagInput, setTagInput] = useState("")
    const [audioProjectId, setAudioProjectId] = useState<string>("")
    const [audioTitle, setAudioTitle] = useState<string>("")

    // Auth token for audio
    const [token, setToken] = useState("")

    useEffect(() => {
        loadData()
        getFileToken().then(setToken).catch(() => { })
    }, [])

    // ── Keyboard shortcuts ─────────────────────────────────────────
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            // Ctrl+Z — undo
            if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
                e.preventDefault()
                performUndo()
            }
        }
        window.addEventListener("keydown", handler)
        return () => window.removeEventListener("keydown", handler)
    }, [undoStack, notes])

    // ── Close context menu on click anywhere ───────────────────────
    useEffect(() => {
        if (!ctxMenu) return
        const close = () => setCtxMenu(null)
        window.addEventListener("click", close)
        window.addEventListener("contextmenu", close)
        return () => {
            window.removeEventListener("click", close)
            window.removeEventListener("contextmenu", close)
        }
    }, [ctxMenu])

    const pushUndo = useCallback((action: UndoAction) => {
        setUndoStack(prev => [...prev.slice(-(MAX_UNDO - 1)), action])
    }, [])

    const showToast = useCallback((msg: string) => {
        setUndoToast(msg)
        if (toastTimer.current) clearTimeout(toastTimer.current)
        toastTimer.current = setTimeout(() => setUndoToast(null), 3000)
    }, [])

    const performUndo = useCallback(async () => {
        if (undoStack.length === 0) return
        const action = undoStack[undoStack.length - 1]
        setUndoStack(prev => prev.slice(0, -1))

        try {
            if (action.type === "delete") {
                const restored: Note[] = []
                for (const note of action.notes) {
                    const res = await apiJson<Note>("/api/notes", {
                        method: "POST",
                        body: JSON.stringify({
                            title: note.title,
                            content: note.content,
                            project_id: note.project_id || undefined,
                            tags: note.tags || [],
                        })
                    })
                    restored.push(res)
                }
                setNotes(prev => [...restored, ...prev])
                showToast(`Restored ${restored.length} note${restored.length > 1 ? "s" : ""}`)
            } else if (action.type === "create") {
                await apiFetch(`/api/notes/${action.noteId}`, { method: "DELETE" })
                setNotes(prev => prev.filter(n => n.id !== action.noteId))
                showToast("Creation undone")
            }
        } catch (err) {
            console.error("Undo failed:", err)
            showToast("Undo failed")
        }
    }, [undoStack, showToast])

    const loadData = async () => {
        setLoading(true)
        try {
            const [projRes, notesRes] = await Promise.all([
                listProjects(),
                apiJson<Note[]>("/api/notes")
            ])
            setProjects(projRes)
            setNotes(notesRes)
        } catch (err) {
            console.error(err)
        } finally {
            setLoading(false)
        }
    }

    const handleSave = async () => {
        if (!newNote.title && !newNote.content) return

        try {
            const payload = {
                ...newNote,
                project_id: newNote.project_id === "" ? undefined : newNote.project_id
            }

            if (editingNote) {
                const res = await apiJson<Note>(`/api/notes/${editingNote.id}`, {
                    method: "PATCH",
                    body: JSON.stringify(payload)
                })
                setNotes(notes.map(n => n.id === editingNote.id ? res : n))
            } else {
                const res = await apiJson<Note>("/api/notes", {
                    method: "POST",
                    body: JSON.stringify(payload)
                })
                setNotes([res, ...notes])
                pushUndo({ type: "create", noteId: res.id })
            }
        } catch (err) {
            console.error("Failed to save note:", err)
        }

        setNewNote({ title: "", content: "", project_id: "", tags: [] })
        setIsCreating(false)
        setEditingNote(null)
    }

    // ── Delete (no confirm) ────────────────────────────────────────
    const deleteNote = async (id: string) => {
        const note = notes.find(n => n.id === id)
        if (!note) return
        try {
            await apiFetch(`/api/notes/${id}`, { method: "DELETE" })
            setNotes(prev => prev.filter(n => n.id !== id))
            setSelectedIds(prev => { const s = new Set(prev); s.delete(id); return s })
            pushUndo({ type: "delete", notes: [note] })
            showToast("Note deleted — Ctrl+Z to undo")
        } catch (err) {
            console.error("Failed to delete note:", err)
        }
    }

    // ── Bulk delete ────────────────────────────────────────────────
    const deleteSelected = async () => {
        const ids = Array.from(selectedIds)
        const deletedNotes = notes.filter(n => ids.includes(n.id))
        try {
            await Promise.all(ids.map(id => apiFetch(`/api/notes/${id}`, { method: "DELETE" })))
            setNotes(prev => prev.filter(n => !ids.includes(n.id)))
            setSelectedIds(new Set())
            pushUndo({ type: "delete", notes: deletedNotes })
            showToast(`${deletedNotes.length} notes deleted — Ctrl+Z to undo`)
        } catch (err) {
            console.error("Failed to bulk delete:", err)
        }
    }

    // ── Click handler with shift-select ─────────────────────────────
    const handleNoteClick = (noteId: string, e: React.MouseEvent) => {
        if (e.shiftKey && lastClickedId.current) {
            const ids = filteredNotes.map(n => n.id)
            const a = ids.indexOf(lastClickedId.current)
            const b = ids.indexOf(noteId)
            if (a !== -1 && b !== -1) {
                const [start, end] = a < b ? [a, b] : [b, a]
                const rangeIds = ids.slice(start, end + 1)
                setSelectedIds(prev => {
                    const s = new Set(prev)
                    rangeIds.forEach(id => s.add(id))
                    return s
                })
            }
        } else if (e.ctrlKey || e.metaKey) {
            setSelectedIds(prev => {
                const s = new Set(prev)
                if (s.has(noteId)) s.delete(noteId)
                else s.add(noteId)
                return s
            })
        } else {
            setSelectedIds(prev => {
                if (prev.has(noteId) && prev.size === 1) return new Set()
                return new Set([noteId])
            })
        }
        lastClickedId.current = noteId
    }

    // ── Right-click context menu ───────────────────────────────────
    const handleContextMenu = (noteId: string, e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setCtxMenu({ x: e.clientX, y: e.clientY, noteId })
    }

    const handleAudioCapture = async (blob: Blob) => {
        setIsUploading(true)
        try {
            const formData = new FormData()
            const now = new Date()
            const timeStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`
            formData.append("file", new File([blob], `recording_${timeStr}.webm`, { type: "audio/webm" }))

            const uploadUrl = audioProjectId
                ? `/api/files/project/${audioProjectId}/notes/upload`
                : `/api/files/global/notes/upload`

            const uploadRes = await apiFetch(uploadUrl, { method: "POST", body: formData })
            if (!uploadRes.ok) throw new Error("Upload failed")
            const fileData = await uploadRes.json()

            const title = audioTitle.trim() || `Audio Note - ${now.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`

            const res = await apiJson<Note>("/api/notes", {
                method: "POST",
                body: JSON.stringify({
                    title,
                    project_id: audioProjectId || undefined,
                    audio_file_id: fileData.id,
                    content: "",
                    tags: []
                })
            })
            setNotes([res, ...notes])
            pushUndo({ type: "create", noteId: res.id })

            setIsCreatingAudio(false)
            setAudioProjectId("")
            setAudioTitle("")
        } catch (err) {
            console.error("Audio upload failed:", err)
            alert("Failed to save audio note.")
        } finally {
            setIsUploading(false)
        }
    }

    const startEditing = (note: Note) => {
        setEditingNote(note)
        setNewNote({
            title: note.title || "",
            content: note.content || "",
            project_id: note.project_id || "",
            tags: note.tags || []
        })
        setIsCreating(true)
    }

    const filteredNotes = notes.filter(n => {
        const q = searchQuery.toLowerCase()
        const matchesSearch = q === "" ||
            (n.title?.toLowerCase().includes(q) || n.content?.toLowerCase().includes(q))
        const matchesProject = selectedProject === "all" || n.project_id === selectedProject
        return matchesSearch && matchesProject
    })

    const getProjectName = (id: string | null) => {
        if (!id) return "Personal"
        const p = projects.find(proj => proj.id === id)
        return p?.display_name || p?.name || "Unknown Project"
    }

    const formatDate = (dateStr: string) => {
        return new Date(dateStr).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })
    }

    return (
        <div className="flex flex-col h-full min-h-0 bg-[#030712] text-white">
            <div className="flex-1 min-h-0 overflow-y-auto px-6 lg:px-10 py-6 lg:py-8 custom-scrollbar">
                <div className="max-w-6xl mx-auto h-full flex flex-col">
                    {/* Header */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 mb-8">
                        <h1 className="text-4xl font-black text-white tracking-tighter flex items-center gap-3">
                            <StickyNote size={32} className="text-cyan-500" />
                            Notes
                        </h1>

                        <div className="flex items-center gap-3">
                            {selectedIds.size > 0 ? (
                                <>
                                    <span className="text-sm text-cyan-400 font-bold">{selectedIds.size} selected</span>
                                    <button
                                        onClick={deleteSelected}
                                        className="flex items-center gap-1.5 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-xl text-red-400 text-xs font-bold transition-all"
                                    >
                                        <Trash2 size={14} /> Delete
                                    </button>
                                    <button
                                        onClick={() => setSelectedIds(new Set())}
                                        className="text-xs text-gray-500 hover:text-white transition-colors px-3 py-2"
                                    >
                                        Clear
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button
                                        onClick={() => {
                                            setEditingNote(null)
                                            setNewNote({ title: "", content: "", project_id: "", tags: [] })
                                            setIsCreating(true)
                                        }}
                                        className="flex items-center gap-2.5 px-5 py-2.5 bg-cyan-500/10 hover:bg-cyan-500/15 border border-cyan-500/20 rounded-xl transition-all group"
                                    >
                                        <div className="p-1 bg-cyan-500/10 rounded-md group-hover:scale-110 transition-transform">
                                            <Pencil size={14} className="text-cyan-400" />
                                        </div>
                                        <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Text Note</span>
                                    </button>
                                    <button
                                        onClick={() => setIsCreatingAudio(true)}
                                        className="flex items-center gap-2.5 px-5 py-2.5 bg-cyan-500/10 hover:bg-cyan-500/15 border border-cyan-500/20 rounded-xl transition-all group"
                                    >
                                        <div className="p-1 bg-cyan-500/10 rounded-md group-hover:scale-110 transition-transform">
                                            <Mic size={14} className="text-cyan-400" />
                                        </div>
                                        <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Audio</span>
                                    </button>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Filters & Search */}
                    <div className="bg-gray-900/40 border border-gray-800 p-4 rounded-2xl mb-6 flex flex-col md:flex-row gap-4 backdrop-blur-md">
                        <div className="relative flex-1">
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                            <input
                                type="text"
                                placeholder="Search notes..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full bg-gray-950/50 border border-gray-800 rounded-xl pl-12 pr-4 py-2.5 text-sm focus:outline-none focus:border-cyan-500/50 transition-all text-white"
                            />
                        </div>

                        <div className="flex items-center gap-2 bg-gray-950/50 border border-gray-800 rounded-xl px-4 py-2.5">
                            <Filter size={16} className="text-gray-500" />
                            <select
                                value={selectedProject}
                                onChange={(e) => setSelectedProject(e.target.value)}
                                className="bg-transparent text-sm text-gray-300 focus:outline-none cursor-pointer"
                            >
                                <option value="all" className="bg-gray-900 text-white">All Projects</option>
                                <option value="personal" className="bg-gray-900 text-white">Personal (No Project)</option>
                                {projects.map(p => (
                                    <option key={p.id} value={p.id} className="bg-gray-900 text-white">{p.display_name || p.name}</option>
                                ))}
                            </select>
                        </div>
                    </div>



                    {/* Notes Grid */}
                    {loading ? (
                        <div className="flex-1 min-h-[280px] flex flex-col items-center justify-center py-16 gap-4">
                            <Loader2 className="w-10 h-10 text-cyan-500 animate-spin" />
                            <p className="text-gray-500 animate-pulse italic">Retrieving notes...</p>
                        </div>
                    ) : filteredNotes.length === 0 ? (
                        <div className="flex-1 min-h-[340px] flex flex-col items-center justify-center py-10 bg-gray-900/10 border border-dashed border-gray-800/50 rounded-3xl space-y-6">
                            <div className="text-center mb-4">
                                <div className="w-16 h-16 bg-gray-800/40 rounded-full flex items-center justify-center mx-auto mb-3 opacity-50">
                                    <StickyNote size={40} className="text-gray-500" />
                                </div>
                                <p className="text-xl font-medium text-gray-400">No notes found</p>
                                <p className="text-sm text-gray-600 mt-1 italic">Start by creating your first insight.</p>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-xl px-4">
                                <button
                                    onClick={() => setIsCreating(true)}
                                    className="flex flex-col items-center gap-3 p-5 bg-cyan-500/5 hover:bg-cyan-500/10 border border-cyan-500/20 rounded-3xl transition-all group"
                                >
                                    <div className="p-3 bg-cyan-500/10 rounded-2xl group-hover:scale-110 transition-transform">
                                        <Pencil size={24} className="text-cyan-400" />
                                    </div>
                                    <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Create Text Note</span>
                                </button>
                                <button
                                    onClick={() => setIsCreatingAudio(true)}
                                    className="flex flex-col items-center gap-3 p-5 bg-red-500/5 hover:bg-red-500/10 border border-red-500/20 rounded-3xl transition-all group"
                                    title="New Audio Note"
                                >
                                    <div className="p-3 bg-red-500/10 rounded-2xl group-hover:scale-110 transition-transform">
                                        <Mic size={24} className="text-red-400" />
                                    </div>
                                    <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Audio Recording</span>
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredNotes.map(note => {
                                const isSelected = selectedIds.has(note.id)
                                return (
                                    <div
                                        key={note.id}
                                        onClick={(e) => handleNoteClick(note.id, e)}
                                        onContextMenu={(e) => handleContextMenu(note.id, e)}
                                        className={`group bg-gray-900/60 border rounded-3xl p-6 transition-all shadow-xl flex flex-col cursor-pointer select-none
                                            ${isSelected
                                                ? "border-cyan-500/60 ring-1 ring-cyan-500/30 bg-cyan-500/5"
                                                : "border-gray-800 hover:border-cyan-500/30"
                                            }`}
                                    >
                                        <div className="flex items-start justify-between mb-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1.5">
                                                    <span className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest ${note.project_id ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' : 'bg-green-500/10 text-green-400 border border-green-500/20'}`}>
                                                        {note.project_id ? "Project" : "Personal"}
                                                    </span>
                                                    {note.audio_file_id && (
                                                        <span className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest flex items-center gap-1">
                                                            <Music size={10} /> Audio
                                                        </span>
                                                    )}
                                                </div>
                                                <h3 className="font-bold text-lg text-white truncate group-hover:text-cyan-400 transition-colors">
                                                    {note.title || "Untitled Note"}
                                                </h3>
                                            </div>
                                            <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                                                <button onClick={() => startEditing(note)} className="p-2 text-gray-700 hover:text-cyan-400 transition-colors">
                                                    <Edit2 size={16} />
                                                </button>
                                                <button onClick={() => deleteNote(note.id)} className="p-2 text-gray-700 hover:text-red-500 transition-colors">
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        </div>

                                        <div className="flex-1 mb-6">
                                            <p className="text-gray-400 text-sm line-clamp-4 leading-relaxed whitespace-pre-wrap">
                                                {note.content || "Empty content..."}
                                            </p>
                                            <div className="flex flex-wrap gap-1.5 mt-3">
                                                {note.tags?.map(tag => (
                                                    <span key={tag} className="px-2 py-0.5 bg-gray-950/40 text-gray-500 rounded-md text-[10px] border border-white/5">
                                                        #{tag}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>

                                        {note.audio_file_id && token && (
                                            <div className="mb-6 p-3 bg-black/40 rounded-2xl border border-white/5" onClick={e => e.stopPropagation()}>
                                                <audio
                                                    controls
                                                    src={`${BASE_URL}/api/files/download/${note.audio_file_id}?token=${token}`}
                                                    className="w-full h-8"
                                                />
                                            </div>
                                        )}

                                        <div className="mt-auto pt-4 border-t border-white/5 flex items-center justify-between">
                                            <div className="flex flex-col">
                                                <span className="text-[10px] text-gray-600 font-bold uppercase mb-0.5">Project</span>
                                                <div className="flex items-center gap-1">
                                                    {note.project_id ? (
                                                        <button onClick={(e) => { e.stopPropagation(); onOpenProject(note.project_id!) }} className="text-xs text-gray-400 hover:text-cyan-400 flex items-center gap-1 transition-colors">
                                                            {getProjectName(note.project_id)}
                                                            <ExternalLink size={10} />
                                                        </button>
                                                    ) : (
                                                        <span className="text-xs text-gray-500">Global Space</span>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <span className="text-[10px] text-gray-600 font-bold uppercase block mb-0.5">Created</span>
                                                <span className="text-[10px] font-mono text-gray-500">{formatDate(note.created_at)}</span>
                                            </div>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* Context Menu */}
            {ctxMenu && (
                <div
                    className="fixed z-[100] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[160px] animate-in fade-in zoom-in-95 duration-100"
                    style={{ left: ctxMenu.x, top: ctxMenu.y }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <button
                        onClick={() => {
                            const note = notes.find(n => n.id === ctxMenu.noteId)
                            if (note) startEditing(note)
                            setCtxMenu(null)
                        }}
                        className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
                    >
                        <Edit2 size={14} /> Edit
                    </button>
                    <button
                        onClick={() => {
                            if (selectedIds.size > 1 && selectedIds.has(ctxMenu.noteId)) {
                                deleteSelected()
                            } else {
                                deleteNote(ctxMenu.noteId)
                            }
                            setCtxMenu(null)
                        }}
                        className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                        <Trash2 size={14} /> {selectedIds.size > 1 && selectedIds.has(ctxMenu.noteId) ? `Delete ${selectedIds.size} Notes` : "Delete"}
                    </button>
                </div>
            )}

            {/* Undo Toast */}
            {undoToast && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-gray-800 border border-gray-700 px-5 py-3 rounded-xl shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-200">
                    <Undo2 size={16} className="text-cyan-400" />
                    <span className="text-sm text-gray-200">{undoToast}</span>
                    <button
                        onClick={performUndo}
                        className="text-cyan-400 hover:text-cyan-300 text-sm font-bold ml-2 transition-colors"
                    >
                        Undo
                    </button>
                </div>
            )}

            {/* Modals */}
            {isCreating && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-gray-800 w-full max-w-xl rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
                        <div className="p-6 border-b border-gray-800 flex justify-between items-center">
                            <h2 className="text-xl font-bold text-white">{editingNote ? "Edit Note" : "New Note"}</h2>
                            <button onClick={() => { setIsCreating(false); setEditingNote(null) }} className="text-gray-500 hover:text-white transition-colors text-xl">&times;</button>
                        </div>
                        <div className="p-6 space-y-4">
                            <input
                                type="text"
                                placeholder="Title"
                                value={newNote.title}
                                onChange={(e) => setNewNote({ ...newNote, title: e.target.value })}
                                className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50"
                                autoFocus
                            />
                            <textarea
                                placeholder="Write your note..."
                                rows={6}
                                value={newNote.content}
                                onChange={(e) => setNewNote({ ...newNote, content: e.target.value })}
                                className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50 resize-none"
                            />
                            <div className="flex flex-col gap-1.5">
                                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Link to Project</label>
                                <select
                                    value={newNote.project_id}
                                    onChange={(e) => setNewNote({ ...newNote, project_id: e.target.value })}
                                    className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-gray-300 focus:outline-none focus:border-cyan-500/50"
                                >
                                    <option value="" className="bg-gray-900 text-white">None (Personal)</option>
                                    {projects.map(p => (
                                        <option key={p.id} value={p.id} className="bg-gray-900 text-white">{p.display_name || p.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Tags</label>
                                <div className="flex flex-wrap gap-2 mb-2">
                                    {newNote.tags.map(tag => (
                                        <span key={tag} className="flex items-center gap-1 px-2 py-1 bg-cyan-500/10 text-cyan-400 rounded-lg text-xs border border-cyan-500/20">
                                            {tag}
                                            <X size={12} className="cursor-pointer hover:text-white" onClick={() => setNewNote({ ...newNote, tags: newNote.tags.filter(t => t !== tag) })} />
                                        </span>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    placeholder="Add tag and press Enter..."
                                    value={tagInput}
                                    onChange={(e) => setTagInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && tagInput.trim()) {
                                            if (!newNote.tags.includes(tagInput.trim())) {
                                                setNewNote({ ...newNote, tags: [...newNote.tags, tagInput.trim()] })
                                            }
                                            setTagInput("")
                                        }
                                    }}
                                    className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50"
                                />
                            </div>
                        </div>
                        <div className="p-6 bg-gray-950/50 flex justify-end gap-3">
                            <button onClick={() => { setIsCreating(false); setEditingNote(null) }} className="px-6 py-2 rounded-xl text-gray-400 hover:text-white transition-colors">Cancel</button>
                            <button onClick={handleSave} className="bg-cyan-500 hover:bg-cyan-400 text-black px-8 py-2 rounded-xl font-bold transition-all active:scale-95">Save {editingNote ? "Changes" : "Note"}</button>
                        </div>
                    </div>
                </div>
            )}

            {isCreatingAudio && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-gray-800 w-full max-w-md rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
                        <div className="p-6 border-b border-gray-800 flex justify-between items-center">
                            <h2 className="text-xl font-bold text-white">Audio Capture</h2>
                            <button onClick={() => setIsCreatingAudio(false)} className="text-gray-500 hover:text-white transition-colors text-xl">&times;</button>
                        </div>
                        <div className="p-6 space-y-4">
                            <div className="space-y-1">
                                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Title</label>
                                <input
                                    type="text"
                                    placeholder="Audio Note Title..."
                                    value={audioTitle}
                                    onChange={(e) => setAudioTitle(e.target.value)}
                                    disabled={isUploading}
                                    className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500/50"
                                />
                            </div>
                            <div className="space-y-1">
                                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1">Associate with Project</label>
                                <select
                                    value={audioProjectId}
                                    onChange={(e) => setAudioProjectId(e.target.value)}
                                    disabled={isUploading}
                                    className="w-full bg-black/40 border border-gray-800 rounded-xl px-4 py-3 text-gray-300 focus:outline-none focus:border-cyan-500/50"
                                >
                                    <option value="" className="bg-gray-900 text-white">None (Personal)</option>
                                    {projects.map(p => (
                                        <option key={p.id} value={p.id} className="bg-gray-900 text-white">{p.display_name || p.name}</option>
                                    ))}
                                </select>
                            </div>
                            {isUploading ? (
                                <div className="flex flex-col items-center gap-3 py-8">
                                    <Loader2 size={32} className="text-cyan-500 animate-spin" />
                                    <p className="text-sm text-gray-400 italic">Saving audio note...</p>
                                </div>
                            ) : (
                                <AudioRecorder onRecordingComplete={handleAudioCapture} onCancel={() => setIsCreatingAudio(false)} />
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
