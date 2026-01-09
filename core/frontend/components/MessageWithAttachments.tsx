"use client";

import { useState, memo } from "react";
import { Copy, Check } from "lucide-react";
import { getFileToken } from "@/lib/api";
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
    nodeType?: string;
    nodeName?: string;
}

function MessageWithAttachmentsBase({
    role,
    content,
    attached_files = [],
    type = "llm",
    tool_calls = [], // Use API-provided tool_calls
    nodeType = "hub",
    nodeName = "hub"
}: MessageWithAttachmentsProps) {
    const [toolsExpanded, setToolsExpanded] = useState(true);
    const [isCopied, setIsCopied] = useState(false);

    const handleCopy = () => {
        if (!content) return;
        navigator.clipboard.writeText(content);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    const downloadFile = async (url: string, filename: string) => {
        try {
            const token = await getFileToken();
            const downloadUrl = `${url}${url.includes('?') ? '&' : '?'}token=${token}`;

            // Create a temporary link and click it to trigger download
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error("Download failed:", error);
        }
    };

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
                className={`max-w-[85%] relative group ${role === "user"
                    ? "bg-gradient-to-br from-purple-600 to-purple-800 text-white rounded-2xl rounded-tr-sm shadow-lg shadow-purple-900/20 p-5"
                    : type === "system"
                        ? "bg-gray-900/80 backdrop-blur-md border border-blue-500/30 text-blue-100 rounded-2xl rounded-tl-sm shadow-xl p-5"
                        : "text-gray-100 p-2"
                    } transition-all`}
            >
                {/* Copy Button Overlay */}
                <div className={`absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2 ${isCopied ? "opacity-100" : ""}`}>
                    {isCopied && (
                        <span className="text-[10px] bg-gray-950 text-gray-300 px-1.5 py-0.5 rounded border border-gray-800 shadow-xl whitespace-nowrap transition-all duration-200 opacity-100">
                            Copied!
                        </span>
                    )}
                    <button
                        onClick={handleCopy}
                        className={`p-1.5 rounded-lg backdrop-blur-md border transition-all duration-200 ${role === "user"
                            ? "bg-white/10 border-white/20 hover:bg-white/20 text-white"
                            : "bg-gray-800/50 border-gray-700/50 hover:bg-gray-700/50 text-gray-400 hover:text-white"
                            }`}
                        title="Copy message"
                    >
                        {isCopied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                    </button>
                </div>

                {/* Message Content - AI Response */}
                <div className="prose prose-invert max-w-none">
                    {role === "assistant" ? (
                        content ? (
                            <MarkdownRenderer content={content} nodeType={nodeType} nodeName={nodeName} />
                        ) : tool_calls.length === 0 ? (
                            <span className="text-gray-400 italic">(No response)</span>
                        ) : null
                    ) : (
                        <div className="whitespace-pre-wrap break-words leading-relaxed">{content}</div>
                    )}
                </div>

                {/* Attachments */}
                {attached_files.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-gray-700/30 space-y-2">
                        <p className="text-[10px] uppercase tracking-wider text-gray-500 font-bold mb-2">Attached Files</p>
                        {attached_files.map((file, index) => (
                            <div
                                key={index}
                                className={`flex items-center gap-3 p-3 rounded-xl transition-colors ${role === "user"
                                    ? "bg-white/10 hover:bg-white/20"
                                    : "bg-gray-900/50 hover:bg-gray-900/80 border border-gray-700/50"
                                    }`}
                            >
                                <div className="text-2xl drop-shadow-sm">{getFileIcon(file.type)}</div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-semibold truncate">
                                        {file.name}
                                    </div>
                                    <div className="text-[11px] opacity-60 font-mono">
                                        {formatFileSize(file.size)}
                                    </div>
                                </div>
                                {file.url ? (
                                    <button
                                        onClick={() => downloadFile(file.url!, file.name)}
                                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-blue-400"
                                        title="Download file"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v12m0 0l-4-4m4 4l4-4M4 16h16" />
                                        </svg>
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => downloadFile(`/api/files/${nodeType}/${nodeName}/refs/${file.name}`, file.name)}
                                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 group-hover:text-blue-400"
                                        title="Download from storage"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v12m0 0l-4-4m4 4l4-4M4 16h16" />
                                        </svg>
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Tool Calls Section - Now at the bottom */}
                {role === "assistant" && tool_calls.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-gray-700/30">
                        <div className="rounded-xl border border-gray-700/50 bg-gray-950/50 overflow-hidden shadow-inner">
                            <button
                                onClick={() => setToolsExpanded(!toolsExpanded)}
                                className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-900/50 transition-colors group"
                            >
                                <div className="flex items-center gap-3">
                                    <div className="w-6 h-6 rounded-md bg-purple-500/20 border border-purple-500/30 flex items-center justify-center">
                                        <span className="text-xs">🔧</span>
                                    </div>
                                    <span className="text-sm font-semibold text-gray-300 group-hover:text-purple-400 transition-colors">Internal Operations</span>
                                    <span className="px-2 py-0.5 rounded-full bg-gray-800 text-[10px] text-gray-500 font-mono">
                                        {tool_calls.length} steps
                                    </span>
                                </div>
                                <span className={`text-gray-500 text-xs transition-transform duration-200 ${toolsExpanded ? "rotate-180" : ""}`}>
                                    ▼
                                </span>
                            </button>

                            {toolsExpanded && (
                                <div className="px-4 pb-4 space-y-3 pt-1 border-t border-gray-800/50">
                                    {tool_calls.map((tool, idx) => (
                                        <div key={idx} className="flex flex-col gap-1">
                                            <div className="flex items-center gap-2 text-[11px] font-mono">
                                                <span className="text-purple-500/60 font-bold">EXEC</span>
                                                <span className="text-cyan-400 font-semibold">{tool.name}</span>
                                                <span className={`ml-auto px-1.5 py-0.5 rounded text-[9px] uppercase font-bold ${tool.success ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"}`}>
                                                    {tool.success ? "Success" : "Failed"}
                                                </span>
                                            </div>
                                            <div className="pl-4 border-l border-gray-800 ml-1 mt-1">
                                                <div className="text-[12px] text-gray-500 font-mono line-clamp-2 hover:line-clamp-none transition-all cursor-pointer bg-gray-900/50 p-2 rounded-lg border border-gray-800/30">
                                                    {tool.result}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {role === "user" && (
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-600 to-cyan-400 flex items-center justify-center text-white font-black flex-shrink-0 shadow-lg shadow-cyan-900/20 text-xs tracking-tighter">
                    YOU
                </div>
            )}
        </div>
    );
}

// Memoize to prevent re-renders when parent state changes
const MessageWithAttachments = memo(MessageWithAttachmentsBase);
export default MessageWithAttachments;

