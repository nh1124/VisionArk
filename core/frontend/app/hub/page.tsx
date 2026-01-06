"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import CommandAutocomplete from "../components/CommandAutocomplete";
import FilesSidebar from "@/components/FilesSidebar";
import InboxView from "@/components/InboxView";
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
    type?: "llm" | "system";
    tool_calls?: Array<{ name: string; result: string; success: boolean }>;
}

export default function HubPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [showSidebar, setShowSidebar] = useState(false);
    const [selectedModel, setSelectedModel] = useState("gemini-2.5-flash-lite");
    const [view, setView] = useState<"chat" | "inbox">("chat");
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Derive showCommandHelp from input (no separate state needed)
    const showCommandHelp = useMemo(() => view === "chat" && input.trim().startsWith('/'), [input, view]);

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

        try {
            const formData = new FormData();
            formData.append("message", message);
            files.forEach((file) => {
                formData.append("files", file);
            });

            const response = await apiFetch("/api/agents/hub/chat", {
                method: "POST",
                body: formData,
                headers: {
                    "X-Preferred-Model": selectedModel
                }
            });

            const data = await response.json();
            const assistantMessage: Message = {
                role: "assistant",
                content: data.response,
                attached_files: data.attached_files || [],
                tool_calls: data.tool_calls || []
            };
            setMessages((prev) => [...prev, assistantMessage]);

            if (data.executed_commands && data.executed_commands.length > 0) {
                for (const cmd of data.executed_commands) {
                    const cmdMessage: Message = {
                        role: "assistant",
                        content: `💻 Executed: ${cmd.command}\n${cmd.success ? '✅' : '❌'} ${cmd.message}`,
                        type: "system"
                    };
                    setMessages((prev) => [...prev, cmdMessage]);

                    // Handle redirects (e.g., from /move)
                    if (cmd.success && cmd.data?.redirect_url) {
                        setTimeout(() => {
                            window.location.href = cmd.data.redirect_url;
                        }, 1000);
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
            setLoading(false);
        }
    };

    return (
        <div className="flex h-full">
            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Header */}
                <div className="bg-gray-900 border-b border-gray-800 p-6 flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-8">
                        <div>
                            <h1 className="text-2xl font-bold text-purple-400">Hub Agent (PM)</h1>
                            <p className="text-gray-400 text-sm mt-1">
                                Strategic guidance and LBS management
                            </p>
                        </div>

                        {/* View Toggle */}
                        <div className="flex bg-gray-800 rounded-lg p-1">
                            <button
                                onClick={() => setView("chat")}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${view === "chat"
                                    ? "bg-purple-600 text-white shadow-lg"
                                    : "text-gray-400 hover:text-gray-200"
                                    }`}
                            >
                                💬 Chat
                            </button>
                            <button
                                onClick={() => setView("inbox")}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${view === "inbox"
                                    ? "bg-purple-600 text-white shadow-lg"
                                    : "text-gray-400 hover:text-gray-200"
                                    }`}
                            >
                                📥 Inbox
                            </button>
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => setShowSidebar(!showSidebar)}
                            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors text-sm"
                        >
                            {showSidebar ? "Hide" : "Show"} Files
                        </button>
                    </div>
                </div>

                {view === "chat" ? (
                    <>
                        {/* Messages - Scrollable area with flex-1 */}
                        <div className="flex-1 overflow-y-auto px-4 py-8">
                            <div className="max-w-4xl mx-auto space-y-6">
                                {messages.length === 0 && (
                                    <div className="text-center text-gray-500 py-20">
                                        <div className="w-16 h-16 bg-purple-500/10 rounded-2xl flex items-center justify-center mx-auto mb-6">
                                            <span className="text-3xl">🧠</span>
                                        </div>
                                        <h2 className="text-3xl font-bold text-white mb-2">How can I help you today?</h2>
                                        <p className="text-gray-400">Ask about your workload, schedule, or strategic goals.</p>
                                        <p className="text-xs text-gray-600 mt-6 tracking-widest uppercase">
                                            Tip: Type / for command shortcuts
                                        </p>
                                    </div>
                                )}

                                {messages.map((msg, idx) => (
                                    <MessageWithAttachments
                                        key={idx}
                                        role={msg.role}
                                        content={msg.content}
                                        attached_files={msg.attached_files}
                                        type={msg.type}
                                        tool_calls={msg.tool_calls}
                                    />
                                ))}

                                {loading && (
                                    <div className="flex justify-start">
                                        <div className="bg-gray-800/40 border border-gray-700/50 rounded-2xl px-6 py-4 animate-pulse">
                                            <p className="text-sm text-gray-400">Thinking...</p>
                                        </div>
                                    </div>
                                )}
                                <div ref={messagesEndRef} />
                            </div>
                        </div>

                        {/* Command Help Overlay */}
                        {showCommandHelp && (
                            <div className="border-t border-gray-800 bg-gray-900/95 p-4 flex-shrink-0">
                                <CommandAutocomplete
                                    value={input}
                                    onChange={setInput}
                                    onSubmit={() => sendMessage(input, [])}
                                    placeholder=""
                                    context="hub"
                                    disabled={loading}
                                />
                            </div>
                        )}

                        {/* Input - Fixed at bottom */}
                        <div className="pb-8 px-4">
                            <div className="max-w-4xl mx-auto flex flex-col min-h-0">
                                <ChatInput
                                    value={input}
                                    onChange={setInput}
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

            {/* Sidebar - Files & Artifacts */}
            {showSidebar && (
                <div className="w-80 bg-gray-900 border-l border-gray-800 p-4 flex-shrink-0">
                    <FilesSidebar nodeType="hub" nodeName="hub" />
                </div>
            )}
        </div>
    );
}
