"use client";

import { useState, useEffect, useRef } from "react";
import { Loader2, X, Sparkles, LayoutList } from "lucide-react";
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

export default function TaskAssistant() {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(false);
    const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
    const { showToast } = useNotification();
    const pollInterval = useRef<NodeJS.Timeout | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Initial greeting
    useEffect(() => {
        if (messages.length === 0) {
            setMessages([
                {
                    id: "initial",
                    role: "assistant",
                    content: "Hello! I am your Task Assistant. I can help you plan your day, break down complex tasks, and optimize your schedule. How can I help you today?",
                    created_at: new Date().toISOString()
                }
            ]);
        }
    }, [messages.length]);

    // Scroll to bottom
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, loading]);

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

            const response = await apiFetch("/api/agents/system/task_manager/chat", {
                method: "POST",
                body: formData
            });

            if (!response.ok) throw new Error("Failed to send message");

            const data = await response.json();
            setActiveTaskId(data.task_id);
            startPolling(data.task_id);
        } catch (error) {
            console.error("Error sending message:", error);
            showToast("Failed to communicate with Task Assistant", "error");
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
        <>
            {/* Floating Button */}
            <button
                onClick={() => setIsOpen(true)}
                className={`fixed bottom-6 right-24 w-12 h-12 rounded-full bg-blue-600/20 hover:bg-blue-600/40 border border-blue-500/30 text-blue-400 shadow-xl flex items-center justify-center transition-all hover:scale-110 active:scale-95 z-[100] backdrop-blur-md ${isOpen ? "opacity-0 scale-0 pointer-events-none" : "opacity-90 scale-100"}`}
                title="Task Assistant"
            >
                <LayoutList size={20} />
            </button>

            {/* Slide-over Panel */}
            <div
                className={`fixed inset-y-0 right-0 w-full sm:w-[450px] bg-gray-950 border-l border-white/10 shadow-2xl transition-transform duration-300 ease-in-out z-[110] flex flex-col ${isOpen ? "translate-x-0" : "translate-x-full"}`}
            >
                {/* Header */}
                <div className="p-4 border-b border-white/10 bg-gray-900/50 flex items-center justify-between backdrop-blur-md">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-500/20 rounded-xl">
                            <LayoutList size={18} className="text-blue-400" />
                        </div>
                        <div>
                            <h2 className="font-bold text-white text-sm">Task Assistant</h2>
                            <div className="flex items-center gap-1.5">
                                <span className="w-1 h-1 bg-blue-500 rounded-full animate-pulse"></span>
                                <span className="text-[9px] text-blue-500 font-bold uppercase tracking-widest">Active Partner</span>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setIsOpen(false)}
                            className="p-2 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-all"
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-hide">
                    {messages.map((msg) => (
                        <MessageWithAttachments
                            key={msg.id}
                            role={msg.role === "system" ? "assistant" : msg.role as "user" | "assistant"}
                            content={msg.content}
                            attached_files={msg.meta_payload?.attached_files || []}
                            tool_calls={msg.meta_payload?.tool_calls || []}
                            type={msg.role === "system" ? "system" : "llm"}
                            nodeType="system"
                            nodeName="task_manager"
                        />
                    ))}
                    {loading && (
                        <div className="flex items-center gap-3 text-blue-500/70 p-4 animate-pulse">
                            <Loader2 size={16} className="animate-spin" />
                            <span className="text-xs font-medium italic">Planning...</span>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-white/10 bg-gray-900/30 backdrop-blur-xl">
                    <ChatInput
                        onSend={sendMessage}
                        disabled={loading}
                        placeholder="Ask Task Assistant..."
                        compact
                    />
                    <div className="mt-3 flex flex-wrap gap-1.5">
                        {["Plan my day", "Break down task", "What's my load today?"].map(suggestion => (
                            <button
                                key={suggestion}
                                onClick={() => sendMessage(suggestion)}
                                className="px-2.5 py-1 bg-gray-800/50 hover:bg-blue-500/10 border border-gray-700/50 hover:border-blue-500/30 rounded-full text-[9px] text-gray-400 hover:text-blue-400 transition-all font-medium"
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Backdrop */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[105] transition-opacity duration-300"
                    onClick={() => setIsOpen(false)}
                />
            )}
        </>
    );
}
