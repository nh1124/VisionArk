"use client";

import { useState, memo } from "react";
import { Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Share2, MoreHorizontal, MessageSquarePlus, Volume2, Pencil, Trash2, Bot, Loader2 } from "lucide-react";
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
    is_success: boolean;
}

interface MessageWithAttachmentsProps {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    type?: "llm" | "system";
    tool_calls?: ToolCall[];  // Received from API
    nodeType?: string;
    nodeName?: string;
    approvalStatuses?: Record<string, string>; // Map of requestId -> status
    onSend?: (content: string) => void;
    onApprove?: (requestId: string, approved: boolean) => void;
    onRegenerate?: () => void;
    onBranch?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
}

const AsyncReport = ({ content, headerText, nodeType, nodeName }: { content: string, headerText: string, nodeType: string, nodeName: string }) => {
    const [isReportExpanded, setIsReportExpanded] = useState(false);
    return (
        <div className="my-2 w-full max-w-full rounded-xl border border-gray-700/50 bg-gray-950/50 overflow-hidden shadow-inner">
            <button
                onClick={() => setIsReportExpanded(!isReportExpanded)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-900/50 transition-colors text-left group"
            >
                <div className="w-6 h-6 rounded-md bg-blue-500/20 border border-blue-500/30 flex items-center justify-center shrink-0">
                    <Bot size={14} className="text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-gray-200 truncate group-hover:text-blue-400 transition-colors">{headerText}</h4>
                </div>
                <div className={`text-gray-500 transition-transform duration-200 ${isReportExpanded ? "rotate-180" : ""}`}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M6 9l6 6 6-6" />
                    </svg>
                </div>
            </button>

            {isReportExpanded && (
                <div className="px-4 pb-4 border-t border-gray-800/50 pt-4 bg-black/20 w-full overflow-x-auto">
                    <div className="max-w-full">
                        <MarkdownRenderer content={content} nodeType={nodeType} nodeName={nodeName} />
                    </div>
                </div>
            )}
        </div>
    );
};

function MessageWithAttachmentsBase({
    role,
    content,
    attached_files = [],
    type = "llm",
    tool_calls = [], // Use API-provided tool_calls
    nodeType = "hub",
    nodeName = "hub",
    approvalStatuses = {},
    onSend,
    onApprove,
    onRegenerate,
    onBranch,
    onEdit,
    onDelete
}: MessageWithAttachmentsProps) {
    const [toolsExpanded, setToolsExpanded] = useState(true);
    const [isCopied, setIsCopied] = useState(false);
    const [showMoreMenu, setShowMoreMenu] = useState(false);
    const [processingAction, setProcessingAction] = useState<{ id: string, type: 'approve' | 'reject' | null }>({ id: '', type: null });

    const handleCopy = () => {
        if (!content) return;
        navigator.clipboard.writeText(content);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    const handleAction = async (requestId: string, approved: boolean) => {
        if (!onApprove) return;
        setProcessingAction({ id: requestId, type: approved ? 'approve' : 'reject' });
        try {
            await onApprove(requestId, approved);
            // We usually don't need to clear it here because fetchHistory will re-render
            // but for safety if the re-render is slow:
        } finally {
            // Keep the loading state until the message is updated or if it fails
            // setProcessingAction({ id: '', type: null }); 
        }
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

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "approved":
            case "executed":
                return <span className="text-green-400 text-xs font-bold flex items-center gap-1">✅ Approved</span>;
            case "rejected":
                return <span className="text-red-400 text-xs font-bold flex items-center gap-1">❌ Rejected</span>;
            case "failed":
                return <span className="text-orange-400 text-xs font-bold flex items-center gap-1">⚠️ Failed</span>;
            default:
                return null;
        }
    };

    return (
        <div
            className={`flex gap-3 mb-4 ${role === "user" ? "justify-end" : "justify-center"
                }`}
        >

            <div className={`max-w-[85%] min-w-0 flex flex-col group ${role === "user" ? "items-end" : "items-start"}`}>
                <div
                    className={`relative w-full ${role === "user"
                        ? "bg-gradient-to-br from-purple-600 to-purple-800 text-white rounded-2xl rounded-tr-sm shadow-lg shadow-purple-900/20 p-5"
                        : type === "system"
                            ? "bg-gray-900/80 backdrop-blur-md border border-blue-500/30 text-blue-100 rounded-2xl rounded-tl-sm shadow-xl p-5"
                            : "text-gray-100 p-5"
                        } transition-all`}
                >
                    {/* Message Content - AI Response */}
                    <div className="prose prose-invert max-w-none overflow-hidden break-words">
                        {role === "assistant" ? (
                            content ? (
                                // Check for Async Report Pattern
                                content.match(/^(?:🤖|SYSTEM|Node)? ?(.+) has completed background work:/i) ? (
                                    (() => {
                                        const match = content.match(/^(?:🤖|SYSTEM|Node)? ?(.+) has completed background work:/i);
                                        // Clean up header text (remove markdown bolding)
                                        const rawHeader = match ? match[0] : "System Report";
                                        const headerText = rawHeader.replace(/\*\*/g, "").replace(/^🤖\s*/, "");
                                        const bodyText = content.replace(match ? match[0] : "", "").trim();

                                        return <AsyncReport content={bodyText} headerText={headerText} nodeType={nodeType} nodeName={nodeName} />;
                                    })()
                                ) : (
                                    <MarkdownRenderer content={content} nodeType={nodeType} nodeName={nodeName} />
                                )
                            ) : tool_calls.length === 0 ? (
                                <span className="text-gray-400 italic">(No response)</span>
                            ) : null
                        ) : (
                            <div className="whitespace-pre-wrap break-words leading-relaxed">
                                {content.includes("[CANVAS_CONTEXT_START]")
                                    ? content.split("[CANVAS_CONTEXT_START]")[0].trim()
                                    : content}
                            </div>
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
                                        {tool_calls.map((tool, idx) => {
                                            let isPendingApproval = false;
                                            let requestId = "";
                                            let commandToApprove = "";
                                            let currentStatus = "";

                                            if (tool.name === "run_safe_shell") {
                                                try {
                                                    const parsed = JSON.parse(tool.result);

                                                    // Check live status map first (priority)
                                                    if (parsed.request_id && approvalStatuses[parsed.request_id]) {
                                                        const liveStatus = approvalStatuses[parsed.request_id];
                                                        currentStatus = liveStatus;
                                                        isPendingApproval = liveStatus === "pending";
                                                        requestId = parsed.request_id;
                                                    }
                                                    // Fallback to embedded status if no live update
                                                    else if (parsed.status === "pending_approval") {
                                                        isPendingApproval = true;
                                                        currentStatus = "pending";
                                                        commandToApprove = parsed.command;
                                                        requestId = parsed.request_id;
                                                    }
                                                } catch (e) {
                                                    // Fallback for non-JSON results (Legacy or Error)
                                                }
                                            }

                                            return (
                                                <div key={idx} className="flex flex-col gap-1">
                                                    <div className="flex items-center gap-2 text-[11px] font-mono">
                                                        <span className="text-purple-500/60 font-bold">EXEC</span>
                                                        <span className="text-cyan-400 font-semibold">{tool.name}</span>
                                                        <span className={`ml-auto px-1.5 py-0.5 rounded text-[9px] uppercase font-bold ${tool.is_success ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"}`}>
                                                            {isPendingApproval ? "Approval Required" : tool.is_success ? "Success" : "Failed"}
                                                        </span>
                                                    </div>
                                                    <div className="pl-4 border-l border-gray-800 ml-1 mt-1">
                                                        <div className="text-[12px] text-gray-500 font-mono line-clamp-2 hover:line-clamp-none transition-all cursor-pointer bg-gray-900/50 p-2 rounded-lg border border-gray-800/30">
                                                            {tool.result}
                                                        </div>

                                                        {isPendingApproval && requestId && onApprove ? (
                                                            <div className="mt-3 flex gap-2">
                                                                <button
                                                                    disabled={processingAction.id === requestId}
                                                                    onClick={() => handleAction(requestId, true)}
                                                                    className="px-4 py-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/30 rounded-lg text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                    {processingAction.id === requestId && processingAction.type === 'approve' ? (
                                                                        <Loader2 size={14} className="animate-spin" />
                                                                    ) : (
                                                                        <span>✅ Approve</span>
                                                                    )}
                                                                </button>
                                                                <button
                                                                    disabled={processingAction.id === requestId}
                                                                    onClick={() => handleAction(requestId, false)}
                                                                    className="px-4 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 rounded-lg text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                                                >
                                                                    {processingAction.id === requestId && processingAction.type === 'reject' ? (
                                                                        <Loader2 size={14} className="animate-spin" />
                                                                    ) : (
                                                                        <span>❌ Reject</span>
                                                                    )}
                                                                </button>
                                                            </div>
                                                        ) : (
                                                            requestId && currentStatus && getStatusBadge(currentStatus) && (
                                                                <div className="mt-2">
                                                                    {getStatusBadge(currentStatus)}
                                                                </div>
                                                            )
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* User Action Bar */}
                {role === "user" && (
                    <div className="flex items-center gap-1 mt-1.5 mr-1 opacity-0 group-hover:opacity-100 transition-opacity justify-end">
                        {onEdit && (
                            <button
                                onClick={onEdit}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"
                                title="Edit message"
                            >
                                <Pencil size={14} />
                            </button>
                        )}
                        {onDelete && (
                            <button
                                onClick={onDelete}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-red-400/80 transition-all"
                                title="Delete message"
                            >
                                <Trash2 size={14} />
                            </button>
                        )}
                        <button
                            onClick={handleCopy}
                            className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"
                            title="Copy"
                        >
                            {isCopied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                        </button>
                    </div>
                )}

                {/* Assistant Action Bar - Adding Delete here too */}
                {role === "assistant" && (
                    <div className="flex items-center justify-start gap-1 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity w-full">
                        <button
                            onClick={handleCopy}
                            className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all relative group/btn"
                            title="Copy"
                        >
                            {isCopied ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
                            {isCopied && (
                                <span className="absolute -top-8 left-1/2 -translate-x-1/2 text-[10px] bg-gray-950 text-gray-300 px-1.5 py-0.5 rounded border border-gray-800 shadow-xl whitespace-nowrap">
                                    Copied!
                                </span>
                            )}
                        </button>
                        {onDelete && (
                            <button
                                onClick={onDelete}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-red-400/80 transition-all"
                                title="Delete response"
                            >
                                <Trash2 size={16} />
                            </button>
                        )}
                        <button className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all" title="Good response">
                            <ThumbsUp size={16} />
                        </button>
                        <button className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all" title="Bad response">
                            <ThumbsDown size={16} />
                        </button>
                        <button className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all" title="Share">
                            <Share2 size={16} />
                        </button>
                        {onRegenerate && (
                            <button
                                onClick={onRegenerate}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"
                                title="Regenerate"
                            >
                                <RotateCcw size={16} />
                            </button>
                        )}
                        <div className="relative">
                            <button
                                onClick={() => setShowMoreMenu(!showMoreMenu)}
                                className={`p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all ${showMoreMenu ? "bg-white/10 text-gray-200" : ""}`}
                                title="More"
                            >
                                <MoreHorizontal size={16} />
                            </button>
                            {showMoreMenu && (
                                <div className="absolute bottom-full left-0 mb-2 w-48 bg-gray-900 border border-gray-800 rounded-xl shadow-2xl py-1.5 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
                                    {onBranch && (
                                        <button
                                            onClick={() => {
                                                onBranch();
                                                setShowMoreMenu(false);
                                            }}
                                            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-white/5 transition-colors"
                                        >
                                            <MessageSquarePlus size={16} className="text-purple-400" />
                                            <span>Branch to new chat</span>
                                        </button>
                                    )}
                                    <button className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-300 hover:bg-white/5 transition-colors">
                                        <Volume2 size={16} className="text-blue-400" />
                                        <span>Read aloud</span>
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

        </div >
    );
}

// Memoize to prevent re-renders when parent state changes
const MessageWithAttachments = memo(MessageWithAttachmentsBase);
export default MessageWithAttachments;
