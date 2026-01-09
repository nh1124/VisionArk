"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { use } from "react";
import Link from "next/link";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import FilesSidebar from "@/components/FilesSidebar";
import CommandAutocomplete, { CommandAutocompleteHandle } from "../../components/CommandAutocomplete";
import { apiFetch } from "@/lib/api";
import { Settings, Files, RotateCcw } from "lucide-react";

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
}

export default function SpokeChatPage({
    params,
}: {
    params: Promise<{ spokeName: string }>;
}) {
    const { spokeName } = use(params);
    const [messages, setMessages] = useState<Message[]>([]);
    const [commandInputValue, setCommandInputValue] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(false);
    const [showCommandHelp, setShowCommandHelp] = useState(false);
    const [selectedModel, setSelectedModel] = useState("gemini-3-pro-preview");
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [displayName, setDisplayName] = useState("");
    const [elapsedTime, setElapsedTime] = useState(0);
    const commandRef = useRef<CommandAutocompleteHandle>(null);

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    // Load metadata and history on mount
    useEffect(() => {
        const loadMetadata = async () => {
            try {
                const response = await apiFetch(`/api/agents/spoke/${spokeName}`);
                const data = await response.json();
                setDisplayName(data.display_name || spokeName.replace("_", " "));
            } catch (error) {
                console.error("Failed to load metadata:", error);
                setDisplayName(spokeName.replace("_", " "));
            }
        };

        const loadHistory = async () => {
            try {
                const response = await apiFetch(`/api/agents/spoke/${spokeName}/history`);
                const data = await response.json();
                if (data.history && Array.isArray(data.history)) {
                    setMessages(data.history.map((m: any) => ({
                        role: m.role,
                        content: m.content,
                        attached_files: m.meta_payload?.attached_files || [],
                        tool_calls: m.meta_payload?.tool_calls || []
                    })));
                }
            } catch (error) {
                console.error("Failed to load history:", error);
            }
        };

        loadMetadata();
        loadHistory();
    }, [spokeName]);

    const [statusText, setStatusText] = useState("");

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
            files.forEach((file) => formData.append("files", file));
            formData.append("stream", "true");

            const response = await apiFetch(`/api/agents/spoke/${spokeName}/chat`, {
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
                            }
                        } catch (e) {
                            console.error("Failed to parse event:", e, "Line:", line);
                        }
                    }
                }
            }
        } catch (error) {
            console.error("Error:", error);
            setMessages((prev) => [...prev, { role: "assistant", content: "Error: Could not connect to Spoke agent." }]);
        } finally {
            clearInterval(timerInterval);
            setLoading(false);
            setStatusText("");
            setElapsedTime(0);
        }
    };

    const handleClone = async () => {
        const newName = `${spokeName}_copy`;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/spoke/${spokeName}/clone`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ new_name: newName || undefined }),
            });

            if (response.ok) {
                const data = await response.json();
                alert(`Project cloned successfully as '${data.new_spoke_name}'`);
                window.location.href = `/spokes/${data.new_spoke_name}`;
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
            const response = await apiFetch(`/api/agents/spoke/${spokeName}/branch`, {
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
    }, [loading, spokeName]);

    const handleEdit = useCallback(async (index: number) => {
        if (loading) return;
        const msg = messages[index];
        if (msg.role !== "user") return;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/spoke/${spokeName}/messages/truncate`, {
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
    }, [messages, loading, spokeName]);

    const handleDelete = useCallback(async (index: number) => {
        if (loading) return;
        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/spoke/${spokeName}/messages/truncate`, {
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
    }, [loading, spokeName]);

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
            <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Header - Minimal Gemini-style */}
                <div className="bg-gray-900/50 border-b border-gray-800/50 px-4 py-2.5 flex items-center justify-between flex-shrink-0">
                    <h1 className="text-lg font-semibold text-cyan-400 truncate" title={displayName}>
                        {displayName}
                    </h1>
                    <div className="flex gap-2">
                        <Link href={`/spokes/${spokeName}/settings`}
                            className="p-2 text-gray-400 hover:bg-gray-800 hover:text-white rounded-lg transition-all"
                            title="Settings"
                        >
                            <Settings size={18} />
                        </Link>
                        <button
                            onClick={() => setShowSidebar(!showSidebar)}
                            className={`p-2 rounded-lg transition-all ${showSidebar
                                ? "bg-cyan-500/20 text-cyan-400"
                                : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}
                            title={showSidebar ? "Hide Files" : "Show Files"}
                        >
                            <Files size={18} />
                        </button>
                    </div>
                </div>

                {/* Messages - Scrollable area */}
                <div className="flex-1 overflow-y-auto px-4 py-8">
                    <div className="max-w-4xl mx-auto space-y-6">
                        {messages.length === 0 && (
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
                                    nodeType="spoke"
                                    nodeName={spokeName}
                                    onRegenerate={messageCallbacks[idx]?.onRegenerate}
                                    onBranch={messageCallbacks[idx]?.onBranch}
                                    onEdit={messageCallbacks[idx]?.onEdit}
                                    onDelete={messageCallbacks[idx]?.onDelete}
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
                        <div className="max-w-4xl mx-auto">
                            <CommandAutocomplete
                                ref={commandRef}
                                value={commandInputValue}
                                onChange={setCommandInputValue}
                                onSubmit={() => sendMessage(commandInputValue, [])}
                                placeholder=""
                                context="spoke"
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
                                    className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500 hover:text-cyan-400 uppercase tracking-wider transition-colors disabled:opacity-50"
                                >
                                    <RotateCcw size={12} />
                                    Undo Last
                                </button>
                            )}
                        </div>
                        <ChatInput
                            value={commandInputValue}
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
                            showModelSelector={true}
                            onClone={handleClone}
                        />
                    </div>
                </div>
            </div>

            {/* Sidebar */}
            {showSidebar && (
                <div className="w-80 bg-gray-900 border-l border-gray-800 p-4 flex-shrink-0">
                    <FilesSidebar nodeType="spoke" nodeName={spokeName} />
                </div>
            )}
        </div>
    );
}
