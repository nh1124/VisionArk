import React, { useCallback, useEffect, useRef, useState } from "react"
import type { ModelGroup } from "./ChatInput"
import { fetchHistory, sendChat, getTaskStatus, cancelTask, apiJson, truncateProjectMessages, copyProjectSession, executeCommand, type ChatMessage as ChatMessageType } from "../lib/api"
import ChatMessage, { type MessageVote } from "./ChatMessage"
import ChatInput from "./ChatInput"
import FileViewer from "./FileViewer"
import ImagePreviewModal from "./ImagePreviewModal"

import { type ProjectSidebarMode } from "../App"
import ProjectNotes from "./ProjectNotes"
import AutomationTab from "./AutomationTab"
import FilesSidebar from "./FilesSidebar"
import ProjectSettingsPanel from "./ProjectSettingsPanel"

interface Props {
    projectId: string
    sessionId: string | null
    projectName: string
    sidebarMode?: ProjectSidebarMode
    setSidebarMode?: (mode: ProjectSidebarMode) => void
    onSessionChange?: (sessionId: string | null) => void
}

interface RealtimeTaskState {
    taskId: string
    message: string
    statusText: string
}

interface PendingLocalSend {
    content: string
    createdAt: number
}

const LOCAL_SEND_DEDUP_WINDOW_MS = 15_000

interface CachedSessionState {
    pendingUserByTaskId: Map<string, string>
    realtimeByTaskId: Map<string, RealtimeTaskState>
}

const sessionRuntimeCache = new Map<string, CachedSessionState>()

function sessionKey(projectId: string, sessionId?: string | null) {
    return `${projectId}::${sessionId || "default"}`
}

function getSessionCache(projectId: string, sessionId?: string | null): CachedSessionState {
    const key = sessionKey(projectId, sessionId)
    let state = sessionRuntimeCache.get(key)
    if (!state) {
        state = {
            pendingUserByTaskId: new Map<string, string>(),
            realtimeByTaskId: new Map<string, RealtimeTaskState>(),
        }
        sessionRuntimeCache.set(key, state)
    }
    return state
}

function upsertSessionCacheTask(projectId: string, sessionId: string | null | undefined, taskId: string, message: string, statusText: string) {
    if (!taskId) return
    const state = getSessionCache(projectId, sessionId)
    if (message) state.pendingUserByTaskId.set(taskId, message)
    state.realtimeByTaskId.set(taskId, { taskId, message: message || state.pendingUserByTaskId.get(taskId) || "Scheduled message", statusText })
}

function clearSessionCacheTask(projectId: string, sessionId: string | null | undefined, taskId: string, dropPendingUser = false) {
    if (!taskId) return
    const state = getSessionCache(projectId, sessionId)
    if (dropPendingUser) state.pendingUserByTaskId.delete(taskId)
    state.realtimeByTaskId.delete(taskId)
}

const normalizeMessageContent = (content: string): string =>
    (content || "").trim().replace(/\s+/g, " ")

