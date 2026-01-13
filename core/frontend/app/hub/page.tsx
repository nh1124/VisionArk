"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import CommandAutocomplete, { CommandAutocompleteHandle } from "../components/CommandAutocomplete";
import FilesSidebar from "@/components/FilesSidebar";
import InboxView from "@/components/InboxView";
import { apiFetch } from "@/lib/api";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Files, RotateCcw } from "lucide-react";

interface MessageAttachment {
    name: string;
    size: number;
    type: string;
}

interface Message {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    type?: "llm" | "system";
    tool_calls?: Array<{ name: string; result: string; success: boolean }>;
}

export default function HubPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [showCommandHelp, setShowCommandHelp] = useState(false);
    const [commandInputValue, setCommandInputValue] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(false);
    const [selectedModel, setSelectedModel] = useState("gemini-3-pro-preview");
    const [view, setView] = useState<"chat" | "inbox">("chat");
    const router = useRouter();
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const commandRef = useRef<CommandAutocompleteHandle>(null);
    const isMobile = useIsMobile();

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        if (view === "chat") {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, view]);

    // Load conversation history on mount
    useEffect(() => {
        const loadHistory = async () => {
            try {
                const response = await apiFetch("/api/agents/hub/history");
                const data = await response.json();
                if (data.history && Array.isArray(data.history)) {
                    setMessages(data.history.map((m: any) => ({
                        role: m.role,
                        content: m.content,
                        attached_files: m.meta_payload?.attached_files || [],
                        tool_calls: m.meta_payload?.tool_calls || [],
                        type: m.type
                    })));
                }
            } catch (error) {
                console.error("Failed to load history:", error);
            }
        };
        loadHistory();
    }, []);

    const [statusText, setStatusText] = useState("");
    const [elapsedTime, setElapsedTime] = useState(0);

    const sendMessage = async (content: string, files: File[]) => {
        if (!content.trim() && files.length === 0) return;
        setShowCommandHelp(false);

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
        setLoading(true);
        setStatusText("Thinking...");
        setElapsedTime(0);
        const startTime = Date.now();
        const timerInterval = setInterval(() => {
            setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);

        try {
            const formData = new FormData();
            formData.append("message", content);
            files.forEach((file) => {
                formData.append("files", file);
            });
            formData.append("stream", "true");

            const response = await apiFetch("/api/agents/hub/chat", {
                method: "POST",
                body: formData,
                headers: {
                    "X-Preferred-Model": selectedModel
                }
            });

            if (!response.ok) throw new Error("Failed to send message");

            // Handle streaming response
            const reader = response.body?.getReader();
            if (!reader) throw new Error("No reader");

            const decoder = new TextDecoder();
            let assistantContent = "";
            let toolCalls: any[] = [];
            let buffer = "";

            // Create a temporary assistant message that we will update
            setMessages((prev) => [...prev, { role: "assistant", content: "", attached_files: [] }]);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (line.trim().startsWith("data: ")) {
                        try {
                            const event = JSON.parse(line.trim().substring(6));
                            if (event.type === "status") {
                                setStatusText(event.data);
                            } else if (event.type === "content") {
                                assistantContent += event.data;
                                // Update the last message
                                setMessages((prev) => {
                                    const next = [...prev];
                                    if (next.length > 0) {
                                        next[next.length - 1] = {
                                            ...next[next.length - 1],
                                            content: assistantContent
                                        };
                                    }
                                    return next;
                                });
                            } else if (event.type === "final_response") {
                                toolCalls = event.data.tool_calls || [];
                                // Update the last message with final data
                                setMessages((prev) => {
                                    const next = [...prev];
                                    if (next.length > 0) {
                                        next[next.length - 1] = {
                                            ...next[next.length - 1],
                                            content: event.data.content,
                                            tool_calls: toolCalls,
                                            attached_files: event.data.attached_files || []
                                        };
                                    }
                                    return next;
                                });

                                // Handle command-based redirection
                                if (event.data.executed_commands) {
                                    for (const cmd of event.data.executed_commands) {
                                        if (cmd.success && cmd.data?.redirect_url) {
                                            router.push(cmd.data.redirect_url);
                                            break;
                                        }
                                    }
                                }
                            }
                        } catch (e) {
                            console.error("Failed to parse event:", e, "Line:", line);
                        }
                    }
                }
            }
        } catch (error) {
            console.error("Error:", error);
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    content: "Error: Could not connect to Hub agent. Is the backend running?",
                },
            ]);
        } finally {
            clearInterval(timerInterval);
            setLoading(false);
            setStatusText("");
            setElapsedTime(0);
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
            const response = await apiFetch("/api/agents/hub/branch", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_index: index })
            });

            if (response.ok) {
                const data = await response.json();
                console.log("Branched to new spoke:", data.new_spoke_name);

                // Navigate to the new spoke
                window.location.href = `/spokes/${data.new_spoke_name}`;
            } else {
                throw new Error("Failed to branch chat");
            }
        } catch (error) {
            console.error("Branching error:", error);
        } finally {
            setLoading(false);
        }
    }, [loading]);

    const handleEdit = useCallback(async (index: number) => {
        if (loading) return;
        const msg = messages[index];
        if (msg.role !== "user") return;

        try {
            setLoading(true);
            const response = await apiFetch("/api/agents/hub/messages/truncate", {
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
    }, [messages, loading]);

    const handleDelete = useCallback(async (index: number) => {
        if (loading) return;
        try {
            setLoading(true);
            const response = await apiFetch("/api/agents/hub/messages/truncate", {
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
    }, [loading]);

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
            handleDelete(lastUserIndex);
        }
    }, [messages, loading, handleDelete]);

    // Create stable callback refs for message actions - prevents re-renders of MessageWithAttachments
    const messageCallbacks = useMemo(() => {
        return messages.map((msg, idx) => ({
            onRegenerate: msg.role === "assistant" ? () => handleRegenerate(idx) : undefined,
            onBranch: msg.role === "assistant" ? () => handleBranch(idx) : undefined,
            onEdit: msg.role === "user" ? () => handleEdit(idx) : undefined,
            onDelete: () => handleDelete(idx),
        }));
    }, [messages.length, handleRegenerate, handleBranch, handleEdit, handleDelete]);

    return (
        <div className="flex h-full">
            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Header - Minimal Gemini-style */}
                <div className="bg-gray-900/50 border-b border-gray-800/50 px-4 py-2.5 flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-4">
                        <h1 className="text-lg font-semibold text-purple-400">Hub Agent</h1>

                        {/* View Toggle */}
                        <div className="flex bg-gray-800/50 rounded-lg p-0.5">
                            <button
                                onClick={() => setView("chat")}
                                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${view === "chat"
                                    ? "bg-purple-600 text-white"
                                    : "text-gray-400 hover:text-gray-200"
                                    }`}
                            >
                                Chat
                            </button>
                            <button
                                onClick={() => setView("inbox")}
                                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${view === "inbox"
                                    ? "bg-purple-600 text-white"
                                    : "text-gray-400 hover:text-gray-200"
                                    }`}
                            >
                                Inbox
                            </button>
                        </div>
                    </div>

                    {!isMobile && (
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setShowSidebar(!showSidebar)}
                                className={`p-2 rounded-lg transition-all ${showSidebar
                                    ? "bg-purple-500/20 text-purple-400"
                                    : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}
                                title={showSidebar ? "Hide Files" : "Show Files"}
                            >
                                <Files size={18} />
                            </button>
                        </div>
                    )}
                </div>

                {view === "chat" ? (
                    <>
                        {/* Messages - Scrollable area with flex-1 */}
                        <div className="flex-1 overflow-y-auto px-6 py-10 scrollbar-hide bg-[radial-gradient(circle_at_50%_50%,rgba(30,30,45,1),rgba(10,10,15,1))]">
                            <div className="max-w-5xl mx-auto space-y-10">
                                {messages.length === 0 && (
                                    <div className="text-center py-32 animate-in fade-in slide-in-from-bottom-4 duration-1000">
                                        <div className="w-24 h-24 bg-gradient-to-tr from-purple-500/20 to-blue-500/20 rounded-3xl flex items-center justify-center mx-auto mb-8 border border-purple-500/20 shadow-2xl shadow-purple-500/10">
                                            <span className="text-5xl drop-shadow-lg">✨</span>
                                        </div>
                                        <h2 className="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-white via-white to-gray-500 mb-4 tracking-tighter">VisionArk Hub</h2>
                                        <p className="text-gray-400 text-lg font-medium max-w-md mx-auto leading-relaxed">
                                            Your strategic partner for intelligent task management and resource optimization.
                                        </p>
                                        <div className="mt-12 flex items-center justify-center gap-2">
                                            <div className="h-px w-8 bg-gray-800"></div>
                                            <p className="text-[10px] text-gray-600 tracking-[0.3em] uppercase font-bold">
                                                Press / for command engine
                                            </p>
                                            <div className="h-px w-8 bg-gray-800"></div>
                                        </div>
                                    </div>
                                )}

                                {messages.map((msg, idx) => {
                                    // Skip rendering the last empty assistant message while loading
                                    const isLastEmptyAssistant = loading && idx === messages.length - 1 && msg.role === "assistant" && !msg.content && (!msg.tool_calls || msg.tool_calls.length === 0);
                                    if (isLastEmptyAssistant) return null;
                                    const callbacks = messageCallbacks[idx];
                                    return (
                                        <MessageWithAttachments
                                            key={idx}
                                            role={msg.role}
                                            content={msg.content}
                                            attached_files={msg.attached_files}
                                            type={msg.type}
                                            tool_calls={msg.tool_calls}
                                            nodeType="hub"
                                            nodeName="hub"
                                            onRegenerate={callbacks?.onRegenerate}
                                            onBranch={callbacks?.onBranch}
                                            onEdit={callbacks?.onEdit}
                                            onDelete={callbacks?.onDelete}
                                        />
                                    );
                                })}

                                {loading && (
                                    <div className="flex justify-start">
                                        <div className="bg-gray-900/50 backdrop-blur-xl border border-gray-700/30 rounded-2xl px-8 py-5 shadow-2xl flex items-center gap-4">
                                            <div className="flex gap-2">
                                                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce shadow-[0_0_10px_purple]" style={{ animationDelay: '0ms' }}></div>
                                                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce shadow-[0_0_10px_purple]" style={{ animationDelay: '150ms' }}></div>
                                                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce shadow-[0_0_10px_purple]" style={{ animationDelay: '300ms' }}></div>
                                            </div>
                                            <p className="text-sm font-bold text-gray-300 tracking-wide uppercase">
                                                {statusText || "Processing Intelligence..."}
                                                {elapsedTime > 0 && (
                                                    <span className="ml-2 text-gray-500 font-mono text-xs normal-case">
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
                                <div className="max-w-4xl mx-auto">
                                    <CommandAutocomplete
                                        ref={commandRef}
                                        value={commandInputValue}
                                        onChange={setCommandInputValue}
                                        onSubmit={() => sendMessage(commandInputValue, [])}
                                        placeholder=""
                                        context="hub"
                                        disabled={loading}
                                        showInput={false}
                                    />
                                </div>
                            </div>
                        )}

                        {/* Input - Fixed at bottom */}
                        <div className="pb-8 px-4">
                            <div className="max-w-4xl mx-auto flex flex-col min-h-0">
                                <div className="flex justify-between items-center mb-2 px-4">
                                    <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
                                        Ready for input
                                    </div>
                                    {messages.length > 0 && (
                                        <button
                                            onClick={handleUndo}
                                            disabled={loading}
                                            className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 hover:text-purple-400 uppercase tracking-wider transition-colors disabled:opacity-50"
                                        >
                                            <RotateCcw size={12} />
                                            Undo Last
                                        </button>
                                    )}
                                </div>
                                <ChatInput
                                    value={commandInputValue}
                                    onCommandModeChange={(isCommand, value) => {
                                        setShowCommandHelp(view === "chat" && isCommand);
                                        setCommandInputValue(value);
                                    }}
                                    onKeyDown={(e) => {
                                        if (showCommandHelp && commandRef.current) {
                                            commandRef.current.handleKeyDown(e);
                                        }
                                    }}
                                    onSend={sendMessage}
                                    placeholder="Ask Hub about workload, schedule, or resources..."
                                    disabled={loading}
                                    allowFileAttach={true}
                                    selectedModel={selectedModel}
                                    onModelChange={setSelectedModel}
                                    showModelSelector={true}
                                />
                            </div>
                        </div>
                    </>
                ) : (
                    <InboxView />
                )}
            </div>

            {/* Sidebar - Files & Artifacts (Desktop only) */}
            {!isMobile && showSidebar && (
                <div className="fixed inset-y-0 right-0 z-50 w-80 bg-gray-900 border-l border-gray-800 p-4 flex-shrink-0 flex-col h-full shadow-2xl md:shadow-none md:relative md:translate-x-0 animate-in slide-in-from-right-full duration-300 ease-out">
                    <div className="flex-1 overflow-hidden">
                        <FilesSidebar nodeType="hub" nodeName="hub" />
                    </div>
                </div>
            )}
        </div>
    );
}
