import React, { useEffect, useState, useRef, useCallback } from "react"
import { X, Copy, Check, FileText, Code2, Save, Pencil, Eye, Bold, Italic, List, ListOrdered, Code, Heading1, Heading2, Heading3, Link2, Quote, Minus, Download, ExternalLink, PanelRight, GripVertical } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { apiFetch, BASE_URL } from "../lib/api"

// ── View mode ─────────────────────────────────────────────────────────────────
export type FileViewerMode = "overlay" | "inline" | "popout"

export interface FileViewerProps {
    content: string
    filePath: string
    format: "markdown" | "code" | "pdf"
    projectId: string
    onClose: () => void
    fileUrl?: string
    /** Initial display mode. Defaults to "overlay". */
    initialMode?: FileViewerMode
    /** Called in inline mode when user drags the resize handle; ChatView uses this to adjust its layout. */
    onInlineWidthChange?: (w: number) => void
    /** Current inline width controlled by parent (ChatView). Only used in inline mode. */
    inlineWidth?: number
    /** Called when user switches display mode via the header toggle buttons. */
    onModeChange?: (mode: FileViewerMode) => void
}

// ── Toolbar helpers ────────────────────────────────────────────────────────────
const ToolbarBtn = ({ icon: Icon, label, onClick, active }: {
    icon: React.ElementType; label: string; onClick: () => void; active?: boolean
}) => (
    <button
        onClick={onClick}
        title={label}
        className={`p-1 rounded transition-colors ${active ? "bg-cyan-500/20 text-cyan-400" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
    >
        <Icon size={14} />
    </button>
)

const ToolbarSep = () => <div className="w-px h-4 bg-gray-800 mx-0.5" />

// ── Main component ─────────────────────────────────────────────────────────────
export default function FileViewer({
    content,
    filePath,
    format,
    projectId,
    onClose,
    fileUrl,
    initialMode = "overlay",
    onInlineWidthChange,
    inlineWidth = 560,
    onModeChange,
}: FileViewerProps) {
    const [editableContent, setEditableContent] = useState(content)
    const [isEditing, setIsEditing] = useState(false)
    const [copied, setCopied] = useState(false)
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)
    const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
    const [pdfLoading, setPdfLoading] = useState(false)
    const [pdfError, setPdfError] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // ── View Mode ──────────────────────────────────────────────────────────────
    const [mode, setMode] = useState<FileViewerMode>(initialMode)
    const changeMode = (m: FileViewerMode) => { setMode(m); onModeChange?.(m) }

    // ── Inline panel drag-resize refs (width managed by parent) ───────────────
    const isDraggingRef = useRef(false)
    const dragStartXRef = useRef(0)
    const dragStartWidthRef = useRef(0)

    // ── Popout window position (draggable within app — only shown as fallback) ─
    const [popoutPos, setPopoutPos] = useState({ x: 80, y: 60 })
    const [popoutSize, setPopoutSize] = useState({ w: 720, h: 520 })
    const isDraggingPopoutRef = useRef(false)
    const isDraggingPopoutEdgeRef = useRef<string | null>(null)
    const dragPopoutStartRef = useRef({ mx: 0, my: 0, px: 0, py: 0, pw: 0, ph: 0 })

    const fileName = filePath.split("/").pop() || filePath
    const isTextFile = format === "markdown" || format === "code"
    const isMarkdown = format === "markdown"

    useEffect(() => {
        setEditableContent(content)
        setIsEditing(false)
    }, [content, filePath])

    // ── PDF URL ──────────────────────────────────────────────────────────────
    const resolvedPdfUrl = fileUrl
        ? (fileUrl.startsWith("http") ? fileUrl : `${BASE_URL}${fileUrl}`)
        : undefined

    useEffect(() => {
        if (format !== "pdf" || !resolvedPdfUrl) return
        setPdfLoading(true)
        setPdfError(false)
        fetch(resolvedPdfUrl)
            .then(res => { if (!res.ok) throw new Error("PDF fetch failed"); return res.blob() })
            .then(blob => { const url = URL.createObjectURL(blob); setPdfBlobUrl(url) })
            .catch(() => setPdfError(true))
            .finally(() => setPdfLoading(false))
        return () => { if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl) }
    }, [format, resolvedPdfUrl])

    // ── Clipboard ────────────────────────────────────────────────────────────
    const handleCopy = async () => {
        const text = isTextFile ? editableContent : content
        try { await navigator.clipboard.writeText(text) } catch {
            const ta = document.createElement("textarea"); ta.value = text
            document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta)
        }
        setCopied(true); setTimeout(() => setCopied(false), 2000)
    }

    // ── Save ─────────────────────────────────────────────────────────────────
    const handleSave = useCallback(async () => {
        if (!isTextFile) return
        setSaving(true)
        try {
            let directory: "refs" | "artifacts" | "files" = "refs"
            let relativePath = filePath
            if (filePath.startsWith("artifacts/")) { directory = "artifacts"; relativePath = filePath.replace("artifacts/", "") }
            else if (filePath.startsWith("files/")) { directory = "files"; relativePath = filePath.replace("files/", "") }
            else if (filePath.startsWith("refs/")) { directory = "refs"; relativePath = filePath.replace("refs/", "") }

            const response = await apiFetch(`/api/files/project/${projectId}/save`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: relativePath, content: editableContent, directory }),
            })
            if (response.ok) { setSaved(true); setTimeout(() => setSaved(false), 2000); setIsEditing(false) }
            else { const d = await response.json(); console.error("Save failed:", d.detail) }
        } catch (e) { console.error("Save error:", e) } finally { setSaving(false) }
    }, [editableContent, filePath, projectId, isTextFile])

    // ── Keyboard shortcuts ────────────────────────────────────────────────────
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") { if (isEditing) setIsEditing(false); else onClose() }
            if ((e.ctrlKey || e.metaKey) && e.key === "s" && isEditing) { e.preventDefault(); handleSave() }
        }
        document.addEventListener("keydown", handler)
        return () => document.removeEventListener("keydown", handler)
    }, [onClose, isEditing, handleSave])

    useEffect(() => { if (isEditing && textareaRef.current) textareaRef.current.focus() }, [isEditing])

    // ── Markdown toolbar ──────────────────────────────────────────────────────
    const insertMarkdown = (before: string, after: string = "") => {
        const ta = textareaRef.current; if (!ta) return
        const start = ta.selectionStart; const end = ta.selectionEnd
        const selected = editableContent.substring(start, end)
        const replacement = `${before}${selected || "text"}${after}`
        const newContent = editableContent.substring(0, start) + replacement + editableContent.substring(end)
        setEditableContent(newContent)
        setTimeout(() => {
            ta.focus()
            const cursorPos = start + before.length + (selected || "text").length + after.length
            ta.setSelectionRange(cursorPos, cursorPos)
        }, 0)
    }

    const insertAtLineStart = (prefix: string) => {
        const ta = textareaRef.current; if (!ta) return
        const start = ta.selectionStart
        const lineStart = editableContent.lastIndexOf("\n", start - 1) + 1
        const newContent = editableContent.substring(0, lineStart) + prefix + editableContent.substring(lineStart)
        setEditableContent(newContent)
        setTimeout(() => { ta.focus(); ta.setSelectionRange(start + prefix.length, start + prefix.length) }, 0)
    }

    // ── Language label ─────────────────────────────────────────────────────────
    const ext = fileName.split(".").pop()?.toLowerCase() || ""
    const langLabel = (() => {
        const map: Record<string, string> = {
            ts: "TypeScript", tsx: "TypeScript (JSX)", js: "JavaScript", jsx: "JavaScript (JSX)",
            py: "Python", rs: "Rust", go: "Go", rb: "Ruby", php: "PHP",
            html: "HTML", css: "CSS", json: "JSON", yaml: "YAML", yml: "YAML",
            md: "Markdown", sql: "SQL", sh: "Shell", bat: "Batch",
            c: "C", cpp: "C++", h: "C Header", hpp: "C++ Header",
            toml: "TOML", xml: "XML", env: "Env", pdf: "PDF",
        }
        return map[ext] || ext.toUpperCase()
    })()

    // ── Inline resize (drag left grip → notify parent) ────────────────────────
    const handleResizeMouseDown = (e: React.MouseEvent) => {
        e.preventDefault()
        isDraggingRef.current = true
        dragStartXRef.current = e.clientX
        dragStartWidthRef.current = inlineWidth

        const onMove = (ev: MouseEvent) => {
            if (!isDraggingRef.current) return
            const delta = dragStartXRef.current - ev.clientX
            const newW = Math.max(320, Math.min(1400, dragStartWidthRef.current + delta))
            onInlineWidthChange?.(newW)
        }
        const onUp = () => {
            isDraggingRef.current = false
            window.removeEventListener("mousemove", onMove)
            window.removeEventListener("mouseup", onUp)
        }
        window.addEventListener("mousemove", onMove)
        window.addEventListener("mouseup", onUp)
    }

    // ── Popout drag (title bar) ────────────────────────────────────────────────
    const handlePopoutDragStart = (e: React.MouseEvent) => {
        if ((e.target as HTMLElement).closest("button")) return
        e.preventDefault()
        isDraggingPopoutRef.current = true
        dragPopoutStartRef.current = { mx: e.clientX, my: e.clientY, px: popoutPos.x, py: popoutPos.y, pw: popoutSize.w, ph: popoutSize.h }

        const onMove = (ev: MouseEvent) => {
            if (!isDraggingPopoutRef.current) return
            const { mx, my, px, py } = dragPopoutStartRef.current
            setPopoutPos({ x: Math.max(0, px + ev.clientX - mx), y: Math.max(0, py + ev.clientY - my) })
        }
        const onUp = () => {
            isDraggingPopoutRef.current = false
            window.removeEventListener("mousemove", onMove)
            window.removeEventListener("mouseup", onUp)
        }
        window.addEventListener("mousemove", onMove)
        window.addEventListener("mouseup", onUp)
    }

    // ── Popout resize (right/bottom/corner edges) ─────────────────────────────
    const handlePopoutEdgeDown = (e: React.MouseEvent, edge: string) => {
        e.preventDefault(); e.stopPropagation()
        isDraggingPopoutEdgeRef.current = edge
        dragPopoutStartRef.current = { mx: e.clientX, my: e.clientY, px: popoutPos.x, py: popoutPos.y, pw: popoutSize.w, ph: popoutSize.h }

        const onMove = (ev: MouseEvent) => {
            const { mx, my, pw, ph } = dragPopoutStartRef.current
            const dx = ev.clientX - mx; const dy = ev.clientY - my
            if (isDraggingPopoutEdgeRef.current === "right" || isDraggingPopoutEdgeRef.current === "corner") {
                setPopoutSize(s => ({ ...s, w: Math.max(400, pw + dx) }))
            }
            if (isDraggingPopoutEdgeRef.current === "bottom" || isDraggingPopoutEdgeRef.current === "corner") {
                setPopoutSize(s => ({ ...s, h: Math.max(240, ph + dy) }))
            }
        }
        const onUp = () => {
            isDraggingPopoutEdgeRef.current = null
            window.removeEventListener("mousemove", onMove)
            window.removeEventListener("mouseup", onUp)
        }
        window.addEventListener("mousemove", onMove)
        window.addEventListener("mouseup", onUp)
    }

    // ── Open native OS window via Tauri WebviewWindow ─────────────────────────
    const handlePopoutOpen = useCallback(async () => {
        try {
            // Store content in localStorage so the new Tauri window can read it
            const payload = JSON.stringify({ content, filePath, format, projectId, fileUrl })
            localStorage.setItem("va_fileviewer_payload", payload)

            const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow")
            const label = `fileviewer_${Date.now()}`
            const win = new WebviewWindow(label, {
                url: `/?fileviewer=1`,
                title: fileName,
                width: 900,
                height: 650,
                resizable: true,
                decorations: true,
            })
            win.once("tauri://created", () => {
                // Window opened successfully — dismiss the viewer in main window
                onClose()
            })
            win.once("tauri://error", (e) => {
                console.error("Failed to open fileviewer window:", e)
                // Fall back to in-app popout
                setMode("popout")
            })
        } catch (err) {
            console.error("Tauri WebviewWindow not available:", err)
            setMode("popout")
        }
    }, [content, filePath, format, projectId, fileUrl, fileName, onClose])

    // ── Shared content body ────────────────────────────────────────────────────
    const ContentBody = () => (
        <>
            {format === "pdf" ? (
                pdfLoading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-500">
                        <div className="w-8 h-8 border-2 border-gray-600 border-t-cyan-400 rounded-full animate-spin" />
                        <p className="text-sm">Loading PDF...</p>
                    </div>
                ) : pdfBlobUrl ? (
                    <iframe src={pdfBlobUrl} className="w-full h-full border-none" title={fileName} />
                ) : (
                    <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-500">
                        <FileText size={48} className="text-gray-700" />
                        <p className="text-sm">{pdfError ? "Failed to load PDF" : "Unable to preview PDF"}</p>
                        {resolvedPdfUrl && (
                            <a href={resolvedPdfUrl} target="_blank" rel="noopener noreferrer"
                                className="px-4 py-2 bg-cyan-500/20 text-cyan-400 rounded-lg text-sm hover:bg-cyan-500/30 transition-colors">
                                Open in Browser
                            </a>
                        )}
                    </div>
                )
            ) : isEditing ? (
                <textarea
                    ref={textareaRef}
                    value={editableContent}
                    onChange={(e) => setEditableContent(e.target.value)}
                    className="w-full h-full bg-transparent text-sm font-mono text-gray-300 p-4 resize-none outline-none leading-relaxed"
                    spellCheck={false}
                />
            ) : isMarkdown ? (
                <div className="p-6 prose prose-invert prose-sm max-w-none
                    prose-headings:text-gray-100 prose-headings:font-semibold
                    prose-h1:text-2xl prose-h1:border-b prose-h1:border-gray-800 prose-h1:pb-2
                    prose-h2:text-xl prose-h3:text-lg
                    prose-p:text-gray-300 prose-p:leading-relaxed
                    prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
                    prose-strong:text-gray-200
                    prose-code:text-cyan-400 prose-code:bg-gray-800/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
                    prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-800 prose-pre:rounded-xl
                    prose-blockquote:border-l-cyan-500 prose-blockquote:text-gray-400
                    prose-li:text-gray-300
                    prose-hr:border-gray-800
                    prose-table:text-sm
                    prose-th:text-gray-300 prose-th:border-gray-700 prose-th:bg-gray-900/50
                    prose-td:text-gray-400 prose-td:border-gray-800
                ">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{editableContent}</ReactMarkdown>
                </div>
            ) : (
                <pre className="p-4 text-sm font-mono text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
                    <code>{editableContent}</code>
                </pre>
            )}
        </>
    )

    // ── Mode toggle buttons (shared) ──────────────────────────────────────────
    const ModeButtons = ({ size = 14 }: { size?: number }) => (
        <>
            <button
                onClick={() => changeMode("overlay")}
                title="Overlay mode"
                className={`p-1.5 rounded-lg transition-colors ${mode === "overlay" ? "text-cyan-400 bg-cyan-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
            >
                <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="2" width="20" height="20" rx="2" />
                    <path d="M9 2v20" />
                </svg>
            </button>
            <button
                onClick={() => changeMode("inline")}
                title="Inline mode (right side panel)"
                className={`p-1.5 rounded-lg transition-colors ${mode === "inline" ? "text-cyan-400 bg-cyan-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
            >
                <PanelRight size={size} />
            </button>
            <button
                onClick={handlePopoutOpen}
                title="Open in separate window"
                className={`p-1.5 rounded-lg transition-colors ${mode === "popout" ? "text-cyan-400 bg-cyan-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
            >
                <ExternalLink size={size} />
            </button>
        </>
    )

    // ── Shared header ──────────────────────────────────────────────────────────
    const Header = () => (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900/80 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
                {format === "code"
                    ? <Code2 size={15} className="text-cyan-400 flex-shrink-0" />
                    : format === "pdf"
                        ? <FileText size={15} className="text-red-400 flex-shrink-0" />
                        : <FileText size={15} className="text-cyan-400 flex-shrink-0" />}
                <span className="text-sm font-medium text-gray-200 truncate">{fileName}</span>
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600 flex-shrink-0">{langLabel}</span>
                {isEditing && <span className="text-[10px] font-bold uppercase tracking-widest text-amber-500 flex-shrink-0">Editing</span>}
            </div>
            <div className="flex items-center gap-1">
                <ModeButtons />
                <div className="w-px h-4 bg-gray-800 mx-0.5" />
                {isTextFile && (
                    <button onClick={() => setIsEditing(!isEditing)}
                        className={`p-1.5 rounded-lg transition-colors ${isEditing ? "text-amber-400 bg-amber-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
                        title={isEditing ? "View mode" : "Edit file"}>
                        {isEditing ? <Eye size={14} /> : <Pencil size={14} />}
                    </button>
                )}
                {isEditing && (
                    <button onClick={handleSave} disabled={saving}
                        className={`p-1.5 rounded-lg transition-colors ${saved ? "text-green-400 bg-green-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"} disabled:opacity-50`}
                        title="Save (Ctrl+S)">
                        {saved ? <Check size={14} /> : <Save size={14} />}
                    </button>
                )}
                {isTextFile && (
                    <button onClick={handleCopy} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Copy">
                        {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                    </button>
                )}
                {format === "pdf" && resolvedPdfUrl && (
                    <a href={resolvedPdfUrl} download={fileName} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Download PDF">
                        <Download size={14} />
                    </a>
                )}
                <button onClick={onClose} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Close (Esc)">
                    <X size={16} />
                </button>
            </div>
        </div>
    )

    const Breadcrumb = () => (
        <div className="px-4 py-1.5 border-b border-gray-800/50 bg-gray-900/40 flex-shrink-0">
            <span className="text-[10px] text-gray-600 font-mono">{filePath}</span>
        </div>
    )

    const EditorToolbar = () => (
        isEditing && isMarkdown ? (
            <div className="flex items-center gap-0.5 px-4 py-2 border-b border-gray-800/50 bg-gray-900/60 flex-shrink-0 flex-wrap">
                <ToolbarBtn icon={Heading1} label="Heading 1" onClick={() => insertAtLineStart("# ")} />
                <ToolbarBtn icon={Heading2} label="Heading 2" onClick={() => insertAtLineStart("## ")} />
                <ToolbarBtn icon={Heading3} label="Heading 3" onClick={() => insertAtLineStart("### ")} />
                <ToolbarSep />
                <ToolbarBtn icon={Bold} label="Bold" onClick={() => insertMarkdown("**", "**")} />
                <ToolbarBtn icon={Italic} label="Italic" onClick={() => insertMarkdown("*", "*")} />
                <ToolbarBtn icon={Code} label="Inline Code" onClick={() => insertMarkdown("`", "`")} />
                <ToolbarSep />
                <ToolbarBtn icon={List} label="Bullet List" onClick={() => insertAtLineStart("- ")} />
                <ToolbarBtn icon={ListOrdered} label="Numbered List" onClick={() => insertAtLineStart("1. ")} />
                <ToolbarBtn icon={Quote} label="Blockquote" onClick={() => insertAtLineStart("> ")} />
                <ToolbarSep />
                <ToolbarBtn icon={Link2} label="Link" onClick={() => insertMarkdown("[", "](url)")} />
                <ToolbarBtn icon={Minus} label="Horizontal Rule" onClick={() => insertMarkdown("\n---\n")} />
                <ToolbarSep />
                <span className="text-[10px] text-gray-600 mr-1">Color:</span>
                {[
                    { color: "#ef4444", label: "Red" }, { color: "#f97316", label: "Orange" },
                    { color: "#eab308", label: "Yellow" }, { color: "#22c55e", label: "Green" },
                    { color: "#3b82f6", label: "Blue" }, { color: "#a855f7", label: "Purple" },
                ].map(c => (
                    <button key={c.color} title={c.label}
                        onClick={() => insertMarkdown(`<span style="color:${c.color}">`, "</span>")}
                        className="w-4 h-4 rounded-full border border-gray-700 hover:scale-125 transition-transform mx-0.5"
                        style={{ backgroundColor: c.color }}
                    />
                ))}
            </div>
        ) : null
    )

    const Footer = () => (
        isTextFile ? (
            <div className="px-4 py-2 border-t border-gray-800 bg-gray-900/50 flex-shrink-0 flex items-center justify-between">
                <span className="text-[10px] text-gray-600">
                    {editableContent.split("\n").length} lines · {new Blob([editableContent]).size > 1024
                        ? `${(new Blob([editableContent]).size / 1024).toFixed(1)} KB`
                        : `${new Blob([editableContent]).size} B`}
                </span>
                {isEditing && <span className="text-[10px] text-gray-600">Ctrl+S to save · Esc to exit editing</span>}
            </div>
        ) : null
    )

    // ── Inner panel (shared by overlay & inline) ──────────────────────────────
    const PanelContent = () => (
        <div className="flex flex-col h-full bg-gray-950 overflow-hidden">
            <Header />
            <Breadcrumb />
            <EditorToolbar />
            <div className="flex-1 overflow-auto min-h-0">
                <ContentBody />
            </div>
            <Footer />
        </div>
    )

    // ════════════════════════════════════════════════════════════════════════════
    // OVERLAY MODE (original behavior — slide from right, with backdrop)
    // ════════════════════════════════════════════════════════════════════════════
    if (mode === "overlay") {
        return (
            <div className="fixed inset-0 z-[90] flex animate-in fade-in duration-200">
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
                <div className="relative ml-auto w-full max-w-3xl h-full border-l border-gray-800 shadow-2xl animate-in slide-in-from-right duration-300">
                    <PanelContent />
                </div>
            </div>
        )
    }

    // ════════════════════════════════════════════════════════════════════════════
    // INLINE MODE — rendered as flex child by ChatView (no fixed positioning here)
    // The parent (ChatView) controls the width via the `inlineWidth` prop and
    // listens to `onInlineWidthChange` to update its own layout.
    // ════════════════════════════════════════════════════════════════════════════
    if (mode === "inline") {
        return (
            <div className="flex flex-row h-full border-l border-gray-700 bg-gray-950 animate-in slide-in-from-right duration-200" style={{ width: inlineWidth, flexShrink: 0 }}>
                {/* ── Resize handle (left edge grip) ── */}
                <div
                    onMouseDown={handleResizeMouseDown}
                    className="flex items-center justify-center w-2.5 bg-gray-900/80 border-r border-gray-800 cursor-ew-resize flex-shrink-0 group hover:bg-cyan-500/10 transition-colors"
                    title="Drag to resize"
                >
                    <GripVertical size={12} className="text-gray-600 group-hover:text-cyan-400 transition-colors" />
                </div>
                <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
                    <PanelContent />
                </div>
            </div>
        )
    }

    // ════════════════════════════════════════════════════════════════════════════
    // POPOUT MODE — in-app draggable floating window (fallback if Tauri fails)
    // ════════════════════════════════════════════════════════════════════════════
    return (
        <div
            className="fixed z-[100] bg-gray-950 border border-gray-700 rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
            style={{ left: popoutPos.x, top: popoutPos.y, width: popoutSize.w, height: popoutSize.h, minWidth: 400, minHeight: 240 }}
        >
            {/* Draggable title bar */}
            <div
                onMouseDown={handlePopoutDragStart}
                className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/90 flex-shrink-0 cursor-grab active:cursor-grabbing select-none"
            >
                <div className="flex items-center gap-2 min-w-0 pointer-events-none">
                    {format === "code" ? <Code2 size={14} className="text-cyan-400 flex-shrink-0" />
                        : format === "pdf" ? <FileText size={14} className="text-red-400 flex-shrink-0" />
                            : <FileText size={14} className="text-cyan-400 flex-shrink-0" />}
                    <span className="text-sm font-medium text-gray-200 truncate">{fileName}</span>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600 flex-shrink-0">{langLabel}</span>
                    {isEditing && <span className="text-[10px] font-bold uppercase tracking-widest text-amber-500 flex-shrink-0">Editing</span>}
                </div>
                <div className="flex items-center gap-1 pointer-events-auto">
                    <ModeButtons size={13} />
                    <div className="w-px h-4 bg-gray-800 mx-0.5" />
                    {isTextFile && (
                        <button onClick={() => setIsEditing(!isEditing)}
                            className={`p-1.5 rounded-lg transition-colors ${isEditing ? "text-amber-400 bg-amber-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}
                            title={isEditing ? "View mode" : "Edit file"}>
                            {isEditing ? <Eye size={13} /> : <Pencil size={13} />}
                        </button>
                    )}
                    {isEditing && (
                        <button onClick={handleSave} disabled={saving}
                            className={`p-1.5 rounded-lg transition-colors ${saved ? "text-green-400 bg-green-500/10" : "text-gray-500 hover:text-white hover:bg-gray-800"} disabled:opacity-50`}
                            title="Save (Ctrl+S)">
                            {saved ? <Check size={13} /> : <Save size={13} />}
                        </button>
                    )}
                    {isTextFile && (
                        <button onClick={handleCopy} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Copy">
                            {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
                        </button>
                    )}
                    {format === "pdf" && resolvedPdfUrl && (
                        <a href={resolvedPdfUrl} download={fileName} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Download PDF">
                            <Download size={13} />
                        </a>
                    )}
                    <button onClick={onClose} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Close">
                        <X size={15} />
                    </button>
                </div>
            </div>

            <Breadcrumb />
            <EditorToolbar />
            <div className="flex-1 overflow-auto min-h-0"><ContentBody /></div>
            <Footer />

            {/* Resize edges */}
            <div onMouseDown={e => handlePopoutEdgeDown(e, "right")} className="absolute top-0 right-0 w-1.5 h-full cursor-ew-resize hover:bg-cyan-500/20 transition-colors" />
            <div onMouseDown={e => handlePopoutEdgeDown(e, "bottom")} className="absolute bottom-0 left-0 right-0 h-1.5 cursor-ns-resize hover:bg-cyan-500/20 transition-colors" />
            <div onMouseDown={e => handlePopoutEdgeDown(e, "corner")} className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize">
                <svg width="12" height="12" viewBox="0 0 12 12" className="absolute bottom-1 right-1 text-gray-600">
                    <path d="M11 1L1 11M7 1L1 7M11 5L5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
            </div>
        </div>
    )
}
