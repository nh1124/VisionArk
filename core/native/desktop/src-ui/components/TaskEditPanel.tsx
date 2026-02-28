import React, { useEffect, useState } from "react"
import {
  X, CheckCircle2, Circle, Plus, Trash2, Clock, Lock, Unlock,
  ChevronDown, Save, AlertTriangle,
} from "lucide-react"
import {
  apiFetch, apiJson, getLBSTask, updateLBSTask, deleteLBSTask, createLBSException,
  type LBSTaskFull,
} from "../lib/api"

// ── Spoke color helper ────────────────────────────────────────────────────────

const SPOKE_COLORS: Record<string, string> = {
  research: "#3B82F6",
  development: "#10B981",
  writing: "#F59E0B",
  testing: "#EF4444",
  planning: "#8B5CF6",
  review: "#EC4899",
  deployment: "#14B8A6",
  documentation: "#F97316",
}
function spokeColor(name?: string | null) {
  if (!name) return "#6B7280"
  return SPOKE_COLORS[name.toLowerCase()] ?? "#6B7280"
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Subtask { id: string; text: string; done: boolean }

interface HistoryEntry {
  target_date: string
  status: string
  completed_at?: string | null
}

interface Props {
  taskId: string | null          // task to open; null = closed
  targetDate?: string            // execution date context
  onClose: () => void
  onSaved?: () => void           // called after successful save/delete
  availableProjects?: string[]
  /** "overlay" = fixed right drawer (default), "inline" = fills parent container */
  mode?: "overlay" | "inline"
}

const RULE_TYPES = [
  { value: "ONCE",               label: "Once" },
  { value: "WEEKLY",             label: "Weekly" },
  { value: "EVERY_N_DAYS",       label: "Every N Days" },
  { value: "MONTHLY_DAY",        label: "Monthly (day)" },
  { value: "MONTHLY_NTH_WEEKDAY",label: "Monthly (nth weekday)" },
]

const WEEKDAYS: { key: keyof LBSTaskFull; label: string }[] = [
  { key: "mon", label: "Mo" },
  { key: "tue", label: "Tu" },
  { key: "wed", label: "We" },
  { key: "thu", label: "Th" },
  { key: "fri", label: "Fr" },
  { key: "sat", label: "Sa" },
  { key: "sun", label: "Su" },
]

// ── Main Component ────────────────────────────────────────────────────────────

export default function TaskEditPanel({
  taskId,
  targetDate,
  onClose,
  onSaved,
  availableProjects = [],
  mode = "overlay",
}: Props) {
  const isOpen = !!taskId

  const [task, setTask]           = useState<LBSTaskFull | null>(null)
  const [loading, setLoading]     = useState(false)
  const [saving, setSaving]       = useState(false)
  const [deleting, setDeleting]   = useState(false)
  const [msg, setMsg]             = useState<{ type: "ok" | "err"; text: string } | null>(null)
  const [instanceOnly, setInstanceOnly] = useState(false)
  const [history, setHistory]     = useState<HistoryEntry[]>([])
  const [histLoading, setHistLoading] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  // Fetch task when opened
  useEffect(() => {
    if (!taskId) { setTask(null); return }
    setLoading(true)
    setMsg(null)
    setInstanceOnly(false)
    setShowHistory(false)
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
    getLBSTask(taskId, targetDate)
      .then(data => setTask({ ...data, timezone: data.timezone || tz }))
      .catch(() => setMsg({ type: "err", text: "Failed to load task" }))
      .finally(() => setLoading(false))

    // Fetch history
    if (taskId) {
      setHistLoading(true)
      const end = new Date().toISOString().split("T")[0]
      const start = new Date(Date.now() - 14 * 86400_000).toISOString().split("T")[0]
      apiFetch(`/api/lbs/tasks/${taskId}/history?start_date=${start}&end_date=${end}`)
        .then(r => r.ok ? r.json() : [])
        .then(d => setHistory(Array.isArray(d) ? d : []))
        .catch(() => {})
        .finally(() => setHistLoading(false))
    }
  }, [taskId, targetDate])

  if (!isOpen) return null

  // ── Field helpers ──────────────────────────────────────────────────────────

  function update<K extends keyof LBSTaskFull>(key: K, value: LBSTaskFull[K]) {
    setTask(prev => prev ? { ...prev, [key]: value } : prev)
  }

  function updateMeta(key: string, value: any) {
    setTask(prev => {
      if (!prev) return prev
      return { ...prev, meta_payload: { ...(prev.meta_payload ?? {}), [key]: value } }
    })
  }

  const steps: Subtask[] = task?.meta_payload?.steps ?? []

  function addStep() {
    updateMeta("steps", [...steps, { id: crypto.randomUUID(), text: "", done: false }])
  }
  function removeStep(id: string) {
    updateMeta("steps", steps.filter(s => s.id !== id))
  }
  function updateStep(id: string, field: "text" | "done", value: any) {
    updateMeta("steps", steps.map(s => s.id === id ? { ...s, [field]: value } : s))
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  async function handleSave() {
    if (!task) return
    setSaving(true)
    setMsg(null)
    try {
      const isRecurring = task.rule_type !== "ONCE"

      if (instanceOnly && isRecurring) {
        const date = task.due_date ?? targetDate ?? new Date().toISOString().split("T")[0]
        await createLBSException({
          task_id: task.task_id,
          target_date: date,
          exception_type: "OVERRIDE_LOAD",
          override_load_value: task.base_load_score,
          start_time: task.start_time,
          end_time: task.end_time,
          notes: task.notes,
        })
        setMsg({ type: "ok", text: "This occurrence updated!" })
      } else {
        await updateLBSTask(task.task_id, task)
        setMsg({ type: "ok", text: "Task saved!" })
      }
      setTimeout(() => { onSaved?.(); onClose() }, 800)
    } catch (e: any) {
      setMsg({ type: "err", text: e.message || "Save failed" })
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!task) return
    const ok = window.confirm(`Delete "${task.task_name}"?`)
    if (!ok) return
    setDeleting(true)
    try {
      const isRecurring = task.rule_type !== "ONCE"
      if (instanceOnly && isRecurring) {
        const date = task.due_date ?? targetDate ?? new Date().toISOString().split("T")[0]
        await createLBSException({ task_id: task.task_id, target_date: date, exception_type: "SKIP" })
        setMsg({ type: "ok", text: "Occurrence skipped!" })
      } else {
        await deleteLBSTask(task.task_id)
        setMsg({ type: "ok", text: "Task deleted!" })
      }
      setTimeout(() => { onSaved?.(); onClose() }, 800)
    } catch (e: any) {
      setMsg({ type: "err", text: e.message || "Delete failed" })
    } finally {
      setDeleting(false)
    }
  }

  async function handleToggleStatus(status: string) {
    if (!task) return
    const date = task.due_date ?? targetDate ?? new Date().toISOString().split("T")[0]
    try {
      await apiJson(`/api/lbs/tasks/${task.task_id}/complete`, {
        method: "POST",
        body: JSON.stringify({ target_date: date, status }),
      })
      setTask(prev => prev ? { ...prev, status } : prev)
    } catch { }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const color = spokeColor(task?.context)
  const isRecurring = task?.rule_type !== "ONCE"

  const panelEl = (
    <div className={
      mode === "inline"
        ? "h-full w-[420px] flex-shrink-0 bg-gray-950 border-l border-gray-800 flex flex-col"
        : "fixed right-0 top-0 bottom-0 w-[440px] max-w-full bg-gray-950 border-l border-gray-800 flex flex-col z-50 shadow-2xl"
    }>

        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-xs font-black uppercase tracking-widest text-gray-400">Task Detail</span>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-500 hover:text-white transition-all">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-sm animate-pulse">Loading…</div>
        ) : !task ? (
          <div className="flex-1 flex items-center justify-center text-red-400 text-sm">Failed to load task</div>
        ) : (
          <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-5">

            {/* Status buttons */}
            <div className="flex gap-2">
              {["todo", "done", "skipped"].map(s => (
                <button
                  key={s}
                  onClick={() => handleToggleStatus(s)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                    task.status === s
                      ? s === "done" ? "bg-cyan-600 border-cyan-500 text-white"
                        : s === "skipped" ? "bg-gray-700 border-gray-600 text-gray-300"
                        : "bg-blue-600 border-blue-500 text-white"
                      : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-600 hover:text-gray-300"
                  }`}
                >
                  {s === "done" ? <CheckCircle2 size={12} /> : <Circle size={12} />}
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
              {task.is_locked && (
                <span className="ml-auto flex items-center gap-1 text-xs text-amber-400">
                  <Lock size={12} /> Locked
                </span>
              )}
            </div>

            {/* Task name */}
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Task Name</label>
              <input
                value={task.task_name}
                onChange={e => update("task_name", e.target.value)}
                className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-600 transition-colors"
              />
            </div>

            {/* Context + Load */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Context</label>
                <div className="relative">
                  {availableProjects.length > 0 ? (
                    <>
                      <select
                        value={task.context}
                        onChange={e => update("context", e.target.value)}
                        className="absolute inset-0 opacity-0 cursor-pointer z-10 w-full"
                      >
                        {availableProjects.map(p => <option key={p} value={p}>{p}</option>)}
                        <option value={task.context}>{task.context}</option>
                      </select>
                      <div className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                        <span className="text-white truncate">{task.context}</span>
                      </div>
                    </>
                  ) : (
                    <input
                      value={task.context}
                      onChange={e => update("context", e.target.value)}
                      className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                    />
                  )}
                </div>
              </div>
              <div className="w-24">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Load</label>
                <input
                  type="number" min="0.1" max="10" step="0.1"
                  value={task.base_load_score}
                  onChange={e => update("base_load_score", parseFloat(e.target.value) || 1)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
            </div>

            {/* Rule type */}
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Recurrence</label>
              <select
                value={task.rule_type}
                onChange={e => update("rule_type", e.target.value)}
                className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors appearance-none"
              >
                {RULE_TYPES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>

            {/* Weekly day toggles */}
            {task.rule_type === "WEEKLY" && (
              <div>
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Days</label>
                <div className="flex gap-1.5">
                  {WEEKDAYS.map(({ key, label }) => (
                    <button
                      key={key}
                      onClick={() => update(key, !task[key] as any)}
                      className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold transition-all border ${
                        task[key]
                          ? "bg-cyan-600 border-cyan-500 text-white"
                          : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-600"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Every N Days */}
            {task.rule_type === "EVERY_N_DAYS" && (
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Every N Days</label>
                  <input
                    type="number" min="1"
                    value={task.interval_days ?? 1}
                    onChange={e => update("interval_days", parseInt(e.target.value) || 1)}
                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Anchor Date</label>
                  <input
                    type="date"
                    value={task.anchor_date ?? ""}
                    onChange={e => update("anchor_date", e.target.value || null)}
                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                  />
                </div>
              </div>
            )}

            {/* Due date + times */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Due Date</label>
                <input
                  type="date"
                  value={task.due_date ?? ""}
                  onChange={e => update("due_date", e.target.value || null)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
            </div>

            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Start Time</label>
                <input
                  type="time"
                  value={task.start_time ?? ""}
                  onChange={e => update("start_time", e.target.value || null)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">End Time</label>
                <input
                  type="time"
                  value={task.end_time ?? ""}
                  onChange={e => update("end_time", e.target.value || null)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
            </div>

            {/* Timezone */}
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Timezone</label>
              <select
                value={task.timezone ?? "UTC"}
                onChange={e => update("timezone", e.target.value)}
                className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors appearance-none"
              >
                <option value="UTC">UTC</option>
                {Intl.supportedValuesOf?.('timeZone').map(tz => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>

            {/* Start / End date range */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Active From</label>
                <input
                  type="date"
                  value={task.start_date ?? ""}
                  onChange={e => update("start_date", e.target.value || null)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Active Until</label>
                <input
                  type="date"
                  value={task.end_date ?? ""}
                  onChange={e => update("end_date", e.target.value || null)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors"
                />
              </div>
            </div>

            {/* Notes */}
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Notes</label>
              <textarea
                value={task.notes ?? ""}
                onChange={e => update("notes", e.target.value || null)}
                rows={3}
                className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-cyan-600 transition-colors"
                placeholder="Notes…"
              />
            </div>

            {/* Subtasks */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-gray-500">Subtasks</label>
                <button onClick={addStep} className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300">
                  <Plus size={12} /> Add
                </button>
              </div>
              {steps.length === 0 ? (
                <p className="text-xs text-gray-600 italic">No subtasks yet</p>
              ) : (
                <div className="space-y-2">
                  {steps.map(s => (
                    <div key={s.id} className="flex items-center gap-2 group">
                      <button onClick={() => updateStep(s.id, "done", !s.done)} className="flex-shrink-0 text-gray-500 hover:text-cyan-400 transition-colors">
                        {s.done ? <CheckCircle2 size={15} className="text-cyan-500" /> : <Circle size={15} />}
                      </button>
                      <input
                        value={s.text}
                        onChange={e => updateStep(s.id, "text", e.target.value)}
                        placeholder="Step…"
                        className={`flex-1 bg-transparent text-sm focus:outline-none transition-colors border-b border-transparent focus:border-gray-700 ${
                          s.done ? "line-through text-gray-500" : "text-gray-200"
                        }`}
                      />
                      <button onClick={() => removeStep(s.id)} className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Instance-only toggle for recurring tasks */}
            {isRecurring && (
              <div
                onClick={() => setInstanceOnly(v => !v)}
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  instanceOnly
                    ? "bg-amber-900/20 border-amber-600/40 text-amber-300"
                    : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
                }`}
              >
                <AlertTriangle size={14} className={instanceOnly ? "text-amber-400" : "text-gray-600"} />
                <div className="flex-1">
                  <p className="text-xs font-bold">Apply to this occurrence only</p>
                  {instanceOnly && (
                    <p className="text-[10px] mt-0.5 opacity-70">Changes won't affect the recurring template</p>
                  )}
                </div>
                <div className={`w-8 h-4 rounded-full transition-all ${instanceOnly ? "bg-amber-500" : "bg-gray-700"}`}>
                  <div className={`w-3 h-3 rounded-full bg-white m-0.5 transition-transform ${instanceOnly ? "translate-x-4" : ""}`} />
                </div>
              </div>
            )}

            {/* History */}
            <div>
              <button
                onClick={() => setShowHistory(v => !v)}
                className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-gray-500 hover:text-gray-300 transition-colors"
              >
                <ChevronDown size={12} className={`transition-transform ${showHistory ? "" : "-rotate-90"}`} />
                Execution History (2 weeks)
              </button>
              {showHistory && (
                <div className="mt-2 space-y-1.5">
                  {histLoading ? (
                    <p className="text-xs text-gray-600 animate-pulse">Loading…</p>
                  ) : history.length === 0 ? (
                    <p className="text-xs text-gray-600">No history found</p>
                  ) : (
                    history.slice(0, 14).map((h, i) => (
                      <div key={i} className="flex items-center gap-3 px-3 py-1.5 bg-gray-900 rounded-lg">
                        <span className="text-[10px] text-gray-500 w-20">{h.target_date}</span>
                        <span className={`text-[10px] font-bold capitalize ${
                          h.status === "done" || h.status === "completed" ? "text-cyan-400"
                          : h.status === "skipped" ? "text-gray-500"
                          : "text-gray-400"
                        }`}>
                          {h.status}
                        </span>
                        {h.completed_at && (
                          <span className="text-[9px] text-gray-600 ml-auto">
                            {new Date(h.completed_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

          </div>
        )}

        {/* Footer */}
        {task && (
          <div className="flex-shrink-0 border-t border-gray-800 p-4 space-y-3">
            {msg && (
              <div className={`text-xs px-3 py-2 rounded-lg ${msg.type === "ok" ? "bg-cyan-900/30 text-cyan-300" : "bg-red-900/30 text-red-300"}`}>
                {msg.text}
              </div>
            )}
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                disabled={deleting || saving}
                className="flex items-center gap-1.5 px-3 py-2 bg-gray-900 hover:bg-red-900/40 border border-gray-800 hover:border-red-700/50 text-gray-400 hover:text-red-300 rounded-xl text-xs font-semibold transition-all disabled:opacity-40"
              >
                <Trash2 size={13} />
                {instanceOnly ? "Skip" : "Delete"}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || deleting}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-40"
              >
                <Save size={13} />
                {saving ? "Saving…" : instanceOnly ? "Save Occurrence" : "Save Task"}
              </button>
            </div>
          </div>
        )}
    </div>
  )

  if (mode === "inline") return panelEl
  return (
    <>
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40" onClick={onClose} />
      {panelEl}
    </>
  )
}
