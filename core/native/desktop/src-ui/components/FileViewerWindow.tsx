import React, { useEffect, useState, useRef, useCallback } from "react"
import { X, Copy, Check, FileText, Code2, Save, Pencil, Eye, Bold, Italic, List, ListOrdered, Code, Heading1, Heading2, Heading3, Link2, Quote, Minus, Download } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { initApiBase, getApiBase, getToken, handleRefresh, apiFetch, BASE_URL } from "../lib/api"
import { configure as configureBridge } from "../../../bridge/api"
import { getCurrentWindow } from "@tauri-apps/api/window"

/**
 * Standalone FileViewer window — rendered when Tauri opens a new window
 * with the `fileviewer` label. Reads payload from localStorage.
 * Content fills the entire window (no overlay/backdrop).
 */

// Toolbar helpers (same as FileViewer)
const ToolbarBtn = ({ icon: Icon, label, onClick, active }: {
    icon: React.ElementType; label: string; onClick: () => void; active?: boolean
}) => (
    <button onClick={onClick} title={label}
        className={`p-1 rounded transition-colors ${active ? "bg-cyan-500/20 text-cyan-400" : "text-gray-500 hover:text-white hover:bg-gray-800"}`}>
        <Icon size={14} />
    </button>
)
const ToolbarSep = () => <div className="w-px h-4 bg-gray-800 mx-0.5" />

