import React, { useCallback, useEffect, useRef, useState } from "react"
import { fetchHistory, sendChat, getTaskStatus, type ChatMessage as ChatMessageType } from "../lib/api"
import ChatMessage from "./ChatMessage"
import ChatInput from "./ChatInput"
import FileViewer from "./FileViewer"
import ImagePreviewModal from "./ImagePreviewModal"

import { type ProjectSidebarMode } from "../App"
import ProjectNotes from "./ProjectNotes"
import AutomationTab from "./AutomationTab"
import ActivitySidebar from "./ActivitySidebar"
import FilesSidebar from "./FilesSidebar"

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
    const [model, setModel] = useState("gemini-3.1-pro")
    const [fileViewer, setFileViewer] = useState<{ content: string; path: string; format: "markdown" | "code" | "pdf"; fileUrl?: string } | null>(null)
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

    // Keep effectiveSessionRef in sync when sessionId prop changes (e.g. user switches session)
    useEffect(() => {
        effectiveSessionRef.current = sessionId
    }, [sessionId])

    useEffect(() => {
        loadHistory()
        return () => {
            if (pollRef.current) clearInterval(pollRef.current)
            if (timerRef.current) clearInterval(timerRef.current)
        }
    }, [loadHistory])

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    const handleSend = async (content: string, files?: File[]) => {
        if ((!content.trim() && (!files || files.length === 0)) || loading) return

        // Optimistic add
        setMessages((prev) => [...prev, { role: "user", content }])
        setLoading(true)
        setStatusText("Processing your request...")

        try {
            const { task_id, session_id: usedSessionId } = await sendChat(projectId, content, sessionId, model, files)

            // Update the effective session if the backend resolved to a different one
            if (usedSessionId) {
                effectiveSessionRef.current = usedSessionId
            }

            // Add placeholder for assistant
            setMessages((prev) => [...prev, { role: "assistant", content: "" }])

            // Poll task status
            pollRef.current = setInterval(async () => {
                try {
                    const taskData = await getTaskStatus(task_id)
                    if (taskData.status === "completed") {
                        if (pollRef.current) clearInterval(pollRef.current)
                        setLoading(false)
                        setStatusText("")
                        await loadHistory()
                    } else if (taskData.status === "failed" || taskData.status === "cancelled") {
                        if (pollRef.current) clearInterval(pollRef.current)
                        setLoading(false)
                        setStatusText("")
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
                        setStatusText(taskData.status === "queued" ? "Queued..." : "Processing...")
                    }
                } catch {
                    // polling error, keep trying
                }
            }, 3000)
        } catch (e) {
            console.error("Failed to send:", e)
            setLoading(false)
            setStatusText("")
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: "❌ Failed to send message. Please try again." },
            ])
        }
    }

    return (
        <div className="flex h-full w-full overflow-hidden bg-gray-950 min-w-0">
            <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Messages area */}
                <div className="flex-1 overflow-y-auto px-6">
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
                    loading={loading}
                    statusText={statusText}
                    model={model}
                    onModelChange={setModel}
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
                                    setFileViewer({ content, path, format, fileUrl })
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
                    </div>
                </div>
            )}

            {/* File Viewer Panel */}
            {fileViewer && (
                <FileViewer
                    content={fileViewer.content}
                    filePath={fileViewer.path}
                    format={fileViewer.format}
                    projectId={projectId}
                    onClose={() => setFileViewer(null)}
                    fileUrl={fileViewer.fileUrl}
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
