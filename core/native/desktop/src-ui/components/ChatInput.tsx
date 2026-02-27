import React, { useState, useRef, useEffect } from "react"
import { Send, Plus, ChevronDown } from "lucide-react"

interface Props {
    onSend: (message: string) => void
    loading: boolean
    statusText: string
    model: string
    onModelChange: (model: string) => void
}

const MODEL_GROUPS = [
    {
        group: "Gemini", models: [
            { id: "gemini-3.1-pro", name: "Gemini 3.1 Pro" },
            { id: "gemini-3.1-flash", name: "Gemini 3.1 Flash" },
            { id: "gemini-3-pro-preview", name: "Gemini 3 Pro" },
            { id: "gemini-3-flash-preview", name: "Gemini 3 Flash" },
            { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro" },
            { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash" },
        ]
    },
    {
        group: "OpenAI", models: [
            { id: "openai:gpt-5", name: "GPT-5" },
            { id: "openai:gpt-5-mini", name: "GPT-5 Mini" },
            { id: "openai:gpt-5-nano", name: "GPT-5 Nano" },
            { id: "openai:gpt-5.1", name: "GPT-5.1" },
            { id: "openai:gpt-4.1", name: "GPT-4.1" },
            { id: "openai:gpt-4.1-mini", name: "GPT-4.1 Mini" },
            { id: "openai:o4-mini", name: "o4 Mini (reasoning)" },
            { id: "openai:o3", name: "o3 (reasoning)" },
        ]
    },
    {
        group: "Claude", models: [
            { id: "anthropic:claude-opus-4-6-20260220", name: "Claude Opus 4.6" },
            { id: "anthropic:claude-opus-4-5-20251101", name: "Claude Opus 4.5" },
            { id: "anthropic:claude-sonnet-4-20250514", name: "Claude Sonnet 4" },
            { id: "anthropic:claude-haiku-4-5", name: "Claude Haiku 4.5" },
        ]
    },
]

const getModelDisplayName = (modelId: string): string => {
    for (const g of MODEL_GROUPS) {
        const m = g.models.find(x => x.id === modelId);
        if (m) return m.name;
    }
    const clean = modelId.includes(":") ? modelId.split(":")[1] : modelId;
    return clean.split("-").map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
};

export default function ChatInput({ onSend, loading, statusText, model, onModelChange }: Props) {
    const [value, setValue] = useState("")
    const [showModels, setShowModels] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const modelMenuRef = useRef<HTMLDivElement>(null)

    const handleSend = () => {
        if (!value.trim() || loading) return
        onSend(value.trim())
        setValue("")
        // Reset textarea height
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto"
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    // Auto resize textarea
    useEffect(() => {
        const ta = textareaRef.current
        if (ta) {
            ta.style.height = "auto"
            ta.style.height = Math.min(ta.scrollHeight, 200) + "px"
        }
    }, [value])

    // Close model menu on click outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node)) {
                setShowModels(false)
            }
        }
        document.addEventListener("mousedown", handler)
        return () => document.removeEventListener("mousedown", handler)
    }, [])

    const currentModelLabel = getModelDisplayName(model)

    return (
        <div className="flex-shrink-0 px-4 pb-4 pt-2 max-w-4xl mx-auto w-full">
            {/* Status text */}
            {loading && statusText && (
                <div className="flex items-center gap-2 mb-2 px-2">
                    <span className="text-[10px] font-black uppercase tracking-widest text-gray-600">
                        {statusText}
                    </span>
                </div>
            )}

            {/* Input container */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-2xl backdrop-blur-sm relative">
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Work on tasks, upload files, or type / for commands..."
                    disabled={loading}
                    rows={1}
                    className="w-full bg-transparent text-sm text-gray-200 px-4 pt-4 pb-2 resize-none outline-none placeholder:text-gray-600"
                />

                {/* Bottom toolbar */}
                <div className="flex items-center justify-between px-3 pb-3">
                    <div className="flex items-center gap-1">
                        <button
                            className="p-2 text-gray-500 hover:text-gray-300 hover:bg-gray-800 rounded-lg transition-colors"
                            title="Attach files"
                        >
                            <Plus size={16} />
                        </button>
                    </div>

                    <div className="flex items-center gap-2">
                        {/* Model selector */}
                        <div className="relative" ref={modelMenuRef}>
                            <button
                                onClick={() => setShowModels(!showModels)}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-400 transition-colors"
                            >
                                <span>{currentModelLabel}</span>
                                <ChevronDown size={12} />
                            </button>

                            {showModels && (
                                <div className="absolute bottom-[calc(100%+0.5rem)] right-0 bg-gray-900 border border-gray-800 rounded-2xl shadow-xl py-2 min-w-[200px] z-[100] custom-scrollbar max-h-[300px] overflow-y-auto w-64">
                                    {MODEL_GROUPS.map((group) => (
                                        <div key={group.group}>
                                            <div className="px-4 py-1.5 text-[10px] text-gray-400 font-bold uppercase tracking-widest bg-gray-900/90 sticky top-0 backdrop-blur-sm z-10 border-b border-gray-800/50 mb-1">{group.group}</div>
                                            {group.models.map((m) => (
                                                <button
                                                    key={m.id}
                                                    onClick={() => {
                                                        onModelChange(m.id)
                                                        setShowModels(false)
                                                    }}
                                                    className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-800 transition-colors flex items-center justify-between ${model === m.id ? "text-cyan-400 bg-cyan-500/10" : "text-gray-300"
                                                        }`}
                                                >
                                                    <span className="truncate pr-2">{m.name}</span>
                                                    {model === m.id && <div className="w-1.5 h-1.5 flex-shrink-0 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.5)]"></div>}
                                                </button>
                                            ))}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Send button */}
                        <button
                            onClick={handleSend}
                            disabled={!value.trim() || loading}
                            className={`p-2 rounded-lg transition-all ${value.trim() && !loading
                                ? "bg-cyan-500 text-white hover:bg-cyan-400 shadow-lg shadow-cyan-500/20"
                                : "bg-gray-800 text-gray-600"
                                }`}
                        >
                            <Send size={16} />
                        </button>
                    </div>
                </div>
            </div>

            {/* Helper text */}
            <p className="text-center text-[10px] text-gray-700 mt-2">
                Press / to see available commands
            </p>
        </div>
    )
}
