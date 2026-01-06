"use client";

import { useState, memo } from "react";
import MarkdownRenderer from "./MarkdownRenderer";

interface MessageAttachment {
    name: string;
    size: number;
    type: string;
    url?: string;
}

interface ToolCall {
    name: string;
    result: string;
    success: boolean;
}

interface MessageWithAttachmentsProps {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    type?: "llm" | "system";
    tool_calls?: ToolCall[];  // Received from API
}

function MessageWithAttachmentsBase({
    role,
    content,
    attached_files = [],
    type = "llm",
    tool_calls = []  // Use API-provided tool_calls
}: MessageWithAttachmentsProps) {
    const [toolsExpanded, setToolsExpanded] = useState(true);

    const formatFileSize = (bytes: number): string => {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    };

    const getFileIcon = (type: string): string => {
        if (type.startsWith("image/")) return "🖼️";
        if (type === "application/pdf") return "📄";
        if (type.startsWith("video/")) return "🎥";
        if (type.startsWith("audio/")) return "🎵";
        return "📎";
    };

    return (
        <div
            className={`flex gap-3 mb-4 ${role === "user" ? "justify-end" : "justify-start"
                }`}
        >
            {role === "assistant" && (
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0 ${type === "system" ? "bg-blue-600" : "bg-purple-600"
                    }`}>
                    {type === "system" ? "⚙️" : "AI"}
                </div>
            )}

            <div
                className={`max-w-[70%] ${role === "user"
                    ? "bg-purple-600 text-white rounded-2xl rounded-tr-sm"
                    : type === "system"
                        ? "bg-blue-900/50 border border-blue-700 text-blue-100 rounded-2xl rounded-tl-sm"
                        : "bg-gray-800 text-gray-100 rounded-2xl rounded-tl-sm"
                    } p-4`}
            >
                {/* Tool Calls Section - Collapsible with indentation */}
                {role === "assistant" && tool_calls.length > 0 && (
                    <div className="mb-3 border border-gray-700/50 rounded-lg overflow-hidden">
                        <button
                            onClick={() => setToolsExpanded(!toolsExpanded)}
                            className="w-full flex items-center gap-2 px-3 py-2 bg-gray-900/50 hover:bg-gray-900/70 transition-colors text-sm"
                        >
                            <span className="text-gray-400">
                                {toolsExpanded ? "▼" : "▶"}
                            </span>
                            <span className="text-purple-400 font-medium">🔧 Tool Calls</span>
                            <span className="text-gray-500 text-xs">({tool_calls.length})</span>
                        </button>

                        {toolsExpanded && (
                            <div className="px-3 py-2 bg-gray-900/30 space-y-1">
                                {tool_calls.map((tool, idx) => (
                                    <div key={idx} className="flex items-start gap-2 text-sm font-mono">
                                        <span className="text-gray-600 select-none">├─</span>
                                        <span className="text-cyan-400">{tool.name}</span>
                                        <span className="text-gray-500">→</span>
                                        <span className={tool.success ? "text-green-400" : "text-red-400"}>
                                            {tool.result}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Message Content - AI Response */}
                {role === "assistant" ? (
                    content ? (
                        <MarkdownRenderer content={content} />
                    ) : tool_calls.length === 0 ? (
                        <span className="text-gray-400">(No response)</span>
                    ) : null
                ) : (
                    <div className="whitespace-pre-wrap break-words">{content}</div>
                )}

                {/* Attachments */}
                {attached_files.length > 0 && (
                    <div className="mt-3 space-y-2">
                        {attached_files.map((file, index) => (
                            <div
                                key={index}
                                className={`flex items-center gap-2 p-2 rounded-lg ${role === "user"
                                    ? "bg-purple-700/50"
                                    : "bg-gray-700/50"
                                    }`}
                            >
                                <div className="text-xl">{getFileIcon(file.type)}</div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium truncate">
                                        {file.name}
                                    </div>
                                    <div className="text-xs opacity-70">
                                        {formatFileSize(file.size)}
                                    </div>
                                </div>
                                {file.url && (
                                    <a
                                        href={file.url}
                                        download={file.name}
                                        className="text-xs hover:underline opacity-70 hover:opacity-100"
                                    >
                                        Download
                                    </a>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {role === "user" && (
                <div className="w-8 h-8 rounded-full bg-cyan-600 flex items-center justify-center text-white font-bold flex-shrink-0">
                    You
                </div>
            )}
        </div>
    );
}

// Memoize to prevent re-renders when parent state changes
const MessageWithAttachments = memo(MessageWithAttachmentsBase);
export default MessageWithAttachments;

