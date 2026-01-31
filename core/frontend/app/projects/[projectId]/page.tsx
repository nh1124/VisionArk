"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { use } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import FilesSidebar from "@/components/FilesSidebar";
import CommandAutocomplete, { CommandAutocompleteHandle } from "../../components/CommandAutocomplete";
import { apiFetch } from "@/lib/api";
import { Settings, Files, RotateCcw, X, AlarmClock } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useModel } from "@/lib/ModelContext";
import { Panel, Group, Separator } from "react-resizable-panels";
import Canvas from "@/components/Canvas";
import EditCommandPalette from "@/components/EditCommandPalette";
import { useNotification } from "@/lib/NotificationContext";
import ScheduleMessageModal from "@/components/automation/ScheduleMessageModal";
import AutomationTab from "@/components/automation/AutomationTab";
import ProjectNotes from "@/components/ProjectNotes";
import { StickyNote } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";

interface MessageAttachment {
    name: string;
    size: number;
    type: string;
}

interface Message {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    tool_calls?: any[];
    sub_messages?: any[];
}

export default function ProjectChatPage({
    params,
}: {
    params: Promise<{ projectId: string }>;
}) {
    const { projectId } = use(params);
    const [messages, setMessages] = useState<Message[]>([]);
    const [commandInputValue, setCommandInputValue] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(false);
    const [showCommandHelp, setShowCommandHelp] = useState(false);
    const { selectedModel, setSelectedModel } = useModel();
    const isMobile = useIsMobile();
    const router = useRouter();
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [displayName, setDisplayName] = useState("");
    const [elapsedTime, setElapsedTime] = useState(0);
    const [statusText, setStatusText] = useState("");
    const commandRef = useRef<CommandAutocompleteHandle>(null);
    const [previewImage, setPreviewImage] = useState<{ url: string; name: string } | null>(null);
    const [approvalStatuses, setApprovalStatuses] = useState<Record<string, string>>({});


    // Canvas State
    const [showCanvas, setShowCanvas] = useState(false);
    const [canvasContent, setCanvasContent] = useState("");
    const [canvasFormat, setCanvasFormat] = useState<"markdown" | "code">("markdown");
    const [canvasFilePath, setCanvasFilePath] = useState<string | undefined>(undefined);
    const [canvasSelection, setCanvasSelection] = useState<string | null>(null);
    const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
    const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
    const [sidebarMode, setSidebarMode] = useState<"files" | "automation" | "notes">("files");
    const lastProcessedCanvasUpdateRef = useRef<string | null>(null);
    const { showToast } = useNotification();

    // Polling and task state
    const searchParams = useSearchParams();
    const taskIdFromUrl = searchParams.get('task_id');
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const isPollingActiveRef = useRef(false);
    const currentPollingTaskRef = useRef<string | null>(null);
    const historyFetchId = useRef(0);

    // Stop handler
    const handleStop = async () => {
        if (!taskIdFromUrl) return;
        try {
            const response = await apiFetch(`/api/agents/tasks/${taskIdFromUrl}/stop`, {
                method: "POST"
            });
            if (response.ok) {
                setStatusText("Stopping...");
            } else {
                alert("Failed to stop task.");
            }
        } catch (error) {
            console.error("Failed to stop task:", error);
        }
    };

    // Approval handler
    const handleApprove = async (requestId: string, approved: boolean) => {
        try {
            const endpoint = approved
                ? `/api/approvals/${requestId}/approve`
                : `/api/approvals/${requestId}/reject`;

            const response = await apiFetch(endpoint, { method: "POST" });
            const data = await response.json();

            if (data.task_id) {
                // Update URL to trigger the existing polling mechanism
                // This will show "Processing..." and then automatically fetch history when done
                router.replace(`/projects/${projectId}?task_id=${data.task_id}`, { scroll: false });
            } else {
                // Fallback for immediate responses (e.g. rejection might not be async)
                await fetchHistory();
            }

        } catch (error) {
            console.error("Failed to process approval:", error);
            alert("Failed to process approval request.");
        }
    };

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const fetchHistory = useCallback(async () => {
        const requestId = ++historyFetchId.current;
        try {
            // Fetch history AND approvals in parallel
            const [historyRes, approvalsRes] = await Promise.all([
                apiFetch(`/api/agents/project/${projectId}/history`),
                apiFetch(`/api/approvals/project/${projectId}/list`)
            ]);

            const historyData = await historyRes.json();

            // Allow approvals to fail without breaking history
            let approvalMap: Record<string, string> = {};
            try {
                if (approvalsRes.ok) {
                    const approvalsData = await approvalsRes.json();
                    if (Array.isArray(approvalsData)) {
                        approvalsData.forEach((req: any) => {
                            approvalMap[req.id] = req.status;
                        });
                        setApprovalStatuses(approvalMap);
                    }
                }
            } catch (e) {
                console.error("Failed to parse approvals:", e);
            }

            // If a newer request has started, ignore this result
            if (requestId !== historyFetchId.current) return;

            if (historyData.history && Array.isArray(historyData.history)) {
                const newMessages = historyData.history.map((m: any) => ({
                    role: m.role,
                    content: m.content,
                    attached_files: m.meta_payload?.attached_files || [],
                    tool_calls: m.meta_payload?.tool_calls || [],
                    sub_messages: m.sub_messages || []
                }));

                setMessages((prev) => {
                    const storageKey = `pending_prompt_${projectId}`;
                    const pendingPrompt = sessionStorage.getItem(storageKey);

                    // If server history is missing, but we have a pending prompt and are polling,
                    // ensure we don't wipe out the UI.
                    if (newMessages.length === 0 && pendingPrompt && (isPollingActiveRef.current || taskIdFromUrl)) {
                        // If we already have the optimistic message in state, keep it
                        if (prev.some((m: Message) => m.role === "user" && m.content === pendingPrompt)) return prev;
                        return [{ role: "user", content: pendingPrompt }];
                    }

                    // Merging logic: if server returns fewer messages than we have (including optimistic),
                    // be careful not to overwrite the optimistic turn.
                    if (pendingPrompt && (isPollingActiveRef.current || taskIdFromUrl)) {
                        const alreadyInServer = newMessages.some((m: Message) => m.role === "user" && m.content === pendingPrompt);
                        if (!alreadyInServer) {
                            // Append optimistic message to server history
                            return [...newMessages, { role: "user", content: pendingPrompt }];
                        }
                    }

                    return newMessages;
                });

                // Check for update_canvas in history
                newMessages.forEach((msg: Message) => {
                    if (msg.tool_calls) {
                        msg.tool_calls.forEach((tc: any) => {
                            if (tc.name === "update_canvas") {
                                // Only update if this is a NEW tool call we haven't processed yet
                                const updateId = tc.id || JSON.stringify(tc.args);
                                if (updateId !== lastProcessedCanvasUpdateRef.current) {
                                    const args = tc.args || {};
                                    if (args.content) {
                                        setCanvasContent(args.content);
                                        setCanvasFormat(args.format || "markdown");
                                        setCanvasFilePath(args.file_path);
                                        setShowCanvas(true);
                                        lastProcessedCanvasUpdateRef.current = updateId;
                                    }
                                }
                            }
                        });
                    }
                });
            }
        } catch (error) {
            console.error("Failed to load history:", error);
        }
    }, [projectId, taskIdFromUrl]);

    // Load metadata and history on mount + Recover active task
    useEffect(() => {
        const loadMetadata = async () => {
            try {
                const response = await apiFetch(`/api/agents/project/${projectId}`);
                const data = await response.json();
                setDisplayName(data.display_name || projectId);
            } catch (error) {
                console.error("Failed to load metadata:", error);
                setDisplayName(projectId);
            }
        };

        const recoverActiveTask = async () => {
            try {
                const response = await apiFetch(`/api/agents/project/${projectId}/active-task`);
                const data = await response.json();
                if (data.task_id && !taskIdFromUrl) {
                    console.log("Recovered active task:", data.task_id);
                    router.replace(`/projects/${projectId}?task_id=${data.task_id}`, { scroll: false });
                }
            } catch (error) {
                console.error("Failed to recover active task:", error);
            }
        };

        loadMetadata();

        // Immediate recovery from sessionStorage for smooth UI
        const storageKey = `pending_prompt_${projectId}`;
        const pendingPrompt = sessionStorage.getItem(storageKey);
        if (pendingPrompt) {
            setMessages((prev) => {
                if (prev.length === 0) return [{ role: "user", content: pendingPrompt }];
                return prev;
            });
        }

        fetchHistory();
        recoverActiveTask();
    }, [projectId, fetchHistory, taskIdFromUrl, router]);

    // Cleanup function - only clears intervals if this component started them
    useEffect(() => {
        return () => {
            // Only cleanup if we own the polling
            if (isPollingActiveRef.current && currentPollingTaskRef.current === taskIdFromUrl) {
                console.log("[Cleanup] Clearing intervals for:", currentPollingTaskRef.current);
                if (timerIntervalRef.current) {
                    clearInterval(timerIntervalRef.current);
                    timerIntervalRef.current = null;
                }
                if (pollIntervalRef.current) {
                    clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
                isPollingActiveRef.current = false;
                currentPollingTaskRef.current = null;
            }
        };
    }, [taskIdFromUrl]);

    // Load draft from localStorage on mount
    useEffect(() => {
        try {
            const savedDraft = localStorage.getItem(`chat_draft_${projectId}`);
            if (savedDraft) {
                setCommandInputValue(savedDraft);
            }
        } catch (e) {
            console.error("Failed to load draft:", e);
        }
    }, [projectId]);

    // Effect: Start polling when taskId appears
    useEffect(() => {
        // Skip if no taskId
        if (!taskIdFromUrl) return;

        // Skip if already polling this task
        if (isPollingActiveRef.current && currentPollingTaskRef.current === taskIdFromUrl) {
            return;
        }

        // Mark as polling and store the taskId
        isPollingActiveRef.current = true;
        currentPollingTaskRef.current = taskIdFromUrl;

        // Start polling for this task
        setLoading(true);
        setStatusText("Processing your request...");
        const startTime = Date.now();
        const currentTaskId = taskIdFromUrl; // Capture for closure

        timerIntervalRef.current = setInterval(() => {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            setElapsedTime(elapsed);
        }, 1000);

        const pollTask = async (): Promise<boolean> => {
            try {
                const statusRes = await apiFetch(`/api/agents/tasks/${currentTaskId}`);
                if (!statusRes.ok) return false;

                const statusData = await statusRes.json();
                const status = statusData.status;

                if (status === "completed") {
                    if (timerIntervalRef.current) {
                        clearInterval(timerIntervalRef.current);
                        timerIntervalRef.current = null;
                    }
                    if (pollIntervalRef.current) {
                        clearInterval(pollIntervalRef.current);
                        pollIntervalRef.current = null;
                    }
                    setLoading(false);
                    setStatusText("");
                    // Cleanup optimistic storage
                    sessionStorage.removeItem(`pending_prompt_${projectId}`);

                    // Re-fetch history to get complete messages
                    const requestId = ++historyFetchId.current;
                    try {
                        const historyRes = await apiFetch(`/api/agents/project/${projectId}/history`);
                        const historyData = await historyRes.json();
                        if (requestId === historyFetchId.current && historyData.history && Array.isArray(historyData.history)) {
                            const newMessages = historyData.history.map((m: any) => ({
                                role: m.role,
                                content: m.content,
                                attached_files: m.meta_payload?.attached_files || [],
                                tool_calls: m.meta_payload?.tool_calls || [],
                                sub_messages: m.sub_messages || []
                            }));
                            setMessages(newMessages);

                            // Check for update_canvas in tool calls
                            newMessages.forEach((msg: Message) => {
                                if (msg.tool_calls) {
                                    msg.tool_calls.forEach((tc: any) => {
                                        if (tc.name === "update_canvas") {
                                            const args = tc.args || {};
                                            if (args.content) {
                                                setCanvasContent(args.content);
                                                setCanvasFormat(args.format || "markdown");
                                                setCanvasFilePath(args.file_path);
                                                setShowCanvas(true);
                                            }
                                        }
                                    });
                                }
                            });
                        }
                    } catch (e) {
                        console.error("Failed to refresh history:", e);
                    }

                    // Clear URL AFTER task completes
                    router.replace(`/projects/${projectId}`, { scroll: false });
                    isPollingActiveRef.current = false;
                    currentPollingTaskRef.current = null;
                    return true;
                } else if (status === "failed" || status === "cancelled") {
                    if (timerIntervalRef.current) {
                        clearInterval(timerIntervalRef.current);
                        timerIntervalRef.current = null;
                    }
                    if (pollIntervalRef.current) {
                        clearInterval(pollIntervalRef.current);
                        pollIntervalRef.current = null;
                    }
                    setLoading(false);
                    setStatusText("");
                    // Cleanup optimistic storage
                    sessionStorage.removeItem(`pending_prompt_${projectId}`);

                    const errorMsg = status === "cancelled" ? "Task stopped by user." : (statusData.result || "Task failed");
                    setMessages((prev) => [...prev, {
                        role: "assistant",
                        content: `❌ ${errorMsg}`
                    }]);

                    // Clear URL on failure too
                    router.replace(`/projects/${projectId}`, { scroll: false });
                    isPollingActiveRef.current = false;
                    currentPollingTaskRef.current = null;
                    return true;
                } else {
                    setStatusText(status === "queued" ? "Queued..." : "Processing...");
                    return false;
                }
            } catch (err) {
                console.error("Polling error:", err);
                return false;
            }
        };

        pollIntervalRef.current = setInterval(async () => {
            const done = await pollTask();
            if (done && pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
        }, 1000);

        // Initial poll
        pollTask();

        // NO cleanup here - Effect 1 handles unmount cleanup
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [taskIdFromUrl, projectId]);


    const sendMessage = async (content: string, files: File[]) => {
        if (!content.trim() && files.length === 0) return;
        setShowCommandHelp(false);

        // Clear draft from localStorage
        try {
            localStorage.removeItem(`chat_draft_${projectId}`);
            setCommandInputValue("");
        } catch (e) {
            // ignore
        }

        // Intercept Slash Commands
        if (content.startsWith("/") && files.length === 0) {
            setMessages((prev) => [...prev, { role: "user", content }]);
            setLoading(true);
            setStatusText("Executing command...");

            try {
                const response = await apiFetch("/api/commands/execute", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        text: content,
                        scope: "project",
                        project_id: projectId
                    })
                });

                const result = await response.json();

                if (result.success) {
                    setMessages((prev) => [...prev, {
                        role: "assistant",
                        content: `✅ ${result.message}`
                    }]);

                    // If command was /mv, the backend might return data for redirect
                    if (result.command_name === "move" && result.data?.target_id) {
                        const targetId = result.data.target_id;
                        if (targetId === "main") {
                            router.push("/dashboard");
                        } else {
                            router.push(`/projects/${targetId}`);
                        }
                    }
                } else {
                    setMessages((prev) => [...prev, {
                        role: "assistant",
                        content: `❌ Command Error: ${result.message}`
                    }]);
                }
            } catch (error: any) {
                setMessages((prev) => [...prev, {
                    role: "assistant",
                    content: `❌ Failed to execute command: ${error.message}`
                }]);
            } finally {
                setLoading(false);
                setStatusText("");
                return;
            }
        }

        const userMessage: Message = {
            role: "user",
            content: content,
            attached_files: files.map(f => ({
                name: f.name,
                size: f.size,
                type: f.type
            }))
        };
        setMessages((prev) => [...prev, userMessage]);

        // Store prompt for recovery after refresh
        try {
            sessionStorage.setItem(`pending_prompt_${projectId}`, content);
        } catch (e) {
            // ignore
        }

        setLoading(true);
        setStatusText("Thinking...");
        setElapsedTime(0);

        // Create a temporary assistant message that we will update
        const assistantMsgIndex = messages.length + 1; // +1 because we added userMessage
        setMessages((prev) => [...prev, { role: "assistant", content: "", attached_files: [] }]);

        const startTime = Date.now();
        const timerInterval = setInterval(() => {
            setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);

        try {
            const formData = new FormData();
            formData.append("message", content);
            files.forEach((file) => formData.append("files", file));
            formData.append("stream", "false"); // Polling mode

            const response = await apiFetch(`/api/agents/project/${projectId}/chat`, {
                method: "POST",
                body: formData,
                headers: {
                    "X-Preferred-Model": selectedModel || ""
                }
            });

            if (!response.ok) throw new Error("Failed to send message");

            const data = await response.json();
            const taskId = data.task_id;

            if (!taskId) {
                // Determine if it was a sync response (fallback)
                if (data.response) {
                    setMessages((prev) => {
                        const next = [...prev];
                        next[next.length - 1] = {
                            ...next[next.length - 1],
                            content: data.response
                        };
                        return next;
                    });
                    setLoading(false);
                    clearInterval(timerInterval);
                    return;
                }
                throw new Error("No task ID returned");
            }

            // Sync Task ID to URL - this will trigger the URL-based polling useEffect
            router.replace(`/projects/${projectId}?task_id=${taskId}`, { scroll: false });
            // Handle timer separately as the URL effect starts its own timer
            clearInterval(timerInterval);

        } catch (error: any) {
            console.error("Error:", error);
            const errorMsg = error.message || "Could not connect to Project agent.";
            setMessages((prev) => [
                ...prev.slice(0, -1),
                { role: "assistant", content: `❌ Error: ${errorMsg}` }
            ]);
            setLoading(false);
            // timerInterval is handled by clearInterval in try block or here if it exists
        }
    };

    const handleClone = async () => {
        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/project/${projectId}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_display_name: `${displayName} (Copy)` }),
            });

            if (response.ok) {
                const data = await response.json();
                alert(`Project cloned successfully!`);
                window.location.href = `/projects/${data.new_project_id}`;
            } else {
                const err = await response.json();
                alert(`Failed to clone project: ${err.detail || 'Unknown error'}`);
            }
        } catch (error) {
            console.error("Error cloning:", error);
            alert("Error cloning project");
        } finally {
            setLoading(false);
        }
    };

    const handleRegenerate = useCallback(async (index: number) => {
        if (loading) return;

        // Find the last user message before this one
        let userMsgIndex = -1;
        for (let i = index - 1; i >= 0; i--) {
            if (messages[i].role === "user") {
                userMsgIndex = i;
                break;
            }
        }

        if (userMsgIndex === -1) return;

        const userMsg = messages[userMsgIndex];

        // Truncate messages to just before the AI response and re-send
        setMessages(prev => prev.slice(0, userMsgIndex + 1));

        // Re-send the user message
        sendMessage(userMsg.content, []);
    }, [messages, loading]);

    const handleBranch = useCallback(async (index: number) => {
        if (loading) return;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/project/${projectId}/branch`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_index: index })
            });

            if (response.ok) {
                const data = await response.json();
                console.log("Branched to new project:", data.new_project_id);

                // Navigate to the new project
                window.location.href = `/projects/${data.new_project_id}`;
            } else {
                throw new Error("Failed to branch chat");
            }
        } catch (error) {
            console.error("Branching error:", error);
        } finally {
            setLoading(false);
        }
    }, [loading, projectId]);

    const handleSave = async (content: string) => {
        if (!canvasFilePath) return;
        try {
            let directory: "refs" | "artifacts" | "files" = "refs";
            let relativePath = canvasFilePath;

            if (canvasFilePath.startsWith("artifacts/")) {
                directory = "artifacts";
                relativePath = canvasFilePath.replace("artifacts/", "");
            } else if (canvasFilePath.startsWith("files/")) {
                directory = "files";
                relativePath = canvasFilePath.replace("files/", "");
            } else if (canvasFilePath.startsWith("refs/")) {
                directory = "refs";
                relativePath = canvasFilePath.replace("refs/", "");
            }

            const response = await apiFetch(`/api/files/project/${projectId}/save`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    path: relativePath,
                    content: content,
                    directory: directory
                })
            });

            if (response.ok) {
                console.log("File saved successfully");
                // @ts-ignore - assuming showToast is available or add it
                if (typeof showToast === 'function') {
                    showToast("Changes saved successfully", "success");
                }
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Failed to save file");
            }
        } catch (error: any) {
            console.error("Save error:", error);
            // @ts-ignore
            if (typeof showToast === 'function') {
                showToast(error.message || "Failed to save changes", "error");
            } else {
                alert("Failed to save changes.");
            }
        }
    };

    const handleEdit = useCallback(async (index: number) => {
        if (loading) return;
        const msg = messages[index];
        if (msg.role !== "user") return;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/project/${projectId}/messages/truncate`, {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_index: index })
            });

            if (response.ok) {
                // Populate input with the message content
                setCommandInputValue(msg.content);
                // Truncate local state
                setMessages(prev => prev.slice(0, index));
            } else {
                throw new Error("Failed to truncate for edit");
            }
        } catch (error) {
            console.error("Edit error:", error);
        } finally {
            setLoading(false);
        }
    }, [messages, loading, projectId]);

    const handleDelete = useCallback(async (index: number) => {
        if (loading) return;
        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/project/${projectId}/messages/truncate`, {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_index: index })
            });

            if (response.ok) {
                setMessages(prev => prev.slice(0, index));
            } else {
                throw new Error("Failed to delete messages");
            }
        } catch (error) {
            console.error("Delete error:", error);
        } finally {
            setLoading(false);
        }
    }, [loading, projectId]);

    const handleUndo = useCallback(async () => {
        if (loading || messages.length === 0) return;

        // Find last user message index
        let lastUserIndex = -1;
        for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i].role === "user") {
                lastUserIndex = i;
                break;
            }
        }

        if (lastUserIndex !== -1) {
            // Use handleEdit instead of handleDelete to populate the input with the message content
            handleEdit(lastUserIndex);
        }
    }, [messages, loading, handleEdit]);

    // Create stable callback refs for message actions - prevents re-renders of MessageWithAttachments
    const messageCallbacks = useMemo(() => {
        return messages.map((msg, idx) => ({
            onRegenerate: msg.role === "assistant" ? () => handleRegenerate(idx) : undefined,
            onBranch: msg.role === "assistant" ? () => handleBranch(idx) : undefined,
            onEdit: msg.role === "user" ? () => handleEdit(idx) : undefined,
            onDelete: () => handleDelete(idx),
        }));
    }, [messages.length, handleRegenerate, handleBranch, handleEdit, handleDelete]);

    const handleCanvasCommand = async (action: string) => {
        setIsCommandPaletteOpen(false);
        const contextInfo = canvasFilePath ? ` (File: ${canvasFilePath})` : "";
        const selectionInfo = canvasSelection
            ? `\n\n[SELECTED TEXT TO EDIT]:\n"""\n${canvasSelection}\n"""`
            : "";

        const prompt = `${action} the content in the canvas${contextInfo}${selectionInfo}\n\n[INSTRUCTIONS]: If a selection is provided above, please focus your edits on that specific part. Return the FULL updated canvas content using update_canvas tool.\n\n[CANVAS_FULL_CONTENT]:\n${canvasContent}`;

        sendMessage(prompt, []);
        setCanvasSelection(null); // Clear selection after use
    };

    const chatView = (
        <div className="flex-1 flex flex-col h-full overflow-hidden relative bg-gray-950 min-w-0">
            {/* Header - Minimal Gemini-style - Hide on mobile since the global header handles it */}
            {!isMobile && (
                <div className="bg-gray-900/50 border-b border-gray-800/50 px-4 py-2.5 flex items-center justify-between flex-shrink-0">
                    <h1 className="text-lg font-semibold text-cyan-400 truncate pr-4" title={displayName}>
                        {displayName}
                    </h1>
                    <div className="flex gap-2 items-center">
                        <NotificationBell />
                        <Link href={`/projects/${projectId}/settings`}
                            className="p-2 text-gray-500 hover:text-white transition-colors"
                            title="Project Settings"
                        >
                            <Settings size={20} />
                        </Link>
                        <button
                            onClick={() => {
                                setShowSidebar(true);
                                setSidebarMode("notes");
                            }}
                            className={`p-2 transition-colors ${showSidebar && sidebarMode === "notes" ? "text-cyan-400" : "text-gray-500 hover:text-white"}`}
                            title="Project Notes"
                        >
                            <StickyNote size={20} />
                        </button>
                        <button
                            onClick={() => {
                                if (showSidebar && sidebarMode === "automation") {
                                    setShowSidebar(false);
                                } else {
                                    setSidebarMode("automation");
                                    setShowSidebar(true);
                                }
                            }}
                            className={`p-2 rounded-lg transition-all ${showSidebar && sidebarMode === "automation"
                                ? "bg-cyan-500/20 text-cyan-400"
                                : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}
                            title={showSidebar && sidebarMode === "automation" ? "Hide Automation" : "Show Automation"}
                        >
                            <AlarmClock size={18} />
                        </button>
                        <button
                            onClick={() => {
                                if (showSidebar && sidebarMode === "files") {
                                    setShowSidebar(false);
                                } else {
                                    setSidebarMode("files");
                                    setShowSidebar(true);
                                }
                            }}
                            className={`p-2 rounded-lg transition-all ${showSidebar && sidebarMode === "files"
                                ? "bg-cyan-500/20 text-cyan-400"
                                : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}
                            title={showSidebar && sidebarMode === "files" ? "Hide Files" : "Show Files"}
                        >
                            <Files size={18} />
                        </button>
                    </div>
                </div>
            )}

            {/* Messages - Scrollable area */}
            <div className="flex-1 overflow-y-auto px-4 py-8">
                <div className="max-w-4xl mx-auto space-y-6 min-w-0 w-full" key={`messages-${messages.length}`}>
                    {messages.length === 0 && !loading && (
                        <div className="text-center text-gray-500 py-20">
                            <div className="w-16 h-16 bg-cyan-500/10 rounded-2xl flex items-center justify-center mx-auto mb-6">
                                <span className="text-3xl">💼</span>
                            </div>
                            <h2 className="text-3xl font-bold text-white mb-2 truncate max-w-full px-4" title={`${displayName} Workspace`}>
                                {displayName} Workspace
                            </h2>
                            <p className="text-gray-400">Deep work and specialized execution for this project.</p>
                            <p className="text-xs text-gray-600 mt-6 tracking-widest uppercase">
                                Reference files auto-loaded from library
                            </p>
                        </div>
                    )}

                    {messages.map((msg, idx) => {
                        // Skip rendering the last empty assistant message while loading
                        const isLastEmptyAssistant = loading && idx === messages.length - 1 && msg.role === "assistant" && !msg.content && (!msg.tool_calls || msg.tool_calls.length === 0);
                        if (isLastEmptyAssistant) return null;
                        return (
                            <MessageWithAttachments
                                key={idx}
                                role={msg.role}
                                content={msg.content}
                                attached_files={msg.attached_files}
                                tool_calls={msg.tool_calls}
                                sub_messages={msg.sub_messages}
                                nodeType="project"
                                nodeName={projectId}
                                approvalStatuses={approvalStatuses}
                                onRegenerate={messageCallbacks[idx]?.onRegenerate}
                                onBranch={messageCallbacks[idx]?.onBranch}
                                onEdit={messageCallbacks[idx]?.onEdit}
                                onDelete={messageCallbacks[idx]?.onDelete}
                                onSend={(content) => sendMessage(content, [])}
                                onApprove={handleApprove}
                            />
                        );
                    })}

                    {loading && (
                        <div className="flex justify-start">
                            <div className="bg-gray-800/40 border border-gray-700/50 rounded-2xl px-6 py-4 animate-pulse flex items-center gap-3">
                                <div className="flex gap-1.5">
                                    <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                                    <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                                    <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                                </div>
                                <p className="text-sm text-gray-400">
                                    {statusText || "Thinking..."}
                                    {elapsedTime > 0 && (
                                        <span className="ml-2 text-gray-500 font-mono text-xs">
                                            ({elapsedTime}s)
                                        </span>
                                    )}
                                </p>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Command Help Overlay */}
            {showCommandHelp && (
                <div className="px-4">
                    <div className="max-w-4xl mx-auto border-t border-gray-800 pt-4 min-w-0">
                        <CommandAutocomplete
                            ref={commandRef}
                            value={commandInputValue}
                            onChange={setCommandInputValue}
                            onSubmit={() => sendMessage(commandInputValue, [])}
                            placeholder=""
                            context="project"
                            disabled={loading}
                            showInput={false}
                        />
                    </div>
                </div>
            )}

            {/* Input - Fixed at bottom */}
            <div className="pb-4 px-4">
                <div className="max-w-4xl mx-auto flex flex-col min-h-0 min-w-0">
                    {!isMobile && (
                        <div className="flex justify-between items-center mb-2 px-4">
                            <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
                                Ready for input
                            </div>
                            {messages.length > 0 && (
                                <button
                                    onClick={handleUndo}
                                    disabled={loading}
                                    className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 hover:text-cyan-400 uppercase tracking-wider transition-colors disabled:opacity-50"
                                >
                                    <RotateCcw size={12} />
                                    Undo Last
                                </button>
                            )}
                        </div>
                    )}
                    <ChatInput
                        value={commandInputValue}
                        onChange={(val) => {
                            setCommandInputValue(val);
                            try {
                                localStorage.setItem(`chat_draft_${projectId}`, val);
                            } catch (e) {
                                // ignore quota errors etc
                            }
                        }}
                        onCommandModeChange={(isCommand, value) => {
                            setShowCommandHelp(isCommand);
                            setCommandInputValue(value);
                        }}
                        onKeyDown={(e) => {
                            if (showCommandHelp && commandRef.current) {
                                commandRef.current.handleKeyDown(e);
                            }
                        }}
                        onSend={sendMessage}
                        placeholder="Work on tasks, upload files, or type / for commands..."
                        disabled={loading}
                        allowFileAttach={true}
                        selectedModel={selectedModel}
                        onModelChange={setSelectedModel}
                        showModelSelector={!isMobile}
                        onClone={handleClone}
                        loading={loading}
                        onStop={handleStop}
                        onScheduleMessage={() => setIsScheduleModalOpen(true)} // Added prop
                    />
                    <div className="mt-2 flex items-center justify-center gap-4">
                        <div className="text-[10px] text-gray-600">
                            Press <kbd className="bg-gray-800 px-1 rounded text-gray-400">/</kbd> to see available commands
                        </div>
                        {canvasContent && !showCanvas && (
                            <button
                                onClick={() => setShowCanvas(true)}
                                className="text-[10px] text-cyan-500 font-bold hover:underline uppercase tracking-wider"
                            >
                                Open Canvas
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {isScheduleModalOpen && (
                <ScheduleMessageModal
                    projectId={projectId}
                    onClose={() => setIsScheduleModalOpen(false)}
                    onScheduled={() => {
                        fetchHistory();
                    }}
                />
            )}
        </div>
    );

    return (
        <>
            <div className="flex h-full w-full overflow-hidden bg-gray-950 min-w-0">
                {!isMobile && showCanvas ? (
                    <Group orientation="horizontal" className="h-full w-full">
                        <Panel defaultSize={50} minSize={30}>
                            {chatView}
                        </Panel>
                        <Separator className="w-1.5 bg-gray-950 hover:bg-cyan-500/20 transition-colors flex items-center justify-center cursor-col-resize">
                            <div className="h-8 w-1 bg-gray-800 rounded-full" />
                        </Separator>
                        <Panel defaultSize={50} minSize={30}>
                            <div className="h-full flex flex-col relative border-l border-gray-800">
                                <Canvas
                                    content={canvasContent}
                                    format={canvasFormat}
                                    filePath={canvasFilePath}
                                    onUpdate={setCanvasContent}
                                    onSave={handleSave}
                                    onClose={() => setShowCanvas(false)}
                                    onCommandPalette={(selection) => {
                                        setCanvasSelection(selection || null);
                                        setIsCommandPaletteOpen(true);
                                    }}
                                />
                            </div>
                        </Panel>
                    </Group>
                ) : (
                    <div className="flex-1 flex flex-col h-full min-h-0 min-w-0">
                        {isMobile && showCanvas ? (
                            <div className="flex-1 flex flex-col overflow-hidden">
                                <Canvas
                                    content={canvasContent}
                                    format={canvasFormat}
                                    filePath={canvasFilePath}
                                    onUpdate={setCanvasContent}
                                    onSave={handleSave}
                                    onClose={() => setShowCanvas(false)}
                                    onCommandPalette={(selection) => {
                                        setCanvasSelection(selection || null);
                                        setIsCommandPaletteOpen(true);
                                    }}
                                />
                            </div>
                        ) : chatView}
                    </div>
                )}

                {showSidebar && (
                    <div className="w-80 h-full border-l border-gray-800 bg-gray-900/50 backdrop-blur-xl absolute right-0 top-0 z-30 shadow-2xl animate-in slide-in-from-right duration-300 flex flex-col p-4">
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest">
                                {sidebarMode === "files" ? "Files & Artifacts" : sidebarMode === "notes" ? "Project Notes" : "Project Automation"}
                            </h2>
                            <button
                                onClick={() => setShowSidebar(false)}
                                className="p-1 hover:bg-gray-800 rounded-md text-gray-500 hover:text-white transition-colors"
                            >
                                <X size={18} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-hidden">
                            {sidebarMode === "files" ? (
                                <FilesSidebar
                                    nodeType="project"
                                    nodeName={projectId}
                                    onOpenFile={(content, path, format) => {
                                        setCanvasContent(content);
                                        setCanvasFilePath(path);
                                        setCanvasFormat(format);
                                        setShowCanvas(true);
                                        setShowSidebar(false);
                                    }}
                                    onPreviewImage={(url, name) => setPreviewImage({ url, name })}
                                />
                            ) : sidebarMode === "notes" ? (
                                <ProjectNotes projectId={projectId as string} />
                            ) : (
                                <AutomationTab
                                    projectId={projectId}
                                    onScheduleClick={() => setIsScheduleModalOpen(true)}
                                />
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Global Image Preview */}
            {previewImage && (
                <div
                    className="fixed inset-0 bg-black/90 backdrop-blur-md z-[100] flex flex-col animate-in fade-in duration-300"
                    onClick={() => setPreviewImage(null)}
                >
                    <div className="flex justify-between items-center p-4 bg-gray-900/50">
                        <h3 className="text-sm font-bold text-gray-200">{previewImage.name}</h3>
                        <button
                            onClick={() => setPreviewImage(null)}
                            className="p-2 hover:bg-white/10 rounded-full text-white transition-colors"
                        >
                            <X size={24} />
                        </button>
                    </div>
                    <div className="flex-1 flex items-center justify-center p-4 md:p-12">
                        <img
                            src={previewImage.url}
                            alt={previewImage.name}
                            className="max-w-full max-h-full object-contain shadow-2xl rounded-lg animate-in zoom-in duration-300"
                            onClick={(e) => e.stopPropagation()}
                        />
                    </div>
                </div>
            )}

            <EditCommandPalette
                open={isCommandPaletteOpen}
                onOpenChange={setIsCommandPaletteOpen}
                onSelectAction={handleCanvasCommand}
            />
        </>
    );
}
