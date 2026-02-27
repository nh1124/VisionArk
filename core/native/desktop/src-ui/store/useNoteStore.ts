import { create } from 'zustand';
import { apiFetch } from '../lib/api';

export interface Note {
    id: string;
    project_id: string | null;
    title: string | null;
    content: string | null;
    audio_file_id: string | null;
    tags: string[];
    created_at: string;
    updated_at: string;
}

interface NoteState {
    notes: Note[];
    loading: boolean;
    fetchNotes: (projectId?: string) => Promise<void>;
    addNote: (note: { title?: string; content?: string; project_id?: string; audio_file_id?: string; tags?: string[] }) => Promise<Note>;
    updateNote: (id: string, note: { title?: string; content?: string; project_id?: string; audio_file_id?: string; tags?: string[] }) => Promise<void>;
    deleteNote: (id: string) => Promise<void>;
}

export const useNoteStore = create<NoteState>((set, get) => ({
    notes: [],
    loading: false,
    fetchNotes: async (projectId) => {
        set({ loading: true });
        try {
            const url = projectId ? `/api/notes?project_id=${projectId}` : '/api/notes';
            const response = await apiFetch(url);
            if (!response.ok) throw new Error("Failed to fetch notes");
            const data = await response.json();
            set({ notes: data, loading: false });
        } catch (error) {
            console.error("Failed to fetch notes:", error);
            set({ loading: false });
        }
    },
    addNote: async (note) => {
        const response = await apiFetch('/api/notes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(note),
        });
        if (!response.ok) throw new Error("Failed to add note");
        const newNote = await response.json();
        set((state) => ({ notes: [newNote, ...state.notes] }));
        return newNote;
    },
    updateNote: async (id, note) => {
        const response = await apiFetch(`/api/notes/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(note),
        });
        if (!response.ok) throw new Error("Failed to update note");
        const updatedNote = await response.json();
        set((state) => ({
            notes: state.notes.map((n) => (n.id === id ? updatedNote : n)),
        }));
    },
    deleteNote: async (id) => {
        const response = await apiFetch(`/api/notes/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Failed to delete note");
        set((state) => ({
            notes: state.notes.filter((n) => n.id !== id),
        }));
    },
}));
