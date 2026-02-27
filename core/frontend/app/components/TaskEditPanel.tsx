"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { getSpokeColor } from "../../lib/colors";
import { Lock, Unlock, Clock, X, ChevronDown, CheckCircle2, Circle, Plus, Trash2, Sparkles } from "lucide-react";

interface Subtask {
    id: string;
    text: string;
    done: boolean;
}

interface Task {
    task_id: string;
    task_name: string;
    context: string;
    base_load_score: number;
    active: boolean;
    rule_type: string;
    due_date: string | null;
    notes: string | null;
    // Rule-specific fields
    mon?: boolean;
    tue?: boolean;
    wed?: boolean;
    thu?: boolean;
    fri?: boolean;
    sat?: boolean;
    sun?: boolean;
    interval_days?: number;
    anchor_date?: string | null;
    month_day?: number;
    nth_in_month?: number;
    weekday_mon1?: number;
    start_date?: string | null;
    end_date?: string | null;
    // Execution status for a target date
    status?: string;
    is_locked?: boolean;
    start_time?: string | null;
    end_time?: string | null;
    timezone?: string | null;
    meta_payload?: {
        steps?: Subtask[];
        is_my_day?: boolean;
    };
}

interface TaskEditPanelProps {
    task: Task | null;
    isOpen: boolean;
    onClose: () => void;
    onSave: (task: Task) => void;
    onDelete: (taskId: string) => void;
    availableProjects?: string[];
}

