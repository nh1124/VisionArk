"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { MessageSquare, Plus, MoreHorizontal } from "lucide-react";

export interface Session {
    id: string;
    project_id: string;
    title: string | null;
    is_default: boolean;
    is_archived: boolean;
    last_message_at: string | null;
    created_at: string;
    updated_at: string;
}

interface SessionListProps {
    projectId: string;
    activeSessionId: string | null;
    onSessionSelect: (sessionId: string) => void;
    onSessionCreated?: (session: Session) => void;
}

export default function SessionList({
    projectId,
    activeSessionId,
    onSessionSelect,
    onSessionCreated,
}: SessionListProps) {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [loading, setLoading] = useState(true);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState("");
    const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
    const editInputRef = useRef<HTMLInputElement>(null);

    const fetchSessions = useCallback(async () => {
        try {
            const res = await apiFetch(`/api/agents/project/${projectId}/sessions`);
            const data = await res.json();
            setSessions(data.sessions || []);
        } catch (e) {
            console.error("Failed to fetch sessions:", e);
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchSessions();
    }, [fetchSessions]);

    // Close menu on outside click
    useEffect(() => {
        if (!menuOpenId) return;
        const handler = () => setMenuOpenId(null);
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, [menuOpenId]);

    const createSession = async () => {
        try {
            const res = await apiFetch(`/api/agents/project/${projectId}/sessions`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: "New Chat" }),
            });
            const newSession: Session = await res.json();
            setSessions((prev) => [newSession, ...prev]);
            onSessionCreated?.(newSession);
            onSessionSelect(newSession.id);
        } catch (e) {
            console.error("Failed to create session:", e);
        }
    };

    const updateSession = async (
        sessionId: string,
        updates: { title?: string; is_archived?: boolean }
    ) => {
        try {
            const res = await apiFetch(`/api/agents/sessions/${sessionId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(updates),
            });
            const updated: Session = await res.json();
            if (updates.is_archived) {
                setSessions((prev) => prev.filter((s) => s.id !== sessionId));
            } else {
                setSessions((prev) =>
                    prev.map((s) => (s.id === sessionId ? updated : s))
                );
            }
        } catch (e) {
            console.error("Failed to update session:", e);
        }
    };

    const startEdit = (session: Session) => {
        setEditingId(session.id);
        setEditTitle(session.title || "");
        setMenuOpenId(null);
        setTimeout(() => editInputRef.current?.focus(), 50);
    };

    const submitEdit = async (sessionId: string) => {
        if (editTitle.trim()) {
            await updateSession(sessionId, { title: editTitle.trim() });
        }
        setEditingId(null);
    };

    const formatTime = (dateStr: string | null): string => {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        const now = new Date();
        const diff = now.getTime() - d.getTime();
        if (diff < 86_400_000) {
            return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
    };

    if (loading) {
        return (
            <div className="text-xs text-gray-500 px-3 py-2">Loading chats...</div>
        );
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* New Chat button */}
            <button
                onClick={createSession}
                className="flex items-center gap-2 px-3 py-2 mb-2 text-sm text-cyan-400 hover:bg-cyan-500/10 rounded-lg transition-colors w-full"
            >
                <Plus size={14} />
                New Chat
            </button>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto flex flex-col gap-0.5 pr-0.5">
                {sessions.length === 0 && (
                    <p className="text-xs text-gray-500 px-3 py-2">No chats yet</p>
                )}
                {sessions.map((session) => (
                    <div
                        key={session.id}
                        className={`group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                            activeSessionId === session.id
                                ? "bg-cyan-500/15 text-white"
                                : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                        }`}
                        onClick={() => onSessionSelect(session.id)}
                    >
                        <MessageSquare
                            size={13}
                            className="flex-shrink-0 opacity-50"
                        />

                        <div className="flex-1 min-w-0">
                            {editingId === session.id ? (
                                <input
                                    ref={editInputRef}
                                    value={editTitle}
                                    onChange={(e) => setEditTitle(e.target.value)}
                                    onBlur={() => submitEdit(session.id)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") submitEdit(session.id);
                                        if (e.key === "Escape") setEditingId(null);
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                    className="bg-gray-800 text-white text-xs w-full px-1 py-0.5 rounded outline-none border border-cyan-500/50"
                                />
                            ) : (
                                <p className="text-xs truncate leading-snug">
                                    {session.title || "Untitled Chat"}
                                    {session.is_default && (
                                        <span className="ml-1 text-[10px] text-cyan-500/60">
                                            ·default
                                        </span>
                                    )}
                                </p>
                            )}
                            {session.last_message_at && (
                                <p className="text-[10px] text-gray-600">
                                    {formatTime(session.last_message_at)}
                                </p>
                            )}
                        </div>

                        {/* Kebab menu button */}
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpenId(
                                    menuOpenId === session.id ? null : session.id
                                );
                            }}
                            className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-gray-700 rounded transition-all flex-shrink-0"
                        >
                            <MoreHorizontal size={12} />
                        </button>

                        {/* Dropdown menu */}
                        {menuOpenId === session.id && (
                            <div
                                className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 w-36 py-1 text-xs"
                                onClick={(e) => e.stopPropagation()}
                            >
                                <button
                                    onClick={() => startEdit(session)}
                                    className="w-full text-left px-3 py-1.5 hover:bg-gray-700 text-gray-300"
                                >
                                    Rename
                                </button>
                                <button
                                    onClick={() => {
                                        updateSession(session.id, {
                                            is_archived: true,
                                        });
                                        setMenuOpenId(null);
                                    }}
                                    className="w-full text-left px-3 py-1.5 hover:bg-gray-700 text-red-400"
                                >
                                    Archive
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
