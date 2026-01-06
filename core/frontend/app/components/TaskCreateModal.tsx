"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface TaskCreateModalProps {
    isOpen: boolean;
    onClose: () => void;
    onTaskCreated: () => void;
    availableSpokes?: string[];
}

export default function TaskCreateModal({
    isOpen,
    onClose,
    onTaskCreated,
    availableSpokes = []
}: TaskCreateModalProps) {
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
    const [isNewSpoke, setIsNewSpoke] = useState(false);
    const [formData, setFormData] = useState({
        task_name: "",
        context: "",
        base_load_score: 5,
        rule_type: "ONCE",
        due_date: "",
        notes: "",
        // Weekly fields
        mon: false,
        tue: false,
        wed: false,
        thu: false,
        fri: false,
        sat: false,
        sun: false,
        // Every N Days fields
        interval_days: 7,
        anchor_date: "",
        // Monthly fields
        month_day: 1,
        nth_in_month: 1,
        weekday_mon1: 1,
        // Date range
        start_date: "",
        end_date: "",
    });

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setStatus(null);

        try {
            // Auto-create spoke if it's a new one
            if (isNewSpoke && formData.context && !availableSpokes.includes(formData.context)) {
                setStatus({ type: "success", message: `Creating spoke "${formData.context}"...` });
                try {
                    await apiFetch("/api/agents/spoke/create", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ spoke_name: formData.context })
                    });
                } catch (err) {
                    console.error("Failed to create spoke:", err);
                    // Continue anyway - the spoke might already exist
                }
            }

            const payload: any = {
                task_name: formData.task_name,
                context: formData.context,
                base_load_score: formData.base_load_score,
                rule_type: formData.rule_type,
                notes: formData.notes || null,
                start_date: formData.start_date || null,
                end_date: formData.end_date || null,
            };

            // Add rule-specific fields
            if (formData.rule_type === "ONCE") {
                payload.due_date = formData.due_date || null;
            } else if (formData.rule_type === "WEEKLY") {
                payload.mon = formData.mon;
                payload.tue = formData.tue;
                payload.wed = formData.wed;
                payload.thu = formData.thu;
                payload.fri = formData.fri;
                payload.sat = formData.sat;
                payload.sun = formData.sun;
            } else if (formData.rule_type === "EVERY_N_DAYS") {
                payload.interval_days = formData.interval_days;
                payload.anchor_date = formData.anchor_date || null;
            } else if (formData.rule_type === "MONTHLY_DAY") {
                payload.month_day = formData.month_day;
            } else if (formData.rule_type === "MONTHLY_NTH_WEEKDAY") {
                payload.nth_in_month = formData.nth_in_month;
                payload.weekday_mon1 = formData.weekday_mon1;
            }

            const response = await apiFetch("/api/lbs/tasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (response.ok) {
                onTaskCreated();
                onClose();
                // Reset form
                setFormData({
                    task_name: "",
                    context: "",
                    base_load_score: 5,
                    rule_type: "ONCE",
                    due_date: "",
                    notes: "",
                    mon: false,
                    tue: false,
                    wed: false,
                    thu: false,
                    fri: false,
                    sat: false,
                    sun: false,
                    interval_days: 7,
                    anchor_date: "",
                    month_day: 1,
                    nth_in_month: 1,
                    weekday_mon1: 1,
                    start_date: "",
                    end_date: "",
                });
                setStatus(null);
                setIsNewSpoke(false);
            } else {
                const errorData = await response.json().catch(() => ({ detail: "Failed to create task" }));
                setStatus({ type: "error", message: errorData.detail || "Failed to create task" });
            }
        } catch (error) {
            console.error("Failed to create task:", error);
            setStatus({ type: "error", message: "Network error or server is down" });
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
                onClick={onClose}
            >
                {/* Modal */}
                <div
                    className="bg-gray-900 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Header */}
                    <div className="sticky top-0 bg-gray-900 border-b border-gray-800 p-6 flex items-center justify-between z-10">
                        <h2 className="text-2xl font-bold">Create New Task</h2>
                        <button
                            onClick={onClose}
                            className="text-gray-400 hover:text-white text-2xl"
                        >
                            ×
                        </button>
                    </div>

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="p-6 space-y-6">
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
                                required
                                value={formData.task_name}
                                onChange={(e) =>
                                    setFormData({ ...formData, task_name: e.target.value })
                                }
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                placeholder="e.g., Write research paper"
                            />
                        </div>

                        {/* Spoke/Context */}
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                Spoke *
                            </label>
                            {isNewSpoke || availableSpokes.length === 0 ? (
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        required
                                        autoFocus={isNewSpoke}
                                        value={formData.context}
                                        onChange={(e) =>
                                            setFormData({ ...formData, context: e.target.value })
                                        }
                                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                        placeholder="e.g., research, writing, development"
                                    />
                                    {availableSpokes.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setIsNewSpoke(false);
                                                setFormData({ ...formData, context: availableSpokes[0] });
                                            }}
                                            className="px-4 bg-gray-800 border border-gray-700 rounded-lg text-gray-400 hover:text-white transition-colors"
                                        >
                                            Use Existing
                                        </button>
                                    )}
                                </div>
                            ) : (
                                <select
                                    required
                                    value={formData.context}
                                    onChange={(e) => {
                                        if (e.target.value === "NEW_SPOKE") {
                                            setIsNewSpoke(true);
                                            setFormData({ ...formData, context: "" });
                                        } else {
                                            setFormData({ ...formData, context: e.target.value });
                                        }
                                    }}
                                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 appearance-none"
                                >
                                    <option value="" disabled>Select a Spoke</option>
                                    {availableSpokes.map((s) => (
                                        <option key={s} value={s}>{s}</option>
                                    ))}
                                    <option value="NEW_SPOKE" className="text-purple-400 font-bold">+ Create New Spoke...</option>
                                </select>
                            )}
                        </div>

                        {/* Impact */}
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                Impact (0-10) *
                            </label>
                            <input
                                type="number"
                                required
                                min="0"
                                max="10"
                                step="0.5"
                                value={formData.base_load_score}
                                onChange={(e) =>
                                    setFormData({
                                        ...formData,
                                        base_load_score: parseFloat(e.target.value),
                                    })
                                }
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                How much effort this task requires (0 = minimal, 10 = maximum)
                            </p>
                        </div>

                        {/* Rule Type */}
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                Recurrence *
                            </label>
                            <select
                                value={formData.rule_type}
                                onChange={(e) =>
                                    setFormData({ ...formData, rule_type: e.target.value })
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

                        {/* ONCE: Due Date */}
                        {formData.rule_type === "ONCE" && (
                            <div>
                                <label className="block text-sm font-medium text-gray-400 mb-2">
                                    Due Date
                                </label>
                                <input
                                    type="date"
                                    value={formData.due_date}
                                    onChange={(e) =>
                                        setFormData({ ...formData, due_date: e.target.value })
                                    }
                                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                />
                            </div>
                        )}

                        {/* WEEKLY: Day selection */}
                        {formData.rule_type === "WEEKLY" && (
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
                                            onClick={() =>
                                                setFormData({
                                                    ...formData,
                                                    [day.key]: !formData[day.key as keyof typeof formData],
                                                })
                                            }
                                            className={`py-2 px-3 rounded-lg font-medium transition-colors ${formData[day.key as keyof typeof formData]
                                                ? "bg-purple-500 text-white"
                                                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                                                }`}
                                        >
                                            {day.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* EVERY_N_DAYS: Interval and Anchor */}
                        {formData.rule_type === "EVERY_N_DAYS" && (
                            <>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        Interval (days) *
                                    </label>
                                    <input
                                        type="number"
                                        required
                                        min="1"
                                        value={formData.interval_days}
                                        onChange={(e) =>
                                            setFormData({
                                                ...formData,
                                                interval_days: parseInt(e.target.value),
                                            })
                                        }
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    />
                                    <p className="text-xs text-gray-500 mt-1">
                                        Task will repeat every N days
                                    </p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        Anchor Date (first occurrence)
                                    </label>
                                    <input
                                        type="date"
                                        value={formData.anchor_date}
                                        onChange={(e) =>
                                            setFormData({ ...formData, anchor_date: e.target.value })
                                        }
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    />
                                </div>
                            </>
                        )}

                        {/* MONTHLY_DAY: Day of month */}
                        {formData.rule_type === "MONTHLY_DAY" && (
                            <div>
                                <label className="block text-sm font-medium text-gray-400 mb-2">
                                    Day of Month *
                                </label>
                                <input
                                    type="number"
                                    required
                                    min="1"
                                    max="31"
                                    value={formData.month_day}
                                    onChange={(e) =>
                                        setFormData({
                                            ...formData,
                                            month_day: parseInt(e.target.value),
                                        })
                                    }
                                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                    Task will repeat on this day every month (1-31)
                                </p>
                            </div>
                        )}

                        {/* MONTHLY_NTH_WEEKDAY: Nth day of week */}
                        {formData.rule_type === "MONTHLY_NTH_WEEKDAY" && (
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        Nth Week in Month
                                    </label>
                                    <select
                                        value={formData.nth_in_month}
                                        onChange={(e) =>
                                            setFormData({ ...formData, nth_in_month: parseInt(e.target.value) })
                                        }
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
                                        value={formData.weekday_mon1}
                                        onChange={(e) =>
                                            setFormData({ ...formData, weekday_mon1: parseInt(e.target.value) })
                                        }
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

                        {/* Date Range (for recurring tasks) */}
                        {formData.rule_type !== "ONCE" && (
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        Start Date
                                    </label>
                                    <input
                                        type="date"
                                        value={formData.start_date}
                                        onChange={(e) =>
                                            setFormData({ ...formData, start_date: e.target.value })
                                        }
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-400 mb-2">
                                        End Date
                                    </label>
                                    <input
                                        type="date"
                                        value={formData.end_date}
                                        onChange={(e) =>
                                            setFormData({ ...formData, end_date: e.target.value })
                                        }
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500"
                                    />
                                </div>
                            </div>
                        )}

                        {/* Notes */}
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                Notes
                            </label>
                            <textarea
                                value={formData.notes}
                                onChange={(e) =>
                                    setFormData({ ...formData, notes: e.target.value })
                                }
                                rows={3}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 resize-none"
                                placeholder="Add any additional details..."
                            />
                        </div>

                        {/* Actions */}
                        <div className="flex gap-3 pt-4 border-t border-gray-800 sticky bottom-0 bg-gray-900 pb-2">
                            <button
                                type="button"
                                onClick={onClose}
                                className="flex-1 px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={loading}
                                className="flex-1 px-6 py-3 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
                            >
                                {loading ? "Creating..." : "Create Task"}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </>
    );
}
