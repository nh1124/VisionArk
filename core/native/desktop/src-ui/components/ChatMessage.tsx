import React, { useState } from "react"
import { User, Bot, ChevronDown, ChevronRight, Sparkles, Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Trash2, MoreHorizontal } from "lucide-react"
import type { ChatMessage as ChatMessageType } from "../lib/api"
import MarkdownRenderer from "./MarkdownRenderer"

interface Props {
    message: ChatMessageType
    projectId: string
}

export default function ChatMessage({ message, projectId }: Props) {
    const [thinkingOpen, setThinkingOpen] = useState(false)
    const [isCopied, setIsCopied] = useState(false)
    const isUser = message.role === "user"

    const thinkingTurns = message.sub_messages?.length || 0

    const handleCopy = () => {
        if (!message.content) return
        navigator.clipboard.writeText(message.content)
        setIsCopied(true)
        setTimeout(() => setIsCopied(false), 2000)
    }

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
                <div className="text-sm">
                    <MarkdownRenderer content={message.content} nodeType="project" nodeName={projectId} projectId={projectId} />
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
                            <button className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                                <RotateCcw size={14} />
                            </button>
                            <button className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                                <ThumbsUp size={14} />
                            </button>
                            <button className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                                <ThumbsDown size={14} />
                            </button>
                        </>
                    )}
                    <button className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                        <Trash2 size={14} />
                    </button>
                    <button className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-all">
                        <MoreHorizontal size={14} />
                    </button>
                </div>
            </div>
        </div>
    )
}