export default function TaskEditPanel({
    task,
    isOpen,
    onClose,
    onSave,
    onDelete,
    availableProjects = []
}: TaskEditPanelProps) {
    const [editedTask, setEditedTask] = useState<Task | null>(null);
    const [isNewProject, setIsNewProject] = useState(false);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
    const [applyToInstanceOnly, setApplyToInstanceOnly] = useState(false);

    const [history, setHistory] = useState<any[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    const fetchHistory = async (taskId: string) => {
        if (!taskId || taskId === "undefined") return;
        setHistoryLoading(true);
        try {
            const end = new Date();
            const start = new Date();
            start.setDate(start.getDate() - 14); // Last 2 weeks
            const res = await apiFetch(`/api/lbs/tasks/${taskId}/history?start_date=${start.toISOString().split('T')[0]}&end_date=${end.toISOString().split('T')[0]}`);
            if (res.ok) {
                const data = await res.json();
                setHistory(data);
            }
        } catch (err) {
            console.error("Failed to fetch history:", err);
        } finally {
            setHistoryLoading(false);
        }
    };

    useEffect(() => {
        if (task && isOpen) {
            setLoading(true);
            setIsNewProject(false);
            setApplyToInstanceOnly(false); // Reset toggle when opening new task
            if (!task.task_id || task.task_id === "undefined") {
                setEditedTask(task);
                setLoading(false);
                return;
            }

            const targetDate = task.due_date || new Date().toISOString().split('T')[0];

            // Fetch full task details including the status for the specific date
            apiFetch(`/api/lbs/tasks/${task.task_id}?target_date=${targetDate}`)
                .then(res => {
                    if (!res.ok) throw new Error("Failed to load task details");
                    return res.json();
                })
                .then(data => {
                    const browserTz = typeof Intl !== "undefined"
                        ? Intl.DateTimeFormat().resolvedOptions().timeZone
                        : "UTC";
                    setEditedTask({
                        ...task, // Keep original data as fallback
                        ...data,
                        due_date: data.due_date || targetDate,
                        timezone: data.timezone || task.timezone || browserTz,
                    });
                })
                .catch(err => {
                    console.error("Failed to load task details:", err);
                    const browserTz = typeof Intl !== "undefined"
                        ? Intl.DateTimeFormat().resolvedOptions().timeZone
                        : "UTC";
                    setEditedTask({ ...task, timezone: task.timezone || browserTz });
                })
                .finally(() => setLoading(false));

            fetchHistory(task.task_id);
        }
    }, [task, isOpen]);

    if (!isOpen || !editedTask) return null;

    const handleSave = async () => {
        if (!editedTask) return;
        setLoading(true);
        setStatus(null);
        try {
            // Auto-create project if it's a new one
            if (isNewProject && editedTask.context && !availableProjects.includes(editedTask.context)) {
                try {
                    await apiFetch("/api/agents/project/create", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ project_name: editedTask.context })
                    });
                } catch (err) {
                    console.error("Failed to create project:", err);
                }
            }

            // Manual edits from the TaskEditPanel always use force_override=true to ensure changes are applied
            const isRecurring = editedTask.rule_type !== 'ONCE';

            let response;
            if (applyToInstanceOnly && isRecurring) {
                // Determine exception type
                let exceptionType = "OVERRIDE_LOAD";
                // If only time changed, could be RESCHEDULE, but OVERRIDE_LOAD is safer for general property overrides in LBS

                const targetDate = editedTask.due_date || new Date().toISOString().split('T')[0];
                const exceptionPayload = {
                    task_id: editedTask.task_id,
                    target_date: targetDate,
                    exception_type: exceptionType,
                    override_load_value: editedTask.base_load_score,
                    start_time: editedTask.start_time,
                    end_time: editedTask.end_time,
                    notes: editedTask.notes
                };

                response = await apiFetch("/api/lbs/exceptions?force_override=true", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(exceptionPayload),
                });
            } else {
                const url = `/api/lbs/tasks/${editedTask.task_id}?force_override=true`;
                response = await apiFetch(url, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(editedTask),
                });
            }

            if (response.ok) {
                setStatus({ type: "success", message: applyToInstanceOnly ? "Occurrence updated successfully!" : "Task updated successfully!" });

                // If it was an exception, we might want to get the "resolved" task for the callback
                let finalTask = editedTask;
                if (applyToInstanceOnly && isRecurring) {
                    const targetDate = editedTask.due_date || new Date().toISOString().split('T')[0];
                    const resolveResp = await apiFetch(`/api/lbs/tasks/${editedTask.task_id}/resolved?target_date=${targetDate}`);
                    if (resolveResp.ok) {
                        finalTask = await resolveResp.json();
                    }
                }

                setTimeout(() => {
                    onSave(finalTask);
                    onClose();
                    setStatus(null);
                }, 1000);
            } else {
                const errorData = await response.json().catch(() => ({ detail: "Failed to save task" }));
                setStatus({ type: "error", message: errorData.detail || "Failed to save task" });
            }
        } catch (error) {
            console.error("Failed to save task:", error);
            setStatus({ type: "error", message: "Network error or server is down" });
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async () => {
        if (!editedTask) return;
        const confirmed = window.confirm(`Delete task "${editedTask.task_name}"?`);
        if (!confirmed) return;

        setLoading(true);
        try {
            const isRecurring = editedTask.rule_type !== 'ONCE';
            let response;

            if (applyToInstanceOnly && isRecurring) {
                const targetDate = editedTask.due_date || new Date().toISOString().split('T')[0];
                const exceptionPayload = {
                    task_id: editedTask.task_id,
                    target_date: targetDate,
                    exception_type: "SKIP"
                };
                response = await apiFetch("/api/lbs/exceptions?force_override=true", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(exceptionPayload),
                });
            } else {
                const url = `/api/lbs/tasks/${editedTask.task_id}?force_override=true`;
                response = await apiFetch(url, {
                    method: "DELETE",
                });
            }

            if (response.ok) {
                setStatus({ type: "success", message: applyToInstanceOnly ? "Occurrence skipped successfully!" : "Task deleted successfully!" });
                setTimeout(() => {
                    onDelete(editedTask.task_id);
                    onClose();
                }, 1000);
            } else {
                const errorData = await response.json().catch(() => ({ detail: "Failed to delete task" }));
                alert(errorData.detail || "Failed to delete task");
            }
        } catch (error) {
            console.error("Failed to delete task:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleToggleExecution = async (status: string) => {
        if (!editedTask) return;
        setLoading(true);
        try {
            const targetDate = editedTask.due_date || new Date().toISOString().split('T')[0];
            const response = await apiFetch(`/api/lbs/tasks/${editedTask.task_id}/complete`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ target_date: targetDate, status }),
            });

            if (response.ok) {
                setEditedTask({ ...editedTask, status });
                fetchHistory(editedTask.task_id);
            } else {
                setStatus({ type: "error", message: "Failed to update today's status" });
            }
        } catch (error) {
            console.error("Failed to toggle execution:", error);
            setStatus({ type: "error", message: "Network error" });
        } finally {
            setLoading(false);
        }
    };

    const handleAddStep = () => {
        if (!editedTask) return;
        const newStep: Subtask = { id: crypto.randomUUID(), text: "", done: false };
        const meta = editedTask.meta_payload || {};
        const steps = [...(meta.steps || []), newStep];
        setEditedTask({ ...editedTask, meta_payload: { ...meta, steps } });
    };

    const handleToggleStep = (id: string) => {
        if (!editedTask || !editedTask.meta_payload?.steps) return;
        const steps = editedTask.meta_payload.steps.map(s =>
            s.id === id ? { ...s, done: !s.done } : s
        );
        setEditedTask({ ...editedTask, meta_payload: { ...editedTask.meta_payload, steps } });
    };

    const handleUpdateStepText = (id: string, text: string) => {
        if (!editedTask || !editedTask.meta_payload?.steps) return;
        const steps = editedTask.meta_payload.steps.map(s =>
            s.id === id ? { ...s, text } : s
        );
        setEditedTask({ ...editedTask, meta_payload: { ...editedTask.meta_payload, steps } });
    };

    const handleDeleteStep = (id: string) => {
        if (!editedTask || !editedTask.meta_payload?.steps) return;
        const steps = editedTask.meta_payload.steps.filter(s => s.id !== id);
        setEditedTask({ ...editedTask, meta_payload: { ...editedTask.meta_payload, steps } });
    };

    const isMyDay = editedTask?.meta_payload?.is_my_day || false;
    const toggleMyDay = () => {
        const meta = editedTask.meta_payload || {};
        setEditedTask({ ...editedTask, meta_payload: { ...meta, is_my_day: !isMyDay } });
    };

    const spokeColor = getSpokeColor(editedTask.context);

    if (!isOpen || !editedTask) return null;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/50 z-40 transition-opacity"
                onClick={onClose}
            />

            {/* Slide-in Panel */}
            <div className="fixed top-0 right-0 h-full w-full md:w-[600px] bg-gray-900 shadow-xl z-50 transform transition-transform overflow-y-auto">
                {/* Header */}
                <div className="sticky top-0 bg-gray-900 border-b border-gray-800 p-6 flex items-center justify-between z-10">
                    <h2 className="text-xl font-semibold">Edit Task</h2>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-white"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-6">
                    {status && (
                        <div className={`p-4 rounded-lg flex items-center gap-3 animate-in fade-in slide-in-from-top-4 ${status.type === 'success' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'}`}>
                            <span className="text-xl">{status.type === 'success' ? '✓' : '⚠️'}</span>
                            <span className="font-medium">{status.message}</span>
                        </div>
                    )}
                    {/* Task Name */}
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-2">
                            Task Name *
                        </label>
                        <input
                            type="text"
                            value={editedTask.task_name || ""}
                            onChange={(e) =>
                                setEditedTask({ ...editedTask, task_name: e.target.value })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-lg focus:outline-none focus:border-purple-500"
                        />
                    </div>

                    {/* My Day Toggle & Quick Actions */}
                    <div className="flex items-center gap-3">
                        <button
                            onClick={toggleMyDay}
                            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all border ${isMyDay
                                ? "bg-cyan-500/20 border-cyan-500 text-cyan-400"
                                : "bg-gray-800 border-gray-700 text-gray-500 hover:text-gray-400"
                                }`}
                        >
                            <Sparkles className={`w-3 h-3 ${isMyDay ? "fill-cyan-400" : ""}`} />
                            {isMyDay ? "Pinned to My Day" : "Pin to My Day"}
                        </button>
                    </div>

                    {/* Project/Context - Now Editable */}
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-2">
                            Project *
                        </label>
                        {isNewProject || availableProjects.length === 0 ? (
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={editedTask.context || ""}
                                    onChange={(e) =>
                                        setEditedTask({ ...editedTask, context: e.target.value })
                                    }
                                    className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    style={{
                                        borderLeftWidth: "4px",
                                        borderLeftColor: spokeColor,
                                    }}
                                />
                                {availableProjects.length > 0 && (
                                    <button
                                        type="button"
                                        onClick={() => setIsNewProject(false)}
                                        className="px-4 bg-gray-800 border border-gray-700 rounded-lg text-xs font-bold uppercase tracking-widest text-gray-500 hover:text-white transition-colors"
                                    >
                                        Use Existing
                                    </button>
                                )}
                            </div>
                        ) : (
                            <select
                                value={editedTask.context}
                                onChange={(e) => {
                                    if (e.target.value === "NEW_PROJECT") {
                                        setIsNewProject(true);
                                        setEditedTask({ ...editedTask, context: "" });
                                    } else {
                                        setEditedTask({ ...editedTask, context: e.target.value });
                                    }
                                }}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 appearance-none"
                                style={{
                                    borderLeftWidth: "4px",
                                    borderLeftColor: spokeColor,
                                }}
                            >
                                {availableProjects.map((s) => (
                                    <option key={s} value={s}>{s}</option>
                                ))}
                                {!availableProjects.includes(editedTask.context) && (
                                    <option value={editedTask.context}>{editedTask.context}</option>
                                )}
                                <option value="NEW_PROJECT" className="text-purple-400 font-bold">+ Create New Project...</option>
                            </select>
                        )}
                    </div>

                    {/* Workload */}
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-2">
                            Workload (0-10) *
                        </label>
                        <input
                            type="number"
                            min="0"
                            max="10"
                            step="0.5"
                            value={editedTask.base_load_score ?? 1.0}
                            onChange={(e) =>
                                setEditedTask({
                                    ...editedTask,
                                    base_load_score: parseFloat(e.target.value),
                                })
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                        />
                    </div>

                    {/* Advanced Settings Toggle */}
                    <details className="group border border-gray-800 rounded-xl overflow-hidden [&_summary::-webkit-details-marker]:hidden">
                        <summary className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-800/30 transition-colors">
                            <span className="text-sm font-medium text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                <Clock className="w-4 h-4" /> Advanced Settings
                            </span>
                            <ChevronDown className="w-5 h-5 text-gray-500 transition-transform group-open:rotate-180" />
                        </summary>

                        <div className="p-4 border-t border-gray-800 space-y-6 bg-gray-900/40">
                            {/* System Protection */}
                            <div className="flex items-center justify-between gap-4">
                                <div className="flex-1">
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-2 flex items-center gap-2">
                                        <Lock className="w-3 h-3" /> System Protection
                                    </label>

                                    <button
                                        type="button"
                                        onClick={() =>
                                            setEditedTask({ ...editedTask, is_locked: !editedTask.is_locked })
                                        }
                                        className={`w-full flex items-center justify-center gap-2 px-4 py-2 bg-gray-800/50 border rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${editedTask.is_locked
                                            ? "border-amber-500/50 text-amber-400 bg-amber-500/10"
                                            : "border-gray-700 text-gray-500 hover:text-gray-400"
                                            }`}
                                    >
                                        {editedTask.is_locked ? (
                                            <><Lock className="w-3 h-3" /> Locked</>
                                        ) : (
                                            <><Unlock className="w-3 h-3" /> Unlocked</>
                                        )}
                                    </button>
                                </div>
                            </div>

                            {/* Recurrence Type */}
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        Recurrence Type *
                                    </label>
                                    <select
                                        value={editedTask.rule_type}
                                        onChange={(e) =>
                                            setEditedTask({ ...editedTask, rule_type: e.target.value })
                                        }
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    >
                                        <option value="ONCE">Once (single task)</option>
                                        <option value="WEEKLY">Weekly (specific days)</option>
                                        <option value="EVERY_N_DAYS">Every N Days</option>
                                        <option value="MONTHLY_DAY">Monthly (fixed date)</option>
                                        <option value="MONTHLY_NTH_WEEKDAY">Monthly (nth weekday)</option>
                                    </select>
                                </div>

                                {/* Conditional Fields based on Rule Type */}
                                {editedTask.rule_type === "ONCE" && (
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-2">
                                            Due Date
                                        </label>
                                        <input
                                            type="date"
                                            value={editedTask.due_date || ""}
                                            onChange={(e) => setEditedTask({ ...editedTask, due_date: e.target.value })}
                                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                        />
                                    </div>
                                )}

                                {editedTask.rule_type === "WEEKLY" && (
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-2">
                                            Repeat on Days *
                                        </label>
                                        <div className="grid grid-cols-7 gap-2">
                                            {[
                                                { key: "mon", label: "Mon" },
                                                { key: "tue", label: "Tue" },
                                                { key: "wed", label: "Wed" },
                                                { key: "thu", label: "Thu" },
                                                { key: "fri", label: "Fri" },
                                                { key: "sat", label: "Sat" },
                                                { key: "sun", label: "Sun" },
                                            ].map((day) => (
                                                <button
                                                    key={day.key}
                                                    type="button"
                                                    onClick={() => setEditedTask({ ...editedTask, [day.key]: !editedTask[day.key as keyof Task] })}
                                                    className={`py-2 px-3 rounded-lg font-medium transition-colors ${editedTask[day.key as keyof Task] ? "bg-purple-500 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
                                                >
                                                    {day.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {editedTask.rule_type === "EVERY_N_DAYS" && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                Interval (days) *
                                            </label>
                                            <input
                                                type="number"
                                                min="1"
                                                value={editedTask.interval_days || 7}
                                                onChange={(e) => setEditedTask({ ...editedTask, interval_days: parseInt(e.target.value) })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                Anchor Date
                                            </label>
                                            <input
                                                type="date"
                                                value={editedTask.anchor_date || ""}
                                                onChange={(e) => setEditedTask({ ...editedTask, anchor_date: e.target.value })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            />
                                        </div>
                                    </div>
                                )}

                                {editedTask.rule_type === "MONTHLY_DAY" && (
                                    <div>
                                        <label className="block text-sm font-medium text-gray-400 mb-2">
                                            Day of Month *
                                        </label>
                                        <input
                                            type="number"
                                            min="1"
                                            max="31"
                                            value={editedTask.month_day || 1}
                                            onChange={(e) => setEditedTask({ ...editedTask, month_day: parseInt(e.target.value) })}
                                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                        />
                                    </div>
                                )}

                                {editedTask.rule_type === "MONTHLY_NTH_WEEKDAY" && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                Nth Week
                                            </label>
                                            <select
                                                value={editedTask.nth_in_month || 1}
                                                onChange={(e) => setEditedTask({ ...editedTask, nth_in_month: parseInt(e.target.value) })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            >
                                                <option value={1}>1st</option>
                                                <option value={2}>2nd</option>
                                                <option value={3}>3rd</option>
                                                <option value={4}>4th</option>
                                                <option value={-1}>Last</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                Day of Week
                                            </label>
                                            <select
                                                value={editedTask.weekday_mon1 || 1}
                                                onChange={(e) => setEditedTask({ ...editedTask, weekday_mon1: parseInt(e.target.value) })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            >
                                                <option value={1}>Monday</option>
                                                <option value={2}>Tuesday</option>
                                                <option value={3}>Wednesday</option>
                                                <option value={4}>Thursday</option>
                                                <option value={5}>Friday</option>
                                                <option value={6}>Saturday</option>
                                                <option value={7}>Sunday</option>
                                            </select>
                                        </div>
                                    </div>
                                )}

                                {/* Date Range for recurring tasks */}
                                {editedTask.rule_type !== "ONCE" && (
                                    <div className="grid grid-cols-2 gap-4 pt-2">
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                Start Date
                                            </label>
                                            <input
                                                type="date"
                                                value={editedTask.start_date || ""}
                                                onChange={(e) => setEditedTask({ ...editedTask, start_date: e.target.value })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                                End Date
                                            </label>
                                            <input
                                                type="date"
                                                value={editedTask.end_date || ""}
                                                onChange={(e) => setEditedTask({ ...editedTask, end_date: e.target.value })}
                                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Time Slot */}
                            <div className="pt-2 border-t border-gray-800/50">
                                <label className="block text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                                    <Clock className="w-4 h-4" /> Time Slot
                                </label>
                                <div className="flex items-center gap-4">
                                    <div className="flex-1">
                                        <label className="block text-[10px] uppercase text-gray-500 mb-1">Start</label>
                                        <input
                                            type="time"
                                            value={editedTask.start_time || ""}
                                            onChange={(e) => setEditedTask({ ...editedTask, start_time: e.target.value })}
                                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-purple-500"
                                        />
                                    </div>
                                    <div className="flex-1">
                                        <label className="block text-[10px] uppercase text-gray-500 mb-1">End</label>
                                        <input
                                            type="time"
                                            value={editedTask.end_time || ""}
                                            onChange={(e) => setEditedTask({ ...editedTask, end_time: e.target.value })}
                                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-purple-500"
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Timezone */}
                            <div className="pt-2 border-t border-gray-800/50">
                                <label className="block text-sm font-medium text-gray-400 mb-2">
                                    Timezone
                                </label>
                                <select
                                    value={editedTask.timezone || "UTC"}
                                    onChange={(e) => setEditedTask({ ...editedTask, timezone: e.target.value })}
                                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                >
                                    <option value="UTC">UTC</option>
                                    {typeof Intl !== "undefined" && Intl.supportedValuesOf('timeZone').map((tz) => (
                                        <option key={tz} value={tz}>{tz}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </details>

                    {/* Execution Status for Today */}
                    {
                        editedTask.active && (
                            <div className="p-4 bg-purple-500/5 border border-purple-500/10 rounded-lg">
                                <label className="block text-sm font-medium text-purple-400 mb-3">
                                    Today's status (Source of Truth)
                                </label>
                                <div className="flex gap-2">
                                    {["todo", "done", "skipped"].map(s => (
                                        <button
                                            key={s}
                                            type="button"
                                            onClick={() => handleToggleExecution(s)}
                                            className={`flex-1 py-2 px-3 rounded text-sm font-medium transition-colors ${editedTask.status === s
                                                ? "bg-purple-500 text-white shadow-lg shadow-purple-500/20"
                                                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                                                }`}
                                        >
                                            {s.toUpperCase()}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )
                    }

                    {/* Subtasks / Steps */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <label className="block text-sm font-medium text-gray-400">
                                Subtasks / Steps
                            </label>
                            <button
                                onClick={handleAddStep}
                                className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1 font-bold"
                            >
                                <Plus size={14} /> ADD STEP
                            </button>
                        </div>
                        <div className="space-y-2">
                            {editedTask.meta_payload?.steps?.map((step) => (
                                <div key={step.id} className="group flex items-center gap-3 bg-gray-800/40 p-2 rounded-lg border border-transparent hover:border-gray-700 transition-all">
                                    <button
                                        onClick={() => handleToggleStep(step.id)}
                                        className={`transition-colors ${step.done ? 'text-green-500' : 'text-gray-600 hover:text-gray-500'}`}
                                    >
                                        {step.done ? <CheckCircle2 size={20} /> : <Circle size={20} />}
                                    </button>
                                    <input
                                        type="text"
                                        value={step.text}
                                        onChange={(e) => handleUpdateStepText(step.id, e.target.value)}
                                        className={`flex-1 bg-transparent border-none focus:ring-0 text-sm p-0 ${step.done ? 'line-through text-gray-600' : 'text-gray-200'}`}
                                        placeholder="Enter step detail..."
                                    />
                                    <button
                                        onClick={() => handleDeleteStep(step.id)}
                                        className="opacity-0 group-hover:opacity-100 p-1 text-gray-600 hover:text-red-400 transition-all"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))}
                            {(!editedTask.meta_payload?.steps || editedTask.meta_payload.steps.length === 0) && (
                                <div className="text-center py-4 border border-dashed border-gray-800 rounded-lg text-gray-600 text-xs italic">
                                    No subtasks added yet.
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Notes */}
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-2">
                            Notes
                        </label>
                        <textarea
                            value={editedTask.notes || ""}
                            onChange={(e) =>
                                setEditedTask({ ...editedTask, notes: e.target.value })
                            }
                            rows={4}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 resize-none"
                            placeholder="Add notes..."
                        />
                    </div>
                </div >

                {/* Footer Actions */}
                < div className="sticky bottom-0 bg-gray-900 border-t border-gray-800 p-6 flex flex-col gap-4" >
                    {editedTask.rule_type !== 'ONCE' && (
                        <div className="flex items-center justify-between bg-gray-800/50 p-3 rounded-lg border border-gray-700">
                            <div className="flex items-center gap-3">
                                <div className={`p-1.5 rounded-md ${applyToInstanceOnly ? 'bg-purple-500/20 text-purple-400' : 'bg-gray-700 text-gray-400'}`}>
                                    <Sparkles size={16} />
                                </div>
                                <div className="text-left">
                                    <div className="text-sm font-medium text-gray-200">Apply to this occurrence only</div>
                                    <div className="text-xs text-gray-400">Creates an exception for {editedTask.due_date}</div>
                                </div>
                            </div>
                            <button
                                onClick={() => setApplyToInstanceOnly(!applyToInstanceOnly)}
                                className={`w-10 h-5 rounded-full transition-colors relative ${applyToInstanceOnly ? 'bg-purple-500' : 'bg-gray-600'}`}
                            >
                                <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${applyToInstanceOnly ? 'left-6' : 'left-1'}`} />
                            </button>
                        </div>
                    )}
                    <div className="flex gap-3">
                        <button
                            onClick={handleSave}
                            disabled={loading}
                            className="flex-1 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-700 px-6 py-3 rounded-lg font-medium transition-colors"
                        >
                            {loading ? "Saving..." : applyToInstanceOnly ? "Update Occurrence" : "Save Changes"}
                        </button>
                        <button
                            onClick={handleDelete}
                            disabled={loading}
                            className="px-6 py-3 bg-red-500/20 border border-red-500 text-red-400 hover:bg-red-500/30 rounded-lg font-medium transition-colors"
                        >
                            {applyToInstanceOnly ? "Skip Instance" : "Delete"}
                        </button>
                    </div>
                </div >
            </div >
        </>
    );
}
