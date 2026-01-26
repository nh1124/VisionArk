"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { useNotification } from "@/lib/NotificationContext";
import { Loader2, Calendar, Clock, Trash2, Plus, Zap, RefreshCw } from "lucide-react";

interface ScheduledTask {
    id: string;
    project_id?: string;
    task_type: string;
    payload: any;
    scheduled_at: string;
    recurring_rule?: string;
    status: string;
}

interface AutomationTabProps {
    projectId: string;
    onScheduleClick: () => void;
}

export default function AutomationTab({ projectId, onScheduleClick }: AutomationTabProps) {
    const [tasks, setTasks] = useState<ScheduledTask[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const { showToast, showConfirm } = useNotification();

    const fetchTasks = useCallback(async () => {
        setIsLoading(true);
        try {
            // Fetch tasks for this project
            const response = await apiFetch(`/api/automation/tasks?project_id=${projectId}`);
            if (response.ok) {
                const data = await response.json();
                // Filter out system tasks like HARD_DELETE
                const userFacingTasks = data.filter((t: ScheduledTask) =>
                    !['HARD_DELETE', 'FILE_SYNC'].includes(t.task_type)
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

    const handleCancel = async (taskId: string) => {
        const confirmed = await showConfirm("Are you sure you want to cancel this scheduled task?", {
            title: "Cancel Task",
            confirmText: "Yes, Cancel",
            variant: "danger"
        });

        if (!confirmed) return;

        try {
            const response = await apiFetch(`/api/automation/tasks/${taskId}`, {
                method: "DELETE"
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

    return (
        <div className="flex flex-col h-full space-y-4">
            <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400 font-medium">Scheduled Automations</span>
                <div className="flex items-center gap-1">
                    <button
                        onClick={fetchTasks}
                        className="p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                    </button>
                    <button
                        onClick={onScheduleClick}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded-lg text-xs font-bold transition-all border border-blue-500/20"
                    >
                        <Plus size={14} />
                        Schedule
                    </button>
                </div>
            </div>

            {/* Task List */}
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
                    tasks.map(task => (
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
                                        {task.task_type === 'POST_MESSAGE' ? task.payload.message : JSON.stringify(task.payload)}
                                    </div>
                                </div>
                                <button
                                    onClick={() => handleCancel(task.id)}
                                    className="p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                                    title="Cancel task"
                                >
                                    <Trash2 size={12} />
                                </button>
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-gray-500 font-bold">
                                <div className="flex items-center gap-1">
                                    <Clock size={10} />
                                    {new Date(task.scheduled_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                </div>
                                <span className={`uppercase ${task.status === 'pending' ? 'text-blue-500/70' : task.status === 'processing' ? 'text-amber-500/70 animate-pulse' : 'text-green-500/70'}`}>
                                    {task.status}
                                </span>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
