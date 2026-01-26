"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { useNotification } from "@/lib/NotificationContext";

interface ScheduleMessageModalProps {
    projectId: string;
    onClose: () => void;
    onScheduled: () => void;
}

export default function ScheduleMessageModal({ projectId, onClose, onScheduled }: ScheduleMessageModalProps) {
    const [message, setMessage] = useState("");
    const [scheduledAt, setScheduledAt] = useState("");
    const [recurringRule, setRecurringRule] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);

    const { showToast } = useNotification();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!message || !scheduledAt) {
            showToast("Message and date are required.", "warning");
            return;
        }

        setIsSubmitting(true);
        try {
            const response = await apiFetch("/api/automation/schedule", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_id: projectId,
                    task_type: "POST_MESSAGE",
                    scheduled_at: new Date(scheduledAt).toISOString(),
                    payload: { message },
                    recurring_rule: recurringRule || null
                }),
            });

            if (response.ok) {
                showToast("Message scheduled successfully.", "success");
                onScheduled();
                onClose();
            } else {
                const err = await response.json();
                showToast(`Failed to schedule: ${err.detail || "Unknown error"}`, "error");
            }
        } catch (error) {
            console.error("Schedule failed:", error);
            showToast("Failed to schedule message.", "error");
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl w-full max-w-md shadow-2xl animate-in fade-in zoom-in duration-200">
                <div className="p-6">
                    <h3 className="text-lg font-bold text-white mb-4">Schedule Reserved Message</h3>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                                Message Content
                            </label>
                            <textarea
                                value={message}
                                onChange={(e) => setMessage(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 transition-colors h-32"
                                placeholder="Type the message to be sent..."
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                                Execution Time
                            </label>
                            <input
                                type="datetime-local"
                                value={scheduledAt}
                                onChange={(e) => setScheduledAt(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 transition-colors"
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                                Recurrence (Optional)
                            </label>
                            <select
                                value={recurringRule}
                                onChange={(e) => setRecurringRule(e.target.value)}
                                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 transition-colors"
                            >
                                <option value="">Once</option>
                                <option value="@hourly">Hourly</option>
                                <option value="@daily">Daily</option>
                                <option value="@weekly">Weekly</option>
                            </select>
                            <p className="mt-1.5 text-[10px] text-gray-600 italic">
                                Note: Recurring tasks spawn a new instance after each execution.
                            </p>
                        </div>

                        <div className="flex items-center justify-end gap-3 mt-6 pt-6 border-t border-gray-800">
                            <button
                                type="button"
                                onClick={onClose}
                                className="px-4 py-2 text-sm font-medium text-gray-400 hover:text-white transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:text-blue-300 text-white px-4 py-2 rounded-lg text-sm font-bold transition-all"
                            >
                                {isSubmitting ? "Scheduling..." : "Schedule Message"}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
}
