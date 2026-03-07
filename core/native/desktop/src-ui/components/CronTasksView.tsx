import React, { useState, useEffect, useMemo } from "react"
import {
    AlarmClock,
    CalendarClock,
    CircleHelp,
    Trash2,
    Edit2,
    RefreshCw,
    CheckCircle2,
    Clock,
    AlertCircle,
    Activity,
    Box,
    Plus,
    X,
} from "lucide-react"
import { apiFetch, listProjects, listSessions, Project } from "../lib/api"

interface ScheduledTask {
    id: string
    project_id: string | null
    project_name: string | null
    task_type: string
    payload: any
    scheduled_at: string
    recurring_rule: string | null
    status: string
    last_run_at: string | null
    created_at: string
}

interface SessionMinimal {
    id: string
    title: string | null
    is_default: boolean
    last_message_at: string | null
}

type TabType = "upcoming" | "history"
type RecurrenceMode = "once" | "hourly" | "daily" | "weekly" | "custom"

const RECURRENCE_OPTIONS: Array<{ value: RecurrenceMode; label: string; rule: string | null }> = [
    { value: "once", label: "One-time", rule: null },
    { value: "hourly", label: "Hourly", rule: "@hourly" },
    { value: "daily", label: "Daily", rule: "@daily" },
    { value: "weekly", label: "Weekly", rule: "@weekly" },
    { value: "custom", label: "Custom", rule: null },
]

function parseRecurrence(rule: string | null | undefined): { mode: RecurrenceMode; custom: string } {
    const value = (rule || "").trim()
    if (!value) return { mode: "once", custom: "" }
    const matched = RECURRENCE_OPTIONS.find((option) => option.rule === value)
    if (matched) return { mode: matched.value, custom: "" }
    return { mode: "custom", custom: value }
}

function resolveRecurrence(mode: RecurrenceMode, custom: string): string | null {
    const matched = RECURRENCE_OPTIONS.find((option) => option.value === mode)
    if (!matched) return null
    if (matched.rule !== null) return matched.rule
    return custom.trim() || null
}

function getTimezoneOptions(): string[] {
    try {
        if (typeof Intl.supportedValuesOf === "function") {
            return Intl.supportedValuesOf("timeZone")
        }
    } catch {
        // no-op
    }
    return ["UTC"]
}

function formatInTimezone(date: Date, timezone: string): { year: number; month: number; day: number; hour: number; minute: number } {
    const formatter = new Intl.DateTimeFormat("en-US", {
        timeZone: timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    })
    const parts = formatter.formatToParts(date)
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? "0")
    return {
        year: get("year"),
        month: get("month"),
        day: get("day"),
        hour: get("hour"),
        minute: get("minute"),
    }
}

function zonedDateTimeLocalToUtcIso(localDateTime: string, timezone: string): string {
    const m = localDateTime.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/)
    if (!m) return new Date(localDateTime).toISOString()

    const year = Number(m[1])
    const month = Number(m[2])
    const day = Number(m[3])
    const hour = Number(m[4])
    const minute = Number(m[5])

    let guess = Date.UTC(year, month - 1, day, hour, minute)
    const target = Date.UTC(year, month - 1, day, hour, minute)

    for (let i = 0; i < 5; i++) {
        const parts = formatInTimezone(new Date(guess), timezone)
        const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute)
        const diff = target - asUtc
        if (diff === 0) break
        guess += diff
    }

    return new Date(guess).toISOString()
}

function utcIsoToZonedLocalInput(utcIso: string, timezone: string): string {
    const parts = formatInTimezone(new Date(utcIso), timezone)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`
}

function formatStoredLocalDateTime(localDateTime: string): string | null {
    const m = localDateTime.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/)
    if (!m) return null
    return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`
}

function createInitialForm(projectId: string) {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
    return {
        project_id: projectId,
        session_id: "",
        message: "",
        scheduled_at: "",
        recurrence_mode: "once" as RecurrenceMode,
        recurrence_custom: "",
        recurrence_timezone: timezone,
    }
}

