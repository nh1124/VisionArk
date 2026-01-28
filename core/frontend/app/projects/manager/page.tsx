"use client";

import { useState, useEffect, useRef } from "react";
import { Send, Loader2, ClipboardList, Activity, ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import ChatInput from "@/components/ChatInput";
import MessageWithAttachments from "@/components/MessageWithAttachments";
import { useNotification } from "@/lib/NotificationContext";

interface Message {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    created_at: string;
    meta_payload?: any;
}

export default function ProjectManagerPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(false);
    const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
    const router = useRouter();
    const { showToast } = useNotification();
    const pollInterval = useRef<NodeJS.Timeout | null>(null);

    // Initial greeting
    useEffect(() => {
        setMessages([
            {
                id: "initial",
                role: "assistant",
                content: "Hello! I am your Project Manager. I can help you monitor project health, update metadata, and oversee your entire workspace. How can I assist you today?",
                created_at: new Date().toISOString()
            }
        ]);
    }, []);

    const sendMessage = async (text: string) => {
        if (!text.trim()) return;

        const userMsg: Message = {
            id: Date.now().toString(),
            role: "user",
            content: text,
            created_at: new Date().toISOString()
        };
        setMessages(prev => [...prev, userMsg]);
        setLoading(true);

        try {
            const formData = new FormData();
            formData.append("message", text);

            const response = await apiFetch("/api/agents/system/project_manager/chat", {
                method: "POST",
                body: formData
            });

            if (!response.ok) throw new Error("Failed to send message");

            const data = await response.json();
            setActiveTaskId(data.task_id);
            startPolling(data.task_id);
        } catch (error) {
            console.error("Error sending message:", error);
            showToast("Failed to communicate with Project Manager", "error");
            setLoading(false);
        }
    };

    const startPolling = (taskId: string) => {
        if (pollInterval.current) clearInterval(pollInterval.current);

        pollInterval.current = setInterval(async () => {
            try {
                const response = await apiFetch(`/api/agents/tasks/${taskId}`);
                const data = await response.json();

                if (data.status === "completed") {
                    stopPolling();
                    const assistantMsg: Message = {
                        id: Date.now().toString(),
                        role: "assistant",
                        content: data.result || "Action completed.",
                        created_at: new Date().toISOString()
                    };
                    setMessages(prev => [...prev, assistantMsg]);
                    setLoading(false);
                } else if (data.status === "failed") {
                    stopPolling();
                    showToast("Task failed: " + data.error, "error");
                    setLoading(false);
                }
            } catch (error) {
                console.error("Polling error:", error);
            }
        }, 2000);
    };

    const stopPolling = () => {
        if (pollInterval.current) {
            clearInterval(pollInterval.current);
            pollInterval.current = null;
        }
    };

    return (
        <div className="flex flex-col h-screen bg-[#0a0a0b] text-gray-100">
            {/* Header */}
            <header className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-900/50 backdrop-blur-md">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.push("/projects")}
                        className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h1 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
                            <span className="text-2xl">✦</span> Project Manager
                        </h1>
                        <p className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">System Intelligence</p>
                    </div>
                </div>

                <div className="flex items-center gap-6">
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-gray-500 font-bold uppercase tracking-tighter">System Status</span>
                        <div className="flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
                            <span className="text-xs font-mono text-green-500/80">OPTIMAL</span>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Chat Area */}
            <main className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
                <div className="max-w-4xl mx-auto w-full space-y-8 pb-24">
                    {messages.map((msg) => (
                        <MessageWithAttachments
                            key={msg.id}
                            role={msg.role === "system" ? "assistant" : msg.role as "user" | "assistant"}
                            content={msg.content}
                            attached_files={msg.meta_payload?.attached_files || []}
                            tool_calls={msg.meta_payload?.tool_calls || []}
                            type={msg.role === "system" ? "system" : "llm"}
                            nodeType="system"
                            nodeName="project_manager"
                        />
                    ))}
                    {loading && !messages.some(m => m.id === "loading") && (
                        <div className="flex items-center gap-3 text-cyan-500/70 p-4 animate-pulse">
                            <Loader2 size={18} className="animate-spin" />
                            <span className="text-sm font-medium italic">Analyzing system state...</span>
                        </div>
                    )}
                </div>
            </main>

            {/* Input Area */}
            <div className="p-6 border-t border-gray-800 bg-gray-900/30 backdrop-blur-xl">
                <div className="max-w-4xl mx-auto w-full">
                    <ChatInput
                        onSend={sendMessage}
                        disabled={loading}
                        placeholder="Ask the Project Manager to list projects, check health, or update status..."
                    />
                    <div className="mt-4 flex flex-wrap gap-2">
                        {["List all projects", "Summarize health", "Are there any delays?"].map(suggestion => (
                            <button
                                key={suggestion}
                                onClick={() => sendMessage(suggestion)}
                                className="px-3 py-1 bg-gray-800/50 hover:bg-cyan-500/10 border border-gray-700/50 hover:border-cyan-500/30 rounded-full text-[10px] text-gray-400 hover:text-cyan-400 transition-all"
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
