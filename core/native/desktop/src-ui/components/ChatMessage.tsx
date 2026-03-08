import React, { useEffect, useRef, useState } from "react"
import { User, Bot, ChevronDown, ChevronUp, Sparkles, Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Trash2, MoreHorizontal, MessageSquarePlus, Pencil } from "lucide-react"
import type { ChatMessage as ChatMessageType } from "../lib/api"
import MarkdownRenderer from "./MarkdownRenderer"

export type MessageVote = "up" | "down" | null

interface Props {
    message: ChatMessageType
    projectId: string
    canRegenerate?: boolean
    canEdit?: boolean
    onRegenerate?: () => void
    onDelete?: () => void
    onEdit?: () => void
    onBranch?: () => void
    onVote?: (vote: MessageVote) => void
    vote?: MessageVote
    isEditing?: boolean
    editValue?: string
    onEditValueChange?: (value: string) => void
    onEditSubmit?: () => void
    onEditCancel?: () => void
}

export default function ChatMessage({
    message,
    projectId,
    canRegenerate = false,
    canEdit = false,
    onRegenerate,
    onDelete,
    onEdit,
    onBranch,
    onVote,
    vote = null,
    isEditing = false,
    editValue = "",
    onEditValueChange,
    onEditSubmit,
    onEditCancel,
}: Props) {
    const [thinkingOpen, setThinkingOpen] = useState(false)
    const [isCopied, setIsCopied] = useState(false)
    const [isExpanded, setIsExpanded] = useState(false)
    const [showMoreMenu, setShowMoreMenu] = useState(false)
    const menuRef = useRef<HTMLDivElement>(null)

    const isUser = message.role === "user"
    const contentStr = message.content || ""
    const isLongMessage = isUser && (contentStr.length > 800 || contentStr.split("\n").length > 15)

    const thinkingTurns = message.sub_messages?.length || 0

    const handleCopy = () => {
        if (!message.content) return
        navigator.clipboard.writeText(message.content)
        setIsCopied(true)
        setTimeout(() => setIsCopied(false), 2000)
    }

    const handleVote = (nextVote: Exclude<MessageVote, null>) => {
        if (!onVote) return
        onVote(vote === nextVote ? null : nextVote)
    }

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (!menuRef.current || menuRef.current.contains(e.target as Node)) return
            setShowMoreMenu(false)
        }

        document.addEventListener("mousedown", handler)
        return () => document.removeEventListener("mousedown", handler)
    }, [])

    return (
        <div className={`flex gap-3 py-4 group ${isUser ? "" : ""}`}>
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${isUser ? "bg-gray-800 text-gray-400" : "bg-cyan-500/20 text-cyan-400"
                }`}>
                {isUser ? <User size={16} /> : <Bot size={16} />}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0 select-text">
                <div className="text-xs font-semibold text-gray-500 mb-1 select-none">
                    {isUser ? "You" : "Assistant"}
                </div>
                <div className="text-sm relative">
                    {isUser && isEditing ? (
                        <div className="rounded-xl border border-cyan-500/40 bg-gray-900/60 p-3">
                            <textarea
                                value={editValue}
                                onChange={(e) => onEditValueChange?.(e.target.value)}
                                className="w-full min-h-[72px] bg-transparent text-sm text-gray-100 resize-none outline-none"
                                placeholder="Edit message..."
                            />
                            <div className="mt-2 flex items-center justify-end gap-2">
                                <button
                                    onClick={onEditCancel}
                                    className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={onEditSubmit}
                                    disabled={!editValue.trim()}
                                    className="px-3 py-1.5 rounded-lg text-xs bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 disabled:hover:bg-cyan-600 transition-colors"
                                >
                                    Update
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <div className={`transition-all duration-300 ${isLongMessage && !isExpanded ? "max-h-[300px] overflow-hidden relative" : ""}`}>
                                <MarkdownRenderer content={contentStr} nodeType="project" nodeName={projectId} projectId={projectId} />
                                {isLongMessage && !isExpanded && (
                                    <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-gray-950 to-transparent pointer-events-none" />
                                )}
                            </div>
                            {isLongMessage && (
                                <button
                                    onClick={() => setIsExpanded(!isExpanded)}
                                    className="mt-2 text-xs font-semibold text-cyan-500 hover:text-cyan-400 flex items-center gap-1"
                                >
                                    {isExpanded ? (
                                        <>Show Less <ChevronUp size={14} /></>
                                    ) : (
                                        <>Read More <ChevronDown size={14} /></>
                                    )}
                                </button>
                            )}
                        </>
                    )}
                </div>

                {/* Thinking Process */}
                {!isUser && thinkingTurns > 0 && (
                    <div className="mt-3">
                        <button
                            onClick={() => setThinkingOpen(!thinkingOpen)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/50 border border-gray-800 rounded-full text-xs text-gray-400 hover:text-gray-300 hover:bg-gray-900/80 transition-colors"
                        >
                            <Sparkles size={12} className="text-amber-400/80" />
                            <span className="font-medium text-gray-300">Thinking Process</span>
                            <span className="px-1.5 py-0.5 rounded-full bg-gray-950 text-[10px] text-gray-500 font-mono font-medium">{thinkingTurns} turns</span>
                        </button>
                    </div>
                )}

                {thinkingOpen && message.sub_messages && (
                    <div className="mt-2 pl-3 border-l-2 border-gray-800 space-y-4">
                        {message.sub_messages.map((sub: any, i: number) => (
                            <div key={i} className="text-xs text-gray-400 space-y-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest">Step {i + 1}</span>
                                </div>
                                {sub.content && (
                                    <div className="text-gray-400">
                                        <MarkdownRenderer content={sub.content} nodeType="project" nodeName={projectId} projectId={projectId} />
                                    </div>
                                )}
                                {sub.tool_calls?.map((tc: any, j: number) => (
                                    <div key={j} className="mt-2 text-gray-500 bg-gray-900/40 rounded-lg overflow-hidden border border-gray-800/50">
                                        <div className="px-3 py-2 border-b border-gray-800/50 flex items-center justify-between bg-gray-900/60">
                                            <div className="flex items-center gap-2">
                                                <span className="text-cyan-500 font-mono text-[11px] font-bold">{tc.name}</span>
                                                {tc.status === "running" && <span className="ml-2 text-blue-400 animate-pulse text-[10px]">running...</span>}
                                            </div>
                                            {tc.status !== "running" && (
                                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${tc.is_success ? "bg-green-500/10 text-green-500/80" : "bg-red-500/10 text-red-500/80"}`}>
                                                    {tc.is_success ? "Success" : "Failed"}
                                                </span>
                                            )}
                                        </div>
                                        {tc.args && Object.keys(tc.args).length > 0 && (
                                            <div className="px-3 py-1.5 border-b border-gray-800/30 text-[10px] bg-black/20 font-mono break-all text-gray-500">
                                                <span className="opacity-50">args: </span>
                                                {JSON.stringify(tc.args)}
                                            </div>
                                        )}
                                        {tc.result && (
                                            <div className="px-3 py-2 text-[11px] font-mono whitespace-pre-wrap break-words max-h-48 overflow-y-auto custom-scrollbar text-gray-400 bg-black/40">
                                                {tc.result}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        ))}
                    </div>
                )}

                {/* Footer Action Bar */}
                <div className={`flex items-center gap-1 mt-3 px-1 opacity-0 group-hover:opacity-100 transition-all duration-300 select-none ${isUser ? "justify-end" : "justify-start w-full"}`}>
                    <button onClick={handleCopy} className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                        {isCopied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                    </button>
                    {!isUser && (
                        <>
                            <button
                                onClick={onRegenerate}
                                disabled={!canRegenerate || !onRegenerate}
                                className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all disabled:opacity-40 disabled:hover:bg-transparent"
                                title="Regenerate"
                            >
                                <RotateCcw size={14} />
                            </button>
                            <button
                                onClick={() => handleVote("up")}
                                className={`p-1.5 rounded-lg transition-all ${vote === "up"
                                    ? "bg-green-500/20 text-green-400 hover:bg-green-500/30"
                                    : "hover:bg-gray-800 text-gray-500 hover:text-gray-300"
                                    }`}
                                title="Helpful"
                            >
                                <ThumbsUp size={14} />
                            </button>
                            <button
                                onClick={() => handleVote("down")}
                                className={`p-1.5 rounded-lg transition-all ${vote === "down"
                                    ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                                    : "hover:bg-gray-800 text-gray-500 hover:text-gray-300"
                                    }`}
                                title="Not helpful"
                            >
                                <ThumbsDown size={14} />
                            </button>
                        </>
                    )}
                    <button
                        onClick={onDelete}
                        disabled={!onDelete}
                        className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-red-400 transition-all disabled:opacity-40 disabled:hover:bg-transparent"
                        title="Delete from here"
                    >
                        <Trash2 size={14} />
                    </button>
                    <div className="relative" ref={menuRef}>
                        <button
                            onClick={() => setShowMoreMenu((prev) => !prev)}
                            className={`p-1.5 rounded-lg transition-all ${showMoreMenu
                                ? "bg-gray-800 text-gray-300"
                                : "hover:bg-gray-800 text-gray-500 hover:text-gray-300"
                                }`}
                            title="More actions"
                        >
                            <MoreHorizontal size={14} />
                        </button>
                        {showMoreMenu && (
                            <div className={`absolute bottom-full mb-2 w-52 max-w-[calc(100vw-1rem)] bg-gray-900 border border-gray-800 rounded-xl shadow-xl py-1 z-30 ${isUser ? "right-0" : "left-0"}`}>
                                {canEdit && onEdit && (
                                    <button
                                        onClick={() => {
                                            onEdit()
                                            setShowMoreMenu(false)
                                        }}
                                        className="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-800 flex items-center gap-2"
                                    >
                                        <Pencil size={12} className="text-cyan-400" />
                                        Edit message
                                    </button>
                                )}
                                {!isUser && onBranch && (
                                    <button
                                        onClick={() => {
                                            onBranch()
                                            setShowMoreMenu(false)
                                        }}
                                        className="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-800 flex items-center gap-2"
                                    >
                                        <MessageSquarePlus size={12} className="text-purple-400" />
                                        Copy to new session
                                    </button>
                                )}
                                {onDelete && (
                                    <button
                                        onClick={() => {
                                            onDelete()
                                            setShowMoreMenu(false)
                                        }}
                                        className="w-full text-left px-3 py-2 text-xs text-red-300 hover:bg-red-500/10 flex items-center gap-2"
                                    >
                                        <Trash2 size={12} />
                                        Delete from here
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
