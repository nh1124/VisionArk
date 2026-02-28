import React, { useRef, useState } from "react"
import { X, Upload, FileText, AlertTriangle, CheckCircle2 } from "lucide-react"
import { apiFetch } from "../lib/api"

interface ParsedTask {
  task_name: string
  context: string
  base_load_score: number
  rule_type: string
  due_date: string | null
  notes: string | null
  isNewProject?: boolean
}

interface Props {
  isOpen: boolean
  onClose: () => void
  onImportComplete: () => void
  existingProjects?: string[]
}

// ── CSV helpers ───────────────────────────────────────────────────────────────

function parseCSVLine(line: string): string[] {
  const result: string[] = []
  let current = ""
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { current += '"'; i++ }
      else { inQuotes = !inQuotes }
    } else if (ch === "," && !inQuotes) {
      result.push(current.trim()); current = ""
    } else {
      current += ch
    }
  }
  result.push(current.trim())
  return result
}

function getField(headers: string[], values: string[], name: string): string {
  const idx = headers.findIndex(h => h.toLowerCase() === name.toLowerCase())
  return idx >= 0 ? values[idx] || "" : ""
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ImportModal({ isOpen, onClose, onImportComplete, existingProjects = [] }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName]       = useState("")
  const [parsed, setParsed]           = useState<ParsedTask[]>([])
  const [autoCreate, setAutoCreate]   = useState(true)
  const [loading, setLoading]         = useState(false)
  const [msg, setMsg]                 = useState<{ type: "ok" | "err" | "info"; text: string } | null>(null)

  if (!isOpen) return null

  const newProjects = [...new Set(
    parsed.map(t => t.context).filter(ctx => ctx && !existingProjects.includes(ctx))
  )]

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)
    setMsg(null)

    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const text = ev.target?.result as string
        const lines = text.split(/\r?\n/).filter(l => l.trim())
        if (lines.length < 2) {
          setMsg({ type: "err", text: "CSV needs a header row + at least one data row" })
          return
        }
        const headers = parseCSVLine(lines[0])
        const tasks: ParsedTask[] = []
        for (let i = 1; i < lines.length; i++) {
          const vals = parseCSVLine(lines[i])
          const ctx  = getField(headers, vals, "context") || "general"
          tasks.push({
            task_name:       getField(headers, vals, "task_name") || `Task ${i}`,
            context:         ctx,
            base_load_score: parseFloat(getField(headers, vals, "base_load_score")) || 5,
            rule_type:       getField(headers, vals, "rule_type") || "ONCE",
            due_date:        getField(headers, vals, "due_date") || null,
            notes:           getField(headers, vals, "notes") || null,
            isNewProject:    !existingProjects.includes(ctx),
          })
        }
        setParsed(tasks)
        setMsg({ type: "info", text: `Parsed ${tasks.length} task${tasks.length !== 1 ? "s" : ""} from CSV` })
      } catch {
        setMsg({ type: "err", text: "Failed to parse CSV" })
      }
    }
    reader.readAsText(file)
  }

  async function handleImport() {
    if (parsed.length === 0) { setMsg({ type: "err", text: "No tasks to import" }); return }
    const file = fileRef.current?.files?.[0]
    if (!file) { setMsg({ type: "err", text: "No file selected" }); return }

    setLoading(true)
    setMsg({ type: "info", text: "Importing…" })
    try {
      // Create new projects if needed
      if (autoCreate && newProjects.length > 0) {
        for (const name of newProjects) {
          await apiFetch("/api/agents/project/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_name: name }),
          }).catch(() => {})
        }
      }

      // Upload CSV
      const form = new FormData()
      form.append("file", file)
      const res = await apiFetch("/api/lbs/tasks/upload-csv", { method: "POST", body: form })
      if (res.ok) {
        const data = await res.json()
        setMsg({ type: "ok", text: data.message || `Imported ${parsed.length} tasks!` })
        setTimeout(() => { onImportComplete(); handleClose() }, 1400)
      } else {
        const err = await res.json().catch(() => ({}))
        setMsg({ type: "err", text: err.detail || "Import failed" })
      }
    } catch (e: any) {
      setMsg({ type: "err", text: e.message || "Import failed" })
    } finally {
      setLoading(false)
    }
  }

  function handleClose() {
    setParsed([])
    setFileName("")
    setMsg(null)
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={handleClose}>
        <div className="bg-gray-950 border border-gray-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>

          {/* Header */}
          <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-gray-800">
            <div className="flex items-center gap-3">
              <Upload size={16} className="text-cyan-400" />
              <span className="text-sm font-bold text-white">Import Tasks from CSV</span>
            </div>
            <button onClick={handleClose} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-500 hover:text-white transition-all">
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-5">

            {/* Status */}
            {msg && (
              <div className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium ${
                msg.type === "ok"   ? "bg-cyan-900/30 border border-cyan-700/40 text-cyan-300"
                : msg.type === "err" ? "bg-red-900/30 border border-red-700/40 text-red-300"
                : "bg-blue-900/30 border border-blue-700/40 text-blue-300"
              }`}>
                {msg.type === "ok" ? <CheckCircle2 size={16} /> : msg.type === "err" ? <AlertTriangle size={16} /> : null}
                {msg.text}
              </div>
            )}

            {/* File drop zone */}
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-gray-700 hover:border-cyan-600 rounded-2xl p-8 text-center cursor-pointer transition-colors group"
            >
              <input ref={fileRef} type="file" accept=".csv" onChange={handleFileChange} className="hidden" />
              {fileName ? (
                <div className="space-y-1">
                  <FileText size={28} className="mx-auto text-cyan-400" />
                  <p className="text-sm font-bold text-white mt-2">{fileName}</p>
                  <p className="text-xs text-gray-500">Click to change file</p>
                </div>
              ) : (
                <div className="space-y-1">
                  <Upload size={28} className="mx-auto text-gray-600 group-hover:text-cyan-500 transition-colors" />
                  <p className="text-sm text-gray-400 mt-2">Click to select a CSV file</p>
                  <p className="text-xs text-gray-600">Required columns: task_name, context, base_load_score, rule_type</p>
                </div>
              )}
            </div>

            {/* Preview */}
            {parsed.length > 0 && (
              <div>
                <p className="text-xs font-black uppercase tracking-widest text-gray-500 mb-2">Preview ({parsed.length} tasks)</p>
                <div className="border border-gray-800 rounded-xl overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-gray-900">
                        <th className="px-3 py-2 text-left font-bold text-gray-400">Task</th>
                        <th className="px-3 py-2 text-left font-bold text-gray-400">Context</th>
                        <th className="px-3 py-2 text-left font-bold text-gray-400">Load</th>
                        <th className="px-3 py-2 text-left font-bold text-gray-400">Rule</th>
                        <th className="px-3 py-2 text-left font-bold text-gray-400">Due</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {parsed.slice(0, 8).map((t, i) => (
                        <tr key={i} className="hover:bg-gray-900/50">
                          <td className="px-3 py-2 text-gray-200 truncate max-w-[160px]">{t.task_name}</td>
                          <td className="px-3 py-2">
                            {t.isNewProject
                              ? <span className="text-amber-400 flex items-center gap-1"><AlertTriangle size={10} />{t.context}</span>
                              : <span className="text-gray-400">{t.context}</span>
                            }
                          </td>
                          <td className="px-3 py-2 text-gray-400">{t.base_load_score}</td>
                          <td className="px-3 py-2 text-gray-500">{t.rule_type}</td>
                          <td className="px-3 py-2 text-gray-500">{t.due_date || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {parsed.length > 8 && (
                    <div className="px-3 py-2 text-center text-xs text-gray-600 bg-gray-900/50">
                      …and {parsed.length - 8} more
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* New projects warning */}
            {newProjects.length > 0 && (
              <div className="flex items-start gap-3 px-4 py-3 bg-amber-900/20 border border-amber-700/30 rounded-xl">
                <AlertTriangle size={15} className="text-amber-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-amber-300">{newProjects.length} new project{newProjects.length > 1 ? "s" : ""} will be created</p>
                  <p className="text-xs text-gray-400 mt-0.5 truncate">{newProjects.join(", ")}</p>
                  <label className="flex items-center gap-2 mt-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoCreate}
                      onChange={e => setAutoCreate(e.target.checked)}
                      className="w-3.5 h-3.5 accent-cyan-500"
                    />
                    <span className="text-xs text-gray-400">Auto-create missing projects</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex-shrink-0 flex gap-3 p-5 border-t border-gray-800">
            <button
              onClick={handleClose}
              className="flex-1 py-2.5 bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-300 rounded-xl text-sm font-semibold transition-all"
            >
              Cancel
            </button>
            <button
              onClick={handleImport}
              disabled={loading || parsed.length === 0}
              className="flex-1 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white rounded-xl text-sm font-semibold transition-all"
            >
              {loading ? "Importing…" : `Import ${parsed.length} Task${parsed.length !== 1 ? "s" : ""}`}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
