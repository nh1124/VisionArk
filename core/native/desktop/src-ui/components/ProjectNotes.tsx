import { useEffect, useState } from "react";
import { useNoteStore, Note } from "../store/useNoteStore";
import { Plus, Trash2, StickyNote, Music, Loader2, Search, X, Mic, Pencil, Edit2 } from "lucide-react";
import { format } from "date-fns";
import { apiFetch, getFileToken } from "../lib/api";
import AudioRecorder from "./AudioRecorder";

interface ProjectNotesProps {
    projectId: string;
}

export default function ProjectNotes({ projectId }: ProjectNotesProps) {
    const { notes, loading, fetchNotes, addNote, updateNote, deleteNote } = useNoteStore();
    const [noteType, setNoteType] = useState<"text" | "audio" | null>(null);
    const [newNote, setNewNote] = useState({ title: "", content: "" });
    const [audioTitle, setAudioTitle] = useState(""); // custom title for new audio note
    const [searchQuery, setSearchQuery] = useState("");
    const [token, setToken] = useState("");
    const [isUploading, setIsUploading] = useState(false);
    const [tagInput, setTagInput] = useState("");
    const [tempTags, setTempTags] = useState<string[]>([]);
    const [editingNote, setEditingNote] = useState<Note | null>(null);

    useEffect(() => {
        fetchNotes(projectId);
        getFileToken().then(setToken);
    }, [projectId]);

    const handleSaveNote = async () => {
        if (!newNote.title && !newNote.content) return;

        if (editingNote) {
            await updateNote(editingNote.id, {
                ...newNote,
                tags: tempTags
            });
        } else {
            await addNote({
                ...newNote,
                project_id: projectId,
                tags: tempTags
            });
        }

        setNewNote({ title: "", content: "" });
        setTempTags([]);
        setEditingNote(null);
        setNoteType(null);
    };

    const startEditing = (note: Note) => {
        setEditingNote(note);
        setNewNote({ title: note.title || "", content: note.content || "" });
        setTempTags(note.tags || []);
        setNoteType("text");
    };

    const handleAudioCapture = async (blob: Blob) => {
        setIsUploading(true);
        try {
            const formData = new FormData();
            const filename = `recording_${format(new Date(), "yyyyMMdd_HHmmss")}.webm`;
            const file = new File([blob], filename, { type: "audio/webm" });
            formData.append("file", file);

            const uploadRes = await apiFetch(`/api/files/project/${projectId}/notes/upload`, {
                method: "POST",
                body: formData
            });

            if (!uploadRes.ok) throw new Error("Upload failed");
            const fileData = await uploadRes.json();

            // Use provided title or fallback to timestamp
            const title = audioTitle.trim() || `Audio Note - ${format(new Date(), "MMM d, HH:mm")}`;

            await addNote({
                title,
                project_id: projectId,
                audio_file_id: fileData.id,
                content: "",
                tags: tempTags
            });
            setTempTags([]);
            setAudioTitle("");
            setNoteType(null);
        } catch (err) {
            console.error("Audio upload failed:", err);
            alert("Failed to save audio note.");
        } finally {
            setIsUploading(false);
        }
    };

    const resetAudioCreate = () => {
        setNoteType(null);
        setAudioTitle("");
    };

    const filteredNotes = notes.filter(n =>
        n.project_id === projectId &&
        (n.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            n.content?.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    return (
        <div className="h-full flex flex-col bg-gray-900/20">
            <div className="p-4 border-b border-gray-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <StickyNote size={18} className="text-cyan-400" />
                    <h2 className="font-bold text-sm text-white uppercase tracking-wider">Project Notes</h2>
                </div>
                {!noteType && (
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setNoteType("text")}
                            className="p-1.5 text-gray-400 hover:text-cyan-400 rounded-lg transition-all"
                            title="New Text Note"
                        >
                            <Pencil size={16} />
                        </button>
                        <button
                            onClick={() => setNoteType("audio")}
                            className="p-1.5 text-gray-400 hover:text-red-400 rounded-lg transition-all"
                            title="New Audio Note"
                        >
                            <Mic size={16} />
                        </button>
                    </div>
                )}
            </div>

            <div className="p-3">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" size={14} />
                    <input
                        type="text"
                        placeholder="Search notes..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-black/40 border border-gray-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-cyan-500/30"
                    />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-4">
                {/* Persistent Quick Start Buttons */}
                {!noteType && (
                    <div className="grid grid-cols-2 gap-2 mb-2">
                        <button
                            onClick={() => setNoteType("text")}
                            className="flex items-center justify-center gap-2 p-3 bg-cyan-500/5 hover:bg-cyan-500/10 border border-cyan-500/10 rounded-xl transition-all group"
                        >
                            <Pencil size={14} className="text-cyan-400 group-hover:scale-110 transition-transform" />
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Text</span>
                        </button>
                        <button
                            onClick={() => setNoteType("audio")}
                            className="flex items-center justify-center gap-2 p-3 bg-red-500/5 hover:bg-red-500/10 border border-red-500/10 rounded-xl transition-all group"
                        >
                            <Mic size={14} className="text-red-400 group-hover:scale-110 transition-transform" />
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Audio</span>
                        </button>
                    </div>
                )}
                {noteType === "text" && (
                    <div className="bg-gray-800/40 border border-cyan-500/30 rounded-xl p-3 space-y-3 animate-in slide-in-from-top-2 duration-200 shadow-lg">
                        <input
                            type="text"
                            placeholder="Title..."
                            value={newNote.title}
                            onChange={(e) => setNewNote({ ...newNote, title: e.target.value })}
                            className="w-full bg-transparent text-sm font-bold text-white focus:outline-none"
                            autoFocus
                        />
                        <textarea
                            placeholder="Write something..."
                            value={newNote.content}
                            onChange={(e) => setNewNote({ ...newNote, content: e.target.value })}
                            className="w-full bg-transparent text-xs text-gray-300 focus:outline-none resize-none min-h-[100px]"
                        />

                        {/* Tags UI */}
                        <div className="space-y-2">
                            <div className="flex flex-wrap gap-1">
                                {tempTags.map(tag => (
                                    <span key={tag} className="flex items-center gap-1 px-1.5 py-0.5 bg-cyan-500/10 text-cyan-400 rounded text-[10px] border border-cyan-500/20">
                                        {tag}
                                        <X size={8} className="cursor-pointer hover:text-white" onClick={() => setTempTags(tempTags.filter(t => t !== tag))} />
                                    </span>
                                ))}
                            </div>
                            <input
                                type="text"
                                placeholder="Add tag + Enter"
                                value={tagInput}
                                onChange={(e) => setTagInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && tagInput.trim()) {
                                        if (!tempTags.includes(tagInput.trim())) {
                                            setTempTags([...tempTags, tagInput.trim()]);
                                        }
                                        setTagInput("");
                                    }
                                }}
                                className="w-full bg-black/20 border border-gray-700/50 rounded px-2 py-1 text-[10px] text-gray-400 focus:outline-none focus:border-cyan-500/30"
                            />
                        </div>

                        <div className="flex justify-end gap-2 pt-2 border-t border-gray-700/50">
                            <button onClick={() => { setNoteType(null); setEditingNote(null); setTempTags([]); setNewNote({ title: "", content: "" }); }} className="text-[10px] text-gray-500 hover:text-white uppercase font-bold">Cancel</button>
                            <button onClick={handleSaveNote} className="text-[10px] text-cyan-400 hover:text-cyan-300 uppercase font-bold">
                                {editingNote ? "Update" : "Save"}
                            </button>
                        </div>
                    </div>
                )}

                {noteType === "audio" && (
                    <div className="animate-in slide-in-from-top-2 duration-200 space-y-2">
                        {/* Title input for new audio note */}
                        <input
                            type="text"
                            placeholder={`Audio Note - ${format(new Date(), "MMM d, HH:mm")}`}
                            value={audioTitle}
                            onChange={(e) => setAudioTitle(e.target.value)}
                            disabled={isUploading}
                            className="w-full bg-black/40 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/30"
                        />
                        {isUploading ? (
                            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 flex flex-col items-center gap-3">
                                <Loader2 size={24} className="text-cyan-500 animate-spin" />
                                <p className="text-xs text-gray-500 italic">Uploading audio...</p>
                            </div>
                        ) : (
                            <AudioRecorder
                                onRecordingComplete={handleAudioCapture}
                                onCancel={resetAudioCreate}
                            />
                        )}
                    </div>
                )}

                {loading ? (
                    <div className="flex items-center justify-center py-10">
                        <Loader2 size={24} className="text-gray-700 animate-spin" />
                    </div>
                ) : filteredNotes.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center opacity-40">
                        <StickyNote size={24} className="text-gray-600 mb-2" />
                        <p className="text-[10px] text-gray-600 italic uppercase tracking-widest font-bold">Empty</p>
                    </div>
                ) : (
                    filteredNotes.map(note => (
                        <div key={note.id} className="group bg-gray-800/20 border border-gray-800 hover:border-gray-700 rounded-xl p-3 transition-all">
                            <div className="flex items-start justify-between mb-2">
                                <h3 className="font-bold text-xs text-gray-200 truncate group-hover:text-cyan-400 transition-colors">
                                    {note.title || "Untitled"}
                                </h3>
                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                                    <button onClick={() => startEditing(note)} className="p-1 text-gray-600 hover:text-cyan-400 transition-all">
                                        <Edit2 size={12} />
                                    </button>
                                    <button onClick={() => deleteNote(note.id)} className="p-1 text-gray-600 hover:text-red-500 transition-all">
                                        <Trash2 size={12} />
                                    </button>
                                </div>
                            </div>
                            <p className="text-[11px] text-gray-500 line-clamp-3 mb-3 leading-relaxed">
                                {note.content}
                            </p>

                            {note.audio_file_id && token && (
                                <div className="mb-3 p-1.5 bg-black/40 rounded-lg border border-white/5">
                                    <audio
                                        controls
                                        src={`/api/files/download/${note.audio_file_id}?token=${token}`}
                                        className="w-full h-6"
                                    />
                                </div>
                            )}

                            <div className="flex flex-wrap gap-1 mb-3">
                                {note.tags?.map(tag => (
                                    <span key={tag} className="px-1.5 py-0.5 bg-gray-900/40 text-gray-500 rounded text-[9px] border border-white/5">
                                        #{tag}
                                    </span>
                                ))}
                            </div>

                            <div className="flex items-center justify-between text-[9px] text-gray-600 font-mono">
                                <span>{format(new Date(note.created_at), "MMM d, HH:mm")}</span>
                                <div className="flex items-center gap-2">
                                    {note.audio_file_id && <Music size={10} className="text-cyan-600" />}
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