export default function CronTasksView() {
    const [tasks, setTasks] = useState<ScheduledTask[]>([])
    const [loading, setLoading] = useState(true)
    const [projects, setProjects] = useState<Project[]>([])
    const [sessions, setSessions] = useState<SessionMinimal[]>([])
    const [sessionsLoading, setSessionsLoading] = useState(false)
    const [activeTab, setActiveTab] = useState<TabType>("upcoming")
    const [showRecurrenceHelp, setShowRecurrenceHelp] = useState(false)
    const timezoneOptions = useMemo(() => getTimezoneOptions(), [])

    // Modal State
    const [isModalOpen, setIsModalOpen] = useState(false)
    const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null)
    const [formData, setFormData] = useState(createInitialForm(""))

    const loadTasks = async () => {
        setLoading(true)
        try {
            const response = await apiFetch("/api/automation/tasks?exclude_system=true")
            if (!response.ok) throw new Error("Failed to fetch tasks")
            const data = await response.json()
            setTasks(data)
        } catch (error) {
            console.error("Error loading tasks:", error)
            alert("Failed to load scheduled tasks.")
        } finally {
            setLoading(false)
        }
    }

    const loadProjectsList = async () => {
        try {
            const ps = await listProjects()
            setProjects(ps)
        } catch (e) {
            console.error("Failed to load projects", e)
        }
    }

    const loadSessions = async (projectId: string) => {
        if (!projectId) {
            setSessions([])
            return
        }
        setSessionsLoading(true)
        try {
            const items = await listSessions(projectId)
            setSessions(items)
            setFormData((prev) => {
                if (prev.project_id !== projectId) return prev
                if (prev.session_id && items.some((s) => s.id === prev.session_id)) return prev

                const lastSessionId = localStorage.getItem(`va_last_session_${projectId}`)
                const nextSession =
                    (lastSessionId && items.find((s) => s.id === lastSessionId)?.id) || ""
                return { ...prev, session_id: nextSession }
            })
        } catch (e) {
            console.error("Failed to load sessions", e)
            setSessions([])
        } finally {
            setSessionsLoading(false)
        }
    }

    useEffect(() => {
        loadTasks()
        loadProjectsList()
    }, [])

    useEffect(() => {
        const onRealtime = () => {
            loadTasks()
        }
        window.addEventListener("va-realtime-job", onRealtime)
        return () => window.removeEventListener("va-realtime-job", onRealtime)
    }, [])

    useEffect(() => {
        if (isModalOpen && formData.project_id) {
            loadSessions(formData.project_id)
        } else {
            setSessions([])
        }
    }, [formData.project_id, isModalOpen])

    const filteredTasks = useMemo(() => {
        if (activeTab === "upcoming") {
            return tasks.filter((t) => ["pending", "processing"].includes(t.status.toLowerCase()))
        } else {
            return tasks.filter((t) => ["completed", "failed", "cancelled"].includes(t.status.toLowerCase()))
        }
    }, [tasks, activeTab])

    const handleDelete = async (taskId: string) => {
        if (!confirm("Are you sure you want to cancel this scheduled task?")) return

        try {
            const response = await apiFetch(`/api/automation/tasks/${taskId}`, {
                method: "DELETE",
            })
            if (!response.ok) throw new Error("Failed to delete task")

            setTasks((prev) => prev.filter((t) => t.id !== taskId))
        } catch (error) {
            console.error("Error deleting task:", error)
            alert("Failed to cancel task.")
        }
    }

    const handleEdit = (task: ScheduledTask) => {
        if (task.task_type !== "POST_MESSAGE") {
            alert("Only Message Posting tasks are editable via UI.")
            return
        }

        setEditingTask(task)
        const timezone = task.payload?.recurrence_timezone || "UTC"
        const dateStr = task.payload?.scheduled_local_time || utcIsoToZonedLocalInput(task.scheduled_at, timezone)
        const recurrence = parseRecurrence(task.recurring_rule)

        setFormData({
            project_id: task.project_id || "",
            session_id: task.payload?.session_id || "",
            message: task.payload?.message || "",
            scheduled_at: dateStr,
            recurrence_mode: recurrence.mode,
            recurrence_custom: recurrence.custom,
            recurrence_timezone: timezone,
        })
        setIsModalOpen(true)
    }

    const handleCreate = () => {
        setEditingTask(null)
        const now = new Date()
        now.setHours(now.getHours() + 1)

        // Default to one hour later in the selected timezone's wall-clock.
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
        const dateStr = utcIsoToZonedLocalInput(now.toISOString(), timezone)

        setFormData({
            ...createInitialForm(projects[0]?.id || ""),
            scheduled_at: dateStr,
            recurrence_timezone: timezone,
        })
        setIsModalOpen(true)
    }

    const handleSave = async () => {
        if (!formData.project_id || !formData.message || !formData.scheduled_at) {
            alert("Please fill in all required fields.")
            return
        }
        if (formData.recurrence_mode === "custom" && !formData.recurrence_custom.trim()) {
            alert("Custom recurrence is empty.")
            return
        }

        const recurringRule = resolveRecurrence(formData.recurrence_mode, formData.recurrence_custom)

        const taskPayload: Record<string, string> = {
            message: formData.message,
            recurrence_timezone: formData.recurrence_timezone,
            scheduled_local_time: formData.scheduled_at,
        }
        if (formData.session_id) {
            taskPayload.session_id = formData.session_id
        }

        const payload = {
            project_id: formData.project_id,
            task_type: "POST_MESSAGE",
            scheduled_at: zonedDateTimeLocalToUtcIso(formData.scheduled_at, formData.recurrence_timezone),
            recurring_rule: recurringRule,
            recurrence_timezone: formData.recurrence_timezone,
            payload: taskPayload,
        }

        try {
            let response
            if (editingTask) {
                response = await apiFetch(`/api/automation/tasks/${editingTask.id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                })
            } else {
                response = await apiFetch("/api/automation/schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                })
            }

            if (!response.ok) throw new Error("Failed to save task")

            setIsModalOpen(false)
            loadTasks()
        } catch (error) {
            console.error("Save error:", error)
            alert("Failed to save task.")
        }
    }

    const getStatusIcon = (status: string) => {
        switch (status.toLowerCase()) {
            case "completed":
                return <CheckCircle2 size={14} className="text-green-500" />
            case "pending":
                return <Clock size={14} className="text-yellow-500" />
            case "failed":
                return <AlertCircle size={14} className="text-red-500" />
            case "processing":
                return <Activity size={14} className="text-cyan-500 animate-pulse" />
            default:
                return <Box size={14} className="text-gray-500" />
        }
    }

    const getTaskTypeLabel = (type: string) => {
        switch (type) {
            case "POST_MESSAGE":
                return "Auto Message"
            default:
                return type
        }
    }

    const formatDate = (dateStr: string, timezone: string) => {
        return new Date(dateStr).toLocaleString(undefined, {
            timeZone: timezone,
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        })
    }

    return (
        <div className="flex-1 overflow-y-auto px-12 py-10 bg-[#030712] custom-scrollbar">
            <div className="max-w-7xl mx-auto">
                <header className="mb-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-3xl font-black text-white tracking-tight flex items-center gap-3">
                            <AlarmClock className="text-cyan-500" size={32} />
                            Cron Tasks
                        </h1>
                        <p className="text-gray-500 text-sm mt-1 uppercase tracking-widest font-bold">
                            Automated Systems & Schedules
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={handleCreate}
                            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 text-white rounded-xl font-bold text-sm hover:from-cyan-500 hover:to-blue-500 transition-all shadow-lg shadow-cyan-900/20 active:scale-95"
                        >
                            <Plus size={18} />
                            Create Schedule
                        </button>
                        <button
                            onClick={loadTasks}
                            className="p-2.5 bg-gray-900 border border-gray-800 rounded-xl text-gray-400 hover:text-white transition-all hover:bg-gray-800 active:scale-95"
                            title="Refresh List"
                        >
                            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
                        </button>
                    </div>
                </header>

                {/* Tabs */}
                <div className="flex gap-1 mb-6 p-1 bg-gray-900/50 rounded-2xl w-fit border border-gray-800/50">
                    <button
                        onClick={() => setActiveTab("upcoming")}
                        className={`px-6 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "upcoming"
                                ? "bg-gray-800 text-cyan-400 shadow-sm"
                                : "text-gray-500 hover:text-gray-300"
                            }`}
                    >
                        UPCOMING
                    </button>
                    <button
                        onClick={() => setActiveTab("history")}
                        className={`px-6 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "history"
                                ? "bg-gray-800 text-cyan-400 shadow-sm"
                                : "text-gray-500 hover:text-gray-300"
                            }`}
                    >
                        HISTORY
                    </button>
                </div>

                <div className="grid grid-cols-1 gap-6">
                    {loading && tasks.length === 0 ? (
                        <div className="py-20 flex flex-col items-center justify-center text-gray-600 bg-gray-900/20 rounded-3xl border border-dashed border-gray-800">
                            <RefreshCw size={40} className="animate-spin mb-4 opacity-50" />
                            <p className="font-bold uppercase tracking-widest text-xs">
                                Loading schedules...
                            </p>
                        </div>
                    ) : filteredTasks.length === 0 ? (
                        <div className="py-20 flex flex-col items-center justify-center text-gray-600 bg-gray-900/20 rounded-3xl border border-dashed border-gray-800">
                            <CalendarClock size={40} className="mb-4 opacity-20" />
                            <p className="font-bold uppercase tracking-widest text-xs">
                                {activeTab === "upcoming" ? "No upcoming tasks found" : "No history found"}
                            </p>
                        </div>
                    ) : (
                        <div className="bg-gray-900/40 border border-gray-800 rounded-3xl overflow-hidden backdrop-blur-md">
                            <table className="w-full text-left">
                                <thead className="bg-gray-800/50">
                                    <tr>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                            Task Type
                                        </th>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                            Target Project
                                        </th>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                            Details
                                        </th>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                            Schedule / Recurring
                                        </th>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                                            Status
                                        </th>
                                        <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800/50">
                                    {filteredTasks.map((task) => (
                                        <tr key={task.id} className="hover:bg-gray-800/20 transition-colors">
                                            <td className="px-6 py-4">
                                                <div className="flex flex-col">
                                                    <span className="text-sm font-bold text-cyan-400">
                                                        {getTaskTypeLabel(task.task_type)}
                                                    </span>
                                                    <span className="text-[10px] text-gray-600 font-mono" title={task.id}>
                                                        ID: ...{task.id.slice(-8)}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex flex-col">
                                                    <span className="text-sm font-medium text-gray-300">
                                                        {task.project_name || "No Project"}
                                                    </span>
                                                    <span className="text-[10px] text-gray-600 font-mono">
                                                        ID: {task.project_id ? `...${task.project_id.slice(-8)}` : "-"}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 max-w-[200px]">
                                                {task.task_type === "POST_MESSAGE" ? (
                                                    <div className="flex flex-col gap-0.5">
                                                        {task.payload?.message && (
                                                            <div className="truncate text-xs text-gray-300 italic">
                                                                "{task.payload.message}"
                                                            </div>
                                                        )}
                                                        {task.payload?.session_id ? (
                                                            <span className="text-[10px] text-cyan-700 font-mono">
                                                                Session: ...{task.payload.session_id.slice(-8)}
                                                            </span>
                                                        ) : (
                                                            <span className="text-[10px] text-yellow-700">Auto session</span>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span className="text-xs text-gray-500">-</span>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex flex-col">
                                                    <span className="text-xs text-gray-300">
                                                        {formatStoredLocalDateTime(task.payload?.scheduled_local_time || "")
                                                            || formatDate(task.scheduled_at, task.payload?.recurrence_timezone || "UTC")}
                                                    </span>
                                                    <span className="text-[10px] text-gray-600">
                                                        ({task.payload?.recurrence_timezone || "UTC"})
                                                    </span>
                                                    {task.recurring_rule && (
                                                        <span className="text-[10px] text-purple-400 font-bold uppercase tracking-tighter mt-0.5">
                                                            {task.recurring_rule}
                                                        </span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-2">
                                                    {getStatusIcon(task.status)}
                                                    <span
                                                        className={`text-[10px] font-black uppercase tracking-widest ${task.status === "pending"
                                                                ? "text-yellow-500"
                                                                : task.status === "completed"
                                                                    ? "text-green-500"
                                                                    : task.status === "failed"
                                                                        ? "text-red-500"
                                                                        : "text-cyan-500"
                                                            }`}
                                                    >
                                                        {task.status}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    {task.task_type === "POST_MESSAGE" &&
                                                        ["pending", "processing"].includes(task.status.toLowerCase()) && (
                                                            <button
                                                                onClick={() => handleEdit(task)}
                                                                className="p-2 text-gray-500 hover:text-cyan-400 hover:bg-cyan-500/10 rounded-xl transition-all"
                                                                title="Edit Task"
                                                            >
                                                                <Edit2 size={16} />
                                                            </button>
                                                        )}
                                                    <button
                                                        onClick={() => handleDelete(task.id)}
                                                        className="p-2 text-gray-500 hover:text-red-500 hover:bg-red-500/10 rounded-xl transition-all"
                                                        title="Cancel Task"
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {/* Create/Edit Modal */}
                {isModalOpen && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
                        <div className="bg-[#0A0A0A] border border-gray-800 rounded-3xl w-full max-w-lg p-6 shadow-2xl relative animate-in fade-in zoom-in duration-200">
                            <button
                                onClick={() => setIsModalOpen(false)}
                                className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
                            >
                                <X size={20} />
                            </button>

                            <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                                {editingTask ? (
                                    <Edit2 size={20} className="text-cyan-500" />
                                ) : (
                                    <Plus size={20} className="text-cyan-500" />
                                )}
                                {editingTask ? "Edit Scheduled Message" : "Schedule New Message"}
                            </h2>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                                        Target Project
                                    </label>
                                    <select
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                        value={formData.project_id}
                                        onChange={(e) =>
                                            setFormData({ ...formData, project_id: e.target.value, session_id: "" })
                                        }
                                    >
                                        <option value="" disabled>
                                            Select a project
                                        </option>
                                        {projects.map((p) => (
                                            <option key={p.id} value={p.id}>
                                                {p.display_name || p.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>


                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                                        Target Session
                                        <span className="ml-1 text-gray-600 normal-case font-normal">(Optional)</span>
                                    </label>
                                    <select
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500 disabled:opacity-40"
                                        value={formData.session_id}
                                        onChange={(e) => setFormData({ ...formData, session_id: e.target.value })}
                                        disabled={!formData.project_id || sessionsLoading}
                                    >
                                        <option value="">No session (auto route)</option>
                                        {sessions.map((s) => (
                                            <option key={s.id} value={s.id}>
                                                {s.title || "Untitled"}
                                            </option>
                                        ))}
                                    </select>
                                    {sessionsLoading && (
                                        <p className="text-[10px] text-gray-500 mt-1">Loading sessions...</p>
                                    )}
                                </div>

                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                                        Message
                                    </label>
                                    <textarea
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500 min-h-[100px] resize-none"
                                        placeholder="What should the agent process?"
                                        value={formData.message}
                                        onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                                            Scheduled Time
                                        </label>
                                        <input
                                            type="datetime-local"
                                            className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                            value={formData.scheduled_at}
                                            onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
                                        />
                                    </div>

                                    <div>
                                        <div className="flex items-center gap-1 mb-2">
                                            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider">
                                                Recurrence (Optional)
                                            </label>
                                            <button
                                                type="button"
                                                onClick={() => setShowRecurrenceHelp((prev) => !prev)}
                                                className="text-gray-500 hover:text-cyan-300"
                                                title="Recurrence help"
                                            >
                                                <CircleHelp size={13} />
                                            </button>
                                        </div>
                                        <select
                                            className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                            value={formData.recurrence_mode}
                                            onChange={(e) =>
                                                setFormData({
                                                    ...formData,
                                                    recurrence_mode: e.target.value as RecurrenceMode,
                                                })
                                            }
                                        >
                                            {RECURRENCE_OPTIONS.map((option) => (
                                                <option key={option.value} value={option.value}>
                                                    {option.label}
                                                </option>
                                            ))}
                                        </select>
                                        {formData.recurrence_mode === "custom" && (
                                            <input
                                                type="text"
                                                className="mt-2 w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500 font-mono"
                                                placeholder="*/15 * * * *"
                                                value={formData.recurrence_custom}
                                                onChange={(e) =>
                                                    setFormData({
                                                        ...formData,
                                                        recurrence_custom: e.target.value,
                                                    })
                                                }
                                            />
                                        )}
                                        {showRecurrenceHelp && (
                                            <div className="mt-2 rounded-lg border border-cyan-900/50 bg-cyan-950/20 px-2.5 py-2 text-[11px] text-cyan-100">
                                                Presets set common schedules. Custom accepts @hourly/@daily or 5-field
                                                cron like <span className="font-mono">0 9 * * 1-5</span>.
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                                        Timezone
                                    </label>
                                    <select
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                        value={formData.recurrence_timezone}
                                        onChange={(e) => setFormData({ ...formData, recurrence_timezone: e.target.value })}
                                    >
                                        {timezoneOptions.map((tz) => (
                                            <option key={tz} value={tz}>
                                                {tz}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 mt-8">
                                <button
                                    onClick={() => setIsModalOpen(false)}
                                    className="px-5 py-2.5 rounded-xl border border-gray-800 text-gray-400 hover:text-white hover:bg-gray-800 text-sm font-medium transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    className="px-5 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-bold shadow-lg shadow-cyan-900/20 transition-all active:scale-95"
                                >
                                    {editingTask ? "Save Changes" : "Schedule Task"}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}


