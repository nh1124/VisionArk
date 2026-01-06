"use client";

import { useState, useEffect, useRef } from "react";
import { use } from "react";
import Link from "next/link";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import FilesSidebar from "@/components/FilesSidebar";
import CommandAutocomplete from "../../components/CommandAutocomplete";
import { apiFetch } from "@/lib/api";

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
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(false);
    const [showCommandHelp, setShowCommandHelp] = useState(false);
    const [selectedModel, setSelectedModel] = useState("gemini-3-pro-preview");
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [displayName, setDisplayName] = useState("");
    const [elapsedTime, setElapsedTime] = useState(0);

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    // Show command help when typing /
    useEffect(() => {
        setShowCommandHelp(input.trim().startsWith('/'));
    }, [input]);

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

    const sendMessage = async (message: string, files: File[]) => {
        if (!message.trim() && files.length === 0) return;

        const userMessage: Message = {
            role: "user",
            content: message,
            attached_files: files.map(f => ({
                name: f.name,
                size: f.size,
                type: f.type
            }))
        };
        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setLoading(true);
        setStatusText("Thinking...");
        setElapsedTime(0);
        const startTime = Date.now();
        const timerInterval = setInterval(() => {
            setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
        }, 1000);

        try {
            const formData = new FormData();
            formData.append("message", message);
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

    return (
        <div className="flex h-full">
            <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Header */}
                <div className="bg-gray-900 border-b border-gray-800 p-6 flex items-center justify-between flex-shrink-0">
                    <div className="min-w-0 pr-4">
                        <h1 className="text-2xl font-bold text-cyan-400 truncate" title={`${displayName} Spoke`}>
                            {displayName} Spoke
                        </h1>
                        <p className="text-gray-400 text-sm mt-1 truncate">Deep work and specialized execution</p>
                    </div>
                    <div className="flex gap-2">
                        <Link href={`/spokes/${spokeName}/settings`}
                            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                            ⚙️ Settings
                        </Link>
                        <button onClick={() => setShowSidebar(!showSidebar)}
                            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
                            {showSidebar ? "Hide" : "Show"} Files
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

                        {messages.map((msg, idx) => (
                            <MessageWithAttachments key={idx} role={msg.role} content={msg.content} attached_files={msg.attached_files} tool_calls={msg.tool_calls} />
                        ))}

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
                    <div className="border-t border-gray-800 bg-gray-900/95 p-4 flex-shrink-0">
                        <CommandAutocomplete value={input} onChange={setInput}
                            onSubmit={() => sendMessage(input, [])}
                            placeholder="" context="spoke" disabled={loading} />
                    </div>
                )}

                {/* Input - Fixed at bottom */}
                <div className="pb-8 px-4">
                    <div className="max-w-4xl mx-auto flex flex-col min-h-0">
                        <ChatInput
                            value={input}
                            onChange={setInput}
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
