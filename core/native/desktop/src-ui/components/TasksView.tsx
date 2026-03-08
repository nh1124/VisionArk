import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react"
import {
  CheckCircle2, Circle, Clock, Plus, RefreshCw, Tag, Zap,
  CalendarDays, Calendar, ChevronDown, ChevronRight,
  Hash, Archive, Download, Upload, Trash2, CalendarCheck,
  Square, CheckSquare, X, FileDown,
} from "lucide-react"
import {
  apiFetch,
  listLBSTasks, completeLBSTask, createLBSTask, getOverdueTasks,
  type LBSTask, type LBSTaskCreate,
} from "../lib/api"
import type { CalendarStatusFilter, TaskFilter } from "./NavSidebar"
import TaskEditPanel from "./TaskEditPanel"
import CalendarView from "./CalendarView"
import TimelineView from "./TimelineView"
import ImportModal from "./ImportModal"

// ── Utilities ─────────────────────────────────────────────────────────────────

function getLocalDateString(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
const TODAY = getLocalDateString()

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return getLocalDateString(d)
}

function addMonths(iso: string, months: number) {
  const d = new Date(`${iso}T00:00:00`)
  d.setMonth(d.getMonth() + months)
  return getLocalDateString(d)
}

function weekRangeLabel(anchor: string) {
  const d = new Date(`${anchor}T00:00:00`)
  const dow = d.getDay()
  const sun = new Date(d)
  sun.setDate(d.getDate() - dow)
  const sat = new Date(sun)
  sat.setDate(sun.getDate() + 6)
  const s = sun.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
  const e = sat.toLocaleDateString("en-US", { month: "long", day: "numeric" })
  return `${s} - ${e}`
}

function monthLabel(anchor: string) {
  const d = new Date(`${anchor}T00:00:00`)
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long" })
}

type ViewMode = "list" | "calendar" | "timeline"

const LOAD_COLORS = { low: "text-emerald-400", medium: "text-yellow-400", high: "text-orange-400", critical: "text-red-400" }
function loadLabel(score: number) {
  if (score <= 1) return { color: LOAD_COLORS.low, label: "L" }
  if (score <= 2) return { color: LOAD_COLORS.medium, label: "M" }
  if (score <= 3) return { color: LOAD_COLORS.high, label: "H" }
  return { color: LOAD_COLORS.critical, label: "!!" }
}
function toDisplayDate(iso: string) {
  return new Date(iso).toLocaleDateString("ja-JP", { month: "short", day: "numeric" })
}
function recurrenceLabel(ruleType?: string) {
  const normalized = (ruleType || "").toUpperCase()
  if (normalized === "ONCE") return "once"
  if (normalized === "WEEKLY") return "weekly"
  if (normalized === "EVERY_N_DAYS") return "every n days"
  if (normalized === "MONTHLY_DAY") return "monthly"
  if (normalized === "MONTHLY_NTH_WEEKDAY") return "monthly (nth weekday)"
  return normalized ? normalized.toLowerCase().replace(/_/g, " ") : "recurring"
}
function weeklyDaysText(task: LBSTask) {
  const raw = task as LBSTask & {
    mon?: boolean; tue?: boolean; wed?: boolean; thu?: boolean; fri?: boolean; sat?: boolean; sun?: boolean
  }
  const days = [
    raw.mon ? "Mon" : null, raw.tue ? "Tue" : null, raw.wed ? "Wed" : null,
    raw.thu ? "Thu" : null, raw.fri ? "Fri" : null, raw.sat ? "Sat" : null, raw.sun ? "Sun" : null,
  ].filter(Boolean) as string[]
  return days.length > 0 ? days.join("/") : "weekly"
}
function recurrenceMeta(task: LBSTask) {
  const rule = (task.rule_type || "").toUpperCase()
  const raw = task as LBSTask & { interval_days?: number; anchor_date?: string | null; month_day?: number }
  if (rule === "ONCE") return task.due_date ? `due ${toDisplayDate(task.due_date)}` : null
  if (rule === "WEEKLY") return weeklyDaysText(task)
  if (rule === "EVERY_N_DAYS") {
    const everyText = raw.interval_days && raw.interval_days > 0 ? `every ${raw.interval_days}d` : "every n days"
    return raw.anchor_date ? `${everyText} from ${toDisplayDate(raw.anchor_date)}` : everyText
  }
  if (rule === "MONTHLY_DAY") {
    if (raw.month_day && raw.month_day > 0) return `monthly day ${raw.month_day}`
    return "monthly"
  }
  if (rule === "MONTHLY_NTH_WEEKDAY") return "monthly (nth weekday)"
  return null
}
function groupByContext(tasks: LBSTask[]): Map<string, LBSTask[]> {
  const map = new Map<string, LBSTask[]>()
  for (const t of tasks) {
    const ctx = t.context || "inbox"
    if (!map.has(ctx)) map.set(ctx, [])
    map.get(ctx)!.push(t)
  }
  return map
}

// ── TaskRow ───────────────────────────────────────────────────────────────────

interface TaskRowProps {
  task: LBSTask
  showStatus: boolean
  selected: boolean
  selectionMode: boolean
  onToggle?: (task: LBSTask) => void
  onClick: (task: LBSTask, e: React.MouseEvent) => void
  onContextMenu: (task: LBSTask, e: React.MouseEvent) => void
  onDragStart?: (task: LBSTask, e: React.DragEvent) => void
  onDragEnd?: () => void
}

