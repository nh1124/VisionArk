import React, { useState, useRef, useEffect } from "react"
import { Send, Plus, ChevronDown, X, FileText, Paperclip } from "lucide-react"

interface Props {
    onSend: (message: string, files?: File[]) => void
    loading: boolean
    statusText: string
    model: string
    onModelChange: (model: string) => void
}

// ── Slash Commands ──────────────────────────────────────────────────────────
interface SlashCommand {
    command: string
    label: string
    description: string
    action?: string // "insert" = replace with text, "exec" = run immediately
}

const SLASH_COMMANDS: SlashCommand[] = [
    { command: "/clear", label: "Clear", description: "Clear conversation history" },
    { command: "/model", label: "Model", description: "Switch AI model" },
    { command: "/help", label: "Help", description: "Show available commands" },
    { command: "/export", label: "Export", description: "Export chat as text" },
    { command: "/reset", label: "Reset", description: "Reset the session" },
]

// ── Model definitions ───────────────────────────────────────────────────────
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

// ── Helpers ─────────────────────────────────────────────────────────────────
const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ChatInput({ onSend, loading, statusText, model, onModelChange }: Props) {
    const [value, setValue] = useState("")
    const [showModels, setShowModels] = useState(false)
    const [attachedFiles, setAttachedFiles] = useState<File[]>([])
    const [showSlashMenu, setShowSlashMenu] = useState(false)
    const [slashFilter, setSlashFilter] = useState("")
    const [slashIndex, setSlashIndex] = useState(0)
    const [isDragOver, setIsDragOver] = useState(false)

    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const modelMenuRef = useRef<HTMLDivElement>(null)
    const slashMenuRef = useRef<HTMLDivElement>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // ── Filtered slash commands ─────────────────────────────────────────
    const filteredCommands = SLASH_COMMANDS.filter(c =>
        c.command.toLowerCase().startsWith(`/${slashFilter.toLowerCase()}`)
    )

    // ── Send ────────────────────────────────────────────────────────────
    const handleSend = () => {
        if ((!value.trim() && attachedFiles.length === 0) || loading) return
        onSend(value.trim(), attachedFiles.length > 0 ? attachedFiles : undefined)
        setValue("")
        setAttachedFiles([])
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto"
        }
    }

    // ── Slash command execution ─────────────────────────────────────────
    const executeSlashCommand = (cmd: SlashCommand) => {
        setShowSlashMenu(false)
        setValue("")
        // For now, insert the command as a message for the agent to handle
        onSend(cmd.command)
    }

    const selectSlashCommand = (index: number) => {
        if (filteredCommands[index]) {
            executeSlashCommand(filteredCommands[index])
        }
    }

    // ── Key handling ────────────────────────────────────────────────────
    const handleKeyDown = (e: React.KeyboardEvent) => {
        // Slash menu navigation
        if (showSlashMenu && filteredCommands.length > 0) {
            if (e.key === "ArrowDown") {
                e.preventDefault()
                setSlashIndex(prev => (prev + 1) % filteredCommands.length)
                return
            }
            if (e.key === "ArrowUp") {
                e.preventDefault()
                setSlashIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length)
                return
            }
            if (e.key === "Enter") {
                e.preventDefault()
                selectSlashCommand(slashIndex)
                return
            }
            if (e.key === "Escape") {
                e.preventDefault()
                setShowSlashMenu(false)
                return
            }
            if (e.key === "Tab") {
                e.preventDefault()
                selectSlashCommand(slashIndex)
                return
            }
        }

        // Ctrl / Cmd + Enter to send
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault()
            handleSend()
        }
    }

    // ── Input change with slash detection ───────────────────────────────
    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const newValue = e.target.value
        setValue(newValue)

        // Detect slash command input
        if (newValue.startsWith("/")) {
            const query = newValue.slice(1) // everything after "/"
            setSlashFilter(query)
            setSlashIndex(0)
            setShowSlashMenu(true)
        } else {
            setShowSlashMenu(false)
        }
    }

    // ── File handling ───────────────────────────────────────────────────
    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setAttachedFiles(prev => [...prev, ...Array.from(e.target.files!)])
        }
        // Reset input so re-selecting the same file works
        e.target.value = ""
    }

    const removeFile = (index: number) => {
        setAttachedFiles(prev => prev.filter((_, i) => i !== index))
    }

    // ── Drag & Drop ─────────────────────────────────────────────────────
    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragOver(true)
    }
    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragOver(false)
    }
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragOver(false)
        if (e.dataTransfer.files.length > 0) {
            setAttachedFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)])
        }
    }

    // ── Auto resize ─────────────────────────────────────────────────────
    useEffect(() => {
        const ta = textareaRef.current
        if (ta) {
            ta.style.height = "auto"
            ta.style.height = Math.min(ta.scrollHeight, 200) + "px"
        }
    }, [value])

    // ── Click outside handlers ──────────────────────────────────────────
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node)) {
                setShowModels(false)
            }
            if (slashMenuRef.current && !slashMenuRef.current.contains(e.target as Node)) {
                setShowSlashMenu(false)
            }
        }
        document.addEventListener("mousedown", handler)
        return () => document.removeEventListener("mousedown", handler)
    }, [])

    const currentModelLabel = getModelDisplayName(model)
    const hasContent = value.trim() || attachedFiles.length > 0

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

            {/* Hidden file input */}
            <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFileSelect}
            />

            {/* Input container */}
            <div
                className={`bg-gray-900/80 border rounded-2xl backdrop-blur-sm relative transition-colors ${isDragOver ? "border-cyan-500 bg-cyan-500/5" : "border-gray-800"
                    }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                {/* Drag overlay */}
                {isDragOver && (
                    <div className="absolute inset-0 flex items-center justify-center bg-cyan-500/5 rounded-2xl z-20 pointer-events-none">
                        <div className="flex items-center gap-2 text-cyan-400 text-sm font-medium">
                            <Paperclip size={16} />
                            <span>Drop files here</span>
                        </div>
                    </div>
                )}

                {/* Slash Command Menu */}
                {showSlashMenu && filteredCommands.length > 0 && (
                    <div
                        ref={slashMenuRef}
                        className="absolute bottom-full left-0 mb-2 w-72 bg-gray-900 border border-gray-800 rounded-xl shadow-xl py-1 z-[100] overflow-hidden"
                    >
                        <div className="px-3 py-1.5 text-[10px] text-gray-500 font-bold uppercase tracking-widest border-b border-gray-800/50">
                            Commands
                        </div>
                        {filteredCommands.map((cmd, i) => (
                            <button
                                key={cmd.command}
                                onMouseDown={(e) => {
                                    e.preventDefault()
                                    selectSlashCommand(i)
                                }}
                                className={`w-full text-left px-3 py-2 flex items-center gap-3 transition-colors ${i === slashIndex
                                    ? "bg-cyan-500/10 text-cyan-400"
                                    : "text-gray-300 hover:bg-gray-800"
                                    }`}
                            >
                                <span className="text-sm font-mono text-cyan-400/80">{cmd.command}</span>
                                <span className="text-xs text-gray-500">{cmd.description}</span>
                            </button>
                        ))}
                    </div>
                )}

                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Type a message... (Ctrl+Enter to send)"
                    disabled={loading}
                    rows={1}
                    className="w-full bg-transparent text-sm text-gray-200 px-4 pt-4 pb-2 resize-none outline-none placeholder:text-gray-600"
                />

                {/* Attached files chips */}
                {attachedFiles.length > 0 && (
                    <div className="flex flex-wrap gap-2 px-4 pb-2">
                        {attachedFiles.map((file, i) => (
                            <div
                                key={`${file.name}-${i}`}
                                className="flex items-center gap-1.5 bg-gray-800 text-gray-300 text-xs px-2.5 py-1.5 rounded-lg border border-gray-700 group"
                            >
                                <FileText size={12} className="text-gray-500 flex-shrink-0" />
                                <span className="truncate max-w-[140px]">{file.name}</span>
                                <span className="text-gray-600">({formatFileSize(file.size)})</span>
                                <button
                                    onClick={() => removeFile(i)}
                                    className="ml-0.5 text-gray-600 hover:text-red-400 transition-colors"
                                >
                                    <X size={12} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}

                {/* Bottom toolbar */}
                <div className="flex items-center justify-between px-3 pb-3">
                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => fileInputRef.current?.click()}
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
                            disabled={!hasContent || loading}
                            className={`p-2 rounded-lg transition-all ${hasContent && !loading
                                ? "bg-cyan-500 text-white hover:bg-cyan-400 shadow-lg shadow-cyan-500/20"
                                : "bg-gray-800 text-gray-600"
                                }`}
                            title="Send (Ctrl+Enter)"
                        >
                            <Send size={16} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
