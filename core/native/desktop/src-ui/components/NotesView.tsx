import React, { useEffect, useState } from "react"
import { Search, Plus, Trash2, Edit2, Music, StickyNote, Filter, ExternalLink, Loader2, X, Pencil, Mic } from "lucide-react"
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

export default function NotesView({ onOpenProject }: { onOpenProject: (projectId: string) => void }) {
    const [notes, setNotes] = useState<Note[]>([])
    const [projects, setProjects] = useState<Project[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState("")
    const [selectedProject, setSelectedProject] = useState<string>("all")

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
            }
        } catch (err) {
            console.error("Failed to save note:", err)
        }

        setNewNote({ title: "", content: "", project_id: "", tags: [] })
        setIsCreating(false)
        setEditingNote(null)
    }

    const deleteNote = async (id: string) => {
        if (!confirm("Are you sure you want to delete this note?")) return
        try {
            await apiFetch(`/api/notes/${id}`, { method: "DELETE" })
            setNotes(notes.filter(n => n.id !== id))
        } catch (err) {
            console.error("Failed to delete note:", err)
        }
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
        <div className="flex flex-col h-full bg-[#030712] text-white">
            <div className="flex-1 overflow-y-auto px-12 py-10 custom-scrollbar">
                <div className="max-w-6xl mx-auto min-h-full">
                    {/* Header */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
                        <div>
                            <h1 className="text-4xl font-black text-white tracking-tighter mb-2 flex items-center gap-3">
                                <StickyNote size={36} className="text-cyan-500" />
                                Notes
                            </h1>
                            <p className="text-gray-500 text-sm">Capture thoughts, audio, and project insights.</p>
                        </div>

                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setIsCreating(true)}
                                className="bg-cyan-500 hover:bg-cyan-400 text-black px-6 py-2.5 rounded-xl font-bold text-sm transition-all flex items-center gap-2 shadow-lg shadow-cyan-500/20 active:scale-95"
                            >
                                <Plus size={18} /> New Note
                            </button>
                        </div>
                    </div>

                    {/* Filters & Search */}
                    <div className="bg-gray-900/40 border border-gray-800 p-4 rounded-2xl mb-8 flex flex-col md:flex-row gap-4 backdrop-blur-md">
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

                    {/* Quick Actions */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                        <button
                            onClick={() => setIsCreating(true)}
                            className="flex items-center gap-4 p-4 bg-cyan-500/5 hover:bg-cyan-500/10 border border-cyan-500/10 rounded-2xl transition-all group"
                        >
                            <div className="p-2 bg-cyan-500/10 rounded-lg group-hover:scale-110 transition-transform">
                                <Pencil size={18} className="text-cyan-400" />
                            </div>
                            <div className="text-left">
                                <span className="block text-xs font-bold text-white uppercase tracking-wider">New Text Note</span>
                                <span className="block text-[10px] text-gray-500">Quickly jot down your thoughts</span>
                            </div>
                        </button>
                        <button
                            onClick={() => setIsCreatingAudio(true)}
                            className="flex items-center gap-4 p-4 bg-cyan-500/5 hover:bg-cyan-500/10 border border-cyan-500/10 rounded-2xl transition-all group"
                            title="New Audio Note"
                        >
                            <div className="p-2 bg-cyan-500/10 rounded-lg group-hover:scale-110 transition-transform">
                                <Mic size={18} className="text-cyan-400" />
                            </div>
                            <div className="text-left">
                                <span className="block text-xs font-bold text-white uppercase tracking-wider">Audio capture</span>
                                <span className="block text-[10px] text-gray-500">Record a quick voice note</span>
                            </div>
                        </button>
                    </div>

                    {/* Notes Grid */}
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-32 gap-4">
                            <Loader2 className="w-10 h-10 text-cyan-500 animate-spin" />
                            <p className="text-gray-500 animate-pulse italic">Retrieving notes...</p>
                        </div>
                    ) : filteredNotes.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-24 bg-gray-900/10 border border-dashed border-gray-800/50 rounded-3xl space-y-8">
                            <div className="text-center mb-8">
                                <div className="w-20 h-20 bg-gray-800/40 rounded-full flex items-center justify-center mx-auto mb-4 opacity-50">
                                    <StickyNote size={40} className="text-gray-500" />
                                </div>
                                <p className="text-xl font-medium text-gray-400">No notes found</p>
                                <p className="text-sm text-gray-600 mt-1 italic">Start by creating your first insight.</p>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-md">
                                <button
                                    onClick={() => setIsCreating(true)}
                                    className="flex flex-col items-center gap-4 p-8 bg-cyan-500/5 hover:bg-cyan-500/10 border border-cyan-500/20 rounded-3xl transition-all group"
                                >
                                    <div className="p-4 bg-cyan-500/10 rounded-2xl group-hover:scale-110 transition-transform">
                                        <Pencil size={32} className="text-cyan-400" />
                                    </div>
                                    <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Create Text Note</span>
                                </button>
                                <button
                                    onClick={() => setIsCreatingAudio(true)}
                                    className="flex flex-col items-center gap-4 p-8 bg-red-500/5 hover:bg-red-500/10 border border-red-500/20 rounded-3xl transition-all group"
                                    title="New Audio Note"
                                >
                                    <div className="p-4 bg-red-500/10 rounded-2xl group-hover:scale-110 transition-transform">
                                        <Mic size={32} className="text-red-400" />
                                    </div>
                                    <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Audio Recording</span>
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredNotes.map(note => (
                                <div
                                    key={note.id}
                                    className="group bg-gray-900/60 border border-gray-800 hover:border-cyan-500/30 rounded-3xl p-6 transition-all shadow-xl flex flex-col"
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
                                        <div className="flex items-center gap-2">
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
                                        <div className="mb-6 p-3 bg-black/40 rounded-2xl border border-white/5">
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
                                                    <button onClick={() => onOpenProject(note.project_id!)} className="text-xs text-gray-400 hover:text-cyan-400 flex items-center gap-1 transition-colors">
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
                            ))}
                        </div>
                    )}
                </div>
            </div>

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