export default function FileViewerWindow() {
    const [ready, setReady] = useState(false)
    const [payload, setPayload] = useState<{
        content: string
        filePath: string
        format: "markdown" | "code" | "pdf"
        projectId: string
        fileUrl?: string
    } | null>(null)

    const [editableContent, setEditableContent] = useState("")
    const [isEditing, setIsEditing] = useState(false)
    const [copied, setCopied] = useState(false)
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)
    const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
    const [pdfLoading, setPdfLoading] = useState(false)
    const [pdfError, setPdfError] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    useEffect(() => {
        const init = async () => {
            await initApiBase()
            configureBridge({ getBaseUrl: getApiBase, getToken, handleRefresh })

            const raw = localStorage.getItem("va_fileviewer_payload")
            if (raw) {
                try {
                    const data = JSON.parse(raw)
                    setPayload(data)
                    setEditableContent(data.content || "")
                } catch (e) {
                    console.error("Failed to parse fileviewer payload:", e)
                }
            }
            setReady(true)
        }
        init()
    }, [])

    // Close the actual Tauri window
    const handleClose = useCallback(async () => {
        try {
            const win = getCurrentWindow()
            await win.close()
        } catch {
            window.close()
        }
    }, [])

    // Derived values
    const filePath = payload?.filePath || ""
    const format = payload?.format || "markdown"
    const projectId = payload?.projectId || ""
    const fileUrl = payload?.fileUrl
    const fileName = filePath.split("/").pop() || filePath
    const isTextFile = format === "markdown" || format === "code"
    const isMarkdown = format === "markdown"

    // PDF URL
    const resolvedPdfUrl = fileUrl
        ? (fileUrl.startsWith("http") ? fileUrl : `${BASE_URL}${fileUrl}`)
        : undefined

    useEffect(() => {
        if (format !== "pdf" || !resolvedPdfUrl) return
        setPdfLoading(true); setPdfError(false)
        fetch(resolvedPdfUrl)
            .then(res => { if (!res.ok) throw new Error(); return res.blob() })
            .then(blob => setPdfBlobUrl(URL.createObjectURL(blob)))
            .catch(() => setPdfError(true))
            .finally(() => setPdfLoading(false))
        return () => { if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl) }
    }, [format, resolvedPdfUrl])

    // Clipboard
    const handleCopy = async () => {
        const text = isTextFile ? editableContent : (payload?.content || "")
        try { await navigator.clipboard.writeText(text) } catch {
            const ta = document.createElement("textarea"); ta.value = text
            document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta)
        }
        setCopied(true); setTimeout(() => setCopied(false), 2000)
    }

    // Save
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

    // Keyboard shortcuts
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") { if (isEditing) setIsEditing(false); else handleClose() }
            if ((e.ctrlKey || e.metaKey) && e.key === "s" && isEditing) { e.preventDefault(); handleSave() }
        }
        document.addEventListener("keydown", handler)
        return () => document.removeEventListener("keydown", handler)
    }, [isEditing, handleSave, handleClose])

    useEffect(() => { if (isEditing && textareaRef.current) textareaRef.current.focus() }, [isEditing])

    // Markdown toolbar helpers
    const insertMarkdown = (before: string, after: string = "") => {
        const ta = textareaRef.current; if (!ta) return
        const start = ta.selectionStart; const end = ta.selectionEnd
        const selected = editableContent.substring(start, end)
        const replacement = `${before}${selected || "text"}${after}`
        const newContent = editableContent.substring(0, start) + replacement + editableContent.substring(end)
        setEditableContent(newContent)
        setTimeout(() => { ta.focus(); const cp = start + before.length + (selected || "text").length + after.length; ta.setSelectionRange(cp, cp) }, 0)
    }
    const insertAtLineStart = (prefix: string) => {
        const ta = textareaRef.current; if (!ta) return
        const start = ta.selectionStart
        const lineStart = editableContent.lastIndexOf("\n", start - 1) + 1
        const newContent = editableContent.substring(0, lineStart) + prefix + editableContent.substring(lineStart)
        setEditableContent(newContent)
        setTimeout(() => { ta.focus(); ta.setSelectionRange(start + prefix.length, start + prefix.length) }, 0)
    }

    // Language label
    const ext = fileName.split(".").pop()?.toLowerCase() || ""
    const langLabel = (() => {
        const map: Record<string, string> = {
            ts: "TypeScript", tsx: "TypeScript (JSX)", js: "JavaScript", jsx: "JavaScript (JSX)",
            py: "Python", rs: "Rust", go: "Go", md: "Markdown", json: "JSON", yaml: "YAML", yml: "YAML",
            html: "HTML", css: "CSS", sql: "SQL", sh: "Shell", pdf: "PDF",
            c: "C", cpp: "C++", toml: "TOML", xml: "XML",
        }
        return map[ext] || ext.toUpperCase()
    })()

    // ── Loading state ──
    if (!ready) {
        return (
            <div className="h-screen bg-gray-950 flex items-center justify-center text-gray-400">
                <div className="w-8 h-8 border-2 border-gray-600 border-t-cyan-400 rounded-full animate-spin" />
            </div>
        )
    }

    if (!payload) {
        return (
            <div className="h-screen bg-gray-950 flex flex-col items-center justify-center gap-3 text-gray-400">
                <p className="text-sm">No file content available.</p>
                <button onClick={handleClose} className="px-4 py-2 bg-gray-800 rounded-lg text-sm hover:bg-gray-700 transition-colors">
                    Close Window
                </button>
            </div>
        )
    }

    // ── Full-screen file viewer ──
    return (
        <div className="h-screen bg-gray-950 flex flex-col overflow-hidden text-white">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800 bg-gray-900/80 flex-shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                    {format === "code" ? <Code2 size={15} className="text-cyan-400 flex-shrink-0" />
                        : format === "pdf" ? <FileText size={15} className="text-red-400 flex-shrink-0" />
                            : <FileText size={15} className="text-cyan-400 flex-shrink-0" />}
                    <span className="text-sm font-medium text-gray-200 truncate">{fileName}</span>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600 flex-shrink-0">{langLabel}</span>
                    {isEditing && <span className="text-[10px] font-bold uppercase tracking-widest text-amber-500 flex-shrink-0">Editing</span>}
                </div>
                <div className="flex items-center gap-1">
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
                    <button onClick={handleClose} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors" title="Close (Esc)">
                        <X size={16} />
                    </button>
                </div>
            </div>

            {/* Breadcrumb */}
            <div className="px-4 py-1 border-b border-gray-800/50 bg-gray-900/40 flex-shrink-0">
                <span className="text-[10px] text-gray-600 font-mono">{filePath}</span>
            </div>

            {/* Editor toolbar (markdown edit mode) */}
            {isEditing && isMarkdown && (
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
                </div>
            )}

            {/* Content — fills the rest of the window */}
            <div className="flex-1 overflow-auto min-h-0">
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
            </div>

            {/* Footer */}
            {isTextFile && (
                <div className="px-4 py-2 border-t border-gray-800 bg-gray-900/50 flex-shrink-0 flex items-center justify-between">
                    <span className="text-[10px] text-gray-600">
                        {editableContent.split("\n").length} lines · {new Blob([editableContent]).size > 1024
                            ? `${(new Blob([editableContent]).size / 1024).toFixed(1)} KB`
                            : `${new Blob([editableContent]).size} B`}
                    </span>
                    {isEditing && <span className="text-[10px] text-gray-600">Ctrl+S to save · Esc to exit editing</span>}
                </div>
            )}
        </div>
    )
}
