import React, { useCallback, useEffect, useRef, useState } from "react"
import type { ModelGroup } from "./ChatInput"
import { fetchHistory, sendChat, getTaskStatus, cancelTask, apiJson, type ChatMessage as ChatMessageType } from "../lib/api"
import ChatMessage from "./ChatMessage"
import ChatInput from "./ChatInput"
import FileViewer from "./FileViewer"
import ImagePreviewModal from "./ImagePreviewModal"

import { type ProjectSidebarMode } from "../App"
import ProjectNotes from "./ProjectNotes"
import AutomationTab from "./AutomationTab"
import ActivitySidebar from "./ActivitySidebar"
import FilesSidebar from "./FilesSidebar"
import ProjectSettingsPanel from "./ProjectSettingsPanel"

interface Props {
    projectId: string
    sessionId: string | null
    projectName: string
    sidebarMode?: ProjectSidebarMode
    setSidebarMode?: (mode: ProjectSidebarMode) => void
}

export default function ChatView({ projectId, sessionId, projectName, sidebarMode, setSidebarMode }: Props) {
    const [messages, setMessages] = useState<ChatMessageType[]>([])
    const [loading, setLoading] = useState(false)
    const [statusText, setStatusText] = useState("")
    const [model, setModel] = useState("gemini-3-pro-preview")
    const [modelGroups, setModelGroups] = useState<ModelGroup[]>([])
    const [elapsedTime, setElapsedTime] = useState(0)
    const currentTaskIdRef = useRef<string | null>(null)
    const [fileViewer, setFileViewer] = useState<{ content: string; path: string; format: "markdown" | "code" | "pdf"; fileUrl?: string; mode: "overlay" | "inline" | "popout" } | null>(null)
    const [inlineWidth, setInlineWidth] = useState(560)
    const [previewImage, setPreviewImage] = useState<{ url: string; name: string } | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const pollRef = useRef<NodeJS.Timeout | null>(null)
    const timerRef = useRef<NodeJS.Timeout | null>(null)

    // effectiveSessionId: session confirmed by backend (may differ from prop when
    // the provided session was not found and backend fell back to default)
    const effectiveSessionRef = useRef<string | null | undefined>(sessionId)

    const loadHistory = useCallback(async () => {
        try {
            const msgs = await fetchHistory(projectId, effectiveSessionRef.current)
            setMessages(msgs)
        } catch (e) {
            console.error("Failed to load history:", e)
        }
    }, [projectId])

    // Reload history whenever session or project changes
    useEffect(() => {
        effectiveSessionRef.current = sessionId
        // Stop any in-progress polling from the previous session
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
        setLoading(false)
        setStatusText("")
        setElapsedTime(0)
        currentTaskIdRef.current = null
        setMessages([])
        loadHistory()
    }, [sessionId, loadHistory])

    // Fetch model catalog from backend
    useEffect(() => {
        apiJson<{ groups: ModelGroup[]; default_model: string }>("/api/llm/models")
            .then(data => {
                setModelGroups(data.groups)
                setModel(data.default_model)
            })
            .catch(() => { /* keep fallback */ })
    }, [])

    // Cleanup intervals on unmount only
    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current)
            if (timerRef.current) clearInterval(timerRef.current)
        }
    }, [])

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    const stopPolling = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    }

    const handleStop = async () => {
        const taskId = currentTaskIdRef.current
        stopPolling()
        setLoading(false)
        setStatusText("")
        setElapsedTime(0)
        if (taskId) {
            try { await cancelTask(taskId) } catch { /* best-effort */ }
        }
        setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role === "assistant" && !last.content) {
                return [...prev.slice(0, -1), { role: "assistant", content: "Generation stopped." }]
            }
            return prev
        })
    }

    const handleSend = async (content: string, files?: File[]) => {
        if ((!content.trim() && (!files || files.length === 0)) || loading) return

        // Optimistic add
        setMessages((prev) => [...prev, { role: "user", content }])
        setLoading(true)
        setStatusText("Processing your request...")
        setElapsedTime(0)

        try {
            const { task_id, session_id: usedSessionId } = await sendChat(projectId, content, sessionId, model, files)
            currentTaskIdRef.current = task_id

            // Update the effective session if the backend resolved to a different one
            if (usedSessionId) {
                effectiveSessionRef.current = usedSessionId
            }

            // Add placeholder for assistant
            setMessages((prev) => [...prev, { role: "assistant", content: "" }])

            // Elapsed time counter
            const startTime = Date.now()
            timerRef.current = setInterval(() => {
                setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
            }, 1000)

            // Poll task status
            pollRef.current = setInterval(async () => {
                try {
                    const taskData = await getTaskStatus(task_id)
                    if (taskData.status === "completed") {
                        stopPolling()
                        setLoading(false)
                        setStatusText("")
                        setElapsedTime(0)
                        currentTaskIdRef.current = null
                        await loadHistory()
                    } else if (taskData.status === "failed" || taskData.status === "cancelled") {
                        stopPolling()
                        setLoading(false)
                        setStatusText("")
                        setElapsedTime(0)
                        currentTaskIdRef.current = null
                        setMessages((prev) => {
                            const last = prev[prev.length - 1]
                            if (last?.role === "assistant" && !last.content) {
                                return [
                                    ...prev.slice(0, -1),
                                    { role: "assistant", content: taskData.status === "failed" ? `❌ ${taskData.result || "Task failed"}` : "Generation stopped." },
                                ]
                            }
                            return prev
                        })
                    } else {
                        // Show detailed status using phase/step if available
                        if (taskData.status === "queued") {
                            setStatusText("Queued...")
                        } else if (taskData.step) {
                            setStatusText(`Running: ${taskData.step}`)
                        } else if (taskData.phase) {
                            setStatusText(`${taskData.phase}...`)
                        } else {
                            setStatusText("Processing...")
                        }
                    }
                } catch {
                    // polling error, keep trying
                }
            }, 1000)
        } catch (e) {
            console.error("Failed to send:", e)
            stopPolling()
            setLoading(false)
            setStatusText("")
            setElapsedTime(0)
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: "❌ Failed to send message. Please try again." },
            ])
        }
    }

    return (
        <div className="flex h-full w-full overflow-hidden bg-gray-950 min-w-0">
            {/* ── Chat column (shrinks when inline panel is open) ── */}
            <div className={`flex flex-col h-full overflow-hidden ${fileViewer?.mode === "inline" ? "flex-1 min-w-0" : "flex-1"}`}>
                {/* Messages area */}
                <div className="flex-1 overflow-y-auto overflow-x-hidden px-6">
                    <div className="max-w-3xl mx-auto py-6">
                        {messages.length === 0 && !loading ? (
                            <div className="flex flex-col items-center justify-center h-full py-20">
                                <div className="w-16 h-16 bg-cyan-500/10 rounded-2xl flex items-center justify-center mb-4">
                                    <span className="text-2xl">💬</span>
                                </div>
                                <h2 className="text-lg font-semibold text-gray-300 mb-1">{projectName}</h2>
                                <p className="text-sm text-gray-600">Start a conversation with your AI assistant</p>
                            </div>
                        ) : (
                            messages.map((msg, i) => {
                                // Hide the empty placeholder message when loading, because the loading indicator draws its own avatar
                                if (loading && i === messages.length - 1 && msg.role === "assistant" && !msg.content) return null;
                                return <ChatMessage key={i} message={msg} projectId={projectId} />
                            })
                        )}

                        {/* Loading indicator */}
                        {loading && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.content && (
                            <div className="flex gap-3 py-4">
                                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <div className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                </div>
                                <div className="flex-1">
                                    <div className="text-xs font-semibold text-gray-500 mb-1">Assistant</div>
                                    <div className="flex gap-1 mt-2">
                                        <span className="w-2 h-2 bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                                        <span className="w-2 h-2 bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                                        <span className="w-2 h-2 bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                                    </div>
                                </div>
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {/* Chat Input */}
                <ChatInput
                    onSend={handleSend}
                    onStop={handleStop}
                    loading={loading}
                    statusText={elapsedTime > 0 ? `${statusText} (${elapsedTime}s)` : statusText}
                    model={model}
                    onModelChange={setModel}
                    modelGroups={modelGroups}
                />
            </div>

            {/* Sidebar Pane (Right side) */}
            {sidebarMode && (
                <div className="w-80 h-full border-l border-gray-800 bg-gray-900/50 backdrop-blur-xl relative shadow-2xl animate-in slide-in-from-right duration-300 flex flex-col p-4">
                    {/* Header */}
                    <div className="flex justify-between items-center mb-4">
                        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">
                            {sidebarMode === "files" ? "Files & Artifacts"
                                : sidebarMode === "notes" ? "Project Notes"
                                    : sidebarMode === "activity" ? "Project Activity"
                                        : sidebarMode === "settings" ? "Project Settings"
                                            : "Project Automation"}
                        </h2>
                        {setSidebarMode && (
                            <button
                                onClick={() => setSidebarMode(null)}
                                className="text-gray-500 hover:text-white transition-colors"
                            >
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <line x1="18" y1="6" x2="6" y2="18"></line>
                                    <line x1="6" y1="6" x2="18" y2="18"></line>
                                </svg>
                            </button>
                        )}
                    </div>

                    {/* Content area */}
                    <div className="flex-1 overflow-hidden min-h-0">
                        {sidebarMode === "files" && (
                            <FilesSidebar
                                nodeType="project"
                                nodeName={projectId}
                                onOpenFile={(content, path, format, fileUrl) => {
                                    setFileViewer(prev => ({ content, path, format, fileUrl, mode: prev?.mode || "overlay" }))
                                }}
                                onPreviewImage={(url, name) => {
                                    setPreviewImage({ url, name })
                                }}
                            />
                        )}
                        {sidebarMode === "notes" && (
                            <ProjectNotes projectId={projectId} />
                        )}
                        {sidebarMode === "activity" && (
                            <ActivitySidebar projectId={projectId} />
                        )}
                        {sidebarMode === "automation" && (
                            <AutomationTab projectId={projectId} onScheduleClick={() => console.log('Schedule clicked')} />
                        )}
                        {sidebarMode === "settings" && (
                            <ProjectSettingsPanel projectId={projectId} />
                        )}
                    </div>
                </div>
            )}

            {/* ── Inline FileViewer — rendered as flex sibling so chat shrinks ── */}
            {fileViewer && fileViewer.mode === "inline" && (
                <FileViewer
                    content={fileViewer.content}
                    filePath={fileViewer.path}
                    format={fileViewer.format}
                    projectId={projectId}
                    onClose={() => setFileViewer(null)}
                    fileUrl={fileViewer.fileUrl}
                    initialMode="inline"
                    inlineWidth={inlineWidth}
                    onInlineWidthChange={setInlineWidth}
                    onModeChange={(m) => setFileViewer(fv => fv ? { ...fv, mode: m } : null)}
                />
            )}

            {/* ── Overlay / Popout FileViewer (fixed-positioned, rendered outside flex flow) ── */}
            {fileViewer && fileViewer.mode !== "inline" && (
                <FileViewer
                    content={fileViewer.content}
                    filePath={fileViewer.path}
                    format={fileViewer.format}
                    projectId={projectId}
                    onClose={() => setFileViewer(null)}
                    fileUrl={fileViewer.fileUrl}
                    initialMode={fileViewer.mode}
                    inlineWidth={inlineWidth}
                    onInlineWidthChange={setInlineWidth}
                    onModeChange={(m) => setFileViewer(fv => fv ? { ...fv, mode: m } : null)}
                />
            )}

            {/* Image Preview Modal */}
            {previewImage && (
                <ImagePreviewModal
                    url={previewImage.url}
                    name={previewImage.name}
                    onClose={() => setPreviewImage(null)}
                />
            )}
        </div>
    )
}
