import React, { useCallback, useEffect, useRef, useState } from "react"
import {
  CheckCircle2, Circle, Clock, Plus, RefreshCw, Tag, Zap,
} from "lucide-react"
import {
  listLBSTasks, completeLBSTask, createLBSTask, getOverdueTasks,
  type LBSTask, type LBSTaskCreate,
} from "../lib/api"
import type { TaskFilter } from "./NavSidebar"

const TODAY = new Date().toISOString().slice(0, 10)

interface Props {
  filter?: TaskFilter
  filterContext?: string
}

function toDisplayDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString("ja-JP", { month: "short", day: "numeric" })
}

const LOAD_COLORS = { low: "text-emerald-400", medium: "text-yellow-400", high: "text-orange-400", critical: "text-red-400" }

function loadLabel(score: number): { color: string; label: string } {
  if (score <= 1) return { color: LOAD_COLORS.low, label: "L" }
  if (score <= 2) return { color: LOAD_COLORS.medium, label: "M" }
  if (score <= 3) return { color: LOAD_COLORS.high, label: "H" }
  return { color: LOAD_COLORS.critical, label: "!!" }
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

// ── TaskRow ──────────────────────────────────────────────────────────────────

interface TaskRowProps {
  task: LBSTask
  showStatus: boolean
  onToggle?: (task: LBSTask) => void
}

function TaskRow({ task, showStatus, onToggle }: TaskRowProps) {
  const isDone = task.status === "done"
  const isSkipped = task.status === "skipped"
  const load = loadLabel(task.base_load_score)

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-xl transition-colors group ${
        isDone ? "opacity-50" : "hover:bg-gray-800/50"
      }`}
    >
      {showStatus && onToggle ? (
        <button
          onClick={() => onToggle(task)}
          className="flex-shrink-0 mt-0.5 text-gray-500 hover:text-cyan-400 transition-colors"
          title={isDone ? "Mark as todo" : "Mark as done"}
        >
          {isDone ? (
            <CheckCircle2 size={18} className="text-cyan-500" />
          ) : isSkipped ? (
            <Circle size={18} className="text-gray-600" />
          ) : (
            <Circle size={18} />
          )}
        </button>
      ) : (
        <span className="flex-shrink-0 mt-1">
          <Circle size={14} className="text-gray-700" />
        </span>
      )}

      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-medium leading-snug ${
            isDone ? "line-through text-gray-500" : "text-gray-200"
          }`}
        >
          {task.task_name}
        </p>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className={`text-[10px] font-bold ${load.color}`}>
            <Zap size={9} className="inline mr-0.5" />
            {load.label} {task.base_load_score.toFixed(1)}
          </span>
          <span className="flex items-center gap-1 text-[10px] text-gray-500">
            <Tag size={9} />
            {task.context}
          </span>
          <span className="text-[10px] text-gray-600 capitalize">
            {task.rule_type?.replace(/_/g, " ")}
          </span>
          {(task.start_time || task.end_time) && (
            <span className="flex items-center gap-1 text-[10px] text-gray-500">
              <Clock size={9} />
              {task.start_time}{task.end_time ? ` – ${task.end_time}` : ""}
            </span>
          )}
          {!showStatus && task.due_date && (
            <span className="text-[10px] text-gray-600">due {toDisplayDate(task.due_date)}</span>
          )}
          {task.notes && (
            <span className="text-[10px] text-gray-600 italic truncate max-w-[140px]">
              {task.notes}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── ContextGroup ──────────────────────────────────────────────────────────────

interface ContextGroupProps {
  context: string
  tasks: LBSTask[]
  showStatus: boolean
  onToggle?: (task: LBSTask) => void
}

function ContextGroup({ context, tasks, showStatus, onToggle }: ContextGroupProps) {
  const [expanded, setExpanded] = useState(true)
  const doneCount = tasks.filter((t) => t.status === "done").length

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
      {expanded && (
        <div>
          {tasks.map((t) => (
            <TaskRow
              key={`${t.task_id}-${t.due_date ?? "all"}`}
              task={t}
              showStatus={showStatus}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── AddTaskForm ───────────────────────────────────────────────────────────────

const RULE_TYPES = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "one_time", label: "One-time" },
  { value: "monthly", label: "Monthly" },
]

interface AddTaskFormProps {
  onAdd: (task: LBSTaskCreate) => Promise<void>
  onCancel: () => void
  defaultContext?: string
}

function AddTaskForm({ onAdd, onCancel, defaultContext }: AddTaskFormProps) {
  const [name, setName] = useState("")
  const [context, setContext] = useState(defaultContext || "inbox")
  const [load, setLoad] = useState("1")
  const [ruleType, setRuleType] = useState("daily")
  const [dueDate, setDueDate] = useState("")
  const [notes, setNotes] = useState("")
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => { nameRef.current?.focus() }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      await onAdd({
        task_name: name.trim(),
        context: context.trim() || "inbox",
        base_load_score: parseFloat(load) || 1,
        rule_type: ruleType,
        due_date: dueDate || null,
        notes: notes.trim() || null,
        timezone,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-4 mb-4 bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-3"
    >
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">New Task</p>
      <input
        ref={nameRef}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Task name…"
        className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 border border-gray-700 focus:outline-none focus:border-cyan-500"
      />
      <div className="flex gap-2">
        <input
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Context (inbox)"
          className="flex-1 bg-gray-800 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 border border-gray-700 focus:outline-none focus:border-cyan-500"
        />
        <input
          type="number" min="0.1" max="5" step="0.1"
          value={load}
          onChange={(e) => setLoad(e.target.value)}
          title="Base load score (0.1–5)"
          className="w-20 bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
        />
      </div>
      <div className="flex gap-2">
        <select
          value={ruleType}
          onChange={(e) => setRuleType(e.target.value)}
          className="flex-1 bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
        >
          {RULE_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <input
          type="date" value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          className="flex-1 bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
        />
      </div>
      <select
        value={timezone}
        onChange={(e) => setTimezone(e.target.value)}
        className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white border border-gray-700 focus:outline-none focus:border-cyan-500"
        title="Timezone"
      >
        <option value="UTC">UTC</option>
        {Intl.supportedValuesOf('timeZone').map((tz) => (
          <option key={tz} value={tz}>{tz}</option>
        ))}
      </select>
      <input
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        className="w-full bg-gray-800 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-600 border border-gray-700 focus:outline-none focus:border-cyan-500"
      />
      <div className="flex gap-2 justify-end">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 text-xs text-gray-500 hover:text-gray-300 transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={!name.trim() || saving}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-xs font-semibold rounded-xl transition-colors">
          {saving ? "Adding…" : "Add Task"}
        </button>
      </div>
    </form>
  )
}

// ── FilterLabel ───────────────────────────────────────────────────────────────

const FILTER_LABELS: Record<string, string> = {
  today: "Today",
  "my-day": "My Day",
  planned: "Planned",
  overdue: "Overdue",
  inbox: "All Tasks",
  project: "Project",
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function TasksView({ filter = "today", filterContext }: Props) {
  const [tasks, setTasks] = useState<LBSTask[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [toggling, setToggling] = useState<Set<string>>(new Set())

  const showStatus = filter === "today" || filter === "overdue"

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let result: LBSTask[] = []

      if (filter === "today") {
        result = await listLBSTasks({ targetDate: TODAY })
      } else if (filter === "overdue") {
        result = await getOverdueTasks()
      } else if (filter === "my-day") {
        const all = await listLBSTasks({ active: true })
        result = all.filter((t) => t.meta_payload?.is_my_day)
      } else if (filter === "planned") {
        const all = await listLBSTasks({ active: true })
        result = all.filter((t) => t.due_date && t.due_date > TODAY)
      } else if (filter === "project" && filterContext) {
        result = await listLBSTasks({ active: true, context: filterContext })
      } else {
        // inbox / all
        result = await listLBSTasks({ active: true })
      }

      setTasks(result)
    } catch (e: any) {
      setError(e.message || "Failed to load tasks")
    } finally {
      setLoading(false)
    }
  }, [filter, filterContext])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  async function handleToggle(task: LBSTask) {
    if (toggling.has(task.task_id)) return
    const targetDate = task.due_date || TODAY
    const newStatus = task.status === "done" ? "todo" : "done"

    setToggling((s) => new Set(s).add(task.task_id))
    setTasks((prev) =>
      prev.map((t) => t.task_id === task.task_id ? { ...t, status: newStatus } : t)
    )
    try {
      await completeLBSTask(task.task_id, targetDate, newStatus as any)
    } catch {
      setTasks((prev) =>
        prev.map((t) => t.task_id === task.task_id ? { ...t, status: task.status } : t)
      )
    } finally {
      setToggling((s) => {
        const next = new Set(s)
        next.delete(task.task_id)
        return next
      })
    }
  }

  async function handleAddTask(taskData: LBSTaskCreate) {
    await createLBSTask(taskData)
    setShowAddForm(false)
    await fetchTasks()
  }

  const grouped = groupByContext(tasks)

  const todayDone = tasks.filter((t) => t.status === "done").length
  const todayTotal = tasks.length
  const progress = todayTotal > 0 ? (todayDone / todayTotal) * 100 : 0

  const title = filter === "project" && filterContext
    ? filterContext
    : FILTER_LABELS[filter] ?? filter

  return (
    <div className="flex flex-col h-full bg-gray-950 text-white">
      {/* Header */}
      <div className="flex-shrink-0 px-6 pt-6 pb-4 border-b border-gray-800/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-lg font-bold text-white">{title}</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              {new Date().toLocaleDateString("en-US", {
                weekday: "long", month: "long", day: "numeric",
              })}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchTasks}
              className="p-2 text-gray-500 hover:text-gray-300 rounded-xl hover:bg-gray-800 transition-all"
              title="Refresh"
            >
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all ${
                showAddForm
                  ? "bg-gray-800 text-gray-300"
                  : "bg-cyan-600 hover:bg-cyan-500 text-white"
              }`}
            >
              <Plus size={14} />
              Add Task
            </button>
          </div>
        </div>

        {/* Progress bar for today / overdue */}
        {showStatus && todayTotal > 0 && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>{filter === "overdue" ? "Completion" : "Today's progress"}</span>
              <span className="text-cyan-400 font-medium">{todayDone}/{todayTotal}</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Add task form */}
      {showAddForm && (
        <div className="flex-shrink-0 pt-4">
          <AddTaskForm
            onAdd={handleAddTask}
            onCancel={() => setShowAddForm(false)}
            defaultContext={filter === "project" ? filterContext : undefined}
          />
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar py-3">
        {error ? (
          <div className="mx-4 p-4 bg-red-900/20 border border-red-800/40 rounded-2xl text-sm text-red-400">
            {error}
          </div>
        ) : loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-gray-600 text-sm">
            Loading…
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            <CheckCircle2 size={32} className="text-gray-800" />
            <p className="text-sm text-gray-600">No tasks found</p>
          </div>
        ) : (
          Array.from(grouped.entries()).map(([ctx, ctxTasks]) => (
            <ContextGroup
              key={ctx}
              context={ctx}
              tasks={ctxTasks}
              showStatus={showStatus}
              onToggle={showStatus ? handleToggle : undefined}
            />
          ))
        )}
      </div>
    </div>
  )
}
