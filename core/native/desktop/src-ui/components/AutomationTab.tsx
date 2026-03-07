import { useState, useEffect, useCallback, useMemo } from "react";
import { apiFetch } from "../lib/api";
import { Loader2, Calendar, Clock, Trash2, Plus, AlarmClock, RefreshCw, X, CircleHelp, Edit2 } from "lucide-react";

const useNotification = () => ({
    showConfirm: async (msg: string) => window.confirm(msg),
    showToast: (msg: string, type: string) => console.log(type, msg),
});

interface ScheduledTask {
    id: string;
    project_id?: string;
    task_type: string;
    payload: any;
    scheduled_at: string;
    recurring_rule?: string | null;
    status: string;
}

type RecurrenceMode = "once" | "hourly" | "daily" | "weekly" | "custom";

const RECURRENCE_OPTIONS: Array<{ value: RecurrenceMode; label: string; rule: string | null }> = [
    { value: "once", label: "One-time", rule: null },
    { value: "hourly", label: "Hourly", rule: "@hourly" },
    { value: "daily", label: "Daily", rule: "@daily" },
    { value: "weekly", label: "Weekly", rule: "@weekly" },
    { value: "custom", label: "Custom", rule: null },
];

interface AutomationTabProps {
    projectId: string;
    onScheduleClick?: () => void;
}

function resolveRecurrence(mode: RecurrenceMode, custom: string): string | null {
    const matched = RECURRENCE_OPTIONS.find((option) => option.value === mode);
    if (!matched) return null;
    if (matched.rule !== null) return matched.rule;
    return custom.trim() || null;
}

function parseRecurrence(rule: string | null | undefined): { mode: RecurrenceMode; custom: string } {
    const value = (rule || "").trim();
    if (!value) return { mode: "once", custom: "" };
    const matched = RECURRENCE_OPTIONS.find((option) => option.rule === value);
    if (matched) return { mode: matched.value, custom: "" };
    return { mode: "custom", custom: value };
}

function getTimezoneOptions(): string[] {
    try {
        if (typeof Intl.supportedValuesOf === "function") {
            return Intl.supportedValuesOf("timeZone");
        }
    } catch {
        // no-op
    }
    return ["UTC"];
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
    });
    const parts = formatter.formatToParts(date);
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? "0");
    return {
        year: get("year"),
        month: get("month"),
        day: get("day"),
        hour: get("hour"),
        minute: get("minute"),
    };
}

function zonedDateTimeLocalToUtcIso(localDateTime: string, timezone: string): string {
    const m = localDateTime.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
    if (!m) return new Date(localDateTime).toISOString();

    const year = Number(m[1]);
    const month = Number(m[2]);
    const day = Number(m[3]);
    const hour = Number(m[4]);
    const minute = Number(m[5]);

    let guess = Date.UTC(year, month - 1, day, hour, minute);
    const target = Date.UTC(year, month - 1, day, hour, minute);

    for (let i = 0; i < 5; i++) {
        const parts = formatInTimezone(new Date(guess), timezone);
        const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
        const diff = target - asUtc;
        if (diff === 0) break;
        guess += diff;
    }

    return new Date(guess).toISOString();
}

function utcIsoToZonedLocalInput(utcIso: string, timezone: string): string {
    const parts = formatInTimezone(new Date(utcIso), timezone);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`;
}

function formatScheduledAt(utcIso: string, timezone: string): string {
    return new Date(utcIso).toLocaleString(undefined, {
        timeZone: timezone,
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function formatStoredLocalDateTime(localDateTime: string): string | null {
    const m = localDateTime.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/)
    if (!m) return null
    return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`
}

function initialScheduleLocalTime(timezone: string): string {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    return utcIsoToZonedLocalInput(now.toISOString(), timezone);
}

