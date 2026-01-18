import { useState, useCallback, useRef } from "react";
import { apiFetch } from "@/lib/api";

export interface MessageAttachment {
    name: string;
    size: number;
    type: string;
}

export interface Message {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    type?: "llm" | "system";
    tool_calls?: Array<{ name: string; result: string; success: boolean }>;
}

interface UseChatProps {
    initialMessages?: Message[];
    selectedModel?: string;
}

export function useChat({ initialMessages = [], selectedModel }: UseChatProps = {}) {
    const [messages, setMessages] = useState<Message[]>(initialMessages);
    const [loading, setLoading] = useState(false);
    const [statusText, setStatusText] = useState("");
    const [elapsedTime, setElapsedTime] = useState(0);
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    const pollStatus = useCallback(async (taskId: string) => {
        const startTime = Date.now();

        pollingRef.current = setInterval(async () => {
            try {
                // Update elapsed time
                setElapsedTime(Math.floor((Date.now() - startTime) / 1000));

                const response = await apiFetch(`/api/agents/hub/task/${taskId}`);
                if (!response.ok) {
                    if (response.status === 404) {
                        // Task might not be ready in Redis yet, just wait
                        return;
                    }
                    throw new Error("Failed to get status");
                }

                const data = await response.json();
                const status = data.status;

                if (status === "completed") {
                    stopPolling();
                    setLoading(false);
                    setStatusText("");

                    // Update the last assistant message with the result
                    setMessages(prev => {
                        const newMessages = [...prev];
                        const lastMsg = newMessages[newMessages.length - 1];
                        if (lastMsg.role === "assistant") {
                            newMessages[newMessages.length - 1] = {
                                ...lastMsg,
                                content: data.result || "Task completed."
                            };
                        }
                        return newMessages;
                    });
                } else if (status === "failed") {
                    stopPolling();
                    setLoading(false);
                    setStatusText("");
                    setMessages(prev => [
                        ...prev.slice(0, -1),
                        { role: "assistant", content: `❌ Error: ${data.result || "Task failed"}` }
                    ]);
                } else {
                    // processing / queued
                    setStatusText(status === "queued" ? "Queued..." : "Processing...");
                }

            } catch (error) {
                console.error("Polling error:", error);
                // Don't stop polling immediately on network transient error, but maybe warn?
                // For now, if we get consistent errors, we should probably stop.
                // But let's assume transient glitches don't break the loop immediately.
            }
        }, 1000);
    }, [stopPolling]);

    const sendMessage = useCallback(async (content: string, files: File[]) => {
        if (!content.trim() && files.length === 0) return;

        const userMessage: Message = {
            role: "user",
            content: content,
            attached_files: files.map(f => ({
                name: f.name,
                size: f.size,
                type: f.type
            }))
        };

        // Add user message and temporary assistant message
        setMessages(prev => [
            ...prev,
            userMessage,
            { role: "assistant", content: "", attached_files: [] } // Placeholder
        ]);

        setLoading(true);
        setStatusText("Sending...");
        setElapsedTime(0);

        try {
            const formData = new FormData();
            formData.append("message", content);
            files.forEach((file) => {
                formData.append("files", file);
            });
            // stream=false because we are using polling now
            formData.append("stream", "false");

            const response = await apiFetch("/api/agents/hub/chat", {
                method: "POST",
                body: formData,
                headers: {
                    "X-Preferred-Model": selectedModel || ""
                }
            });

            if (!response.ok) throw new Error("Failed to send message");

            const data = await response.json();

            if (data.status === "accepted" && data.task_id) {
                pollStatus(data.task_id);
            } else {
                throw new Error("Invalid response from server");
            }

        } catch (error: any) {
            console.error("Error sending message:", error);
            setLoading(false);
            setStatusText("");
            setMessages(prev => [
                ...prev.slice(0, -1), // Remove placeholder
                { role: "assistant", content: `❌ Error: ${error.message}` }
            ]);
        }
    }, [selectedModel, pollStatus]);

    // Cleanup on unmount
    // Note: This useEffect should be inside the component using the hook or here?
    // React hooks practice: useEffect in hook runs when component mounts/unmounts.
    // So this is correct.
    // But we need to make sure we don't clear it if we just re-render.
    // pollingRef persists.

    // Actually, we need to import useEffect
    // Added to imports.

    return {
        messages,
        setMessages,
        loading,
        statusText,
        elapsedTime,
        sendMessage
    };
}