export default function ChatView({ projectId, sessionId, projectName, sidebarMode, setSidebarMode, onSessionChange }: Props) {
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
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const isInitialLoad = useRef(true)
    const injectedTaskIdsRef = useRef<Set<string>>(new Set())
    const pendingLocalSendsRef = useRef<PendingLocalSend[]>([])
    const [realtimeTasks, setRealtimeTasks] = useState<RealtimeTaskState[]>([])
    const [messageVotes, setMessageVotes] = useState<Record<number, MessageVote>>({})
    const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)
    const [editingMessageText, setEditingMessageText] = useState("")
    const prevProjectIdRef = useRef<string>(projectId)

    // effectiveSessionId: session confirmed by backend (may differ from prop when
    // the provided session was not found and backend fell back to default)
    const effectiveSessionRef = useRef<string | null | undefined>(sessionId)

    const loadHistory = useCallback(async () => {
        try {
            const msgs = await fetchHistory(projectId, effectiveSessionRef.current)
            const state = getSessionCache(projectId, effectiveSessionRef.current)
            const persistedUserTexts = new Set(
                msgs
                    .filter((m) => m.role === "user")
                    .map((m) => normalizeMessageContent(m.content || ""))
                    .filter(Boolean)
            )

            const injected = Array.from(state.pendingUserByTaskId.entries())
                .filter(([, content]) => {
                    const normalized = normalizeMessageContent(content || "")
                    return !normalized || !persistedUserTexts.has(normalized)
                })
                .map(([taskId, content]) => ({
                    role: "user" as const,
                    content: content || "Scheduled message",
                    meta_payload: { transient: true, realtime_task_id: taskId },
                }))

            // Drop pending cache entries once their user message is confirmed in DB.
            for (const [taskId, content] of state.pendingUserByTaskId.entries()) {
                const normalized = normalizeMessageContent(content || "")
                if (normalized && persistedUserTexts.has(normalized)) {
                    state.pendingUserByTaskId.delete(taskId)
                }
            }
            setMessages([...msgs, ...injected])
            setRealtimeTasks(Array.from(state.realtimeByTaskId.values()))
        } catch (e) {
            console.error("Failed to load history:", e)
        }
    }, [projectId])

    const upsertRealtimeTask = useCallback((taskId: string, message: string, phase: string) => {
        setRealtimeTasks((prev) => {
            const existing = prev.find((t) => t.taskId === taskId)
            if (existing) {
                return prev.map((t) => (t.taskId === taskId ? { ...t, statusText: phase, message: t.message || message } : t))
            }
            return [...prev, { taskId, message: message || "Scheduled message", statusText: phase }]
        })
    }, [])

    // Reload history whenever session or project changes
    useEffect(() => {
        const projectChanged = prevProjectIdRef.current !== projectId
        prevProjectIdRef.current = projectId
        isInitialLoad.current = true
        effectiveSessionRef.current = sessionId
        injectedTaskIdsRef.current.clear()
        setRealtimeTasks([])
        // Stop any in-progress polling from the previous session
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
        setLoading(false)
        setStatusText("")
        setElapsedTime(0)
        currentTaskIdRef.current = null
        if (projectChanged) {
            setMessages([])
        }
        setEditingMessageIndex(null)
        setEditingMessageText("")
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
        if (messages.length > 0 && isInitialLoad.current) {
            messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
            isInitialLoad.current = false;
        } else if (!isInitialLoad.current) {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages])

    useEffect(() => {
        const onRealtime = (evt: Event) => {
            const detail = (evt as CustomEvent<any>).detail || {}
            const sameProject = !detail.project_id || detail.project_id === projectId
            if (!sameProject) {
                return
            }
            const eventSessionId = detail.session_id ? String(detail.session_id) : (effectiveSessionRef.current ?? null)
            const sameSession =
                !detail.session_id ||
                !effectiveSessionRef.current ||
                detail.session_id === effectiveSessionRef.current

            if (detail.task_type === "user_message" && detail.task_id) {
                const taskId = String(detail.task_id)
                const status = String(detail.status || "").toLowerCase()
                const msg = String(detail.message || "")
                const normalizedMsg = normalizeMessageContent(msg)
                const step = detail.step ? ` - ${detail.step}` : ""
                const phase = detail.phase ? `${detail.phase}${step}` : (status || "processing")

                if (normalizedMsg) {
                    const now = Date.now()
                    pendingLocalSendsRef.current = pendingLocalSendsRef.current.filter((s) => now - s.createdAt <= LOCAL_SEND_DEDUP_WINDOW_MS)
                }

                if (status === "queued" || status === "processing") {
                    upsertSessionCacheTask(projectId, eventSessionId, taskId, msg, phase)
                    const pendingIdx = normalizedMsg
                        ? pendingLocalSendsRef.current.findIndex((s) => normalizeMessageContent(s.content) === normalizedMsg)
                        : -1
                    const isCurrentTask = !!currentTaskIdRef.current && taskId === currentTaskIdRef.current
                    if (sameSession) upsertRealtimeTask(taskId, msg, phase)
                    if (pendingIdx >= 0) {
                        pendingLocalSendsRef.current.splice(pendingIdx, 1)
                        if (!currentTaskIdRef.current) {
                            currentTaskIdRef.current = taskId
                        }
                    }
                    if (sameSession && !isCurrentTask && pendingIdx < 0 && !injectedTaskIdsRef.current.has(taskId)) {
                        const normalizedIncoming = normalizeMessageContent(msg || "Scheduled message")
                        setMessages((prev) => {
                            const alreadyExists = prev.some((m) => {
                                if (m.role !== "user") return false
                                if (m.meta_payload?.realtime_task_id === taskId) return true
                                const normalizedExisting = normalizeMessageContent(m.content || "")
                                return normalizedExisting && normalizedExisting === normalizedIncoming
                            })
                            if (alreadyExists) {
                                injectedTaskIdsRef.current.add(taskId)
                                return prev
                            }
                            injectedTaskIdsRef.current.add(taskId)
                            return [
                                ...prev,
                                {
                                    role: "user",
                                    content: msg || "Scheduled message",
                                    meta_payload: { transient: true, realtime_task_id: taskId },
                                },
                            ]
                        })
                    }
                    return
                }

                if (status === "completed" || status === "failed" || status === "cancelled") {
                    clearSessionCacheTask(projectId, eventSessionId, taskId, false)
                    if (sameSession) {
                        setRealtimeTasks((prev) => prev.filter((t) => t.taskId !== taskId))
                        loadHistory()
                    }
                }
                return
            }

            if (sameSession && !loading) {
                loadHistory()
            }
        }
        window.addEventListener("va-realtime-job", onRealtime as EventListener)
        return () => window.removeEventListener("va-realtime-job", onRealtime as EventListener)
    }, [loadHistory, loading, upsertRealtimeTask])

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
            clearSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, taskId, false)
            setRealtimeTasks((prev) => prev.filter((t) => t.taskId !== taskId))
            try { await cancelTask(taskId) } catch { /* best-effort */ }
        }
        currentTaskIdRef.current = null
    }

    const handleDelete = useCallback(async (index: number) => {
        if (loading) return
        try {
            await truncateProjectMessages(projectId, index, effectiveSessionRef.current ?? null)
            setMessages((prev) => prev.slice(0, index))
            if (editingMessageIndex !== null && editingMessageIndex >= index) {
                setEditingMessageIndex(null)
                setEditingMessageText("")
            }
            setMessageVotes((prev) => {
                const next: Record<number, MessageVote> = {}
                Object.entries(prev).forEach(([k, v]) => {
                    const idx = Number(k)
                    if (idx < index) next[idx] = v
                })
                return next
            })
        } catch (e) {
            console.error("Failed to delete messages:", e)
            alert("Failed to delete messages.")
        }
    }, [loading, projectId, editingMessageIndex])

    const handleEdit = useCallback(async (index: number) => {
        if (loading) return
        const msg = messages[index]
        if (!msg || msg.role !== "user") return
        setEditingMessageIndex(index)
        setEditingMessageText(msg.content || "")
    }, [loading, messages])

    const handleSubmitEditedMessage = useCallback(async () => {
        if (editingMessageIndex === null || loading) return
        const nextContent = editingMessageText.trim()
        if (!nextContent) return

        try {
            await truncateProjectMessages(projectId, editingMessageIndex, effectiveSessionRef.current ?? null)
            setMessages((prev) => prev.slice(0, editingMessageIndex))
            setMessageVotes((prev) => {
                const next: Record<number, MessageVote> = {}
                Object.entries(prev).forEach(([k, v]) => {
                    const idx = Number(k)
                    if (idx < editingMessageIndex) next[idx] = v
                })
                return next
            })
            setEditingMessageIndex(null)
            setEditingMessageText("")
            await handleSend(nextContent)
        } catch (e) {
            console.error("Failed to submit edited message:", e)
            alert("Failed to update this message.")
        }
    }, [editingMessageIndex, editingMessageText, loading, projectId])

    const handleRegenerate = useCallback(async (assistantIndex: number) => {
        if (loading) return
        let userMsgIndex = -1
        for (let i = assistantIndex - 1; i >= 0; i--) {
            if (messages[i].role === "user") {
                userMsgIndex = i
                break
            }
        }
        if (userMsgIndex === -1) return

        const userMsg = messages[userMsgIndex]
        try {
            await truncateProjectMessages(projectId, userMsgIndex + 1, effectiveSessionRef.current ?? null)
            setMessages((prev) => prev.slice(0, userMsgIndex + 1))
            await handleSend(userMsg.content)
        } catch (e) {
            console.error("Failed to regenerate:", e)
            alert("Failed to regenerate this response.")
        }
    }, [loading, messages, projectId])

    const handleBranch = useCallback(async (index: number) => {
        if (loading) return
        try {
            const result = await copyProjectSession(projectId, index, effectiveSessionRef.current ?? null)
            if (result.session?.id) {
                effectiveSessionRef.current = result.session.id
                onSessionChange?.(result.session.id)
                localStorage.setItem(`va_last_session_${projectId}`, result.session.id)
                window.dispatchEvent(new CustomEvent("va-sessions-updated", {
                    detail: {
                        project_id: projectId,
                        session_id: result.session.id,
                    },
                }))
                setMessages([])
                setRealtimeTasks([])
                setEditingMessageIndex(null)
                setEditingMessageText("")
                await loadHistory()
            }
        } catch (e) {
            console.error("Failed to copy session:", e)
        }
    }, [loading, projectId, loadHistory, onSessionChange])

    const handleSend = async (content: string, files?: File[]) => {
        if ((!content.trim() && (!files || files.length === 0)) || loading) return
        const trimmedContent = content.trim()
        const isCommandOnly = !files || files.length === 0

        if (isCommandOnly && (trimmedContent === "/compress" || trimmedContent === "/archive")) {
            setMessages((prev) => [...prev, { role: "user", content: trimmedContent }])
            setLoading(true)
            setStatusText("Executing command...")
            setElapsedTime(0)

            try {
                const currentSessionId = effectiveSessionRef.current ?? sessionId
                const result = await executeCommand(trimmedContent, projectId, currentSessionId, model)

                if (result.success) {
                    setMessages((prev) => [...prev, {
                        role: "assistant",
                        content: `✅ ${result.message}`,
                    }])

                    if (result.command_name === "compress" || result.command_name === "archive") {
                        const nextSessionId = result.data?.new_session_id || result.data?.promoted_session_id || null
                        if (nextSessionId) {
                            effectiveSessionRef.current = nextSessionId
                            onSessionChange?.(nextSessionId)
                            localStorage.setItem(`va_last_session_${projectId}`, nextSessionId)
                        }

                        window.dispatchEvent(new CustomEvent("va-sessions-updated", {
                            detail: { project_id: projectId, session_id: nextSessionId },
                        }))

                        await loadHistory()
                    }
                } else {
                    setMessages((prev) => [...prev, {
                        role: "assistant",
                        content: `❌ Command Error: ${result.message}`,
                    }])
                }
            } catch (e: any) {
                setMessages((prev) => [...prev, {
                    role: "assistant",
                    content: `❌ Failed to execute command: ${e?.message || "Unknown error"}`,
                }])
            } finally {
                setLoading(false)
                setStatusText("")
                setElapsedTime(0)
            }
            return
        }

        const normalizedContent = normalizeMessageContent(content)
        if (normalizedContent) {
            pendingLocalSendsRef.current.push({ content: normalizedContent, createdAt: Date.now() })
        }

        // Optimistic add
        setMessages((prev) => [...prev, { role: "user", content }])
        setLoading(true)
        setStatusText("Processing your request...")
        setElapsedTime(0)

        try {
            const requestedSessionId = effectiveSessionRef.current ?? sessionId
            const { task_id, session_id: usedSessionId } = await sendChat(projectId, content, requestedSessionId, model, files)
            currentTaskIdRef.current = task_id
            if (normalizedContent) {
                pendingLocalSendsRef.current = pendingLocalSendsRef.current.filter(
                    (s) => normalizeMessageContent(s.content) !== normalizedContent
                )
            }

            // Update the effective session if the backend resolved to a different one
            if (usedSessionId) {
                effectiveSessionRef.current = usedSessionId
                if (usedSessionId !== sessionId) {
                    onSessionChange?.(usedSessionId)
                    localStorage.setItem(`va_last_session_${projectId}`, usedSessionId)
                    window.dispatchEvent(new CustomEvent("va-sessions-updated", {
                        detail: {
                            project_id: projectId,
                            session_id: usedSessionId,
                        },
                    }))
                }
            }
            const resolvedSessionId = usedSessionId || effectiveSessionRef.current || sessionId || null
            upsertSessionCacheTask(projectId, resolvedSessionId, task_id, content, "Queued...")
            localStorage.setItem("va_last_command_session", JSON.stringify({
                project_id: projectId,
                session_id: resolvedSessionId,
            }))

            upsertRealtimeTask(task_id, content, "Queued...")

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
                        clearSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, false)
                        setRealtimeTasks((prev) => prev.filter((t) => t.taskId !== task_id))
                        await loadHistory()
                    } else if (taskData.status === "failed" || taskData.status === "cancelled") {
                        stopPolling()
                        setLoading(false)
                        setStatusText("")
                        setElapsedTime(0)
                        currentTaskIdRef.current = null
                        clearSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, false)
                        setRealtimeTasks((prev) => prev.filter((t) => t.taskId !== task_id))
                        if (taskData.status === "failed") {
                            setMessages((prev) => [
                                ...prev,
                                { role: "assistant", content: `Failed: ${taskData.result || "Task failed"}` },
                            ])
                        }
                    } else {
                        // Show detailed status using phase/step if available
                        if (taskData.status === "queued") {
                            setStatusText("Queued...")
                            upsertSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, content, "Queued...")
                            upsertRealtimeTask(task_id, content, "Queued...")
                        } else if (taskData.step) {
                            setStatusText(`Running: ${taskData.step}`)
                            upsertSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, content, `Running: ${taskData.step}`)
                            upsertRealtimeTask(task_id, content, `Running: ${taskData.step}`)
                        } else if (taskData.phase) {
                            setStatusText(`${taskData.phase}...`)
                            upsertSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, content, `${taskData.phase}...`)
                            upsertRealtimeTask(task_id, content, `${taskData.phase}...`)
                        } else {
                            setStatusText("Processing...")
                            upsertSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, task_id, content, "Processing...")
                            upsertRealtimeTask(task_id, content, "Processing...")
                        }
                    }
                } catch {
                    // polling error, keep trying
                }
            }, 1000)
        } catch (e) {
            console.error("Failed to send:", e)
            if (normalizedContent) {
                pendingLocalSendsRef.current = pendingLocalSendsRef.current.filter(
                    (s) => normalizeMessageContent(s.content) !== normalizedContent
                )
            }
            stopPolling()
            setLoading(false)
            setStatusText("")
            setElapsedTime(0)
            const failedTaskId = currentTaskIdRef.current
            currentTaskIdRef.current = null
            if (failedTaskId) {
                clearSessionCacheTask(projectId, effectiveSessionRef.current ?? sessionId, failedTaskId, false)
                setRealtimeTasks((prev) => prev.filter((t) => t.taskId !== failedTaskId))
            }
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: "Failed to send message. Please try again." },
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
                                if (msg.meta_payload?.transient && msg.role === "assistant" && !msg.content) return null;
                                return (
                                    <ChatMessage
                                        key={i}
                                        message={msg}
                                        projectId={projectId}
                                        canRegenerate={msg.role === "assistant"}
                                        canEdit={msg.role === "user"}
                                        onRegenerate={msg.role === "assistant" ? () => handleRegenerate(i) : undefined}
                                        onDelete={() => handleDelete(i)}
                                        onEdit={msg.role === "user" ? () => handleEdit(i) : undefined}
                                        onBranch={msg.role === "assistant" ? () => handleBranch(i) : undefined}
                                        vote={messageVotes[i] ?? null}
                                        onVote={msg.role === "assistant" ? (vote) => setMessageVotes((prev) => ({ ...prev, [i]: vote })) : undefined}
                                        isEditing={msg.role === "user" && editingMessageIndex === i}
                                        editValue={msg.role === "user" && editingMessageIndex === i ? editingMessageText : ""}
                                        onEditValueChange={msg.role === "user" && editingMessageIndex === i ? setEditingMessageText : undefined}
                                        onEditSubmit={msg.role === "user" && editingMessageIndex === i ? handleSubmitEditedMessage : undefined}
                                        onEditCancel={msg.role === "user" && editingMessageIndex === i ? () => {
                                            setEditingMessageIndex(null)
                                            setEditingMessageText("")
                                        } : undefined}
                                    />
                                )
                            })
                        )}

                        {realtimeTasks.map((rt) => (
                            <div key={rt.taskId} className="flex gap-3 py-4">
                                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <div className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                                </div>
                                <div className="flex-1">
                                    <div className="text-xs font-semibold text-gray-500 mb-1">Assistant</div>
                                    <div className="text-xs text-gray-500 mb-1 truncate max-w-[520px]">{rt.message}</div>
                                    <div className="text-xs text-gray-400">{rt.statusText}</div>
                                </div>
                            </div>
                        ))}

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
                        {sidebarMode === "automation" && (
                            <AutomationTab projectId={projectId} />
                        )}
                        {sidebarMode === "settings" && (
                            <ProjectSettingsPanel projectId={projectId} />
                        )}
                    </div>
                </div>
            )}

            {/* Inline FileViewer rendered as flex sibling so chat shrinks */}
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
