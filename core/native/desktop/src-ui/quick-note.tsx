import React, { useState, useEffect, useRef } from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./index.css";
import { apiFetch, initApiBase, getApiBase, getToken, handleRefresh, listProjects, type Project } from "./lib/api";
import { configure as configureBridge } from "../../bridge/api";

const QuickNoteApp = () => {
    const [noteContent, setNoteContent] = useState("");
    const [projects, setProjects] = useState<Project[]>([]);
    const [selectedProjectId, setSelectedProjectId] = useState("");
    const [isSaving, setIsSaving] = useState(false);
    const [isReady, setIsReady] = useState(false);
    const textRef = useRef<HTMLTextAreaElement>(null);
    const appWindowRef = useRef(getCurrentWindow());

    const focusEditor = () => {
        const el = textRef.current;
        if (!el) return;
        try {
            el.focus({ preventScroll: true });
        } catch {
            el.focus();
        }
        const pos = el.value.length;
        el.setSelectionRange(pos, pos);
    };

    // Initialize API bridge and auto-focus
    useEffect(() => {
        const init = async () => {
            await initApiBase();
            configureBridge({ getBaseUrl: getApiBase, getToken, handleRefresh });
            const projectList = await listProjects().catch(() => []);
            setProjects(projectList);
            const activeProjectId = localStorage.getItem("va_active_project_id") || "";
            if (activeProjectId && projectList.some((p) => p.id === activeProjectId)) {
                setSelectedProjectId(activeProjectId);
            }
            setIsReady(true);
        };
        init();
    }, []);

    useEffect(() => {
        // Ensure immediate typing without extra click when Quick Note opens.
        appWindowRef.current.setFocus().catch(() => {});
        const t1 = window.setTimeout(focusEditor, 0);
        const t2 = window.setTimeout(focusEditor, 80);
        const t3 = window.setTimeout(focusEditor, 180);
        return () => {
            window.clearTimeout(t1);
            window.clearTimeout(t2);
            window.clearTimeout(t3);
        };
    }, []);

    const handleClose = () => {
        appWindowRef.current.destroy();
    };

    const handleSave = async () => {
        if (!noteContent.trim()) {
            handleClose();
            return;
        }

        setIsSaving(true);
        try {
            const res = await apiFetch("/api/notes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: "",
                    content: noteContent,
                    tags: ["quick-note"],
                    project_id: selectedProjectId || undefined,
                }),
            });

            if (res.ok) {
                handleClose();
            } else {
                console.error("Failed to save quick note");
            }
        } catch (err) {
            console.error("Error saving quick note:", err);
        } finally {
            setIsSaving(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Escape") {
            handleClose();
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            handleSave();
        }
    };

    return (
        <div
            className="flex flex-col h-screen w-screen overflow-hidden"
            style={{ background: "transparent" }}
        >
            <div className="flex flex-col h-full bg-gray-900/95 backdrop-blur-md rounded-xl border border-gray-700 shadow-2xl p-4 overflow-hidden">
                {/* Draggable title bar */}
                <div
                    data-tauri-drag-region
                    className="flex justify-between items-center mb-3 cursor-move select-none"
                >
                    <span
                        data-tauri-drag-region
                        className="text-gray-400 text-xs font-bold tracking-wider"
                    >
                        QUICK NOTE
                    </span>
                    <button
                        onClick={handleClose}
                        className="hover:text-white text-gray-500 transition-colors p-1 text-sm"
                        title="Close (Esc)"
                    >
                        ✕
                    </button>
                </div>

                {/* Text area */}
                <textarea
                    ref={textRef}
                    value={noteContent}
                    onChange={(e) => setNoteContent(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type here... (Ctrl+Enter to save, Esc to close)"
                    className="flex-1 bg-black/30 text-white p-3 rounded-lg border border-gray-800 focus:outline-none focus:border-cyan-500/50 resize-none font-sans text-sm"
                    disabled={isSaving}
                />

                {/* Footer */}
                <div className="flex justify-between items-center mt-3">
                    <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-500">Project</span>
                        <select
                            value={selectedProjectId}
                            onChange={(e) => setSelectedProjectId(e.target.value)}
                            className="bg-black/30 border border-gray-800 rounded-md px-2 py-1 text-[11px] text-gray-300 focus:outline-none focus:border-cyan-500/50"
                            disabled={isSaving || !isReady}
                        >
                            <option value="" className="bg-gray-900 text-white">None</option>
                            {projects.map((p) => (
                                <option key={p.id} value={p.id} className="bg-gray-900 text-white">{p.display_name || p.name}</option>
                            ))}
                        </select>
                    </div>
                    <button
                        onClick={handleSave}
                        disabled={isSaving || !isReady || !noteContent.trim()}
                        className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-1.5 rounded-lg text-xs font-bold transition-all"
                    >
                        {isSaving ? "Saving..." : "Save"}
                    </button>
                </div>
            </div>
        </div>
    );
};

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
        <QuickNoteApp />
    </React.StrictMode>
);