function TaskRow({ task, showStatus, selected, selectionMode, onToggle, onClick, onContextMenu, onDragStart, onDragEnd }: TaskRowProps) {
  const isDone = task.status === "done"
  const isSkipped = task.status === "skipped"
  const load = loadLabel(task.base_load_score)

  return (
    <div
      draggable
      onDragStart={e => onDragStart?.(task, e)}
      onDragEnd={onDragEnd}
      onClick={e => onClick(task, e)}
      onContextMenu={e => onContextMenu(task, e)}
      className={`flex items-start gap-3 px-4 py-3 rounded-xl transition-colors group cursor-pointer active:cursor-grabbing select-none ${selected ? "bg-blue-900/25 ring-1 ring-blue-700/40"
          : isDone ? "opacity-50 hover:opacity-70"
            : "hover:bg-gray-800/50"
        }`}
    >
      {/* Selection checkbox / status toggle */}
      <div className="flex-shrink-0 mt-0.5">
        {selectionMode ? (
          <div className={`w-[18px] h-[18px] rounded-[4px] border transition-all flex items-center justify-center ${selected ? "bg-blue-600 border-blue-500" : "border-gray-600 hover:border-blue-500"
            }`}>
            {selected && <CheckSquare size={14} className="text-white" />}
          </div>
        ) : showStatus && onToggle ? (
          <button
            onClick={e => { e.stopPropagation(); onToggle(task) }}
            className="text-gray-500 hover:text-cyan-400 transition-colors"
            title={isDone ? "Mark as todo" : "Mark as done"}
          >
            {isDone ? <CheckCircle2 size={18} className="text-cyan-500" />
              : isSkipped ? <Circle size={18} className="text-gray-600" />
                : <Circle size={18} />}
          </button>
        ) : (
          <Circle size={14} className="text-gray-700 mt-0.5" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium leading-snug ${isDone ? "line-through text-gray-500" : "text-gray-200"}`}>
          {task.task_name}
        </p>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className={`text-[10px] font-bold ${load.color}`}>
            <Zap size={9} className="inline mr-0.5" />{load.label} {task.base_load_score.toFixed(1)}
          </span>
          <span className="flex items-center gap-1 text-[10px] text-gray-500"><Tag size={9} />{task.context}</span>
          <span className="text-[10px] text-gray-600">{recurrenceLabel(task.rule_type)}</span>
          {(task.start_time || task.end_time) && (
            <span className="flex items-center gap-1 text-[10px] text-gray-500">
              <Clock size={9} />{task.start_time}{task.end_time ? `  E${task.end_time}` : ""}
            </span>
          )}
          {!showStatus && recurrenceMeta(task) && (
            <span className="text-[10px] text-gray-600">{recurrenceMeta(task)}</span>
          )}
          {task.notes && (
            <span className="text-[10px] text-gray-600 italic truncate max-w-[140px]">{task.notes}</span>
          )}
        </div>
      </div>

      <ChevronRight size={13} className="flex-shrink-0 mt-1 text-gray-700 group-hover:text-gray-500 transition-colors" />
    </div>
  )
}

// ── ContextGroup ──────────────────────────────────────────────────────────────

interface ContextGroupProps {
  context: string
  tasks: LBSTask[]
  showStatus: boolean
  selectionMode: boolean
  selectedIds: Set<string>
  onToggle?: (task: LBSTask) => void
  onRowClick: (task: LBSTask, e: React.MouseEvent) => void
  onContextMenu: (task: LBSTask, e: React.MouseEvent) => void
  onTaskDragStart: (task: LBSTask, e: React.DragEvent) => void
  onTaskDragEnd: () => void
}

function ContextGroup({ context, tasks, showStatus, selectionMode, selectedIds, onToggle, onRowClick, onContextMenu, onTaskDragStart, onTaskDragEnd }: ContextGroupProps) {
  const [expanded, setExpanded] = useState(true)
  const doneCount = tasks.filter(t => t.status === "done").length
  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-gray-200 transition-colors"
      >
        <span className={`transition-transform duration-150 ${expanded ? "" : "-rotate-90"}`}>▾</span>
        <span className="uppercase tracking-wider">{context}</span>
        <span className="ml-auto text-gray-600 font-normal">
          {showStatus ? `${doneCount}/${tasks.length}` : tasks.length}
        </span>
      </button>
      {expanded && tasks.map(t => (
        <TaskRow
          key={`${t.task_id}-${t.due_date ?? "all"}`}
          task={t}
          showStatus={showStatus}
          selected={selectedIds.has(t.task_id)}
          selectionMode={selectionMode}
          onToggle={onToggle}
          onClick={onRowClick}
          onContextMenu={onContextMenu}
          onDragStart={onTaskDragStart}
          onDragEnd={onTaskDragEnd}
        />
      ))}
    </div>
  )
}

// ── AddTaskForm ───────────────────────────────────────────────────────────────

const RULE_TYPES = [
  { value: "ONCE", label: "Once" }, { value: "WEEKLY", label: "Weekly" },
  { value: "EVERY_N_DAYS", label: "Daily-N" }, { value: "MONTHLY_DAY", label: "Monthly" },
]
const WEEKDAYS: Array<{ key: "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun"; label: string }> = [
  { key: "mon", label: "Mo" },
  { key: "tue", label: "Tu" },
  { key: "wed", label: "We" },
  { key: "thu", label: "Th" },
  { key: "fri", label: "Fr" },
  { key: "sat", label: "Sa" },
  { key: "sun", label: "Su" },
]

function SelectOption({ value, label }: { value: string | number; label: string }) {
  return <option value={value} style={{ color: "#E5E7EB", backgroundColor: "#1F2937" }}>{label}</option>
}

function AddTaskForm({ onAdd, onCancel, defaultContext, availableProjects = [] }: {
  onAdd: (t: LBSTaskCreate) => Promise<void>
  onCancel: () => void
  defaultContext?: string
  availableProjects?: string[]
}) {
  const [name, setName] = useState("")
  const [context, setContext] = useState(defaultContext || "inbox")
  const [load, setLoad] = useState("1")
  const [ruleType, setRuleType] = useState("ONCE")
  const [dueDate, setDueDate] = useState(TODAY)
  const [notes, setNotes] = useState("")
  const [weeklyDays, setWeeklyDays] = useState<Record<"mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun", boolean>>({
    mon: false, tue: false, wed: false, thu: false, fri: false, sat: false, sun: false,
  })
  const [intervalDays, setIntervalDays] = useState("1")
  const [anchorDate, setAnchorDate] = useState(TODAY)
  const [monthDay, setMonthDay] = useState(String(new Date().getDate()))
  const [saving, setSaving] = useState(false)
  const [showMore, setShowMore] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const dateRef = useRef<HTMLInputElement>(null)
  const contextOptions = useMemo(() => {
    const set = new Set<string>(["inbox", ...availableProjects.filter(Boolean)])
    if (defaultContext) set.add(defaultContext)
    if (context) set.add(context)
    return Array.from(set)
  }, [availableProjects, context, defaultContext])
  useEffect(() => { nameRef.current?.focus() }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const payload: LBSTaskCreate = {
        task_name: name.trim(), context: context.trim() || "inbox",
        base_load_score: parseFloat(load) || 1, rule_type: ruleType,
        due_date: ruleType === "ONCE" ? (dueDate || null) : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        notes: notes.trim() || null,
      }

      if (ruleType === "WEEKLY") {
        const hasAnyDay = Object.values(weeklyDays).some(Boolean)
        const normalized = hasAnyDay ? weeklyDays : {
          ...weeklyDays,
          [WEEKDAYS[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1].key]: true,
        }
        Object.assign(payload, normalized)
      } else if (ruleType === "EVERY_N_DAYS") {
        payload.interval_days = Math.max(1, parseInt(intervalDays, 10) || 1)
        payload.anchor_date = anchorDate || null
      } else if (ruleType === "MONTHLY_DAY") {
        payload.month_day = Math.min(31, Math.max(1, parseInt(monthDay, 10) || 1))
      }

      await onAdd(payload)
    } finally { setSaving(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-4 mb-4 bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-3">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">New Task</p>
      <input ref={nameRef} value={name} onChange={e => setName(e.target.value)} placeholder="Task name…"
        className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 border border-gray-700 focus:outline-none focus:border-cyan-500" />
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <Archive size={10} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
          <select
            value={context}
            onChange={e => setContext(e.target.value)}
            className="w-full appearance-none bg-gray-800 rounded-xl pl-7 pr-7 py-1.5 text-[10px] font-bold text-gray-300 border border-gray-700 focus:outline-none focus:border-cyan-500"
            style={{ colorScheme: "dark" }}
          >
            {contextOptions.map(p => <SelectOption key={p} value={p} label={p} />)}
          </select>
          <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        </div>
        <div className="relative w-24">
          <Hash size={10} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
          <select
            value={load}
            onChange={e => setLoad(e.target.value)}
            className="w-full appearance-none bg-gray-800 rounded-xl pl-7 pr-7 py-1.5 text-[10px] font-bold text-gray-300 border border-gray-700 focus:outline-none focus:border-cyan-500"
            style={{ colorScheme: "dark" }}
          >
            {["0.5", "1", "2", "3", "5", "8"].map(n => <SelectOption key={n} value={n} label={n} />)}
          </select>
          <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        </div>
        <div className="relative flex-1">
          <input ref={dateRef} type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="absolute inset-0 opacity-0 pointer-events-none" />
          <button type="button" onClick={() => dateRef.current?.showPicker()}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-800 rounded-xl border border-gray-700 text-[10px] font-bold text-gray-400 w-full">
            <Calendar size={10} /><span className="truncate">{dueDate === TODAY ? "Today" : dueDate}</span>
          </button>
        </div>
      </div>
      <button type="button" onClick={() => setShowMore(v => !v)}
        className="flex items-center gap-1 text-[10px] text-gray-600 hover:text-gray-400 transition-colors">
        <ChevronDown size={10} className={`transition-transform ${showMore ? "" : "-rotate-90"}`} />More options
      </button>
      {showMore && (
        <div className="space-y-2">
          <select value={ruleType} onChange={e => setRuleType(e.target.value)}
            className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
            style={{ colorScheme: "dark" }}>
            {RULE_TYPES.map(r => <SelectOption key={r.value} value={r.value} label={r.label} />)}
          </select>

          {ruleType === "WEEKLY" && (
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1.5">Days</p>
              <div className="grid grid-cols-7 gap-1.5">
                {WEEKDAYS.map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setWeeklyDays(prev => ({ ...prev, [key]: !prev[key] }))}
                    className={`py-1.5 rounded-lg text-[10px] font-bold transition-all border ${
                      weeklyDays[key]
                        ? "bg-cyan-600 border-cyan-500 text-white"
                        : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {ruleType === "EVERY_N_DAYS" && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1.5">Every N Days</p>
                <input
                  type="number"
                  min="1"
                  value={intervalDays}
                  onChange={e => setIntervalDays(e.target.value)}
                  className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
                />
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1.5">Anchor Date</p>
                <input
                  type="date"
                  value={anchorDate}
                  onChange={e => setAnchorDate(e.target.value)}
                  className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>
          )}

          {ruleType === "MONTHLY_DAY" && (
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1.5">Day Of Month</p>
              <input
                type="number"
                min="1"
                max="31"
                value={monthDay}
                onChange={e => setMonthDay(e.target.value)}
                className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
              />
            </div>
          )}

          <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes (optional)"
            className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 border border-gray-700 focus:outline-none focus:border-cyan-500" />
        </div>
      )}
      <div className="flex gap-2 justify-end pt-1">
        <button type="button" onClick={onCancel} className="px-4 py-2 text-xs text-gray-500 hover:text-gray-300 transition-colors">Cancel</button>
        <button type="submit" disabled={!name.trim() || saving}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-xs font-semibold rounded-xl transition-colors">
          {saving ? "Adding…" : "Add Task"}
        </button>
      </div>
    </form>
  )
}