export default function AutomationTab({ projectId, onScheduleClick }: AutomationTabProps) {
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    const timezoneOptions = useMemo(() => getTimezoneOptions(), []);

    const [tasks, setTasks] = useState<ScheduledTask[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isScheduling, setIsScheduling] = useState(false);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [showRecurrenceHelp, setShowRecurrenceHelp] = useState(false);
    const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
    const [formData, setFormData] = useState({
        message: "",
        scheduled_at: initialScheduleLocalTime(browserTimezone),
        recurrence_mode: "once" as RecurrenceMode,
        recurrence_custom: "",
        recurrence_timezone: browserTimezone,
    });

    const { showToast, showConfirm } = useNotification();

    const fetchTasks = useCallback(async () => {
        setIsLoading(true);
        try {
            const response = await apiFetch(`/api/automation/tasks?project_id=${projectId}`);
            if (response.ok) {
                const data = await response.json();
                const userFacingTasks = data.filter((t: ScheduledTask) =>
                    !["HARD_DELETE", "FILE_SYNC"].includes(t.task_type)
                );
                setTasks(userFacingTasks);
            }
        } catch (error) {
            console.error("Failed to fetch tasks:", error);
        } finally {
            setIsLoading(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchTasks();
    }, [fetchTasks]);

    useEffect(() => {
        const onRealtime = (evt: Event) => {
            const detail = (evt as CustomEvent<any>).detail || {};
            if (!detail.project_id || detail.project_id === projectId) {
                fetchTasks();
            }
        };
        window.addEventListener("va-realtime-job", onRealtime as EventListener);
        return () => window.removeEventListener("va-realtime-job", onRealtime as EventListener);
    }, [fetchTasks]);

    const handleCancel = async (taskId: string) => {
        const confirmed = await showConfirm("Are you sure you want to cancel this scheduled task?");
        if (!confirmed) return;

        try {
            const response = await apiFetch(`/api/automation/tasks/${taskId}`, {
                method: "DELETE",
            });
            if (response.ok) {
                showToast("Task cancelled", "success");
                fetchTasks();
            } else {
                showToast("Failed to cancel task", "error");
            }
        } catch (error) {
            console.error("Cancel failed:", error);
            showToast("Error cancelling task", "error");
        }
    };

    const openScheduleModal = () => {
        onScheduleClick?.();
        setEditingTaskId(null);
        setFormData({
            message: "",
            scheduled_at: initialScheduleLocalTime(browserTimezone),
            recurrence_mode: "once",
            recurrence_custom: "",
            recurrence_timezone: browserTimezone,
        });
        setShowRecurrenceHelp(false);
        setIsModalOpen(true);
    };

    const openEditModal = (task: ScheduledTask) => {
        if (task.task_type !== "POST_MESSAGE") {
            showToast("Only POST_MESSAGE is editable", "error");
            return;
        }

        const timezone = task.payload?.recurrence_timezone || browserTimezone;
        const recurrence = parseRecurrence(task.recurring_rule);
        const localWallClock = task.payload?.scheduled_local_time || utcIsoToZonedLocalInput(task.scheduled_at, timezone);

        setEditingTaskId(task.id);
        setFormData({
            message: task.payload?.message || "",
            scheduled_at: localWallClock,
            recurrence_mode: recurrence.mode,
            recurrence_custom: recurrence.custom,
            recurrence_timezone: timezone,
        });
        setShowRecurrenceHelp(false);
        setIsModalOpen(true);
    };

    const handleSchedule = async () => {
        if (!formData.message.trim() || !formData.scheduled_at) {
            showToast("Message and schedule time are required", "error");
            return;
        }
        if (formData.recurrence_mode === "custom" && !formData.recurrence_custom.trim()) {
            showToast("Custom recurrence is empty", "error");
            return;
        }

        const recurringRule = resolveRecurrence(formData.recurrence_mode, formData.recurrence_custom);
        const scheduledAtUtc = zonedDateTimeLocalToUtcIso(formData.scheduled_at, formData.recurrence_timezone);

        setIsScheduling(true);
        try {
            const body = {
                project_id: projectId,
                task_type: "POST_MESSAGE",
                scheduled_at: scheduledAtUtc,
                recurring_rule: recurringRule,
                recurrence_timezone: formData.recurrence_timezone,
                payload: {
                    message: formData.message.trim(),
                    recurrence_timezone: formData.recurrence_timezone,
                    scheduled_local_time: formData.scheduled_at,
                },
            };

            const response = await apiFetch(
                editingTaskId ? `/api/automation/tasks/${editingTaskId}` : "/api/automation/schedule",
                {
                    method: editingTaskId ? "PUT" : "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                }
            );
            if (!response.ok) {
                const text = await response.text().catch(() => "");
                throw new Error(text || "Failed to schedule task");
            }

            setIsModalOpen(false);
            setEditingTaskId(null);
            showToast(editingTaskId ? "Updated" : "Scheduled", "success");
            fetchTasks();
        } catch (error) {
            console.error("Schedule failed:", error);
            showToast("Failed to schedule", "error");
        } finally {
            setIsScheduling(false);
        }
    };

    return (
        <div className="flex flex-col h-full space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <AlarmClock size={16} className="text-cyan-500" />
                    <span className="text-sm text-gray-400 font-medium">Scheduled Automations</span>
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={fetchTasks}
                        className="p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                    </button>
                    <button
                        onClick={openScheduleModal}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg text-xs font-bold transition-all border border-blue-500/20"
                    >
                        <Plus size={14} />
                        Schedule
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {isLoading && tasks.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-gray-600">
                        <Loader2 size={24} className="animate-spin mb-2" />
                        <span className="text-xs font-bold uppercase tracking-widest">Loading...</span>
                    </div>
                ) : tasks.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-gray-600 border border-dashed border-gray-800 rounded-2xl">
                        <Calendar size={24} className="mb-2 opacity-20" />
                        <span className="text-[10px] font-bold uppercase tracking-widest">No active tasks</span>
                    </div>
                ) : (
                    tasks.map((task) => {
                        const timezone = task.payload?.recurrence_timezone || "UTC";
                        const displayLocal = formatStoredLocalDateTime(task.payload?.scheduled_local_time || "");
                        return (
                            <div key={task.id} className="bg-gray-900/40 border border-gray-800 rounded-xl p-3 hover:bg-gray-800/60 transition-all group">
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] font-black text-blue-400 uppercase tracking-tighter">
                                                {task.task_type}
                                            </span>
                                            {task.recurring_rule && (
                                                <span className="px-1.5 py-0.5 bg-purple-500/10 text-purple-400 rounded text-[8px] font-black uppercase">
                                                    {task.recurring_rule}
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-xs text-gray-200 font-medium truncate mt-0.5">
                                            {task.task_type === "POST_MESSAGE" ? task.payload.message : JSON.stringify(task.payload)}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {task.task_type === "POST_MESSAGE" && ["pending", "processing"].includes(task.status.toLowerCase()) && (
                                            <button
                                                onClick={() => openEditModal(task)}
                                                className="p-1.5 text-gray-600 hover:text-cyan-400 hover:bg-cyan-400/10 rounded-lg"
                                                title="Edit task"
                                            >
                                                <Edit2 size={12} />
                                            </button>
                                        )}
                                        <button
                                            onClick={() => handleCancel(task.id)}
                                            className="p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                                            title="Cancel task"
                                        >
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between text-[10px] text-gray-500 font-bold">
                                    <div className="flex items-center gap-1">
                                        <Clock size={10} />
                                        {displayLocal || formatScheduledAt(task.scheduled_at, timezone)}
                                        <span className="text-gray-600">({timezone})</span>
                                    </div>
                                    <span className={`uppercase ${task.status === "pending" ? "text-blue-500/70" : task.status === "processing" ? "text-amber-500/70 animate-pulse" : "text-green-500/70"}`}>
                                        {task.status}
                                    </span>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>

            {isModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                    <div className="w-[92%] max-w-md rounded-2xl border border-gray-800 bg-[#0b0f18] p-4 shadow-2xl">
                        <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-sm font-bold text-white">{editingTaskId ? "Edit Project Automation" : "Schedule Project Automation"}</h3>
                            <button
                                onClick={() => setIsModalOpen(false)}
                                className="text-gray-500 hover:text-white"
                                title="Close"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="space-y-3">
                            <div>
                                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">Message</label>
                                <textarea
                                    value={formData.message}
                                    onChange={(e) => setFormData((prev) => ({ ...prev, message: e.target.value }))}
                                    rows={4}
                                    placeholder="What should run on schedule?"
                                    className="w-full rounded-xl border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">Scheduled Time</label>
                                    <input
                                        type="datetime-local"
                                        value={formData.scheduled_at}
                                        onChange={(e) => setFormData((prev) => ({ ...prev, scheduled_at: e.target.value }))}
                                        className="w-full rounded-xl border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                                    />
                                </div>

                                <div>
                                    <div className="mb-1 flex items-center gap-1">
                                        <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Recurrence</label>
                                        <button
                                            type="button"
                                            onClick={() => setShowRecurrenceHelp((prev) => !prev)}
                                            className="text-gray-500 hover:text-cyan-300"
                                            title="Recurrence help"
                                        >
                                            <CircleHelp size={12} />
                                        </button>
                                    </div>
                                    <select
                                        value={formData.recurrence_mode}
                                        onChange={(e) => setFormData((prev) => ({ ...prev, recurrence_mode: e.target.value as RecurrenceMode }))}
                                        className="w-full rounded-xl border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                                    >
                                        {RECURRENCE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>{option.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">Timezone</label>
                                <select
                                    value={formData.recurrence_timezone}
                                    onChange={(e) => setFormData((prev) => ({ ...prev, recurrence_timezone: e.target.value }))}
                                    className="w-full rounded-xl border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none"
                                >
                                    {timezoneOptions.map((tz) => (
                                        <option key={tz} value={tz}>{tz}</option>
                                    ))}
                                </select>
                            </div>

                            {formData.recurrence_mode === "custom" && (
                                <div>
                                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">Custom Cron</label>
                                    <input
                                        type="text"
                                        value={formData.recurrence_custom}
                                        onChange={(e) => setFormData((prev) => ({ ...prev, recurrence_custom: e.target.value }))}
                                        placeholder="*/10 * * * *"
                                        className="w-full rounded-xl border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-sm text-white focus:border-cyan-500 focus:outline-none"
                                    />
                                </div>
                            )}

                            {showRecurrenceHelp && (
                                <div className="rounded-lg border border-cyan-900/50 bg-cyan-950/20 px-2.5 py-2 text-[11px] text-cyan-100">
                                    One-time runs once. Presets use @hourly/@daily/@weekly. Custom accepts 5-field cron like <span className="font-mono">0 9 * * 1-5</span>.
                                </div>
                            )}

                            <div className="flex justify-end gap-2 pt-1">
                                <button
                                    onClick={() => setIsModalOpen(false)}
                                    className="rounded-lg border border-gray-800 px-3 py-1.5 text-xs font-medium text-gray-400 hover:bg-gray-800 hover:text-white"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSchedule}
                                    disabled={isScheduling}
                                    className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-cyan-500 disabled:opacity-60"
                                >
                                    {isScheduling ? "Saving..." : editingTaskId ? "Save" : "Schedule"}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
