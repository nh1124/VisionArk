"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface InboxMessage {
    id: number;
    source_spoke: string;
    message_type: string;
    payload: any;
    received_at: string;
}

export default function InboxView() {
    const [messages, setMessages] = useState<InboxMessage[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedMessage, setSelectedMessage] = useState<InboxMessage | null>(null);
    const [hubResponse, setHubResponse] = useState<string | null>(null);
    const [isHubThinking, setIsHubThinking] = useState(false);

    useEffect(() => {
        loadMessages();
    }, []);

    const loadMessages = async () => {
        try {
            const response = await apiFetch("/api/inbox/pending");
            const data = await response.json();
            setMessages(data);
        } catch (error) {
            console.error("Error loading inbox:", error);
        } finally {
            setLoading(false);
        }
    };

    const processMessage = async (messageId: number, action: string) => {
        setIsHubThinking(true);
        setHubResponse(null);
        try {
            const response = await apiFetch("/api/inbox/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_id: messageId, action }),
            });
            const data = await response.json();

            if (data.hub_notified) {
                setHubResponse(data.hub_response);
            }

            await loadMessages();
            if (action !== "accept") {
                setSelectedMessage(null);
            }
        } catch (error) {
            console.error("Error processing message:", error);
        } finally {
            setIsHubThinking(false);
        }
    };

    const handleAcceptAll = async () => {
        setIsHubThinking(true);
        setHubResponse(null);
        try {
            const response = await apiFetch("/api/inbox/accept-all", { method: "POST" });
            const data = await response.json();

            if (data.hub_notified) {
                setHubResponse(data.hub_response);
            }

            await loadMessages();
            setSelectedMessage(null);
        } catch (error) {
            console.error("Error accepting all:", error);
        } finally {
            setIsHubThinking(false);
        }
    };

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <p className="text-gray-400">Loading inbox...</p>
            </div>
        );
    }

    return (
        <div className="flex-1 flex overflow-hidden">
            {/* Message List */}
            <div className="w-1/3 border-r border-gray-800 overflow-y-auto">
                <div className="p-6 border-b border-gray-800">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-bold text-green-400">Hub Inbox</h2>
                            <p className="text-gray-400 text-sm mt-1">
                                {messages.length} pending requests
                            </p>
                        </div>
                        {messages.length > 0 && (
                            <button
                                onClick={handleAcceptAll}
                                className="bg-green-500 hover:bg-green-600 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                disabled={isHubThinking}
                            >
                                ✓ Accept All
                            </button>
                        )}
                    </div>
                </div>

                <div className="divide-y divide-gray-800">
                    {Array.isArray(messages) && messages.map((msg) => (
                        <div
                            key={msg.id}
                            onClick={() => {
                                setSelectedMessage(msg);
                                setHubResponse(null);
                            }}
                            className={`p-4 cursor-pointer hover:bg-gray-800/50 transition-colors ${selectedMessage?.id === msg.id ? "bg-gray-800/50" : ""
                                }`}
                        >
                            <div className="flex items-center justify-between mb-2">
                                <span className="font-semibold text-green-400">
                                    {msg.source_spoke}
                                </span>
                                <span className="text-xs text-gray-500">
                                    {new Date(msg.received_at).toLocaleTimeString()}
                                </span>
                            </div>
                            <p className="text-sm text-gray-400 truncate">
                                {msg.payload.summary || msg.message_type}
                            </p>
                        </div>
                    ))}

                    {(!messages || messages.length === 0) && (
                        <div className="p-8 text-center text-gray-500">
                            <p>No pending messages</p>
                            <p className="text-sm mt-2">All caught up! 🎉</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Message Detail */}
            <div className="flex-1 overflow-y-auto bg-gray-950/30 flex flex-col">
                <div className="flex-1 p-6">
                    {selectedMessage ? (
                        <>
                            <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 mb-6">
                                <div className="flex items-center justify-between mb-4">
                                    <h2 className="text-xl font-semibold">
                                        From: {selectedMessage.source_spoke}
                                    </h2>
                                    <span className="text-sm text-gray-400">
                                        {new Date(selectedMessage.received_at).toLocaleString()}
                                    </span>
                                </div>

                                <div className="mb-4">
                                    <p className="text-sm text-gray-400 mb-2">Summary:</p>
                                    <p className="text-gray-200">{selectedMessage.payload.summary}</p>
                                </div>

                                {selectedMessage.payload.request && (
                                    <div className="mb-4">
                                        <p className="text-sm text-gray-400 mb-2">Request:</p>
                                        <p className="text-yellow-400">{selectedMessage.payload.request}</p>
                                    </div>
                                )}

                                {selectedMessage.payload.lbs_updates && (
                                    <div className="mb-4">
                                        <p className="text-sm text-gray-400 mb-2">LBS Updates:</p>
                                        <pre className="bg-gray-800/50 p-4 rounded text-xs overflow-x-auto text-gray-300 border border-gray-700">
                                            {JSON.stringify(selectedMessage.payload.lbs_updates, null, 2)}
                                        </pre>
                                    </div>
                                )}
                            </div>

                            {/* Actions */}
                            {!hubResponse && !isHubThinking && (
                                <div className="flex gap-4">
                                    <button
                                        onClick={() => processMessage(selectedMessage.id, "accept")}
                                        className="flex-1 bg-green-600 hover:bg-green-500 px-6 py-3 rounded-lg font-medium transition-colors"
                                    >
                                        ✓ Accept
                                    </button>
                                    <button
                                        onClick={() => processMessage(selectedMessage.id, "reject")}
                                        className="flex-1 bg-red-600 hover:bg-red-500 px-6 py-3 rounded-lg font-medium transition-colors"
                                    >
                                        ✗ Reject
                                    </button>
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="flex items-center justify-center h-full text-gray-500">
                            <p>Select a message to view details</p>
                        </div>
                    )}
                </div>

                {/* Hub Analysis Overlay/Section */}
                {(isHubThinking || hubResponse) && (
                    <div className="p-6 border-t border-gray-800 bg-purple-900/10 backdrop-blur-md">
                        <div className="max-w-3xl mx-auto">
                            <div className="flex items-center gap-2 mb-4">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold bg-purple-600 ${isHubThinking ? "animate-pulse" : ""}`}>
                                    AI
                                </div>
                                <h3 className="font-semibold text-purple-400 text-sm italic">Hub Strategic Analysis</h3>
                            </div>

                            {isHubThinking ? (
                                <div className="space-y-3">
                                    <div className="h-3 bg-gray-800 rounded w-3/4 animate-pulse"></div>
                                    <div className="h-3 bg-gray-800 rounded w-5/6 animate-pulse"></div>
                                    <div className="h-3 bg-gray-800 rounded w-2/3 animate-pulse"></div>
                                </div>
                            ) : (
                                <div className="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed bg-blue-900/10 p-4 rounded-xl border border-blue-800/30">
                                    {hubResponse}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
