"use client";

import { useState, memo } from "react";
import { Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Share2, MoreHorizontal, MessageSquarePlus, Volume2, Pencil, Trash2, Bot, Loader2, ChevronDown, Wrench, Sparkles } from "lucide-react";
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
    args?: any;
    result: string;
    is_success: boolean;
}

interface SubMessage {
    sub_id: string;
    content: string;
    tool_calls: ToolCall[];
    timestamp?: string;
    meta_info?: any;
}

interface MessageWithAttachmentsProps {
    role: "user" | "assistant";
    content: string;
    attached_files?: MessageAttachment[];
    type?: "llm" | "system";
    tool_calls?: ToolCall[];  // Legacy support
    sub_messages?: SubMessage[]; // New structured format
    nodeType?: string;
    nodeName?: string;
    approvalStatuses?: Record<string, string>; // Map of requestId -> status
    onSend?: (content: string) => void;
    onApprove?: (requestId: string, approved: boolean) => void;
    onRegenerate?: () => void;
    onBranch?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
    onOpenLocalLink?: (href: string) => void;
}

const AsyncReport = ({ content, headerText, nodeType, nodeName, onOpenLocalLink }: { content: string, headerText: string, nodeType: string, nodeName: string, onOpenLocalLink?: (href: string) => void }) => {
    const [isReportExpanded, setIsReportExpanded] = useState(false);
    return (
        <div className="my-2 w-full max-w-full rounded-xl border border-gray-700/50 bg-gray-950/50 overflow-hidden shadow-inner font-sans">
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
                    <ChevronDown size={16} />
                </div>
            </button>

            {isReportExpanded && (
                <div className="px-4 pb-4 border-t border-gray-800/50 pt-4 bg-black/20 w-full overflow-x-auto">
                    <div className="max-w-full">
                        <MarkdownRenderer content={content} nodeType={nodeType} nodeName={nodeName} onOpenLocalLink={onOpenLocalLink} />
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
    tool_calls = [],
    sub_messages = [],
    nodeType = "hub",
    nodeName = "hub",
    approvalStatuses = {},
    onSend,
    onApprove,
    onRegenerate,
    onBranch,
    onEdit,
    onDelete,
    onOpenLocalLink
}: MessageWithAttachmentsProps) {
    const [stepsExpanded, setStepsExpanded] = useState(false);
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
        } catch (e) {
            setProcessingAction({ id: '', type: null });
        }
    };

    const downloadFile = async (url: string, filename: string) => {
        try {
            const token = await getFileToken();
            const downloadUrl = `${url}${url.includes('?') ? '&' : '?'}token=${token}`;
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
                return <span className="text-green-400 text-xs font-bold flex items-center gap-1 font-sans">✅ Approved</span>;
            case "rejected":
                return <span className="text-red-400 text-xs font-bold flex items-center gap-1 font-sans">❌ Rejected</span>;
            case "failed":
                return <span className="text-orange-400 text-xs font-bold flex items-center gap-1 font-sans">⚠️ Failed</span>;
            default:
                return null;
        }
    };

    return (
        <div className={`flex gap-3 mb-6 ${role === "user" ? "justify-end" : "justify-center"} animate-in fade-in slide-in-from-bottom-2 duration-300 font-sans`}>
            <div className={`max-w-[85%] min-w-0 flex flex-col group ${role === "user" ? "items-end" : "items-start"}`}>
                <div className={`relative w-full ${role === "user"
                    ? "bg-gradient-to-br from-indigo-600 to-purple-700 text-white rounded-2xl rounded-tr-sm shadow-lg shadow-purple-900/10 p-5 px-6"
                    : type === "system"
                        ? "bg-gray-900/80 backdrop-blur-md border border-blue-500/20 text-blue-100 rounded-2xl rounded-tl-sm shadow-xl p-5"
                        : "text-gray-100 p-5"
                    } transition-all`}
                >
                    {/* Final Response Content */}
                    <div className="prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-gray-950 prose-pre:border prose-pre:border-gray-800 break-words">
                        {role === "assistant" ? (
                            content ? (
                                content.match(/^(?:🤖|SYSTEM|Node)? ?(.+) has completed background work:/i) ? (
                                    (() => {
                                        const match = content.match(/^(?:🤖|SYSTEM|Node)? ?(.+) has completed background work:/i);
                                        const rawHeader = match ? match[0] : "System Report";
                                        const headerText = rawHeader.replace(/\*\*/g, "").replace(/^🤖\s*/, "");
                                        const bodyText = content.replace(match ? match[0] : "", "").trim();
                                        return <AsyncReport content={bodyText} headerText={headerText} nodeType={nodeType} nodeName={nodeName} onOpenLocalLink={onOpenLocalLink} />;
                                    })()
                                ) : (
                                    <MarkdownRenderer content={content} nodeType={nodeType} nodeName={nodeName} onOpenLocalLink={onOpenLocalLink} />
                                )
                            ) : sub_messages.length === 0 ? (
                                <span className="text-gray-500 italic font-medium flex items-center gap-2"><Bot size={14} /> Waiting for response...</span>
                            ) : null
                        ) : (
                            <div className="whitespace-pre-wrap break-words leading-relaxed text-[15px] font-medium tracking-tight">
                                {content.includes("[CANVAS_CONTEXT_START]")
                                    ? content.split("[CANVAS_CONTEXT_START]")[0].trim()
                                    : content}
                            </div>
                        )}
                    </div>

                    {/* Collapsible Thinking Steps - Moved to bottom */}
                    {role === "assistant" && sub_messages.length > 0 && (
                        <div className="mt-4">
                            <div className="rounded-2xl border border-gray-800/40 bg-gray-950/40 overflow-hidden shadow-sm transition-all hover:border-gray-700/40">
                                <button
                                    onClick={() => setStepsExpanded(!stepsExpanded)}
                                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-900/40 transition-colors group/steps"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="w-5 h-5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                                            <Sparkles size={12} className="text-amber-400/80" />
                                        </div>
                                        <span className="text-xs font-semibold text-gray-400 group-hover/steps:text-gray-300 transition-colors">Thinking Process</span>
                                        <span className="px-2 py-0.5 rounded-full bg-gray-900/80 text-[10px] text-gray-500 font-mono tracking-tight font-medium">
                                            {sub_messages.length} turn{sub_messages.length > 1 ? 's' : ''}
                                        </span>
                                    </div>
                                    <ChevronDown size={14} className={`text-gray-600 transition-transform duration-300 ${stepsExpanded ? "rotate-180" : ""}`} />
                                </button>

                                {stepsExpanded && (
                                    <div className="px-4 pb-5 space-y-5 pt-2 border-t border-gray-800/20 bg-black/10">
                                        {sub_messages.map((step, sIdx) => (
                                            <div key={sIdx} className="space-y-3">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[10px] font-black text-gray-700 uppercase tracking-[0.2em]">Step {sIdx + 1}</span>
                                                    <div className="h-[1px] flex-1 bg-gray-800/30" />
                                                </div>

                                                {step.content && (
                                                    <div className="text-[12px] text-gray-400 leading-relaxed pl-3 border-l-2 border-gray-800/40 py-1 font-normal opacity-90">
                                                        <MarkdownRenderer content={step.content} nodeType={nodeType} nodeName={nodeName} onOpenLocalLink={onOpenLocalLink} />
                                                    </div>
                                                )}



                                                {step.tool_calls.length > 0 && (
                                                    <div className="space-y-3 ml-2">
                                                        {step.tool_calls.map((tool, tIdx) => {
                                                            let isPendingApproval = false;
                                                            let requestId = "";
                                                            let currentStatus = "";

                                                            if (tool.name === "run_safe_shell") {
                                                                try {
                                                                    const parsed = typeof tool.result === 'string' ? JSON.parse(tool.result) : tool.result;
                                                                    if (parsed?.request_id) {
                                                                        requestId = parsed.request_id;
                                                                        currentStatus = approvalStatuses[requestId] || (parsed.status === "pending_approval" ? "pending" : "");
                                                                        isPendingApproval = currentStatus === "pending";
                                                                    }
                                                                } catch (e) { }
                                                            }

                                                            return (
                                                                <div key={tIdx} className="rounded-xl border border-gray-800/40 bg-gray-900/40 overflow-hidden shadow-sm">
                                                                    <div className="flex items-center gap-2.5 px-3.5 py-2 border-b border-gray-800/20 bg-gray-900/50">
                                                                        <Wrench size={12} className="text-purple-400/60" />
                                                                        <span className="text-[11px] font-mono font-bold text-purple-300/80">{tool.name}</span>
                                                                        <span className={`ml-auto px-2 py-0.5 rounded-lg text-[9px] uppercase font-black tracking-tight ${tool.is_success ? "bg-green-500/10 text-green-500/80" : "bg-red-500/10 text-red-500/80"}`}>
                                                                            {isPendingApproval ? "Approval Required" : tool.is_success ? "Success" : "Failed"}
                                                                        </span>
                                                                    </div>

                                                                    {tool.args && (
                                                                        <div className="px-3.5 py-1.5 text-[10px] font-mono text-gray-500 border-b border-gray-800/10 bg-black/10">
                                                                            <span className="opacity-40 select-none">args:</span> {JSON.stringify(tool.args)}
                                                                        </div>
                                                                    )}

                                                                    <div className="px-4 py-3 text-[12px] font-mono text-gray-400 bg-black/30 break-all whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed custom-scrollbar">
                                                                        {tool.result || "No response received"}
                                                                    </div>

                                                                    {isPendingApproval && requestId && onApprove && (
                                                                        <div className="px-3 py-2.5 bg-amber-500/5 flex gap-2 border-t border-amber-900/10">
                                                                            <button
                                                                                disabled={!!processingAction.id}
                                                                                onClick={() => handleAction(requestId, true)}
                                                                                className="flex-1 py-2 bg-green-500/15 hover:bg-green-500/25 text-green-400 border border-green-500/20 rounded-lg text-[11px] font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                                                                            >
                                                                                {processingAction.id === requestId && processingAction.type === 'approve' ? <Loader2 size={12} className="animate-spin" /> : "Approve Command"}
                                                                            </button>
                                                                            <button
                                                                                disabled={!!processingAction.id}
                                                                                onClick={() => handleAction(requestId, false)}
                                                                                className="flex-1 py-2 bg-red-500/15 hover:bg-red-500/25 text-red-400 border border-red-500/20 rounded-lg text-[11px] font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                                                                            >
                                                                                {processingAction.id === requestId && processingAction.type === 'reject' ? <Loader2 size={12} className="animate-spin" /> : "Reject"}
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}


                    {/* Legacy Tool Calls Section */}
                    {role === "assistant" && sub_messages.length === 0 && tool_calls.length > 0 && (
                        <div className="mt-5 pt-4 border-t border-gray-800/40">
                            <div className="rounded-2xl border border-gray-800/50 bg-gray-950/50 overflow-hidden shadow-inner">
                                <div className="px-4 py-2 bg-gray-900/30 border-b border-gray-800/30">
                                    <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest flex items-center gap-2">
                                        <Wrench size={10} /> Legacy Tool Reference
                                    </span>
                                </div>
                                <div className="p-4 space-y-4">
                                    {tool_calls.map((tool, idx) => (
                                        <div key={idx} className="space-y-1.5">
                                            <div className="flex items-center gap-2 text-[10px] font-mono">
                                                <span className="text-purple-400 font-bold">{tool.name}</span>
                                                <span className={`px-1.5 py-0.5 rounded-lg font-black tracking-tight ${tool.is_success ? "bg-green-500/10 text-green-500/80" : "bg-red-500/10 text-red-500/80"}`}>
                                                    {tool.is_success ? "DONE" : "FAIL"}
                                                </span>
                                            </div>
                                            <div className="text-[11px] text-gray-500 font-mono bg-black/30 p-2.5 rounded-xl border border-white/5 truncate opacity-80">
                                                {tool.result}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Attachments Section */}
                    {attached_files.length > 0 && (
                        <div className="mt-5 pt-5 border-t border-gray-800/30 grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {attached_files.map((file, index) => (
                                <div
                                    key={index}
                                    className={`flex items-center gap-3 p-3 rounded-2xl transition-all border ${role === "user"
                                        ? "bg-white/10 hover:bg-white/15 border-white/10"
                                        : "bg-gray-900/40 hover:bg-gray-900/60 border-gray-800/40"
                                        }`}
                                >
                                    <div className="text-xl drop-shadow-sm flex items-center justify-center w-10 h-10 rounded-xl bg-black/20">{getFileIcon(file.type)}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[13px] font-bold truncate tracking-tight">{file.name}</div>
                                        <div className="text-[10px] opacity-40 font-mono font-bold uppercase">{formatFileSize(file.size)}</div>
                                    </div>
                                    <button
                                        onClick={() => downloadFile(file.url || `/api/files/${nodeType}/${nodeName}/refs/${file.name}`, file.name)}
                                        className="p-2.5 hover:bg-white/10 rounded-xl transition-colors text-blue-400/80 hover:text-blue-300"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v4h16v-4m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Footer Action Bar */}
                <div className={`flex items-center gap-1 mt-2.5 px-1 opacity-0 group-hover:opacity-100 transition-all duration-300 ${role === "user" ? "justify-end" : "justify-start w-full"}`}>
                    <button onClick={handleCopy} className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all relative">
                        {isCopied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                    </button>
                    {onEdit && role === "user" && (
                        <button onClick={onEdit} className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all">
                            <Pencil size={14} />
                        </button>
                    )}
                    {onDelete && (
                        <button onClick={onDelete} className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-red-400/80 transition-all">
                            <Trash2 size={14} />
                        </button>
                    )}
                    {role === "assistant" && (
                        <>
                            <button className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"><ThumbsUp size={14} /></button>
                            <button className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"><ThumbsDown size={14} /></button>
                            {onRegenerate && <button onClick={onRegenerate} className="p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all"><RotateCcw size={14} /></button>}

                            <div className="relative">
                                <button
                                    onClick={() => setShowMoreMenu(!showMoreMenu)}
                                    className={`p-2 rounded-xl hover:bg-white/5 text-gray-500 hover:text-gray-300 transition-all ${showMoreMenu ? "bg-white/10 text-gray-200" : ""}`}
                                >
                                    <MoreHorizontal size={14} />
                                </button>
                                {showMoreMenu && (
                                    <div className="absolute bottom-full left-0 mb-3 w-52 bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl py-2 z-50 animate-in fade-in zoom-in-95 duration-200 origin-bottom-left">
                                        {onBranch && (
                                            <button
                                                onClick={() => { onBranch(); setShowMoreMenu(false); }}
                                                className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px] font-semibold text-gray-300 hover:bg-white/5 transition-colors"
                                            >
                                                <MessageSquarePlus size={16} className="text-purple-400" />
                                                <span>Branch to new context</span>
                                            </button>
                                        )}
                                        <button className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px] font-semibold text-gray-300 hover:bg-white/5 transition-colors">
                                            <Volume2 size={16} className="text-blue-400" />
                                            <span>Text to Speech</span>
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

const MessageWithAttachments = memo(MessageWithAttachmentsBase);
export default MessageWithAttachments;
