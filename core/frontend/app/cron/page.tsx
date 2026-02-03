"use client";

import { useState, useEffect, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import {
    AlarmClock,
    CalendarClock,
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
} from "lucide-react";
import { useNotification } from "@/lib/NotificationContext";

interface ScheduledTask {
    id: string;
    project_id: string | null;
    project_name: string | null;
    task_type: string;
    payload: any;
    scheduled_at: string;
    recurring_rule: string | null;
    status: string;
    last_run_at: string | null;
    created_at: string;
}

interface ProjectMinimal {
    id: string;
    name: string;
}

type TabType = "upcoming" | "history";

export default function CronTasksPage() {
    const [tasks, setTasks] = useState<ScheduledTask[]>([]);
    const [loading, setLoading] = useState(true);
    const [projects, setProjects] = useState<ProjectMinimal[]>([]);
    const [activeTab, setActiveTab] = useState<TabType>("upcoming");
    const { showToast, showConfirm } = useNotification();

    // Modal State
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
    const [formData, setFormData] = useState({
        project_id: "",
        message: "",
        scheduled_at: "",
        recurring_rule: ""
    });

    const loadTasks = async () => {
        setLoading(true);
        try {
            // Fetch tasks with exclude_system=true by default
            const response = await apiFetch("/api/automation/tasks?exclude_system=true");
            if (!response.ok) throw new Error("Failed to fetch tasks");
            const data = await response.json();
            setTasks(data);
        } catch (error) {
            console.error("Error loading tasks:", error);
            showToast("Failed to load scheduled tasks.", "error");
        } finally {
            setLoading(false);
        }
    };

    const loadProjects = async () => {
        try {
            const response = await apiFetch("/api/agents/project/list");
            if (response.ok) {
                const data = await response.json();
                if (data.projects && Array.isArray(data.projects)) {
                    setProjects(data.projects.map((p: any) => ({
                        id: p.id,
                        name: p.display_name || p.name
                    })));
                }
            }
        } catch (e) {
            console.error("Failed to load projects", e);
        }
    };

    useEffect(() => {
        loadTasks();
        loadProjects();
    }, []);

    const filteredTasks = useMemo(() => {
        if (activeTab === "upcoming") {
            return tasks.filter(t => ["pending", "processing"].includes(t.status.toLowerCase()));
        } else {
            return tasks.filter(t => ["completed", "failed", "cancelled"].includes(t.status.toLowerCase()));
        }
    }, [tasks, activeTab]);

    const handleDelete = async (taskId: string) => {
        const confirmed = await showConfirm("Are you sure you want to cancel this scheduled task?");
        if (!confirmed) return;

        try {
            const response = await apiFetch(`/api/automation/tasks/${taskId}`, {
                method: "DELETE"
            });
            if (!response.ok) throw new Error("Failed to delete task");

            showToast("Task cancelled successfully.");
            setTasks(prev => prev.filter(t => t.id !== taskId));
        } catch (error) {
            console.error("Error deleting task:", error);
            showToast("Failed to cancel task.", "error");
        }
    };

    const handleEdit = (task: ScheduledTask) => {
        if (task.task_type !== "POST_MESSAGE") {
            showToast("Only Message Posting tasks are editable via UI.", "info");
            return;
        }

        setEditingTask(task);
        const dateStr = new Date(task.scheduled_at).toISOString().slice(0, 16);

        setFormData({
            project_id: task.project_id || "",
            message: task.payload?.message || "",
            scheduled_at: dateStr,
            recurring_rule: task.recurring_rule || ""
        });
        setIsModalOpen(true);
    };

    const handleCreate = () => {
        setEditingTask(null);
        const now = new Date();
        now.setHours(now.getHours() + 1);
        const dateStr = now.toISOString().slice(0, 16);

        setFormData({
            project_id: projects[0]?.id || "",
            message: "",
            scheduled_at: dateStr,
            recurring_rule: ""
        });
        setIsModalOpen(true);
    };

    const handleSave = async () => {
        if (!formData.project_id || !formData.message || !formData.scheduled_at) {
            showToast("Please fill in all required fields.", "error");
            return;
        }

        const payload = {
            project_id: formData.project_id,
            task_type: "POST_MESSAGE",
            scheduled_at: new Date(formData.scheduled_at).toISOString(),
            recurring_rule: formData.recurring_rule || null,
            payload: {
                message: formData.message
            }
        };

        try {
            let response;
            if (editingTask) {
                response = await apiFetch(`/api/automation/tasks/${editingTask.id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
            } else {
                response = await apiFetch("/api/automation/schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
            }

            if (!response.ok) throw new Error("Failed to save task");

            showToast(editingTask ? "Task updated." : "Task scheduled.");
            setIsModalOpen(false);
            loadTasks();
        } catch (error) {
            console.error("Save error:", error);
            showToast("Failed to save task.", "error");
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status.toLowerCase()) {
            case "completed": return <CheckCircle2 size={14} className="text-green-500" />;
            case "pending": return <Clock size={14} className="text-yellow-500" />;
            case "failed": return <AlertCircle size={14} className="text-red-500" />;
            case "processing": return <Activity size={14} className="text-cyan-500 animate-pulse" />;
            default: return <Box size={14} className="text-gray-500" />;
        }
    };

    const getTaskTypeLabel = (type: string) => {
        switch (type) {
            case "POST_MESSAGE": return "Auto Message";
            case "PROJECT_PULSE": return "Project Pulse";
            case "AUTO_RESEARCH": return "Background Research";
            case "LBS_REMINDER": return "LBS Reminder";
            default: return type;
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto w-full">
            <header className="mb-10 flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-black text-white tracking-tight flex items-center gap-3">
                        <AlarmClock className="text-cyan-500" size={32} />
                        Cron Tasks
                    </h1>
                    <p className="text-gray-500 text-sm mt-1 uppercase tracking-widest font-bold">Automated Systems & Schedules</p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={handleCreate}
                        className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 text-white rounded-2xl font-bold text-sm hover:from-cyan-500 hover:to-blue-500 transition-all shadow-lg shadow-cyan-900/20"
                    >
                        <Plus size={18} />
                        Create Schedule
                    </button>
                    <button
                        onClick={loadTasks}
                        className="p-3 bg-gray-900 border border-gray-800 rounded-2xl text-gray-400 hover:text-white transition-all hover:bg-gray-800"
                        title="Refresh List"
                    >
                        <RefreshCw size={20} className={loading ? "animate-spin" : ""} />
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
                        <p className="font-bold uppercase tracking-widest text-xs">Loading schedules...</p>
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
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Task Type</th>
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Target Project</th>
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Details</th>
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Schedule / Recurring</th>
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Status</th>
                                    <th className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800/50">
                                {filteredTasks.map((task) => (
                                    <tr key={task.id} className="hover:bg-gray-800/20 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex flex-col">
                                                <span className="text-sm font-bold text-cyan-400">{getTaskTypeLabel(task.task_type)}</span>
                                                <span className="text-[10px] text-gray-600 font-mono" title={task.id}>ID: ...{task.id.slice(-8)}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex flex-col">
                                                <span className="text-sm font-medium text-gray-300">{task.project_name || "No Project"}</span>
                                                <span className="text-[10px] text-gray-600 font-mono">ID: {task.project_id ? `...${task.project_id.slice(-8)}` : "-"}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            {task.task_type === 'POST_MESSAGE' && task.payload?.message ? (
                                                <div className="max-w-[200px] truncate text-xs text-gray-300 italic">
                                                    "{task.payload.message}"
                                                </div>
                                            ) : (
                                                <span className="text-xs text-gray-500">-</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex flex-col">
                                                <span className="text-xs text-gray-300">{new Date(task.scheduled_at).toLocaleString()}</span>
                                                {task.recurring_rule && (
                                                    <span className="text-[10px] text-purple-400 font-bold uppercase tracking-tighter mt-0.5">
                                                        ♻️ {task.recurring_rule}
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                {getStatusIcon(task.status)}
                                                <span className={`text-[10px] font-black uppercase tracking-widest ${task.status === "pending" ? "text-yellow-500" :
                                                    task.status === "completed" ? "text-green-500" :
                                                        task.status === "failed" ? "text-red-500" :
                                                            "text-cyan-500"
                                                    }`}>
                                                    {task.status}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                {task.task_type === "POST_MESSAGE" && task.status.toLowerCase() === "pending" && (
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
                    <div className="bg-[#0A0A0A] border border-gray-800 rounded-3xl w-full max-w-lg p-6 shadow-2xl relative">
                        <button
                            onClick={() => setIsModalOpen(false)}
                            className="absolute top-4 right-4 text-gray-500 hover:text-white"
                        >
                            <X size={20} />
                        </button>

                        <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                            {editingTask ? <Edit2 size={20} className="text-cyan-500" /> : <Plus size={20} className="text-cyan-500" />}
                            {editingTask ? "Edit Scheduled Message" : "Schedule New Message"}
                        </h2>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Target Project</label>
                                <select
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                    value={formData.project_id}
                                    onChange={e => setFormData({ ...formData, project_id: e.target.value })}
                                >
                                    <option value="" disabled>Select a project</option>
                                    {projects.map(p => (
                                        <option key={p.id} value={p.id}>{p.name}</option>
                                    ))}
                                </select>
                                {projects.length === 0 && (
                                    <p className="text-[10px] text-yellow-600 mt-1">No projects loaded. Please wait...</p>
                                )}
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Message</label>
                                <textarea
                                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500 min-h-[100px]"
                                    placeholder="What should the agent process?"
                                    value={formData.message}
                                    onChange={e => setFormData({ ...formData, message: e.target.value })}
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Scheduled Time</label>
                                    <input
                                        type="datetime-local"
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                        value={formData.scheduled_at}
                                        onChange={e => setFormData({ ...formData, scheduled_at: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Recurrence (Optional)</label>
                                    <input
                                        type="text"
                                        className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-500"
                                        placeholder="@daily, @weekly"
                                        value={formData.recurring_rule}
                                        onChange={e => setFormData({ ...formData, recurring_rule: e.target.value })}
                                    />
                                    <p className="text-[10px] text-gray-600 mt-1">Format: @daily, @hourly, or cron</p>
                                </div>
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
                                className="px-5 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-bold shadow-lg shadow-cyan-900/20 transition-all"
                            >
                                {editingTask ? "Save Changes" : "Schedule Task"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