// ── ExportSheet ───────────────────────────────────────────────────────────────

function ExportSheet({ onClose, onExport, taskCount }: {
  onClose: () => void
  onExport: (filename: string) => Promise<void>
  taskCount: number
}) {
  const [filename, setFilename] = useState(`tasks_export_${TODAY}.csv`)
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "err">("idle")
  const [errMsg, setErrMsg] = useState("")

  async function handleExport() {
    setStatus("loading")
    try {
      await onExport(filename || `tasks_export_${TODAY}.csv`)
      setStatus("done")
    } catch (e: any) {
      setErrMsg(e.message || "Export failed")
      setStatus("err")
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-50" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[380px] bg-gray-950 border border-gray-800 rounded-2xl shadow-2xl z-50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <FileDown size={16} className="text-cyan-400" />
            <span className="text-sm font-bold text-white">Export Tasks</span>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-500 hover:text-white transition-all">
            <X size={14} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Task count */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-900 rounded-xl border border-gray-800">
            <CheckSquare size={16} className="text-cyan-400 flex-shrink-0" />
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-gray-500">Exporting</p>
              <p className="text-sm font-bold text-white mt-0.5">{taskCount} active task{taskCount !== 1 ? "s" : ""}</p>
            </div>
          </div>

          {/* Filename */}
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-gray-500 block mb-1.5">Filename</label>
            <input
              value={filename}
              onChange={e => setFilename(e.target.value)}
              className="w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-600 transition-colors font-mono"
            />
          </div>

          {/* Format info */}
          <p className="text-[10px] text-gray-600">
            Columns: task_name, context, base_load_score, rule_type, due_date, start_time, end_time, notes
          </p>

          {/* Status */}
          {status === "done" && (
            <div className="flex items-center gap-2 px-3 py-2.5 bg-cyan-900/30 border border-cyan-700/40 rounded-xl text-xs text-cyan-300 font-medium">
              <CheckCircle2 size={14} />
              <span>Downloaded: <span className="font-mono">{filename}</span></span>
            </div>
          )}
          {status === "err" && (
            <div className="px-3 py-2.5 bg-red-900/30 border border-red-700/40 rounded-xl text-xs text-red-300">
              {errMsg}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-5 pb-5">
          <button onClick={onClose} className="flex-1 py-2.5 bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-300 rounded-xl text-sm font-semibold transition-all">
            {status === "done" ? "Close" : "Cancel"}
          </button>
          {status !== "done" && (
            <button onClick={handleExport} disabled={status === "loading"}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-xl text-sm font-bold transition-all">
              <Download size={14} />
              {status === "loading" ? "Exporting…" : "Download CSV"}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

// ── BulkActionBar ─────────────────────────────────────────────────────────────

function BulkActionBar({ count, onDone, onTodo, onDelete, onMoveDate, onClear }: {
  count: number
  onDone: () => void
  onTodo: () => void
  onDelete: () => void
  onMoveDate: (d: string) => void
  onClear: () => void
}) {
  const dateRef = useRef<HTMLInputElement>(null)
  return (
    <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-blue-950/60 border-b border-blue-800/40">
      <span className="text-xs font-bold text-blue-300 min-w-[60px]">{count} selected</span>
      <div className="flex items-center gap-1 flex-1">
        <button onClick={onDone}
          className="flex items-center gap-1 px-2.5 py-1.5 bg-cyan-700/30 hover:bg-cyan-600/40 border border-cyan-600/30 text-cyan-300 rounded-lg text-[10px] font-bold transition-all">
          <CheckCircle2 size={11} /> Done
        </button>
        <button onClick={onTodo}
          className="flex items-center gap-1 px-2.5 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-lg text-[10px] font-bold transition-all">
          <Circle size={11} /> Todo
        </button>
        {/* Move to date */}
        <div className="relative">
          <input ref={dateRef} type="date" defaultValue={TODAY}
            onChange={e => e.target.value && onMoveDate(e.target.value)}
            className="absolute inset-0 opacity-0 pointer-events-none" />
          <button onClick={() => dateRef.current?.showPicker()}
            className="flex items-center gap-1 px-2.5 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-lg text-[10px] font-bold transition-all">
            <CalendarCheck size={11} /> Move to…
          </button>
        </div>
        <button onClick={onDelete}
          className="flex items-center gap-1 px-2.5 py-1.5 bg-red-900/30 hover:bg-red-800/40 border border-red-700/40 text-red-300 rounded-lg text-[10px] font-bold transition-all">
          <Trash2 size={11} /> Delete
        </button>
      </div>
      <button onClick={onClear} className="p-1.5 text-gray-500 hover:text-gray-300 hover:bg-gray-800 rounded-lg transition-all">
        <X size={13} />
      </button>
    </div>
  )
}

// ── ContextMenu ───────────────────────────────────────────────────────────────

interface CtxMenuProps {
  x: number
  y: number
  task: LBSTask
  onStatus: (s: string) => void
  onEdit: () => void
  onDelete: () => void
  onMoveDate: (d: string) => void
  onClose: () => void
}

function ContextMenu({ x, y, task, onStatus, onEdit, onDelete, onMoveDate, onClose }: CtxMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [showDatePicker, setShowDatePicker] = useState(false)
  const dateRef = useRef<HTMLInputElement>(null)

  // Clamp position to viewport
  const [pos, setPos] = useState({ x, y })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const { offsetWidth: w, offsetHeight: h } = el
    const vw = window.innerWidth, vh = window.innerHeight
    setPos({ x: Math.min(x, vw - w - 8), y: Math.min(y, vh - h - 8) })
  }, [x, y])

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    setTimeout(() => document.addEventListener("mousedown", handler), 0)
    return () => document.removeEventListener("mousedown", handler)
  }, [onClose])

  const isDone = task.status === "done"

  return (
    <div
      ref={ref}
      style={{ position: "fixed", left: pos.x, top: pos.y, zIndex: 200 }}
      className="w-48 bg-gray-900/95 border border-gray-700 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden py-1 text-sm"
    >
      {/* Status toggles */}
      <button onClick={() => onStatus(isDone ? "todo" : "done")}
        className="flex items-center gap-2.5 w-full px-3 py-2 hover:bg-gray-800 text-left transition-colors">
        {isDone ? <Circle size={13} className="text-gray-400" /> : <CheckCircle2 size={13} className="text-cyan-400" />}
        <span className={isDone ? "text-gray-300" : "text-cyan-300 font-semibold"}>
          {isDone ? "Mark as Todo" : "Mark as Done"}
        </span>
      </button>
      <button onClick={() => onStatus("skipped")}
        className="flex items-center gap-2.5 w-full px-3 py-2 hover:bg-gray-800 text-left transition-colors text-gray-400">
        <Square size={13} className="text-gray-500" />Skip this occurrence
      </button>

      <div className="border-t border-gray-800 my-1" />

      {/* Move to date */}
      {showDatePicker ? (
        <div className="px-3 py-2">
          <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1.5">Move to date</p>
          <input
            ref={dateRef}
            type="date"
            defaultValue={task.due_date || TODAY}
            onChange={e => { if (e.target.value) { onMoveDate(e.target.value); onClose() } }}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600"
            autoFocus
          />
        </div>
      ) : (
        <button onClick={() => { setShowDatePicker(true); setTimeout(() => dateRef.current?.showPicker(), 50) }}
          className="flex items-center gap-2.5 w-full px-3 py-2 hover:bg-gray-800 text-left transition-colors text-gray-300">
          <CalendarCheck size={13} className="text-gray-400" />Move to date…
        </button>
      )}

      <button onClick={onEdit}
        className="flex items-center gap-2.5 w-full px-3 py-2 hover:bg-gray-800 text-left transition-colors text-gray-300">
        <ChevronRight size={13} className="text-gray-400" />Edit task…
      </button>

      <div className="border-t border-gray-800 my-1" />

      <button onClick={onDelete}
        className="flex items-center gap-2.5 w-full px-3 py-2 hover:bg-red-900/30 text-left transition-colors text-red-400">
        <Trash2 size={13} />Delete task
      </button>
    </div>
  )
}

// ── Filter Labels ─────────────────────────────────────────────────────────────

const FILTER_LABELS: Record<string, string> = {
  today: "Today", "my-day": "My Day", planned: "Planned",
  overdue: "Overdue", inbox: "All Tasks", project: "Project",
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  mode?: "tasks" | "calendar"
  filter?: TaskFilter
  filterContext?: string
  calendarStatusFilter?: CalendarStatusFilter
}

export default function TasksView({
  mode = "tasks",
  filter = "today",
  filterContext,
  calendarStatusFilter = "all",
}: Props) {
  // Core state
  const [tasks, setTasks] = useState<LBSTask[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [toggling, setToggling] = useState<Set<string>>(new Set())
  const [viewMode, setViewMode] = useState<ViewMode>(mode === "calendar" ? "calendar" : "list")
  const [calendarAnchorDate, setCalendarAnchorDate] = useState(TODAY)
  const [editTaskId, setEditTaskId] = useState<string | null>(null)
  const [editDate, setEditDate] = useState<string | undefined>()
  const [importOpen, setImportOpen] = useState(false)
  const [projects, setProjects] = useState<string[]>([])
  const [refreshKey, setRefreshKey] = useState(0)

  // Export sheet
  const [exportOpen, setExportOpen] = useState(false)
  const [exportCount, setExportCount] = useState(0)
  const [allTasksCache, setAllTasksCache] = useState<LBSTask[]>([])

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [lastSelectedId, setLastSelectedId] = useState<string | null>(null)

  // Context menu
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; task: LBSTask } | null>(null)

  // Responsive inline panel
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  const isWide = containerWidth >= 720

  const showStatus = filter === "today" || filter === "overdue"
  const targetDate = filter === "today" ? TODAY : undefined
  const isTasksPage = mode === "tasks"
  const isCalendarPage = mode === "calendar"

  useEffect(() => {
    setViewMode(mode === "calendar" ? "calendar" : "list")
  }, [mode])

  // Flat task list for range selection
  const flatTasks = useMemo(() => tasks, [tasks])

  // ── Projects ────────────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch("/api/agents/project/list")
      .then(r => r.ok ? r.json() : { projects: [] })
      .then(d => { if (d.projects) setProjects(d.projects.map((p: any) => p.name)) })
      .catch(() => { })
  }, [])

  // ── Fetch tasks ─────────────────────────────────────────────────────────────
  const fetchTasks = useCallback(async () => {
    if (!isTasksPage) return
    setLoading(true); setError(null)
    try {
      let result: LBSTask[] = []
      if (filter === "today") result = await listLBSTasks({ targetDate: TODAY })
      else if (filter === "overdue") result = await getOverdueTasks()
      else if (filter === "my-day") result = (await listLBSTasks({ active: true })).filter(t => t.meta_payload?.is_my_day)
      else if (filter === "planned") result = (await listLBSTasks({ active: true })).filter(t => t.due_date && t.due_date > TODAY)
      else result = await listLBSTasks({ active: true })
      if (filterContext) {
        result = result.filter(t => t.context === filterContext)
      }
      setTasks(result)
      setRefreshKey(k => k + 1)
    } catch (e: any) { setError(e.message || "Failed to load tasks") }
    finally { setLoading(false) }
  }, [filter, filterContext, isTasksPage])

  useEffect(() => { fetchTasks() }, [fetchTasks])
  useEffect(() => {
    const onRefresh = () => { if (isTasksPage) fetchTasks() }
    window.addEventListener("va-tasks-refresh", onRefresh as EventListener)
    return () => window.removeEventListener("va-tasks-refresh", onRefresh as EventListener)
  }, [fetchTasks, isTasksPage])

  // ── ESC clears selection / context menu ─────────────────────────────────────
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSelectedIds(new Set()); setLastSelectedId(null); setCtxMenu(null)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // ── Container width observer ─────────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    setContainerWidth(el.getBoundingClientRect().width)
    const ro = new ResizeObserver(entries => setContainerWidth(entries[0].contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ── Toggle (checkbox) ───────────────────────────────────────────────────────
  async function handleToggle(task: LBSTask) {
    if (toggling.has(task.task_id)) return
    const date = task.due_date || TODAY
    const newStatus = task.status === "done" ? "todo" : "done"
    setToggling(s => new Set(s).add(task.task_id))
    setTasks(prev => prev.map(t => t.task_id === task.task_id ? { ...t, status: newStatus } : t))
    try { await completeLBSTask(task.task_id, date, newStatus as any) }
    catch { setTasks(prev => prev.map(t => t.task_id === task.task_id ? { ...t, status: task.status } : t)) }
    finally { setToggling(s => { const n = new Set(s); n.delete(task.task_id); return n }) }
  }

  // ── Row click (with shift for range) ────────────────────────────────────────
  function handleRowClick(task: LBSTask, e: React.MouseEvent) {
    if (ctxMenu) { setCtxMenu(null); return }
    if (e.shiftKey) {
      e.preventDefault()
      const ids = flatTasks.map(t => t.task_id)
      if (!lastSelectedId) {
        setSelectedIds(new Set([task.task_id]))
      } else {
        const from = ids.indexOf(lastSelectedId)
        const to = ids.indexOf(task.task_id)
        if (from === -1 || to === -1) {
          setSelectedIds(new Set([task.task_id]))
        } else {
          const [lo, hi] = from <= to ? [from, to] : [to, from]
          setSelectedIds(new Set(ids.slice(lo, hi + 1)))
        }
      }
      setLastSelectedId(task.task_id)
    } else if (selectedIds.size > 0) {
      const next = new Set(selectedIds)
      if (next.has(task.task_id)) next.delete(task.task_id)
      else next.add(task.task_id)
      setSelectedIds(next)
      if (next.size === 0) setLastSelectedId(null)
      else setLastSelectedId(task.task_id)
    } else {
      openEdit(task)
    }
  }

  // ── Context menu ─────────────────────────────────────────────────────────────
  function handleContextMenu(task: LBSTask, e: React.MouseEvent) {
    e.preventDefault(); e.stopPropagation()
    setCtxMenu({ x: e.clientX, y: e.clientY, task })
  }

  async function handleCtxStatus(status: string) {
    if (!ctxMenu) return
    const { task } = ctxMenu
    const date = task.due_date || TODAY
    await completeLBSTask(task.task_id, date, status as any).catch(() => { })
    setTasks(prev => prev.map(t => t.task_id === task.task_id ? { ...t, status } : t))
    setCtxMenu(null)
  }

  async function handleCtxDelete() {
    if (!ctxMenu) return
    const { task } = ctxMenu
    await apiFetch(`/api/lbs/tasks/${task.task_id}?force_override=true`, { method: "DELETE" }).catch(() => { })
    setTasks(prev => prev.filter(t => t.task_id !== task.task_id))
    setCtxMenu(null)
    window.dispatchEvent(new Event("va-task-contexts-refresh"))
  }

  async function handleCtxMoveDate(date: string) {
    if (!ctxMenu) return
    await apiFetch(`/api/lbs/tasks/${ctxMenu.task.task_id}?force_override=true`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ due_date: date }),
    }).catch(() => { })
    await fetchTasks()
    setCtxMenu(null)
  }

  // ── Bulk actions ─────────────────────────────────────────────────────────────
  async function handleBulkStatus(status: string) {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map(id => completeLBSTask(id, TODAY, status as any).catch(() => { })))
    setTasks(prev => prev.map(t => selectedIds.has(t.task_id) ? { ...t, status } : t))
    setSelectedIds(new Set()); setLastSelectedId(null)
  }

  async function handleBulkDelete() {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map(id =>
      apiFetch(`/api/lbs/tasks/${id}?force_override=true`, { method: "DELETE" }).catch(() => { })
    ))
    setTasks(prev => prev.filter(t => !selectedIds.has(t.task_id)))
    setSelectedIds(new Set()); setLastSelectedId(null)
    window.dispatchEvent(new Event("va-task-contexts-refresh"))
  }

  function handleTaskDragStart(task: LBSTask, e: React.DragEvent) {
    const payload = {
      task_id: task.task_id,
      task_name: task.task_name,
      context: task.context || "inbox",
    }
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("application/x-visionark-task", JSON.stringify(payload))
    e.dataTransfer.setData("text/plain", task.task_name || task.task_id)
    window.dispatchEvent(new CustomEvent("va-task-drag-active", { detail: { active: true } }))
  }

  function handleTaskDragEnd() {
    window.dispatchEvent(new CustomEvent("va-task-drag-active", { detail: { active: false } }))
  }

  async function handleBulkMoveDate(date: string) {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map(id =>
      apiFetch(`/api/lbs/tasks/${id}?force_override=true`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ due_date: date }),
      }).catch(() => { })
    ))
    await fetchTasks()
    setSelectedIds(new Set()); setLastSelectedId(null)
  }

  // ── Export ───────────────────────────────────────────────────────────────────
  async function openExportSheet() {
    // Pre-fetch all tasks so count is ready
    const all = await listLBSTasks({ active: true }).catch(() => tasks)
    setAllTasksCache(all)
    setExportCount(all.length)
    setExportOpen(true)
  }

  async function doExport(filename: string) {
    const src = allTasksCache.length > 0 ? allTasksCache : tasks
    const headers = ["task_name", "context", "base_load_score", "rule_type", "due_date", "start_time", "end_time", "notes"]
    const rows = src.map(t => [
      `"${(t.task_name || "").replace(/"/g, '""')}"`,
      `"${(t.context || "").replace(/"/g, '""')}"`,
      t.base_load_score, t.rule_type,
      t.due_date ?? "", t.start_time ?? "", t.end_time ?? "",
      `"${(t.notes || "").replace(/"/g, '""')}"`,
    ].join(","))
    const csv = [headers.join(","), ...rows].join("\n")
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = filename.endsWith(".csv") ? filename : filename + ".csv"
    a.click(); URL.revokeObjectURL(url)
  }

  // ── Other ────────────────────────────────────────────────────────────────────
  async function handleAddTask(taskData: LBSTaskCreate) {
    await createLBSTask(taskData)
    setShowAddForm(false)
    await fetchTasks()
    window.dispatchEvent(new Event("va-task-contexts-refresh"))
  }

  function openEdit(task: LBSTask & { due_date?: string | null }) {
    setEditDate(task.due_date ?? targetDate ?? TODAY)
    setEditTaskId(task.task_id)
  }

  function handleRefresh() {
    if (isTasksPage) fetchTasks()
    else setRefreshKey(k => k + 1)
  }

  function jumpToday() {
    setCalendarAnchorDate(TODAY)
  }

  function movePrev() {
    setCalendarAnchorDate(prev => viewMode === "timeline" ? addDays(prev, -7) : addMonths(prev, -1))
  }

  function moveNext() {
    setCalendarAnchorDate(prev => viewMode === "timeline" ? addDays(prev, 7) : addMonths(prev, 1))
  }

  const grouped = groupByContext(tasks)
  const todayDone = tasks.filter(t => t.status === "done").length
  const todayTotal = tasks.length
  const progress = todayTotal > 0 ? (todayDone / todayTotal) * 100 : 0
  const baseTitle = FILTER_LABELS[filter] ?? filter
  const title = isCalendarPage
    ? (filterContext ? `Calendar - ${filterContext}` : "Calendar")
    : (filterContext ? `${baseTitle} - ${filterContext}` : baseTitle)
  const selMode = selectedIds.size > 0

  return (
    <div
      ref={containerRef}
      className={`flex h-full bg-gray-950 text-white ${isWide && !!editTaskId ? "flex-row" : "flex-col"}`}
      onClick={() => ctxMenu && setCtxMenu(null)}
    >
      <div className="flex flex-col flex-1 min-w-0 min-h-0">
        <div className="flex-shrink-0 px-6 pt-6 pb-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              {!isCalendarPage && (
                <>
                  <h1 className="text-lg font-bold text-white">{title}</h1>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
                  </p>
                </>
              )}
              {isCalendarPage && (
                <div className="mt-2 flex items-center gap-2">
                  <button onClick={movePrev} className="px-2 py-1 text-gray-400 hover:text-white transition-all">
                    {"<"}
                  </button>
                  <button
                    onClick={jumpToday}
                    className="px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-gray-400 hover:text-white transition-all"
                  >
                    TODAY
                  </button>
                  <button onClick={moveNext} className="px-2 py-1 text-gray-400 hover:text-white transition-all">
                    {">"}
                  </button>
                  <span className="text-xs font-bold text-gray-300">
                    {viewMode === "timeline" ? weekRangeLabel(calendarAnchorDate) : monthLabel(calendarAnchorDate)}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              {isCalendarPage && (
                <div className="flex items-center gap-0.5 bg-gray-900/80 border border-gray-800 rounded-xl p-1">
                  {([["calendar", <CalendarDays size={14} />], ["timeline", <Calendar size={14} />]] as const).map(([nextMode, icon]) => (
                    <button key={nextMode} onClick={() => setViewMode(nextMode as ViewMode)} title={nextMode}
                      className={`p-1.5 rounded-lg transition-all ${viewMode === nextMode ? "bg-cyan-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"}`}>
                      {icon}
                    </button>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-1">
                {isTasksPage && (
                  <>
                    <button onClick={() => setImportOpen(true)} title="Import CSV"
                      className="p-2 text-gray-500 hover:text-gray-300 rounded-xl hover:bg-gray-800 transition-all"><Upload size={15} /></button>
                    <button onClick={openExportSheet} title="Export CSV"
                      className="p-2 text-gray-500 hover:text-gray-300 rounded-xl hover:bg-gray-800 transition-all"><Download size={15} /></button>
                  </>
                )}
                <button onClick={handleRefresh} title="Refresh"
                  className="p-2 text-gray-500 hover:text-gray-300 rounded-xl hover:bg-gray-800 transition-all">
                  <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
                </button>
              </div>

              {isTasksPage && (
                <button onClick={() => { setViewMode("list"); setShowAddForm(v => !v) }} title="Add task"
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all ${showAddForm && viewMode === "list" ? "bg-gray-800 text-gray-300" : "bg-cyan-600 hover:bg-cyan-500 text-white"
                    }`}>
                  <Plus size={14} />Add
                </button>
              )}
            </div>
          </div>

          {isTasksPage && viewMode === "list" && showStatus && todayTotal > 0 && (
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{filter === "overdue" ? "Completion" : "Today's progress"}</span>
                <span className="text-cyan-400 font-medium">{todayDone}/{todayTotal}</span>
              </div>
              <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </div>

        {isTasksPage && selMode && viewMode === "list" && (
          <BulkActionBar
            count={selectedIds.size}
            onDone={() => handleBulkStatus("done")}
            onTodo={() => handleBulkStatus("todo")}
            onDelete={handleBulkDelete}
            onMoveDate={handleBulkMoveDate}
            onClear={() => { setSelectedIds(new Set()); setLastSelectedId(null) }}
          />
        )}

        {isTasksPage && showAddForm && viewMode === "list" && (
          <div className="flex-shrink-0 pt-4">
            <AddTaskForm onAdd={handleAddTask} onCancel={() => setShowAddForm(false)}
              defaultContext={filterContext} availableProjects={projects} />
          </div>
        )}

        <div className={`flex-1 min-h-0 ${viewMode === "list" ? "overflow-y-auto custom-scrollbar py-3" : "overflow-hidden p-4"}`}>
          {viewMode === "list" ? (
            error ? (
              <div className="mx-4 p-4 bg-red-900/20 border border-red-800/40 rounded-2xl text-sm text-red-400">{error}</div>
            ) : loading && tasks.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-gray-600 text-sm">Loading...</div>
            ) : tasks.length === 0 && !showAddForm ? (
              <div className="flex flex-col items-center justify-center h-40 gap-3">
                <CheckCircle2 size={32} className="text-gray-800" />
                <p className="text-sm text-gray-600">No tasks found</p>
                <button onClick={() => setShowAddForm(true)}
                  className="flex items-center gap-1.5 px-3 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-semibold transition-all">
                  <Plus size={12} />Add Task
                </button>
              </div>
            ) : (
              Array.from(grouped.entries()).map(([ctx, ctxTasks]) => (
                <ContextGroup key={ctx} context={ctx} tasks={ctxTasks} showStatus={showStatus}
                  selectionMode={selMode} selectedIds={selectedIds}
                  onToggle={showStatus ? handleToggle : undefined}
                  onRowClick={handleRowClick}
                  onContextMenu={handleContextMenu}
                  onTaskDragStart={handleTaskDragStart}
                  onTaskDragEnd={handleTaskDragEnd}
                />
              ))
            )
          ) : viewMode === "calendar" ? (
            <CalendarView
              onTaskClick={openEdit}
              refreshKey={refreshKey}
              filterContext={filterContext}
              statusFilter={calendarStatusFilter}
              anchorDate={calendarAnchorDate}
              showNavigation={false}
            />
          ) : (
            <TimelineView
              targetDate={calendarAnchorDate}
              onTaskClick={openEdit}
              refreshKey={refreshKey}
              filterContext={filterContext}
              statusFilter={calendarStatusFilter}
            />
          )}
        </div>

        {isTasksPage && ctxMenu && (
          <ContextMenu
            x={ctxMenu.x} y={ctxMenu.y} task={ctxMenu.task}
            onStatus={handleCtxStatus}
            onEdit={() => { openEdit(ctxMenu.task); setCtxMenu(null) }}
            onDelete={handleCtxDelete}
            onMoveDate={handleCtxMoveDate}
            onClose={() => setCtxMenu(null)}
          />
        )}

        {isTasksPage && exportOpen && (
          <ExportSheet
            taskCount={exportCount}
            onExport={doExport}
            onClose={() => setExportOpen(false)}
          />
        )}

        {isTasksPage && (
          <ImportModal isOpen={importOpen} onClose={() => setImportOpen(false)}
            onImportComplete={() => { setImportOpen(false); fetchTasks() }} existingProjects={projects} />
        )}
      </div>

      {/* ── Task edit panel ──────────────────────────────────────────────────── */}
      <TaskEditPanel taskId={editTaskId} targetDate={editDate}
        onClose={() => setEditTaskId(null)} onSaved={handleRefresh} availableProjects={projects}
        mode={isWide ? "inline" : "overlay"} />
    </div>
  )
}
